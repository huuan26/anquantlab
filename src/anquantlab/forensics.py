"""Free-data forensics, survivorship audit, and implicit OHLCV spread estimation."""

from __future__ import annotations

from typing import Any

import polars as pl
import polars_anta as pa

from .schemas import AnomalyEvent, DatasetForensicsResponse

SPLIT_JUMP_THRESHOLD = 0.35
MAX_SAMPLE_ANOMALIES = 8


def _clean_float(val: Any, digits: int = 2) -> float | None:
    if val is None:
        return None
    fval = float(val)
    if fval != fval or fval in (float("inf"), float("-inf")):
        return None
    return round(fval, digits)


def _finite_series(df: pl.DataFrame, col: str) -> pl.Series:
    non_null = df[col].drop_nulls()
    if non_null.is_empty():
        return non_null
    return non_null.filter(non_null.is_finite())


def _collect_sample_anomalies(
    flagged: pl.DataFrame,
    time_col: str,
    symbol_col: str | None,
) -> list[AnomalyEvent]:
    if flagged.is_empty():
        return []
    events: list[AnomalyEvent] = []
    cast_df = flagged.head(MAX_SAMPLE_ANOMALIES).with_columns(
        pl.col(time_col).cast(pl.String).alias("_t_str")
    )
    for row in cast_df.to_dicts():
        sym = str(row[symbol_col]) if symbol_col and row.get(symbol_col) is not None else None
        ts = str(row["_t_str"])
        if row["_ohlc_bad"]:
            kind = "OHLC_VIOLATION"
            detail = (
                f"O={row['open']:.4f} H={row['high']:.4f} L={row['low']:.4f} C={row['close']:.4f}"
            )
        elif row["_split_jump"]:
            kind = "SPLIT_OR_GAP_JUMP"
            ret_pct = float(row["_ret"] or 0.0) * 100.0
            detail = f"1-bar return {ret_pct:+.1f}% (unadjusted split/dividend or spike suspect)"
        elif row["_zero_vol"]:
            kind = "ZERO_VOLUME"
            detail = f"Bar volume={row['volume']} (illiquid or halted session)"
        else:
            kind = "FROZEN_BAR"
            detail = f"Flat O=H=L=C={row['close']:.4f} (limit-lock or stale feed)"
        events.append(AnomalyEvent(symbol=sym, timestamp=ts, kind=kind, detail=detail))
    return events


