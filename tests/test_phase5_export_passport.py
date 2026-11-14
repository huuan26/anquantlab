"""Phase 5 tests: Pure Polars Codegen Parity, AST Sandbox, Alpha Passport SHA-256 & Tearsheet."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from fastapi.testclient import TestClient

from anquantlab.app import create_app
from anquantlab.backtest_lab import BacktestLabEngine
from anquantlab.backtest_metrics import build_micro_meta
from anquantlab.codegen_polars import generate_polars_script, verify_ast_sandbox_clean
from anquantlab.config import Settings
from anquantlab.export_schemas import ExportBundleRequest
from anquantlab.schemas import BacktestRunRequest
from anquantlab.store import WorkbenchStore
from anquantlab.trial_ledger import TrialLedgerRegistry

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _load_generated_module(tmp_path: Path, name: str, py_code: str) -> ModuleType:
    mod_path = tmp_path / f"{name}.py"
    mod_path.write_text(py_code, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("formula", "idx"),
    [
        ("cs_rank(rsi(close, 14))", 0),
        ("neutralize(cs_winsorize(ts_zscore(close, 20)), sector)", 1),
        ("where(close > shift(close, 5), log(volume), -abs(pct_change(close, 3)))", 2),
        ("field(supertrend(high, low, close, 10, 3.0), 'direction')", 3),
        ("macd(close)", 4),
    ],
)
def test_polars_codegen_exact_parity_and_zero_lockin(
    tmp_path: Path, formula: str, idx: int
) -> None:
    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    entry, raw_df = store.get_frame("builtin_demo_panel")
    meta = build_micro_meta(raw_df.sort(["ticker", "date"]), "date", "ticker")

    req = ExportBundleRequest(
        dataset_id="builtin_demo_panel",
        formula=formula,
        weight_scheme="dollar_neutral",
        fee_bps=5.0,
        slippage_mode="corwin_schultz",
        slippage_bps=5.0,
        limit_lock_skip=True,
        holdout_locked=True,
    )
    py_code = generate_polars_script(
        req,
        columns=set(raw_df.columns),
        time_col="date",
        symbol_col="ticker",
        has_panel=True,
        annualization=meta.annualization,
        close_hm=meta.close_hm,
        dataset_sha256=entry.sha256_prefix or "demo",
    )

    # 1. Zero AnQuantLab lock-in & clean AST security sandbox
    assert "import anquantlab" not in py_code
    assert "from anquantlab" not in py_code
    assert verify_ast_sandbox_clean(py_code) == []

    # 2. Import generated standalone Polars + polars-anta module and verify exact UI parity
    mod = _load_generated_module(tmp_path, f"gen_alpha_{idx}", py_code)
    gen_sig_df = mod.compute_signal(raw_df)
    ui_sig_df, _, _, _ = store.get_or_compute_signal("builtin_demo_panel", formula)

    gen_arr = gen_sig_df["signal"].to_numpy()
    ui_arr = ui_sig_df["signal"].to_numpy()
    finite_mask = np.isfinite(gen_arr) & np.isfinite(ui_arr)
    assert np.array_equal(np.isnan(gen_arr), np.isnan(ui_arr))
    if np.any(finite_mask):
        assert float(np.max(np.abs(gen_arr[finite_mask] - ui_arr[finite_mask]))) < 1e-11

    _, gen_summary = mod.run_backtest(raw_df)
    ui_bt = BacktestLabEngine().run(
        store,
        TrialLedgerRegistry(),
        BacktestRunRequest(
            dataset_id="builtin_demo_panel",
            formula=formula,
            weight_scheme="dollar_neutral",
            fee_bps=5.0,
            slippage_mode="corwin_schultz",
            slippage_bps=5.0,
            limit_lock_skip=True,
            holdout_locked=True,
        ),
    )
    assert gen_summary["net_sharpe"] == pytest.approx(ui_bt.metrics.sharpe_ratio, abs=1e-3)
    assert gen_summary["total_return"] == pytest.approx(ui_bt.metrics.total_return, abs=1e-3)
    assert gen_summary["max_drawdown"] == pytest.approx(ui_bt.metrics.max_drawdown, abs=1e-3)


def test_generated_script_cli_entrypoint_and_sandbox_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Verify AST sandbox catches forbidden imports, calls, and write-mode open()
    bad = "import subprocess\nfrom urllib import request\nx = eval('1+1')\nf = open('a.txt', 'w')\n"
    viol = verify_ast_sandbox_clean(bad)
    assert len(viol) == 4

    store = WorkbenchStore(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    _, raw_df = store.get_frame("builtin_demo_panel")
    pq_path = tmp_path / "panel.parquet"
    raw_df.write_parquet(pq_path)

    py_code = generate_polars_script(
        ExportBundleRequest(
            dataset_id="builtin_demo_panel",
            formula="clip((ema(close, 8) - ema(close, 21)) / close, -0.2, 0.2)",
            slippage_mode="amihud",
            vol_target=0.15,
        ),
        columns=set(raw_df.columns),
        time_col="date",
        symbol_col="ticker",
        has_panel=True,
        annualization=252.0,
        close_hm=None,
        dataset_sha256="abc12345",
    )
    mod = _load_generated_module(tmp_path, "gen_cli_alpha", py_code)
    monkeypatch.setattr(sys, "argv", ["strategy.py", "--input", str(pq_path)])
    mod.main()
    out = capsys.readouterr().out
    assert "Strategy Evaluation Summary:" in out
    assert "net_sharpe" in out


def test_export_bundle_passport_sha256_and_offline_tearsheet(tmp_path: Path) -> None:
    app = create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path))
    client = TestClient(app)

    resp = client.post(
        "/api/export/bundle",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "weight_scheme": "dollar_neutral",
            "fee_bps": 5.0,
            "slippage_mode": "corwin_schultz",
            "delisting_penalty_bps_yr": 50.0,
            "holdout_locked": True,
        },
    )
    assert resp.status_code == 200, resp.text
    bundle = resp.json()
    assert bundle["ast_sandbox_clean"] is True
    assert bundle["python_filename"].endswith(".py")
    assert bundle["passport_filename"].endswith(".json")
    assert bundle["tearsheet_filename"].endswith(".html")

    # Verify cryptographic SHA-256 over canonical sorted JSON payload
    passport = dict(bundle["passport"])
    reported_sha = passport.pop("passport_sha256")
    canonical = json.dumps(passport, sort_keys=True, separators=(",", ":"))
    expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert reported_sha == expected_sha
    assert passport["overall_clearance"] in (
        "APPROVED_CANDIDATE",
        "CONDITIONAL_REVIEW",
        "REJECTED_OVERFIT",
    )
    assert passport["trial_ledger_audit"]["holdout_peeks"] == 0
    assert passport["dataset_audit"]["health_score"] > 0

    # Self-contained offline HTML Tearsheet check (zero external http/https assets)
    html_doc = bundle["tearsheet_html"]
    assert "<!DOCTYPE html>" in html_doc
    assert '<html lang="en">' in html_doc
    assert "<svg" in html_doc
    assert "http://" not in html_doc and "https://" not in html_doc
    assert not _EMOJI_RE.search(html_doc)

    # Bilingual Vietnamese tearsheet export check
    resp_vi = client.post(
        "/api/export/bundle",
        json={
            "dataset_id": "builtin_demo_panel",
            "formula": "cs_rank(rsi(close, 14))",
            "lang": "vi",
        },
    )
    assert resp_vi.status_code == 200, resp_vi.text
    html_vi = resp_vi.json()["tearsheet_html"]
    assert '<html lang="vi">' in html_vi
    assert "Phễu Lọc 7 Cổng" in html_vi
    assert "http://" not in html_vi and "https://" not in html_vi
    assert not _EMOJI_RE.search(html_vi)
    assert "\u2014" not in html_vi and "\u2013" not in html_vi

    # Error handling checks
    assert (
        client.post(
            "/api/export/bundle",
            json={"dataset_id": "builtin_demo_panel", "formula": "unknown_fn(close)"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/export/bundle",
            json={"dataset_id": "missing_ds", "formula": "rsi(close, 14)"},
        ).status_code
        == 404
    )


def test_repo_docs_systemd_and_static_ui_hygiene() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    targets = [
        repo_root / "README.md",
        repo_root / "deploy" / "anquantlab.service.example",
        repo_root / "src" / "anquantlab" / "static" / "index.html",
        repo_root / "src" / "anquantlab" / "static" / "styles.css",
        repo_root / "src" / "anquantlab" / "static" / "js" / "export_hub.js",
        repo_root / "src" / "anquantlab" / "static" / "js" / "shell.js",
    ]
    for p in targets:
        assert p.is_file(), f"Missing expected deliverable: {p}"
        txt = p.read_text(encoding="utf-8")
        assert not _EMOJI_RE.search(txt), f"Emoji detected in {p}"
        assert "\u2014" not in txt and "\u2013" not in txt, f"Non-ASCII dash in {p}"
