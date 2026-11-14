"""Phase 2 tests: Backtest parity, <30ms cost lab, causal dynamic spread, Vault & Trial Ledger."""

from __future__ import annotations

import re
import statistics
import time
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import polars_anta as pa
from fastapi.testclient import TestClient

from anquantlab.app import create_app
from anquantlab.backtest_lab import BacktestLabEngine
from anquantlab.config import Settings
from anquantlab.expr_dsl import evaluate_formula
from anquantlab.schemas import BacktestRunRequest
from anquantlab.store import WorkbenchStore
from anquantlab.trial_ledger import TrialLedgerRegistry

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def test_exact_parity_with_polars_anta_vectorized_backtest(tmp_path: Path) -> None:
    cfg = Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)
    store = WorkbenchStore(cfg)
    ledger = TrialLedgerRegistry()
    engine = BacktestLabEngine()

    _, panel_df = store.get_frame("builtin_demo_panel")
    sig_df, _, _ = evaluate_formula(
        panel_df, "cs_rank(rsi(close, 14))", time_col="date", symbol_col="ticker"
    )
    ref = pa.vectorized_backtest(
        sig_df,
        signal="signal",
        group_by="ticker",
        time_col="date",
        fee_rate=0.0005,
        slippage_rate=0.0005,
        signal_lag=1,
        annualization=252.0,
        weight_scheme="dollar_neutral",
        vol_target=0.15,
        no_trade_buffer=0.02,
        aggregate_portfolio=True,
    )
    res = engine.run(
        store,
        ledger,
        BacktestRunRequest(
            dataset_id="builtin_demo_panel",
            formula="cs_rank(rsi(close, 14))",
            weight_scheme="dollar_neutral",
            fee_bps=5.0,
            slippage_mode="fixed",
            slippage_bps=5.0,
            signal_lag=1,
            vol_target=0.15,
            no_trade_buffer=0.02,
            holdout_locked=False,
            annualization=252.0,
        ),
    )

    assert abs(res.metrics.total_return - ref.summary["total_return"]) < 1e-5
    assert abs(res.metrics.sharpe_ratio - ref.summary["sharpe_ratio"]) < 2e-4
    assert abs(res.metrics.sortino_ratio - ref.summary["sortino_ratio"]) < 2e-4
    assert abs(res.metrics.max_drawdown - ref.summary["max_drawdown"]) < 2e-5
    ref_be_bps = pa.breakeven_cost_from_backtest(ref) * 10_000.0
    assert abs(res.metrics.breakeven_bps - ref_be_bps) < 0.05

    # Single-asset parity with weight_scheme="raw"
    _, fut_df = store.get_frame("builtin_demo_futures")
    fut_sig, _, _ = evaluate_formula(
        fut_df, "sign(ema(close, 12) - ema(close, 26))", time_col="timestamp", symbol_col="ticker"
    )
    ref_fut = pa.vectorized_backtest(
        fut_sig,
        signal="signal",
        time_col="timestamp",
        fee_rate=0.0003,
        slippage_rate=0.0002,
        signal_lag=1,
        annualization=252.0,
        weight_scheme="raw",
    )
    res_fut = engine.run(
        store,
        ledger,
        BacktestRunRequest(
            dataset_id="builtin_demo_futures",
            formula="sign(ema(close, 12) - ema(close, 26))",
            weight_scheme="raw",
            fee_bps=3.0,
            slippage_mode="fixed",
            slippage_bps=2.0,
            signal_lag=1,
            holdout_locked=False,
            annualization=252.0,
        ),
    )
    assert abs(res_fut.metrics.total_return - ref_fut.summary["total_return"]) < 1e-5
    assert res_fut.metrics.n_round_trips == int(ref_fut.summary["n_round_trips"])


