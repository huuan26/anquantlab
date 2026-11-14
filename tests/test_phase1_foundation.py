"""Phase 1 verification suite: Catalog parity, Safe AST DSL, Causality, Store & REST API."""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import polars as pl
import polars_anta as pa
import pytest
from fastapi.testclient import TestClient

from anquantlab import __version__
from anquantlab.app import create_app
from anquantlab.catalog import build_catalog
from anquantlab.cli import build_parser
from anquantlab.cli import main as cli_main
from anquantlab.config import Settings, apply_thread_limits, load_settings
from anquantlab.expr_dsl import FormulaSyntaxError, evaluate_formula
from anquantlab.store import WorkbenchStore, generate_demo_panel

EMOJI_PATTERN = re.compile("[\U0001f300-\U0001f9ff\U00002600-\U000027bf]")


def test_catalog_matches_polars_anta_v040() -> None:
    cat = build_catalog()
    assert cat.polars_anta_version == pa.__version__
    assert cat.total_exports == len(pa.__all__)
    assert cat.total_exports >= 225
    assert cat.public_functions >= 223
    assert cat.exported_classes == 2

    names = {item.name for item in cat.items}
    assert names == set(pa.__all__)
    for metric in ("value_at_risk", "conditional_var", "omega_ratio", "tail_ratio"):
        assert metric in names


@pytest.mark.parametrize(
    "malicious_formula",
    [
        "",
        "__import__('os')",
        "eval('1+1')",
        "close.__class__",
        "close[0]",
        "(lambda x: x)(close)",
        "_secret_col + 1",
        "nonexistent_col + close",
        "sharpe_ratio(close)",
        "falsify_factors(close)",
        "rsi(close, **{'period': 14})",
    ],
)
def test_ast_dsl_blocks_forbidden_constructs(malicious_formula: str) -> None:
    df = generate_demo_panel().filter(pl.col("ticker").is_in(["AQL01", "AQL02"])).head(80)
    with pytest.raises(FormulaSyntaxError):
        evaluate_formula(df, malicious_formula, time_col="date", symbol_col="ticker")


def test_ast_dsl_multipass_cross_sectional_and_struct() -> None:
    df = generate_demo_panel()

    # 1. Nested Time-Series -> Cross-Section -> Time-Series smoothing
    out1, _, stages1 = evaluate_formula(
        df,
        "ema(cs_rank(rsi(close, 14)), 5)",
        time_col="date",
        symbol_col="ticker",
    )
    assert "signal" in out1.columns
    assert out1["signal"].drop_nulls().len() > 0
    assert len(stages1) == 3

    # 2. Neutralize & Orthogonalize pipeline
    out2, _, _ = evaluate_formula(
        df,
        "neutralize(cs_winsorize(ts_zscore(close, 20)), sector)",
        time_col="date",
        symbol_col="ticker",
    )
    # Verify sector mean at the final date is ~0.0 (exact neutralization)
    last_dt = out2["date"].max()
    sec_means = (
        out2.filter(pl.col("date") == last_dt)
        .group_by("sector")
        .agg(pl.col("signal").mean().alias("m"))["m"]
        .to_numpy()
    )
    assert np.allclose(sec_means, 0.0, atol=1e-10)

    # 3. Struct auto-extraction & explicit field() extraction
    out_auto, plan_auto, _ = evaluate_formula(
        df, "macd(close)", time_col="date", symbol_col="ticker"
    )
    assert any("Struct output auto-extracted" in n for n in plan_auto.notes)
    assert out_auto["signal"].drop_nulls().len() > 0

    out_hist, _, _ = evaluate_formula(
        df, "field(macd(close), 'histogram')", time_col="date", symbol_col="ticker"
    )
    assert out_hist["signal"].drop_nulls().len() > 0

    # 4. Safe division by zero produces null instead of inf
    out_div, _, _ = evaluate_formula(
        df.head(40), "close / (close - close)", time_col="date", symbol_col="ticker"
    )
    assert out_div["signal"].drop_nulls().len() == 0

    # 5. Arithmetic, boolean, unary, and primitive helpers
    complex_expr = (
        "where((rsi(close, 14) > 50) and (close >= open), "
        "clip(log(close), -5, 5), -abs(pct_change(close, 1)))"
    )
    out_ops, _, _ = evaluate_formula(
        df.head(120),
        complex_expr,
        time_col="date",
        symbol_col="ticker",
    )
    assert out_ops["signal"].drop_nulls().len() > 0


