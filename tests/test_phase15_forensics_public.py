"""Phase 1.5 tests: Free-data forensics, implicit OHLCV spread, and zero-key public hub."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

from anquantlab.app import create_app
from anquantlab.config import Settings
from anquantlab.forensics import analyze_dataset_forensics
from anquantlab.public_data import validate_public_url

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _make_base_panel(n_syms: int = 6, n_days: int = 40) -> pl.DataFrame:
    rng = np.random.default_rng(123)
    rows: list[dict[str, object]] = []
    start = date(2024, 1, 1)
    for s_idx in range(n_syms):
        sym = f"T{s_idx + 1:02d}"
        price = 50.0 + s_idx * 5.0
        for d_idx in range(n_days):
            dt = start + timedelta(days=d_idx)
            ret = float(rng.normal(0.0005, 0.015))
            open_p = round(price, 4)
            close_p = round(price * (1.0 + ret), 4)
            hi = round(max(open_p, close_p) * 1.012, 4)
            lo = round(min(open_p, close_p) * 0.988, 4)
            price = close_p
            rows.append(
                {
                    "date": dt,
                    "ticker": sym,
                    "sector": "Tech" if s_idx % 2 == 0 else "Banks",
                    "open": open_p,
                    "high": hi,
                    "low": lo,
                    "close": close_p,
                    "volume": float(100_000 + d_idx * 500),
                }
            )
    return pl.DataFrame(rows)


def test_dirty_dataset_forensics_and_survivorship() -> None:
    base = _make_base_panel(n_syms=6, n_days=40)
    records = base.to_dicts()

    # 1. Inject +120% unadjusted split jump on T01 day 15
    t01_idx = next(
        i for i, r in enumerate(records) if r["ticker"] == "T01" and r["date"] == date(2024, 1, 16)
    )
    jumped = round(float(records[t01_idx]["open"]) * 2.25, 4)
    records[t01_idx]["close"] = jumped
    records[t01_idx]["high"] = round(jumped * 1.01, 4)

    # 2. Inject zero-volume bar on T02
    t02_idx = next(
        i for i, r in enumerate(records) if r["ticker"] == "T02" and r["date"] == date(2024, 1, 10)
    )
    records[t02_idx]["volume"] = 0.0

    # 3. Inject frozen O=H=L=C bar on T03
    t03_idx = next(
        i for i, r in enumerate(records) if r["ticker"] == "T03" and r["date"] == date(2024, 1, 12)
    )
    flat_p = float(records[t03_idx]["open"])
    records[t03_idx]["high"] = flat_p
    records[t03_idx]["low"] = flat_p
    records[t03_idx]["close"] = flat_p

    # 4. Inject OHLC violation on T04 + duplicate row
    t04_idx = next(
        i for i, r in enumerate(records) if r["ticker"] == "T04" and r["date"] == date(2024, 1, 14)
    )
    records[t04_idx]["high"] = round(float(records[t04_idx]["low"]) * 0.95, 4)
    records.append(dict(records[0]))

    dirty_df = pl.DataFrame(records)
    rep = analyze_dataset_forensics("dirty_test", dirty_df, time_col="date", symbol_col="ticker")

    assert rep.ohlc_violations == 1
    assert rep.duplicate_rows == 1
    assert rep.split_suspect_jumps >= 1
    assert rep.zero_volume_bars == 1
    assert rep.frozen_bars == 1
    assert rep.survivorship_risk == "HIGH"
    assert rep.corwin_schultz_spread_bps_median is not None
    assert rep.corwin_schultz_spread_bps_p90 is not None
    assert rep.corwin_schultz_spread_bps_p90 > 0.0
    assert rep.recommended_min_slippage_bps >= 1.5
    assert rep.health_score < 85
    assert len(rep.warnings) >= 5
    kinds = {ev.kind for ev in rep.sample_anomalies}
    assert {"OHLC_VIOLATION", "SPLIT_OR_GAP_JUMP", "ZERO_VOLUME", "FROZEN_BAR"}.issubset(kinds)

    # Verify early delisting + late IPO switches survivorship_risk to LOW
    realistic_df = base.filter(
        ~(
            ((pl.col("ticker") == "T06") & (pl.col("date") > date(2024, 1, 22)))
            | ((pl.col("ticker") == "T05") & (pl.col("date") < date(2024, 1, 12)))
        )
    )
    rep_low = analyze_dataset_forensics(
        "delisted_test", realistic_df, time_col="date", symbol_col="ticker"
    )
    assert rep_low.early_dropouts == 1
    assert rep_low.late_listings == 1
    assert rep_low.survivorship_risk == "LOW"


def test_public_url_whitelist_blocks_ssrf() -> None:
    validate_public_url("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT")
    validate_public_url("https://api.binance.com/api/v3/klines?symbol=ETHUSDT")
    validate_public_url("https://stooq.com/q/d/l/?s=xlk.us&i=d")

    bad_urls = [
        "http://data-api.binance.vision/api/v3/klines",
        "https://127.0.0.1/admin",
        "https://localhost/api",
        "https://evil.example.com/klines",
        "https://user:secret@stooq.com/q/d/l/",
        "https://stooq.com:8443/q/d/l/",
        "file:///C:/Windows/System32/drivers/etc/hosts",
    ]
    for bad in bad_urls:
        with pytest.raises(ValueError):
            validate_public_url(bad)


def test_binance_preset_fetch_cache_and_orderflow_formula(tmp_path: Path) -> None:
    call_counter = {"count": 0}
    base_ms = 1_704_067_200_000  # 2024-01-01 UTC

    def fake_binance_get(url: str) -> bytes:
        call_counter["count"] += 1
        klines = []
        price = 42_000.0
        for i in range(36):
            open_ms = base_ms + i * 300_000
            close_ms = open_ms + 299_999
            o = round(price, 2)
            c = round(price * (1.0 + (0.002 if i % 2 == 0 else -0.0015)), 2)
            h = round(max(o, c) * 1.003, 2)
            low_p = round(min(o, c) * 0.997, 2)
            vol = 120.0 + i * 3.0
            taker_buy = round(vol * (0.62 if i % 3 != 0 else 0.38), 4)
            price = c
            klines.append(
                [
                    open_ms,
                    str(o),
                    str(h),
                    str(low_p),
                    str(c),
                    str(vol),
                    close_ms,
                    str(round(vol * c, 2)),
                    1450 + i,
                    str(taker_buy),
                    str(round(taker_buy * c, 2)),
                    "0",
                ]
            )
        return json.dumps(klines).encode("utf-8")

    cfg = Settings(
        auto_discover_sibling_data=False,
        allow_public_fetch=True,
        cache_dir=tmp_path / "outside_cache",
    )
    app = create_app(cfg, http_get=fake_binance_get)
    client = TestClient(app)

    presets_res = client.get("/api/public-data/presets")
    assert presets_res.status_code == 200
    presets = presets_res.json()["presets"]
    assert len(presets) == 4
    assert all(not p["cached"] for p in presets)

    fetch_res = client.post(
        "/api/public-data/fetch",
        json={"preset_id": "binance_btcusdt_5m", "force_refresh": False},
    )
    assert fetch_res.status_code == 200
    ds_info = fetch_res.json()
    assert ds_info["dataset_id"] == "public_binance_btcusdt_5m"
    assert "taker_buy_ratio" in ds_info["columns"]
    assert call_counter["count"] == 1
    assert (cfg.cache_dir / "binance_btcusdt_5m.parquet").is_file()

    # Second call without force_refresh must hit local Parquet cache with 0 network calls
    cached_res = client.post(
        "/api/public-data/fetch",
        json={"preset_id": "binance_btcusdt_5m", "force_refresh": False},
    )
    assert cached_res.status_code == 200
    assert call_counter["count"] == 1

    # Forensics endpoint reports has_taker_flow=True
    for_res = client.get("/api/datasets/public_binance_btcusdt_5m/forensics")
    assert for_res.status_code == 200
    assert for_res.json()["has_taker_flow"] is True

    # Formula DSL evaluates taker_buy_ratio seamlessly
    eval_res = client.post(
        "/api/formula/preview",
        json={
            "dataset_id": "public_binance_btcusdt_5m",
            "formula": "ema(taker_buy_ratio - 0.5, 6)",
            "chart_bars": 30,
        },
    )
    assert eval_res.status_code == 200
    assert eval_res.json()["stats"]["valid_count"] > 20


def test_stooq_preset_and_public_fetch_disabled_403(tmp_path: Path) -> None:
    def fake_stooq_get(url: str) -> bytes:
        lines = ["Date,Open,High,Low,Close,Volume"]
        p = 100.0
        for i in range(25):
            dt = date(2024, 2, 1) + timedelta(days=i)
            c = round(p * (1.0 + 0.004 * ((i % 5) - 2)), 2)
            hi = max(p, c) + 0.8
            lo = min(p, c) - 0.8
            lines.append(f"{dt.isoformat()},{p:.2f},{hi:.2f},{lo:.2f},{c:.2f},2500000")
            p = c
        return ("\n".join(lines) + "\n").encode("utf-8")

    cfg_ok = Settings(
        auto_discover_sibling_data=False,
        allow_public_fetch=True,
        cache_dir=tmp_path / "stooq_cache",
    )
    client_ok = TestClient(create_app(cfg_ok, http_get=fake_stooq_get))
    res = client_ok.post(
        "/api/public-data/fetch",
        json={"preset_id": "stooq_us_sectors_1d", "force_refresh": False},
    )
    assert res.status_code == 200
    assert res.json()["symbol_count"] == 9

    eval_res = client_ok.post(
        "/api/formula/preview",
        json={
            "dataset_id": "public_stooq_us_sectors_1d",
            "formula": "neutralize(rsi(close, 6), sector)",
        },
    )
    assert eval_res.status_code == 200
    assert eval_res.json()["stats"]["valid_count"] > 50

    # Disabled public fetch must return 403 when uncached
    cfg_blocked = Settings(
        auto_discover_sibling_data=False,
        allow_public_fetch=False,
        cache_dir=tmp_path / "empty_cache",
    )
    client_blocked = TestClient(create_app(cfg_blocked, http_get=fake_stooq_get))
    res_403 = client_blocked.post(
        "/api/public-data/fetch",
        json={"preset_id": "stooq_us_sectors_1d", "force_refresh": False},
    )
    assert res_403.status_code == 403


def test_static_ui_has_forensics_and_zero_emojis(tmp_path: Path) -> None:
    static_dir = Path(__file__).resolve().parents[1] / "src" / "anquantlab" / "static"
    for p in static_dir.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".js"}:
            txt = p.read_text(encoding="utf-8")
            assert not _EMOJI_RE.search(txt), f"Emoji detected in {p}"

    client = TestClient(create_app(Settings(auto_discover_sibling_data=False, cache_dir=tmp_path)))
    html = client.get("/").text
    assert "subpanel-forensics" in html
    assert "public-data-modal" in html
    assert "forensics-pill" in html
