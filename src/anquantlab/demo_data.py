"""Deterministic synthetic OHLCV dataset generators for offline workbench testing."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import polars as pl


def generate_demo_panel() -> pl.DataFrame:
    """Build a deterministic 24-ticker, 6-sector, 504-day multi-asset OHLCV panel."""
    rng = np.random.default_rng(42)
    sectors = ["Financials", "Industrials", "Technology", "Consumer", "Materials", "Energy"]
    tickers = [f"AQL{idx:02d}" for idx in range(1, 25)]
    n_days = 504

    dates: list[date] = []
    cur = date(2024, 1, 2)
    while len(dates) < n_days:
        if cur.weekday() < 5:
            dates.append(cur)
        cur += timedelta(days=1)

    mkt_shock = rng.normal(0.0003, 0.011, size=n_days)
    sec_shocks = rng.normal(0.0, 0.007, size=(len(sectors), n_days))

    frames: list[pl.DataFrame] = []
    for i, sym in enumerate(tickers):
        sec_idx = i % len(sectors)
        sec_name = sectors[sec_idx]
        idio = rng.normal(0.0, 0.014, size=n_days)
        rets = np.zeros(n_days, dtype=np.float64)
        for t in range(1, n_days):
            rets[t] = (
                0.8 * mkt_shock[t] + 0.6 * sec_shocks[sec_idx, t] + 0.06 * rets[t - 1] + idio[t]
            )

        base_px = 25.0 + 3.5 * i
        close = np.round(base_px * np.exp(np.cumsum(rets)), 4)
        prev_close = np.concatenate(([base_px], close[:-1]))
        open_px = np.round(prev_close * np.exp(rng.normal(0.0, 0.004, size=n_days)), 4)
        spread = np.abs(rng.normal(0.008, 0.004, size=n_days))
        top = np.maximum(open_px, close)
        bot = np.minimum(open_px, close)
        high_px = np.maximum(top, np.round(top * (1.0 + spread), 4))
        low_px = np.minimum(bot, np.round(bot * (1.0 - spread), 4))
        vol_base = 350_000.0 + 45_000.0 * (i % 7)
        volume = np.round(
            vol_base * np.exp(rng.normal(0.0, 0.35, size=n_days)) * (1.0 + 18.0 * np.abs(rets))
        )

        frames.append(
            pl.DataFrame(
                {
                    "date": dates,
                    "ticker": [sym] * n_days,
                    "sector": [sec_name] * n_days,
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close,
                    "volume": volume,
                }
            )
        )
    return pl.concat(frames).sort(["ticker", "date"])


def generate_demo_single_futures() -> pl.DataFrame:
    """Build a deterministic 1,200-bar 5-minute single-contract futures OHLCV series."""
    rng = np.random.default_rng(104)
    n_bars = 1200
    timestamps: list[datetime] = []
    day = date(2026, 1, 5)
    while len(timestamps) < n_bars:
        if day.weekday() < 5:
            for slot in range(48):
                if len(timestamps) >= n_bars:
                    break
                timestamps.append(
                    datetime(day.year, day.month, day.day, 9, 0) + timedelta(minutes=slot * 5)
                )
        day += timedelta(days=1)

    shocks = rng.normal(0.00004, 0.0018, size=n_bars)
    for t in range(2, n_bars):
        shocks[t] += 0.12 * shocks[t - 1] - 0.05 * shocks[t - 2]

    close = np.round(1280.0 * np.exp(np.cumsum(shocks)), 2)
    prev = np.concatenate(([1280.0], close[:-1]))
    open_px = np.round(prev * (1.0 + rng.normal(0.0, 0.0004, size=n_bars)), 2)
    wiggle = np.abs(rng.normal(0.0009, 0.0005, size=n_bars))
    top = np.maximum(open_px, close)
    bot = np.minimum(open_px, close)
    high_px = np.maximum(top, np.round(top * (1.0 + wiggle), 2))
    low_px = np.minimum(bot, np.round(bot * (1.0 - wiggle), 2))
    volume = np.round(1800.0 * np.exp(rng.normal(0.0, 0.4, size=n_bars)))

    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "ticker": ["VN30F1M_SYN"] * n_bars,
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": close,
            "volume": volume,
        }
    )
