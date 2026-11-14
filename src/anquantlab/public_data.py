"""Zero-key legal public market data connectors with strict HTTPS domain whitelisting."""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from .config import Settings
from .schemas import PublicPresetInfo, PublicPresetListResponse

ALLOWED_PUBLIC_HOSTS: frozenset[str] = frozenset(
    {
        "data-api.binance.vision",
        "api.binance.com",
        "stooq.com",
    }
)
PUBLIC_TIMEOUT_SEC = 10.0
MAX_PUBLIC_RESPONSE_BYTES = 15 * 1024 * 1024

HttpGetter = Callable[[str], bytes]


@dataclass(frozen=True)
class PublicPresetSpec:
    preset_id: str
    name: str
    source: str
    interval: str
    symbols: tuple[str, ...]
    sectors: dict[str, str]
    limit_per_symbol: int
    has_taker_flow: bool
    description: str


_CRYPTO_SECTORS: dict[str, str] = {
    "BTCUSDT": "Layer1",
    "ETHUSDT": "Layer1",
    "SOLUSDT": "Layer1",
    "BNBUSDT": "Exchange",
    "XRPUSDT": "Payments",
    "ADAUSDT": "Layer1",
    "DOGEUSDT": "Meme",
    "AVAXUSDT": "Layer1",
}

_US_ETF_SECTORS: dict[str, str] = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "HealthCare",
    "XLI": "Industrials",
    "XLP": "ConsumerStaples",
    "XLY": "ConsumerDiscretionary",
    "XLU": "Utilities",
    "XLB": "Materials",
}

PUBLIC_PRESETS: dict[str, PublicPresetSpec] = {
    "binance_crypto_flow_1d": PublicPresetSpec(
        preset_id="binance_crypto_flow_1d",
        name="Binance Crypto Major Panel (1d, 8 Pairs + Taker Flow)",
        source="binance",
        interval="1d",
        symbols=tuple(_CRYPTO_SECTORS.keys()),
        sectors=_CRYPTO_SECTORS,
        limit_per_symbol=500,
        has_taker_flow=True,
        description=(
            "500 daily bars across 8 liquid USDT pairs with free aggressive "
            "taker_buy_volume and taker_buy_ratio orderflow columns."
        ),
    ),
    "binance_crypto_flow_1h": PublicPresetSpec(
        preset_id="binance_crypto_flow_1h",
        name="Binance Crypto Major Panel (1h, 8 Pairs + Taker Flow)",
        source="binance",
        interval="1h",
        symbols=tuple(_CRYPTO_SECTORS.keys()),
        sectors=_CRYPTO_SECTORS,
        limit_per_symbol=360,
        has_taker_flow=True,
        description=(
            "360 hourly bars across 8 liquid USDT pairs with taker_buy_volume "
            "and taker_buy_ratio for intraday cross-sectional research."
        ),
    ),
    "binance_btcusdt_5m": PublicPresetSpec(
        preset_id="binance_btcusdt_5m",
        name="Binance BTCUSDT Intraday (5m, 1,000 Bars + Taker Flow)",
        source="binance",
        interval="5m",
        symbols=("BTCUSDT",),
        sectors={"BTCUSDT": "Layer1"},
        limit_per_symbol=1000,
        has_taker_flow=True,
        description=(
            "1,000 5-minute bars of BTCUSDT with trade_count and taker_buy_ratio "
            "for microstructure, VPIN, OFI, and candlestick falsification."
        ),
    ),
    "stooq_us_sectors_1d": PublicPresetSpec(
        preset_id="stooq_us_sectors_1d",
        name="Stooq US S&P Sector ETFs (1d, 9 Sectors)",
        source="stooq",
        interval="1d",
        symbols=tuple(_US_ETF_SECTORS.keys()),
        sectors=_US_ETF_SECTORS,
        limit_per_symbol=756,
        has_taker_flow=False,
        description=(
            "~3 years (756 trading days) across 9 US S&P Sector SPDR ETFs "
            "(XLK..XLB) for cross-asset rotation and regime experiments."
        ),
    ),
}