def analyze_dataset_forensics(
    dataset_id: str,
    df: pl.DataFrame,
    *,
    time_col: str,
    symbol_col: str | None = None,
) -> DatasetForensicsResponse:
    """Audit dirty free-data anomalies, survivorship risk, and implicit OHLCV spread."""
    if df.is_empty():
        return DatasetForensicsResponse(
            dataset_id=dataset_id,
            health_score=0,
            grade="WARN",
            row_count=0,
            symbol_count=0,
            zero_volume_bars=0,
            zero_volume_pct=0.0,
            frozen_bars=0,
            frozen_pct=0.0,
            split_suspect_jumps=0,
            ohlc_violations=0,
            duplicate_rows=0,
            late_listings=0,
            early_dropouts=0,
            survivorship_risk="SINGLE_ASSET",
            has_taker_flow=False,
            recommended_min_slippage_bps=5.0,
            warnings=["Dataset is empty."],
        )

    sort_keys = [symbol_col, time_col] if symbol_col else [time_col]
    work = df.sort(sort_keys)
    row_count = work.height
    symbol_count = int(work[symbol_col].n_unique()) if symbol_col else 1
    duplicate_rows = int(row_count - work.unique(subset=sort_keys).height)

    ret_expr = (
        pl.col("close").pct_change().over(symbol_col)
        if symbol_col
        else pl.col("close").pct_change()
    )
    annotated = work.with_columns(
        ret_expr.alias("_ret"),
        (pl.col("volume").is_null() | (pl.col("volume") <= 0.0)).alias("_zero_vol"),
        ((pl.col("high") <= pl.col("low")) & (pl.col("open") == pl.col("close"))).alias("_frozen"),
        (
            (pl.col("high") < pl.max_horizontal("open", "close"))
            | (pl.col("low") > pl.min_horizontal("open", "close"))
            | (pl.col("close") <= 0.0)
            | (pl.col("low") <= 0.0)
        ).alias("_ohlc_bad"),
    ).with_columns(
        (
            pl.col("_ret").is_not_null()
            & pl.col("_ret").is_finite()
            & (pl.col("_ret").abs() > SPLIT_JUMP_THRESHOLD)
        ).alias("_split_jump")
    )

    counts = annotated.select(
        pl.col("_zero_vol").sum().alias("zero_vol"),
        pl.col("_frozen").sum().alias("frozen"),
        pl.col("_ohlc_bad").sum().alias("ohlc_bad"),
        pl.col("_split_jump").sum().alias("split_jump"),
    ).row(0, named=True)

    zero_vol_bars = int(counts["zero_vol"] or 0)
    frozen_bars = int(counts["frozen"] or 0)
    ohlc_violations = int(counts["ohlc_bad"] or 0)
    split_jumps = int(counts["split_jump"] or 0)
    zero_vol_pct = round(100.0 * zero_vol_bars / row_count, 2)
    frozen_pct = round(100.0 * frozen_bars / row_count, 2)

    flagged_df = (
        annotated.filter(
            pl.col("_ohlc_bad") | pl.col("_split_jump") | pl.col("_zero_vol") | pl.col("_frozen")
        )
        .with_columns(
            pl.when(pl.col("_ohlc_bad"))
            .then(pl.lit(0))
            .when(pl.col("_split_jump"))
            .then(pl.lit(1))
            .when(pl.col("_zero_vol"))
            .then(pl.lit(2))
            .otherwise(pl.lit(3))
            .alias("_prio")
        )
        .sort(["_prio", time_col])
    )
    sample_anomalies = _collect_sample_anomalies(flagged_df, time_col, symbol_col)

    # Survivorship & per-symbol bar count diagnostics
    late_listings = 0
    early_dropouts = 0
    max_bars_per_sym = row_count
    if symbol_col:
        span_df = work.group_by(symbol_col).agg(
            pl.col(time_col).min().alias("first_t"),
            pl.col(time_col).max().alias("last_t"),
            pl.len().alias("bar_cnt"),
        )
        max_bars_per_sym = int(span_df["bar_cnt"].max() or 0)
        if symbol_count >= 5:
            unique_dates = work.select(pl.col(time_col).drop_nulls().unique().sort())[time_col]
            if len(unique_dates) >= 10:
                late_cut = unique_dates[min(4, len(unique_dates) - 1)]
                early_cut = unique_dates[max(0, len(unique_dates) - 5)]
                late_listings = int(span_df.filter(pl.col("first_t") > late_cut).height)
                early_dropouts = int(span_df.filter(pl.col("last_t") < early_cut).height)
            survivorship_risk = "HIGH" if early_dropouts == 0 else "LOW"
        else:
            survivorship_risk = "SINGLE_ASSET"
    else:
        survivorship_risk = "SINGLE_ASSET"

    # Zero-orderbook implicit microstructure via polars-anta
    cs_median: float | None = None
    cs_p90: float | None = None
    roll_median: float | None = None
    amihud_median: float | None = None

    if max_bars_per_sym >= 6:
        period = min(20, max(3, max_bars_per_sym // 2))
        cs_expr = pa.corwin_schultz_spread("high", "low", period=period) * 10_000.0
        roll_expr = pa.roll_spread("close", period=period) * 10_000.0
        ami_expr = pa.amihud_illiquidity("close", "volume", period=period)
        if symbol_col:
            cs_expr = cs_expr.over(symbol_col)
            roll_expr = roll_expr.over(symbol_col)
            ami_expr = ami_expr.over(symbol_col)

        micro_df = work.select(
            cs_expr.alias("_cs_bps"),
            roll_expr.alias("_roll_bps"),
            ami_expr.alias("_amihud"),
        )
        cs_ser = _finite_series(micro_df, "_cs_bps")
        roll_ser = _finite_series(micro_df, "_roll_bps")
        ami_ser = _finite_series(micro_df, "_amihud")

        if not cs_ser.is_empty():
            cs_median = _clean_float(cs_ser.median(), 2)
            cs_p90 = _clean_float(cs_ser.quantile(0.90, interpolation="linear"), 2)
        if not roll_ser.is_empty():
            roll_median = _clean_float(roll_ser.median(), 2)
        if not ami_ser.is_empty():
            amihud_median = _clean_float(ami_ser.median(), 4)

    eff_spread = max(
        cs_median or 0.0,
        0.5 * (cs_p90 or 0.0),
        roll_median or 0.0,
    )
    if eff_spread <= 0.0:
        eff_spread = 8.0
    rec_min_slip = round(max(1.5, min(150.0, 0.5 * eff_spread)), 2)

    has_taker_flow = ("taker_buy_volume" in work.columns) or ("taker_buy_ratio" in work.columns)

    # Warnings & Data Health Score (0..100)
    warnings: list[str] = []
    if ohlc_violations > 0:
        warnings.append(
            f"{ohlc_violations} bar(s) violate H >= max(O,C), L <= min(O,C), or non-positive price."
        )
    if duplicate_rows > 0:
        warnings.append(f"{duplicate_rows} duplicate (symbol, timestamp) row(s) detected.")
    if split_jumps > 0:
        warnings.append(
            f"{split_jumps} bar(s) exceed +/-35% 1-bar return; verify split/dividend adjustment."
        )
    if zero_vol_bars > 0:
        warnings.append(
            f"{zero_vol_bars} zero-volume bar(s) ({zero_vol_pct:.2f}%); "
            "skip fills on zero-volume bars."
        )
    if frozen_bars > 0:
        warnings.append(
            f"{frozen_bars} frozen O=H=L=C bar(s) ({frozen_pct:.2f}%); "
            "check limit-lock execution risk."
        )
    if survivorship_risk == "HIGH":
        warnings.append(
            f"Survivorship Risk HIGH: all {symbol_count} tickers survive to sample end "
            "(0 early dropouts). Apply Survivorship Penalty in Crash-Test."
        )
    if cs_p90 is not None and cs_p90 > 60.0:
        warnings.append(
            f"Wide tail spread (Corwin-Schultz P90 = {cs_p90:.1f} bps); "
            f"enforce >= {rec_min_slip:.1f} bps slippage."
        )

    penalty = (
        min(30.0, ohlc_violations * 10.0)
        + min(25.0, duplicate_rows * 5.0)
        + min(20.0, split_jumps * 4.0)
        + min(15.0, zero_vol_pct * 1.5)
        + min(15.0, frozen_pct * 1.5)
        + (8.0 if survivorship_risk == "HIGH" else 0.0)
    )
    health_score = max(0, min(100, int(round(100.0 - penalty))))
    if health_score >= 85 and ohlc_violations == 0:
        grade = "A"
    elif health_score >= 70:
        grade = "B"
    elif health_score >= 50:
        grade = "C"
    else:
        grade = "WARN"

    return DatasetForensicsResponse(
        dataset_id=dataset_id,
        health_score=health_score,
        grade=grade,
        row_count=row_count,
        symbol_count=symbol_count,
        zero_volume_bars=zero_vol_bars,
        zero_volume_pct=zero_vol_pct,
        frozen_bars=frozen_bars,
        frozen_pct=frozen_pct,
        split_suspect_jumps=split_jumps,
        ohlc_violations=ohlc_violations,
        duplicate_rows=duplicate_rows,
        late_listings=late_listings,
        early_dropouts=early_dropouts,
        survivorship_risk=survivorship_risk,
        has_taker_flow=has_taker_flow,
        corwin_schultz_spread_bps_median=cs_median,
        corwin_schultz_spread_bps_p90=cs_p90,
        roll_spread_bps_median=roll_median,
        amihud_illiq_median=amihud_median,
        recommended_min_slippage_bps=rec_min_slip,
        warnings=warnings,
        sample_anomalies=sample_anomalies,
    )
