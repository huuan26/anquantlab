"""Portfolio metric aggregation, breakeven cost curve, and backtest wire serializers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
import polars_anta as pa

from .schemas import (
    BacktestMetrics,
    ChartBarPoint,
    CostCurvePoint,
    EquityPoint,
    TradeRecord,
    TrialLedgerSnapshot,
)

COST_GRID_BPS: tuple[float, ...] = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0, 75.0, 100.0)


@dataclass
class DatasetMicroMeta:
    split_time: Any
    is_bars: int
    oos_bars: int
    annualization: float
    close_hm: tuple[int, int] | None
    micro_df: pl.DataFrame


def _infer_annualization_and_session(
    df: pl.DataFrame, time_col: str, symbol_col: str | None
) -> tuple[float, tuple[int, int] | None]:
    sample = df.filter(pl.col(symbol_col) == df[symbol_col][0]) if symbol_col else df
    t_ser = sample[time_col].drop_nulls().sort()
    if t_ser.len() < 3:
        return 252.0, None
    dtype = t_ser.dtype
    if dtype == pl.Date:
        return (365.0 if bool((t_ser.dt.weekday() >= 6).any()) else 252.0), None
    if isinstance(dtype, pl.Datetime):
        head_t = t_ser.head(min(120, t_ser.len()))
        diffs_sec = head_t.diff().drop_nulls().dt.total_seconds().to_numpy()
        med_sec = float(np.median(diffs_sec)) if diffs_sec.size > 0 else 86_400.0
        trading_days = 365.0 if bool((t_ser.dt.weekday() >= 6).any()) else 252.0
        if med_sec >= 43_200.0:
            return trading_days, None
        dates = t_ser.dt.date()
        day0_times = t_ser.filter(dates == dates[0])
        last_t0 = day0_times[-1]
        close_hm = (int(last_t0.hour), int(last_t0.minute))
        bars_per_day = max(1.0, float(day0_times.len()))
        if bars_per_day <= 2.0 and med_sec > 0:
            bars_per_day = max(1.0, round(23_400.0 / med_sec))
        return round(trading_days * bars_per_day, 2), close_hm
    return 252.0, None


def build_micro_meta(df: pl.DataFrame, time_col: str, symbol_col: str | None) -> DatasetMicroMeta:
    u_times = df.select(pl.col(time_col).drop_nulls().unique().sort())[time_col]
    n_u = u_times.len()
    if n_u >= 8:
        split_idx = max(2, min(n_u - 1, int(round(0.75 * n_u))))
        split_time, is_bars, oos_bars = u_times[split_idx], split_idx, n_u - split_idx
    else:
        split_time, is_bars, oos_bars = None, n_u, 0

    ann, close_hm = _infer_annualization_and_session(df, time_col, symbol_col)
    max_bars = int(df.group_by(symbol_col).len()["len"].max() or 0) if symbol_col else df.height
    period = min(20, max(3, max_bars // 2)) if max_bars >= 6 else 3

    over_fn = (lambda e: e.over(symbol_col)) if symbol_col else (lambda e: e)
    cs_raw = (0.5 * pa.corwin_schultz_spread("high", "low", period=period)).clip(0.0, 0.05)
    ami_raw = pa.amihud_illiquidity("close", "volume", period=period)
    ami_med = ami_raw.rolling_median(window_size=max(6, period * 2), min_samples=2)
    lock_raw = (
        ((pl.col("high") <= pl.col("low")) & (pl.col("open") == pl.col("close")))
        | pl.col("volume").is_null()
        | (pl.col("volume") <= 0.0)
    )

    cs_prev = over_fn(cs_raw.shift(1)).fill_null(0.0005).fill_nan(0.0005)
    ami_step = (ami_raw / pl.when(ami_med > 1e-12).then(ami_med).otherwise(1.0)).clip(0.25, 4.0)
    ami_r = over_fn(ami_step.shift(1)).fill_null(1.0)
    lock_prev = over_fn(lock_raw.shift(1, fill_value=False))

    base_floor = pl.max_horizontal(cs_prev, pl.lit(0.0004))
    micro_df = df.select(
        cs_prev.alias("_cs_half_rate"),
        (ami_r * base_floor).clip(0.0, 0.05).alias("_ami_half_rate"),
        lock_prev.alias("_locked_prev"),
    )
    return DatasetMicroMeta(
        split_time=split_time,
        is_bars=is_bars,
        oos_bars=oos_bars,
        annualization=ann,
        close_hm=close_hm,
        micro_df=micro_df,
    )


def clean_num(val: Any, default: float = 0.0, digits: int = 6) -> float:
    if val is None:
        return default
    fval = float(val)
    if not math.isfinite(fval):
        return default
    return round(fval, digits)


def compute_portfolio_metrics(
    eval_port: pl.DataFrame,
    trades_df: pl.DataFrame,
    ann: float,
    oos_sr: float | None,
    snap: TrialLedgerSnapshot,
) -> BacktestMetrics:
    """Compute core, tail-risk, breakeven, and multiple-testing DSR metrics on portfolio series."""
    if eval_port.is_empty():
        return BacktestMetrics(
            total_return=0.0,
            gross_total_return=0.0,
            benchmark_return=0.0,
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            gross_sharpe_ratio=0.0,
            oos_sharpe_ratio=oos_sr,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            psr=0.0,
            live_dsr=0.0,
            var_95=0.0,
            cvar_95=0.0,
            omega_ratio=1.0,
            tail_ratio=1.0,
            win_rate=0.0,
            profit_factor=1.0,
            total_turnover=0.0,
            total_cost=0.0,
            n_trades=0,
            n_round_trips=0,
            avg_holding_bars=0.0,
            avg_mae=0.0,
            avg_mfe=0.0,
            breakeven_bps=0.0,
        )

    n_trials_int = max(1, int(math.ceil(snap.effective_n_trials)))
    agg = eval_port.select(
        pl.col("equity_curve").last().alias("eq_last"),
        pl.col("gross_equity").last().alias("geq_last"),
        pl.col("benchmark_equity").last().alias("beq_last"),
        pl.col("net_return").mean().alias("mean_r"),
        pl.col("net_return").std().fill_null(0.0).alias("std_r"),
        pa.sharpe_ratio("net_return", annualization=ann).alias("sr"),
        pa.sharpe_ratio("gross_return", annualization=ann).alias("gsr"),
        pa.sortino_ratio("net_return", annualization=ann).alias("sortino"),
        pa.calmar_ratio("net_return", annualization=ann).alias("calmar"),
        pa.max_drawdown("equity_curve", is_returns=False).alias("mdd"),
        pa.probabilistic_sharpe_ratio("net_return", annualization=ann).alias("psr"),
        pa.deflated_sharpe_ratio(
            "net_return",
            n_trials=n_trials_int,
            trials_sr_std=snap.trials_sr_std,
            annualization=ann,
        ).alias("dsr"),
        pa.value_at_risk("net_return", cutoff=0.05).alias("var95"),
        pa.conditional_var("net_return", cutoff=0.05).alias("cvar95"),
        pa.omega_ratio("net_return", annualization=ann).alias("omega"),
        pa.tail_ratio("net_return", cutoff=0.05).alias("tail"),
        pa.win_rate("net_return", include_zeros=False).alias("win_rate"),
        pa.profit_factor("net_return").alias("pf"),
        (pl.col("turnover") > 1e-12).cast(pl.Int64).sum().alias("n_trades"),
        pl.col("turnover").sum().alias("tot_to"),
        pl.col("cost").sum().alias("tot_cost"),
    ).row(0, named=True)

    be_rate = pa.breakeven_cost(eval_port["gross_return"], eval_port["turnover"])
    be_bps = clean_num(be_rate * 10_000.0, default=0.0, digits=2)
    n_rt = trades_df.height
    avg_hold = clean_num(trades_df["holding_bars"].mean(), 0.0, 2) if n_rt else 0.0
    avg_mae = clean_num(trades_df["mae"].mean(), 0.0, 5) if n_rt else 0.0
    avg_mfe = clean_num(trades_df["mfe"].mean(), 0.0, 5) if n_rt else 0.0

    return BacktestMetrics(
        total_return=clean_num((agg["eq_last"] or 1.0) - 1.0),
        gross_total_return=clean_num((agg["geq_last"] or 1.0) - 1.0),
        benchmark_return=clean_num((agg["beq_last"] or 1.0) - 1.0),
        annualized_return=clean_num(float(agg["mean_r"] or 0.0) * ann),
        annualized_volatility=clean_num(float(agg["std_r"] or 0.0) * math.sqrt(ann)),
        sharpe_ratio=clean_num(agg["sr"], 0.0, 4),
        gross_sharpe_ratio=clean_num(agg["gsr"], 0.0, 4),
        oos_sharpe_ratio=oos_sr,
        sortino_ratio=clean_num(agg["sortino"], 0.0, 4),
        calmar_ratio=clean_num(agg["calmar"], 0.0, 4),
        max_drawdown=clean_num(agg["mdd"], 0.0, 5),
        psr=clean_num(agg["psr"], 0.0, 4),
        live_dsr=clean_num(agg["dsr"], 0.0, 4),
        var_95=clean_num(agg["var95"], 0.0, 5),
        cvar_95=clean_num(agg["cvar95"], 0.0, 5),
        omega_ratio=clean_num(agg["omega"], 1.0, 4),
        tail_ratio=clean_num(agg["tail"], 1.0, 4),
        win_rate=clean_num(agg["win_rate"], 0.0, 4),
        profit_factor=clean_num(agg["pf"], 1.0, 4),
        total_turnover=clean_num(agg["tot_to"], 0.0, 4),
        total_cost=clean_num(agg["tot_cost"], 0.0, 5),
        n_trades=int(agg["n_trades"] or 0),
        n_round_trips=n_rt,
        avg_holding_bars=avg_hold,
        avg_mae=avg_mae,
        avg_mfe=avg_mfe,
        breakeven_bps=be_bps,
    )


def compute_cost_curve(eval_port: pl.DataFrame, ann: float) -> list[CostCurvePoint]:
    gross = eval_port["gross_return"].to_numpy()
    to = eval_port["turnover"].to_numpy()
    if gross.size < 2:
        return []
    sqrt_ann = math.sqrt(ann)
    out: list[CostCurvePoint] = []
    for bps in COST_GRID_BPS:
        net = gross - (bps / 10_000.0) * to
        std = float(np.std(net, ddof=1))
        sr = (float(np.mean(net)) / std * sqrt_ann) if std > 1e-12 else 0.0
        tot_r = float(np.prod(1.0 + net) - 1.0)
        out.append(
            CostCurvePoint(
                cost_bps=bps,
                sharpe=clean_num(sr, 0.0, 4),
                total_return=clean_num(tot_r, 0.0, 5),
            )
        )
    return out


def serialize_equity(eval_port: pl.DataFrame, time_col: str, split_time: Any) -> list[EquityPoint]:
    n = eval_port.height
    if n > 600:
        idx = np.unique(np.linspace(0, n - 1, 600, dtype=np.int64))
        sub = eval_port[idx.tolist()]
    else:
        sub = eval_port

    is_oos_expr = (pl.col(time_col) >= split_time) if split_time is not None else pl.lit(False)
    rows = sub.select(
        pl.col(time_col).cast(pl.String).alias("t"),
        "gross_equity",
        "equity_curve",
        "benchmark_equity",
        "drawdown",
        "turnover",
        is_oos_expr.alias("is_oos"),
    ).to_dicts()
    return [
        EquityPoint(
            t=r["t"],
            gross_eq=clean_num(r["gross_equity"], 1.0, 5),
            net_eq=clean_num(r["equity_curve"], 1.0, 5),
            bench_eq=clean_num(r["benchmark_equity"], 1.0, 5),
            dd=clean_num(r["drawdown"], 0.0, 5),
            turnover=clean_num(r["turnover"], 0.0, 4),
            is_oos=bool(r["is_oos"]),
        )
        for r in rows
    ]


def serialize_candles(sym_bt: pl.DataFrame, time_col: str, chart_bars: int) -> list[ChartBarPoint]:
    rows = (
        sym_bt.tail(chart_bars)
        .select(
            pl.col(time_col).cast(pl.String).alias("t"),
            pl.col("open").alias("o"),
            pl.col("high").alias("h"),
            pl.col("low").alias("l"),
            pl.col("close").alias("c"),
            pl.col("volume").alias("v"),
            pl.col("signal").alias("s"),
        )
        .to_dicts()
    )
    return [
        ChartBarPoint(
            t=r["t"],
            o=float(r["o"]),
            h=float(r["h"]),
            l=float(r["l"]),
            c=float(r["c"]),
            v=float(r["v"]),
            s=clean_num(r["s"], 0.0, 6) if r["s"] is not None else None,
        )
        for r in rows
    ]


def serialize_trades(
    trades_df: pl.DataFrame, active_sym: str | None, max_trades: int
) -> list[TradeRecord]:
    if trades_df.is_empty():
        return []
    cast_exprs = [
        pl.col(tc).cast(pl.String) for tc in ("entry_time", "exit_time") if tc in trades_df.columns
    ]
    tail = trades_df.tail(max_trades)
    if cast_exprs:
        tail = tail.with_columns(cast_exprs)
    return [
        TradeRecord(
            trade_id=int(r["trade_id"]),
            symbol=active_sym,
            side=str(r["side"]),
            entry_time=str(r.get("entry_time", r.get("entry_index", ""))),
            exit_time=str(r.get("exit_time", r.get("exit_index", ""))),
            holding_bars=int(r["holding_bars"]),
            entry_price=clean_num(r.get("entry_price"), 0.0, 4)
            if r.get("entry_price") is not None
            else None,
            exit_price=clean_num(r.get("exit_price"), 0.0, 4)
            if r.get("exit_price") is not None
            else None,
            gross_return=clean_num(r["gross_return"], 0.0, 5),
            cost=clean_num(r["cost"], 0.0, 5),
            net_return=clean_num(r["net_return"], 0.0, 5),
            mae=clean_num(r["mae"], 0.0, 5),
            mfe=clean_num(r["mfe"], 0.0, 5),
        )
        for r in reversed(tail.to_dicts())
    ]