def test_strict_temporal_causality_zero_lookahead() -> None:
    """Prefix truncation test: future bars after T_cut must never alter past signals."""
    df = generate_demo_panel()
    formula = "neutralize(cs_rank(rsi(close, 14) - ts_zscore(volume, 20)), sector)"

    full_res, _, _ = evaluate_formula(df, formula, time_col="date", symbol_col="ticker")
    unique_dates = sorted(df["date"].unique().to_list())
    cutoff_date = unique_dates[250]

    truncated_input = df.filter(pl.col("date") <= cutoff_date)
    trunc_res, _, _ = evaluate_formula(
        truncated_input, formula, time_col="date", symbol_col="ticker"
    )

    full_prefix = full_res.filter(pl.col("date") <= cutoff_date).sort(["ticker", "date"])
    trunc_sorted = trunc_res.sort(["ticker", "date"])

    s_full = full_prefix["signal"].to_numpy()
    s_trunc = trunc_sorted["signal"].to_numpy()
    nan_mask = np.isnan(s_full)
    assert np.array_equal(nan_mask, np.isnan(s_trunc))
    assert np.allclose(s_full[~nan_mask], s_trunc[~nan_mask], rtol=1e-12, atol=1e-12)


def test_fastapi_endpoints_upload_and_lru_cache() -> None:
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        max_threads=2,
        max_concurrent=2,
        max_upload_mb=1,
        max_cached_signals=8,
        auto_discover_sibling_data=False,
    )
    app = create_app(settings)
    client = TestClient(app)

    # Health & Index
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    h = r_health.json()
    assert h["status"] == "ok"
    assert h["polars_max_threads"] == 2
    assert h["catalog_public_functions"] >= 223

    r_idx = client.get("/")
    assert r_idx.status_code == 200
    assert "AnQuantLab" in r_idx.text

    # Datasets & Preview
    r_ds = client.get("/api/datasets")
    assert r_ds.status_code == 200
    ds_ids = [d["dataset_id"] for d in r_ds.json()["datasets"]]
    assert "builtin_demo_panel" in ds_ids
    assert "builtin_demo_futures" in ds_ids

    r_prev = client.get("/api/datasets/builtin_demo_panel/preview")
    assert r_prev.status_code == 200
    assert r_prev.json()["ohlcv_valid"] is True

    # Formula preview + LRU Cache Hit + TradingView Chart Series
    payload = {
        "dataset_id": "builtin_demo_panel",
        "formula": "cs_rank(rsi(close, 14))",
        "symbol": "AQL03",
        "chart_bars": 90,
    }
    r_f1 = client.post("/api/formula/preview", json=payload)
    assert r_f1.status_code == 200
    f1_json = r_f1.json()
    assert f1_json["cache_hit"] is False
    assert f1_json["active_symbol"] == "AQL03"
    assert len(f1_json["available_symbols"]) == 24
    assert len(f1_json["chart_series"]) == 90

    r_f2 = client.post("/api/formula/preview", json=payload)
    assert r_f2.status_code == 200
    assert r_f2.json()["cache_hit"] is True

    # Invalid formula -> HTTP 422
    r_bad = client.post(
        "/api/formula/preview",
        json={"dataset_id": "builtin_demo_panel", "formula": "__import__('sys')"},
    )
    assert r_bad.status_code == 422

    # In-memory CSV & Parquet upload
    mini_df = generate_demo_panel().head(30)
    csv_bytes = mini_df.write_csv().encode("utf-8")
    r_up_csv = client.post(
        "/api/datasets/upload",
        files={"file": ("mini_sample.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r_up_csv.status_code == 200
    assert r_up_csv.json()["row_count"] == 30

    pq_buf = io.BytesIO()
    mini_df.write_parquet(pq_buf)
    r_up_pq = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "mini_sample.parquet",
                io.BytesIO(pq_buf.getvalue()),
                "application/octet-stream",
            )
        },
    )
    assert r_up_pq.status_code == 200
    assert r_up_pq.json()["row_count"] == 30

    # Upload cap guard -> HTTP 413 (> 1 MB configured above)
    oversized = b"x" * (1024 * 1024 + 128)
    r_big = client.post(
        "/api/datasets/upload",
        files={"file": ("huge.csv", io.BytesIO(oversized), "text/csv")},
    )
    assert r_big.status_code == 413


def test_cli_version_and_ui_zero_emoji_hygiene(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_main(["--version"])
    assert rc == 0
    assert __version__ in capsys.readouterr().out

    parser = build_parser()
    parsed_direct = parser.parse_args(["--port", "8000"])
    parsed_serve = parser.parse_args(["serve", "--port", "8000"])
    assert parsed_direct.port == 8000
    assert parsed_serve.port == 8000 and parsed_serve.command == "serve"

    threads = apply_thread_limits(2)
    assert threads == 2
    cfg = load_settings(port=8899, max_threads=2)
    assert cfg.port == 8899

    store = WorkbenchStore(cfg)
    assert store.dataset_count() >= 2

    static_root = Path(__file__).resolve().parents[1] / "src" / "anquantlab" / "static"
    for asset in static_root.rglob("*"):
        if asset.is_file() and asset.suffix in {".html", ".css", ".js"}:
            content = asset.read_text(encoding="utf-8")
            assert not EMOJI_PATTERN.search(content), f"Emoji detected in {asset}"