def test_warm_slider_drag_latency_under_30ms(tmp_path: Path) -> None:
    cfg = Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)
    store = WorkbenchStore(cfg)
    ledger = TrialLedgerRegistry()
    engine = BacktestLabEngine()

    # Cold warm-up
    engine.run(
        store,
        ledger,
        BacktestRunRequest(
            dataset_id="builtin_demo_panel",
            formula="cs_rank(rsi(close, 14))",
            fee_bps=5.0,
            slippage_bps=5.0,
        ),
    )

    latencies_ms: list[float] = []
    modes = ("fixed", "corwin_schultz", "amihud")
    for idx in range(9):
        t0 = time.perf_counter()
        out = engine.run(
            store,
            ledger,
            BacktestRunRequest(
                dataset_id="builtin_demo_panel",
                formula="cs_rank(rsi(close, 14))",
                fee_bps=2.0 + idx * 1.5,
                slippage_mode=modes[idx % 3],
                slippage_bps=1.0 + idx * 2.0,
            ),
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert out.signal_cache_hit is True
        assert out.position_cache_hit is True

    assert statistics.median(latencies_ms) < 30.0


def test_strict_causality_dynamic_spread_limit_lock_and_flatten(tmp_path: Path) -> None:
    cfg = Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)
    store = WorkbenchStore(cfg)
    _, full_fut = store.get_frame("builtin_demo_futures")

    # Inject a frozen/zero-vol bar at index 180 to exercise limit_lock_skip
    recs = full_fut.to_dicts()
    p180 = float(recs[180]["open"])
    recs[180]["high"] = p180
    recs[180]["low"] = p180
    recs[180]["close"] = p180
    recs[180]["volume"] = 0.0
    mod_full = pl.DataFrame(recs).head(580)
    mod_trunc = mod_full.head(420)

    buf_full = mod_full.write_csv().encode("utf-8")
    buf_trunc = mod_trunc.write_csv().encode("utf-8")
    ds_full = store.register_uploaded_bytes("fut_full.csv", buf_full)
    ds_trunc = store.register_uploaded_bytes("fut_trunc.csv", buf_trunc)

    ledger = TrialLedgerRegistry()
    engine = BacktestLabEngine()
    common_kwargs = {
        "formula": "ema(close, 8) - ema(close, 21)",
        "weight_scheme": "dollar_neutral",
        "fee_bps": 4.0,
        "slippage_mode": "corwin_schultz",
        "slippage_bps": 2.0,
        "limit_lock_skip": True,
        "intraday_flatten": True,
        "holdout_locked": False,
        "annualization": 12096.0,
    }
    res_full = engine.run(
        store, ledger, BacktestRunRequest(dataset_id=ds_full.dataset_id, **common_kwargs)
    )
    res_trunc = engine.run(
        store, ledger, BacktestRunRequest(dataset_id=ds_trunc.dataset_id, **common_kwargs)
    )

    full_map = {pt.t: pt.net_eq for pt in res_full.equity_series}
    matched = 0
    for pt in res_trunc.equity_series:
        if pt.t in full_map:
            assert abs(pt.net_eq - full_map[pt.t]) <= 1e-5
            matched += 1
    assert matched == 420


def test_holdout_vault_seal_and_trial_ledger_eigenvalue_neff(tmp_path: Path) -> None:
    rng = np.random.default_rng(77)
    reg = TrialLedgerRegistry()
    base_vec = rng.normal(0.001, 0.012, size=300)

    # Collinear trials -> N_eff ~ 1.0
    for k in range(5):
        snap_c = reg.record_trial(
            "collinear_ds",
            f"trial_{k}",
            base_vec + rng.normal(0.0, 1e-6, size=300),
            1.2 + k * 0.01,
            holdout_locked=True,
        )
    assert snap_c.unique_trials == 5
    assert 1.0 <= snap_c.effective_n_trials <= 1.05
    assert snap_c.holdout_peeks == 0

    # Orthogonal independent trials -> N_eff close to K
    for k in range(6):
        snap_o = reg.record_trial(
            "orth_ds",
            f"orth_{k}",
            rng.normal(0.0, 0.01, size=500),
            0.4 + 0.2 * k,
            holdout_locked=True,
        )
    assert snap_o.unique_trials == 6
    assert snap_o.effective_n_trials > 4.5

    # API Holdout Vault lock & peek tracking
    client = TestClient(create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)))
    r_sealed = client.post(
        "/api/backtest/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "holdout_locked": True,
        },
    )
    assert r_sealed.status_code == 200
    d_sealed = r_sealed.json()
    assert d_sealed["metrics"]["oos_sharpe_ratio"] is None
    assert all(not pt["is_oos"] for pt in d_sealed["equity_series"])
    assert d_sealed["trial_ledger"]["holdout_peeks"] == 0

    # Unlock Vault -> peek logged and OOS metrics exposed
    r_open = client.post(
        "/api/backtest/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "holdout_locked": False,
        },
    )
    assert r_open.status_code == 200
    d_open = r_open.json()
    assert d_open["metrics"]["oos_sharpe_ratio"] is not None
    assert any(pt["is_oos"] for pt in d_open["equity_series"])
    assert d_open["trial_ledger"]["holdout_peeks"] == 1

    # Check GET /api/trials/{dataset_id}
    tl_res = client.get("/api/trials/builtin_demo_panel")
    assert tl_res.status_code == 200
    assert tl_res.json()["holdout_peeks"] == 1


def test_tail_risk_metrics_cost_curve_and_zero_emoji_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)))
    res = client.post(
        "/api/backtest/run",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "neutralize(cs_winsorize(ts_zscore(close, 20)), sector)",
            "slippage_mode": "amihud",
            "fee_bps": 5.0,
            "slippage_bps": 2.0,
        },
    )
    assert res.status_code == 200
    body = res.json()
    m = body["metrics"]
    assert m["var_95"] <= 0.0
    assert m["cvar_95"] <= m["var_95"] + 1e-6
    assert m["omega_ratio"] > 0.0
    assert m["tail_ratio"] > 0.0
    assert 0.0 <= m["live_dsr"] <= 1.0

    curve = body["cost_curve"]
    assert len(curve) == 9
    assert curve[0]["sharpe"] > curve[-1]["sharpe"]

    static_dir = Path(__file__).resolve().parents[1] / "src" / "anquantlab" / "static"
    for p in static_dir.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".js"}:
            txt = p.read_text(encoding="utf-8")
            assert not _EMOJI_RE.search(txt), f"Emoji detected in {p}"
    _ = date(2026, 1, 1)