def validate_public_url(url: str) -> None:
    """Enforce strict HTTPS domain whitelisting to prevent SSRF or arbitrary egress."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS public data URLs are allowed (got '{parsed.scheme}').")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials in public data URLs are forbidden.")
    if parsed.port not in (None, 443):
        raise ValueError(f"Non-standard HTTPS port {parsed.port} is forbidden.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_PUBLIC_HOSTS:
        raise ValueError(
            f"Host '{host}' is not in ALLOWED_PUBLIC_HOSTS {sorted(ALLOWED_PUBLIC_HOSTS)}."
        )


class _WhitelistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_http_get(url: str) -> bytes:
    """Fetch bytes from a whitelisted HTTPS endpoint with strict timeout and byte cap."""
    validate_public_url(url)
    opener = urllib.request.build_opener(_WhitelistedRedirectHandler())
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AnQuantLab/0.1 (Zero-Key Public Research Connector)"},
        method="GET",
    )
    chunks: list[bytes] = []
    total = 0
    with opener.open(req, timeout=PUBLIC_TIMEOUT_SEC) as resp:
        validate_public_url(resp.geturl())
        while True:
            block = resp.read(65536)
            if not block:
                break
            total += len(block)
            if total > MAX_PUBLIC_RESPONSE_BYTES:
                raise ValueError("Public response exceeded 15 MB safety limit.")
            chunks.append(block)
    return b"".join(chunks)


def _fetch_binance_symbol(
    symbol: str,
    sector: str,
    interval: str,
    limit: int,
    getter: HttpGetter,
) -> pl.DataFrame:
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    urls = (
        f"https://data-api.binance.vision/api/v3/klines?{query}",
        f"https://api.binance.com/api/v3/klines?{query}",
    )
    raw_bytes: bytes | None = None
    last_err: Exception | None = None
    for url in urls:
        validate_public_url(url)
        try:
            raw_bytes = getter(url)
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            continue
    if raw_bytes is None:
        raise RuntimeError(f"Binance klines fetch failed for {symbol}: {last_err}")

    rows = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Binance returned empty or invalid kline payload for {symbol}.")

    now_ms = int(time.time() * 1000)
    if len(rows) > 10 and int(rows[-1][6]) > now_ms:
        rows = rows[:-1]

    records = [
        {
            "open_time_ms": int(r[0]),
            "ticker": symbol,
            "sector": sector,
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
            "quote_volume": float(r[7]),
            "trade_count": float(r[8]),
            "taker_buy_volume": float(r[9]),
        }
        for r in rows
    ]
    return (
        pl.DataFrame(records)
        .with_columns(
            pl.from_epoch(pl.col("open_time_ms"), time_unit="ms").alias("timestamp"),
            pl.when(pl.col("volume") > 0.0)
            .then(pl.col("taker_buy_volume") / pl.col("volume"))
            .otherwise(0.5)
            .clip(0.0, 1.0)
            .alias("taker_buy_ratio"),
        )
        .drop("open_time_ms")
        .select(
            "timestamp",
            "ticker",
            "sector",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_ratio",
        )
    )


def _fetch_stooq_symbol(symbol: str, sector: str, limit: int, getter: HttpGetter) -> pl.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
    validate_public_url(url)
    try:
        raw_bytes = getter(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Stooq CSV fetch failed for {symbol}: {exc}") from exc

    text_head = raw_bytes[:120].decode("utf-8", errors="ignore").strip().lower()
    if not text_head or "exceeded" in text_head or "no data" in text_head:
        raise RuntimeError(f"Stooq returned unavailable/rate-limited response for {symbol}.")

    raw_df = pl.read_csv(io.BytesIO(raw_bytes), try_parse_dates=True)
    rename_map = {c: c.strip().lower() for c in raw_df.columns}
    df = raw_df.rename(rename_map)
    required = {"date", "open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"Stooq CSV for {symbol} missing required columns {sorted(required)}.")
    if "volume" not in df.columns:
        df = df.with_columns(pl.lit(0.0).alias("volume"))

    return (
        df.with_columns(
            pl.lit(symbol.upper()).alias("ticker"),
            pl.lit(sector).alias("sector"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").fill_null(0.0).cast(pl.Float64),
        )
        .sort("date")
        .tail(limit)
        .select("date", "ticker", "sector", "open", "high", "low", "close", "volume")
    )


def preset_cache_path(settings: Settings, preset_id: str) -> Path:
    return settings.cache_dir / f"{preset_id}.parquet"


def list_public_presets(settings: Settings) -> PublicPresetListResponse:
    items = [
        PublicPresetInfo(
            preset_id=spec.preset_id,
            name=spec.name,
            source=spec.source,
            interval=spec.interval,
            symbols=list(spec.symbols),
            has_taker_flow=spec.has_taker_flow,
            description=spec.description,
            cached=preset_cache_path(settings, spec.preset_id).is_file(),
        )
        for spec in PUBLIC_PRESETS.values()
    ]
    return PublicPresetListResponse(
        allow_public_fetch=settings.allow_public_fetch,
        cache_dir=str(settings.cache_dir),
        presets=items,
    )


def fetch_or_load_public_preset(
    preset_id: str,
    settings: Settings,
    *,
    force_refresh: bool = False,
    http_get: HttpGetter | None = None,
) -> tuple[PublicPresetSpec, pl.DataFrame, Path]:
    """Load cached Parquet or fetch from zero-key public API into outside-repo cache."""
    spec = PUBLIC_PRESETS.get(preset_id)
    if spec is None:
        raise KeyError(f"Unknown public preset '{preset_id}'.")

    cpath = preset_cache_path(settings, spec.preset_id)
    if not force_refresh and cpath.is_file():
        return spec, pl.read_parquet(cpath), cpath

    if not settings.allow_public_fetch:
        raise PermissionError("Public data fetching is disabled (ANQUANTLAB_ALLOW_PUBLIC_FETCH=0).")

    getter = http_get or default_http_get
    frames: list[pl.DataFrame] = []
    for sym in spec.symbols:
        sec = spec.sectors.get(sym, "General")
        if spec.source == "binance":
            frames.append(
                _fetch_binance_symbol(sym, sec, spec.interval, spec.limit_per_symbol, getter)
            )
        elif spec.source == "stooq":
            frames.append(_fetch_stooq_symbol(sym, sec, spec.limit_per_symbol, getter))
        else:
            raise ValueError(f"Unsupported public source '{spec.source}'.")

    combined = pl.concat(frames, how="vertical_relaxed")
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = settings.cache_dir / f".{spec.preset_id}.tmp.parquet"
    combined.write_parquet(tmp_path)
    tmp_path.replace(cpath)
    return spec, combined, cpath
