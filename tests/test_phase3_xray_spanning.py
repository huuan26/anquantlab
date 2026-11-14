"""Phase 3 tests: 4-Stage Pipeline X-Ray, 5-Factor Spanning R^2, OOS Non-Leakage & UI Hygiene."""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient

from anquantlab.app import create_app
from anquantlab.config import Settings
from anquantlab.expr_dsl import evaluate_formula
from anquantlab.store import WorkbenchStore
from anquantlab.trial_ledger import TrialLedgerRegistry
from anquantlab.xray_lab import XRayLabEngine
from anquantlab.xray_schemas import XRayRunRequest

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def test_four_stage_sector_zero_tilt_and_exact_orthogonality(tmp_path: Path) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    ledger = TrialLedgerRegistry()
    engine = XRayLabEngine()

    # Raw signal with extreme nonlinear spikes & natural sector tilt
    res = engine.run(
        store,
        ledger,
        XRayRunRequest(
            dataset_id="builtin_demo_panel",
            formula="(rsi(close, 14) - 50.0) ** 3",
            winsor_method="quantile",
            winsor_clip=0.03,
            neutralize_mode="auto",
            ic_horizon=1,
            holdout_locked=True,
        ),
    )
    assert len(res.stages) == 4
    s_raw, s_win, s_neut, s_orth = res.stages

    # Stage 2 outlier clipping shrinks cross-sectional dispersion and 90% tail span
    assert s_win.std < s_raw.std
    assert (s_win.q95 - s_win.q05) < (s_raw.q95 - s_raw.q05)

    # Stage 3 sector neutralization drives net tilt in EVERY sector to exact zero
    assert s_raw.max_abs_sector_tilt > 0.005
    assert s_neut.max_abs_sector_tilt < 1e-6
    assert len(s_neut.sector_exposures) >= 4
    for sec_item in s_neut.sector_exposures:
        assert abs(sec_item.net_exposure) < 1e-6

    # Stage 4 orthogonalization removes linear correlation with all 5 benchmark factors
    for ld in res.spanning.loadings:
        assert ld.selected is True
        assert abs(ld.post_ortho_corr) < 1e-4

    # Promoted DSL formulas for Stages 1..4 compile cleanly in the safe AST engine
    _, panel_df = store.get_frame("builtin_demo_panel")
    for st in res.stages:
        out_df, _, _ = evaluate_formula(
            panel_df, st.formula_preview, time_col="date", symbol_col="ticker"
        )
        assert out_df["signal"].drop_nulls().len() > 100


def test_spanning_clone_vs_distinct_alpha_and_subset_selection(tmp_path: Path) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    ledger = TrialLedgerRegistry()
    engine = XRayLabEngine()

    # 1. Pure 20-bar Momentum clone -> Spanning R^2 ~ 1.0, FACTOR_CLONE
    clone_res = engine.run(
        store,
        ledger,
        XRayRunRequest(
            dataset_id="builtin_demo_panel",
            formula="close / shift(close, 20) - 1.0",
            neutralize_mode="demean",
            holdout_locked=True,
        ),
    )
    assert clone_res.spanning.spanning_r2 > 0.98
    assert clone_res.spanning.orthogonal_share < 0.02
    assert clone_res.spanning.verdict == "FACTOR_CLONE"

    # 2. Intraday bar-geometry alpha_101 -> mostly orthogonal (>80%), DISTINCT_ALPHA
    distinct_res = engine.run(
        store,
        ledger,
        XRayRunRequest(
            dataset_id="builtin_demo_panel",
            formula="alpha_101(open, high, low, close)",
            holdout_locked=True,
        ),
    )
    assert distinct_res.spanning.orthogonal_share > 0.80
    assert distinct_res.spanning.verdict == "DISTINCT_ALPHA"

    # 3. Partial subset selection: only orthogonalize against Momentum & Vol
    sub_res = engine.run(
        store,
        ledger,
        XRayRunRequest(
            dataset_id="builtin_demo_panel",
            formula="rsi(close, 14)",
            ortho_factors=["mom_20", "yz_vol_20"],
            holdout_locked=True,
        ),
    )
    assert (
        sub_res.spanning.basis_cache_hit is False
        if hasattr(sub_res.spanning, "basis_cache_hit")
        else True
    )
    assert sub_res.basis_cache_hit is True
    assert sub_res.spanning.selected_r2 <= sub_res.spanning.spanning_r2 + 1e-6
    by_key = {ld.factor_key: ld for ld in sub_res.spanning.loadings}
    assert by_key["mom_20"].selected is True
    assert abs(by_key["mom_20"].post_ortho_corr) < 1e-4
    assert by_key["rev_5"].selected is False


