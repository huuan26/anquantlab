"""Phase 4 tests: 2D Parameter Grid, CSCV PBO, Romano-Wolf, Bootstrap/Null, CUSUM & Delisting."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

from anquantlab.app import create_app
from anquantlab.config import Settings
from anquantlab.crashtest_lab import CrashTestLabEngine
from anquantlab.crashtest_schemas import CrashTestRunRequest
from anquantlab.crashtest_sweep import build_2d_parameter_grid
from anquantlab.store import WorkbenchStore
from anquantlab.trial_ledger import TrialLedgerRegistry

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def test_ast_2d_parameter_grid_topologies() -> None:
    req5 = CrashTestRunRequest(dataset_id="builtin_demo_panel", formula="x", grid_size=5)

    # 1. Two integer lookback constants -> Param0 x Param1 (5x5 = 25 distinct formulas)
    xn, yn, xl, yl, br, bc, specs2 = build_2d_parameter_grid(
        "ema(close, 12) - ema(close, 26)", req5
    )
    assert len(specs2) == 25
    assert (br, bc) == (2, 2)
    assert xl[bc] == "12" and yl[br] == "26"
    assert len({sp.formula for sp in specs2}) == 25
    assert "ema" in xn and "ema" in yn

    # 2. Single integer lookback constant -> Param0 x EMA Smooth
    xn1, yn1, xl1, _, br1, bc1, specs1 = build_2d_parameter_grid("cs_rank(rsi(close, 14))", req5)
    assert len(specs1) == 25
    assert (br1, bc1) == (0, 2)
    assert xl1[bc1] == "14"
    assert "rsi" in xn1 and yn1 == "EMA Smooth"

    # 3. Zero integer lookback constants -> EMA Smooth x No-Trade Buf
    xn0, yn0, _, _, br0, bc0, specs0 = build_2d_parameter_grid(
        "alpha_101(open, high, low, close)", req5
    )
    assert len(specs0) == 25
    assert (br0, bc0) == (0, 0)
    assert xn0 == "EMA Smooth" and yn0 == "No-Trade Buf"

    # 4. Explicit execution_2d mode overrides AST constants
    req_exec = CrashTestRunRequest(
        dataset_id="builtin_demo_panel",
        formula="ema(close, 12) - ema(close, 26)",
        sweep_mode="execution_2d",
        grid_size=3,
    )
    xne, yne, _, _, _, _, specs_e = build_2d_parameter_grid(req_exec.formula, req_exec)
    assert len(specs_e) == 9
    assert xne == "EMA Smooth" and yne == "No-Trade Buf"


def test_seed_reproducibility_and_funnel_monotonicity(tmp_path: Path) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    engine = CrashTestLabEngine()
    req = CrashTestRunRequest(
        dataset_id="builtin_demo_panel",
        formula="ema(close, 12) - ema(close, 26)",
        grid_size=4,
        n_bootstrap=120,
        cscv_splits=8,
        seed=42,
    )

    r1 = engine.run(store, TrialLedgerRegistry(), req)
    r2 = engine.run(store, TrialLedgerRegistry(), req)

    assert r1.pbo.pbo == r2.pbo.pbo
    assert r1.bootstrap.sharpe_median == r2.bootstrap.sharpe_median
    assert r1.bootstrap.null_p_value == r2.bootstrap.null_p_value
    assert r1.cusum.statistic == r2.cusum.statistic
    assert [c.p_romano_wolf for c in r1.candidates] == [c.p_romano_wolf for c in r2.candidates]

    # 7-Stage Funnel must be strictly non-increasing from Gate 1 to Gate 7
    assert len(r1.funnel) == 7
    assert r1.funnel[0].survivors == 16
    for i in range(len(r1.funnel) - 1):
        assert r1.funnel[i].survivors >= r1.funnel[i + 1].survivors

    # Haircut Bars: Observed Peak SR >= Grid DSR Haircut >= Session Ledger DSR
    assert len(r1.haircut_bars) == 4
    assert r1.haircut_bars[0].sharpe_equiv >= r1.haircut_bars[1].sharpe_equiv
    assert r1.haircut_bars[1].sharpe_equiv >= r1.haircut_bars[2].sharpe_equiv


def test_planted_causal_signal_survival_and_cusum_structural_break(tmp_path: Path) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    engine = CrashTestLabEngine()
    rng = np.random.default_rng(123)
    n_days = 320
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]

    # 1. Strong persistent trend-following regime where causal EMA crossover thrives
    shocks = rng.normal(0.0, 0.004, size=n_days)
    regime_drift = np.where((np.arange(n_days) // 35) % 2 == 0, 0.006, -0.006)
    rets = regime_drift + shocks
    closes = 100.0 * np.cumprod(1.0 + rets)
    trend_df = pl.DataFrame(
        {
            "date": dates,
            "open": closes * 0.999,
            "high": closes * 1.003,
            "low": closes * 0.997,
            "close": closes,
            "volume": np.full(n_days, 500_000.0),
        }
    )
    info_trend = store.register_uploaded_bytes(
        "planted_trend.csv", trend_df.write_csv().encode("utf-8")
    )

    res_good = engine.run(
        store,
        TrialLedgerRegistry(),
        CrashTestRunRequest(
            dataset_id=info_trend.dataset_id,
            formula="ema(close, 5) - ema(close, 18)",
            grid_size=3,
            fee_bps=1.0,
            slippage_mode="fixed",
            slippage_bps=1.0,
            n_bootstrap=150,
            cscv_splits=8,
            seed=42,
        ),
    )
    assert res_good.heatmap.baseline_sharpe > 1.5
    assert res_good.pbo.pbo < 0.35
    assert res_good.bootstrap.null_p_value <= 0.05
    assert res_good.verdict == "SURVIVES_FALSIFICATION"
    assert res_good.funnel[4].survivors >= 1  # Survives Romano-Wolf FWER <= 0.05

    # 2. Structural Break Dataset: trend works in first half of IS, then decays in second half
    is_cut = int(round(0.75 * n_days))
    half = is_cut // 2
    brk_rets = np.zeros(n_days, dtype=np.float64)
    # First half: smooth upward drift (+0.8% / bar) -> positive long return
    brk_rets[:half] = 0.008 + rng.normal(0.0, 0.002, size=half)
    # Second half: steady downward crash (-0.8% / bar) while long_only or positive RSI bias breaks
    brk_rets[half:] = -0.007 + rng.normal(0.0, 0.002, size=n_days - half)
    brk_closes = 100.0 * np.cumprod(1.0 + brk_rets)
    brk_df = pl.DataFrame(
        {
            "date": dates,
            "open": brk_closes * 0.999,
            "high": brk_closes * 1.002,
            "low": brk_closes * 0.998,
            "close": brk_closes,
            "volume": np.full(n_days, 500_000.0),
        }
    )
    info_brk = store.register_uploaded_bytes("regime_break.csv", brk_df.write_csv().encode("utf-8"))
    res_brk = engine.run(
        store,
        TrialLedgerRegistry(),
        CrashTestRunRequest(
            dataset_id=info_brk.dataset_id,
            formula="rsi(close, 6) + 50.0",
            weight_scheme="long_only",
            grid_size=3,
            fee_bps=0.0,
            slippage_mode="fixed",
            slippage_bps=0.0,
            n_bootstrap=80,
            seed=42,
        ),
    )
    assert res_brk.cusum.has_break is True
    assert res_brk.cusum.p_value < 0.05
    assert res_brk.cusum.mean_before_bps > 0.0 > res_brk.cusum.mean_after_bps
    peak_bridge = max(abs(pt.stat) for pt in res_brk.cusum.bridge_series)
    assert peak_bridge == pytest.approx(res_brk.cusum.statistic, abs=1e-3)


def test_survivorship_delisting_penalty_and_holdout_invariance(tmp_path: Path) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    engine = CrashTestLabEngine()

    # 1. Delisting penalty strictly reduces Long-Only Sharpe and cumulative return
    base_req = dict(
        dataset_id="builtin_demo_panel",
        formula="cs_rank(rsi(close, 14))",
        weight_scheme="long_only",
        grid_size=3,
        n_bootstrap=80,
        seed=42,
    )
    r_zero = engine.run(
        store, TrialLedgerRegistry(), CrashTestRunRequest(**base_req, delisting_penalty_bps_yr=0.0)
    )
    r_pen = engine.run(
        store,
        TrialLedgerRegistry(),
        CrashTestRunRequest(**base_req, delisting_penalty_bps_yr=350.0),
    )
    assert r_pen.heatmap.baseline_sharpe < r_zero.heatmap.baseline_sharpe
    assert r_pen.candidates[0].total_return < r_zero.candidates[0].total_return

    # 2. Sealed Holdout Vault (75% IS) is 100% invariant to 10x OOS price poisoning
    _, demo_df = store.get_frame("builtin_demo_panel")
    u_dates = demo_df["date"].unique().sort()
    split_dt = u_dates[int(round(0.75 * len(u_dates)))]

    clean_info = store.register_uploaded_bytes(
        "clean_panel.csv", demo_df.write_csv().encode("utf-8")
    )
    poison_df = demo_df.with_columns(
        pl.when(pl.col("date") >= split_dt)
        .then(pl.col("close") * 8.5)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    poison_info = store.register_uploaded_bytes(
        "poison_panel.csv", poison_df.write_csv().encode("utf-8")
    )

    ledger = TrialLedgerRegistry()
    res_clean = engine.run(
        store,
        ledger,
        CrashTestRunRequest(
            dataset_id=clean_info.dataset_id,
            formula="ema(close, 10) - ema(close, 24)",
            grid_size=3,
            holdout_locked=True,
        ),
    )
    res_poison = engine.run(
        store,
        TrialLedgerRegistry(),
        CrashTestRunRequest(
            dataset_id=poison_info.dataset_id,
            formula="ema(close, 10) - ema(close, 24)",
            grid_size=3,
            holdout_locked=True,
        ),
    )
    assert res_clean.heatmap.sharpe_matrix == res_poison.heatmap.sharpe_matrix
    assert res_clean.pbo.pbo == res_poison.pbo.pbo
    assert res_clean.bootstrap.sharpe_median == res_poison.bootstrap.sharpe_median
    assert res_clean.cusum.statistic == res_poison.cusum.statistic

    # Trial Ledger registered all 9 grid trials with 0 OOS peeks while locked
    assert res_clean.trial_ledger.unique_trials == 9
    assert res_clean.trial_ledger.effective_n_trials >= 1.0
    assert res_clean.trial_ledger.holdout_peeks == 0


def test_api_crashtest_endpoint_and_ui_zero_emoji_hygiene(tmp_path: Path) -> None:
    app = create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    client = TestClient(app)

    resp = client.post(
        "/api/crashtest/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "grid_size": 3,
            "n_bootstrap": 100,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in ("SURVIVES_FALSIFICATION", "BORDERLINE_FRAGILE", "OVERFIT_REJECTED")
    assert len(body["candidates"]) == 9
    assert body["trial_ledger"]["unique_trials"] == 9

    bad_syntax = client.post(
        "/api/crashtest/run",
        json={"dataset_id": "builtin_demo_panel", "formula": "__import__('os').system('echo x')"},
    )
    assert bad_syntax.status_code == 422

    missing_ds = client.post(
        "/api/crashtest/run",
        json={"dataset_id": "missing_xyz", "formula": "rsi(close, 14)"},
    )
    assert missing_ds.status_code == 404

    static_dir = Path(__file__).resolve().parents[1] / "src" / "anquantlab" / "static"
    for rel in (
        "index.html",
        "styles.css",
        "js/crashtest_view.js",
        "js/tv_crashtest_chart.js",
        "js/shell.js",
    ):
        txt = (static_dir / rel).read_text(encoding="utf-8")
        assert not _EMOJI_RE.search(txt), f"Emoji found in {rel}"
        assert "\u2014" not in txt and "\u2013" not in txt, f"Non-ASCII dash found in {rel}"