def test_sealed_holdout_vault_blocks_20bar_forward_leakage(tmp_path: Path) -> None:
    """Corrupting OOS prices by 100x must NOT change a single IS X-Ray or Spanning number."""
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    ledger = TrialLedgerRegistry()
    engine = XRayLabEngine()

    for ds_id, fml in [
        ("builtin_demo_panel", "cs_rank(rsi(close, 14))"),
        ("builtin_demo_futures", "ema(close, 12) - ema(close, 26)"),
    ]:
        entry, orig_df = store.get_frame(ds_id)
        t_col = entry.time_col
        u_times = orig_df.select(pl.col(t_col).drop_nulls().unique().sort())[t_col]
        split_time = u_times[int(round(0.75 * u_times.len()))]

        # Poison OOS prices (>= split_time) by 50x!
        poisoned_df = orig_df.with_columns(
            pl.when(pl.col(t_col) >= split_time)
            .then(pl.col("close") * 50.0)
            .otherwise(pl.col("close"))
            .alias("close"),
            pl.when(pl.col(t_col) >= split_time)
            .then(pl.col("high") * 55.0)
            .otherwise(pl.col("high"))
            .alias("high"),
        )
        csv_bytes = poisoned_df.write_csv().encode("utf-8")
        poison_info = store.register_uploaded_bytes(f"poison_{ds_id}.csv", csv_bytes)

        r_clean = engine.run(
            store,
            ledger,
            XRayRunRequest(
                dataset_id=ds_id,
                formula=fml,
                ic_horizon=20,
                holdout_locked=True,
            ),
        )
        r_poison = engine.run(
            store,
            ledger,
            XRayRunRequest(
                dataset_id=poison_info.dataset_id,
                formula=fml,
                ic_horizon=20,
                holdout_locked=True,
            ),
        )

        assert r_clean.spanning.spanning_r2 == r_poison.spanning.spanning_r2
        for s_a, s_b in zip(r_clean.stages, r_poison.stages, strict=True):
            assert s_a.mean == s_b.mean
            assert s_a.ic_mean == s_b.ic_mean
            assert s_a.nw_t_stat == s_b.nw_t_stat
            assert s_a.top_minus_bottom_bps == s_b.top_minus_bottom_bps
            assert len(s_a.ic_decay) == len(s_b.ic_decay)
            for d_a, d_b in zip(s_a.ic_decay, s_b.ic_decay, strict=True):
                assert d_a.ic_mean == d_b.ic_mean


def test_xray_rest_api_holdout_peeks_and_zero_emoji_ui(tmp_path: Path) -> None:
    app = create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    client = TestClient(app)

    r_ok = client.post(
        "/api/xray/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "holdout_locked": True,
        },
    )
    assert r_ok.status_code == 200
    b_ok = r_ok.json()
    assert b_ok["trial_ledger"]["holdout_peeks"] == 0
    assert len(b_ok["stages"]) == 4

    # Unlocking Holdout Vault increments holdout_peeks in Trial Ledger
    r_peek = client.post(
        "/api/xray/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "holdout_locked": False,
        },
    )
    assert r_peek.status_code == 200
    assert r_peek.json()["trial_ledger"]["holdout_peeks"] == 1

    # Invalid formula -> HTTP 422; unknown dataset -> HTTP 404
    r_422 = client.post(
        "/api/xray/run",
        json={"dataset_id": "builtin_demo_panel", "formula": "__import__('os')"},
    )
    assert r_422.status_code == 422

    r_404 = client.post(
        "/api/xray/run",
        json={"dataset_id": "non_existent_ds", "formula": "rsi(close, 14)"},
    )
    assert r_404.status_code == 404

    static_root = Path(__file__).resolve().parents[1] / "src" / "anquantlab" / "static"
    for p in static_root.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".js"}:
            txt = p.read_text(encoding="utf-8")
            assert not _EMOJI_RE.search(txt), f"Emoji detected in {p}"
