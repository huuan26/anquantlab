"""Two-tier cached vectorized backtest, endogenous OHLCV spread, and Holdout Vault engine."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import polars as pl
import polars_anta as pa

from .backtest_metrics import (
    DatasetMicroMeta,
    build_micro_meta,
    clean_num,
    compute_cost_curve,
    compute_portfolio_metrics,
    serialize_candles,
    serialize_equity,
    serialize_trades,
)
from .schemas import BacktestRunRequest, BacktestRunResponse
from .store import DatasetEntry, WorkbenchStore
from .trial_ledger import TrialLedgerRegistry

_VALID_SCHEMES = {"dollar_neutral", "long_only", "equal_weight", "raw"}
_VALID_PRICES = {"close", "open", "twap", "vwap"}
_VALID_SLIP_MODES = {"fixed", "corwin_schultz", "amihud"}


@dataclass
class _CachedPosFrame:
    asset_df: pl.DataFrame
    port_df: pl.DataFrame
    symbol_count: int
    notes: list[str]


class BacktestLabEngine:
    """High-speed 2-tier cached backtest & cost-sensitivity lab on polars-anta."""

    def __init__(self, max_pos_cache: int = 24) -> None:
        self.max_pos_cache = max_pos_cache
        self._meta_cache: OrderedDict[tuple[str, str | None, int], DatasetMicroMeta] = OrderedDict()
        self._pos_cache: OrderedDict[tuple[Any, ...], _CachedPosFrame] = OrderedDict()

    def _get_meta(self, entry: DatasetEntry, df: pl.DataFrame) -> DatasetMicroMeta:
        key = (entry.dataset_id, entry.sha256_prefix, df.height)
        if key in self._meta_cache:
            self._meta_cache.move_to_end(key)
            return self._meta_cache[key]
        meta = build_micro_meta(df, entry.time_col, entry.symbol_col)
        self._meta_cache[key] = meta
        while len(self._meta_cache) > 12:
            self._meta_cache.popitem(last=False)
        return meta

    def _get_or_build_positions(
        self,
        entry: DatasetEntry,
        sig_df: pl.DataFrame,
        norm_formula: str,
        plan_notes: list[str],
        meta: DatasetMicroMeta,
        req: BacktestRunRequest,
        ann: float,
    ) -> tuple[_CachedPosFrame, bool]:
        vol_t = req.vol_target if (req.vol_target is not None and req.vol_target > 0.0) else None
        key = (
            entry.dataset_id,
            entry.sha256_prefix,
            norm_formula,
            req.weight_scheme,
            req.execution_price,
            req.signal_lag,
            round(vol_t, 4) if vol_t is not None else None,
            round(req.no_trade_buffer, 5),
            req.limit_lock_skip,
            req.intraday_flatten,
            round(ann, 2),
        )
        if key in self._pos_cache:
            self._pos_cache.move_to_end(key)
            return self._pos_cache[key], True

        notes = list(plan_notes)
        sym_col = entry.symbol_col
        sym_cnt = int(sig_df[sym_col].n_unique()) if sym_col else 1
        gb_arg = sym_col if (sym_col and sym_cnt > 1) else None

        work = pl.concat([sig_df, meta.micro_df], how="horizontal")
        pa_scheme = req.weight_scheme
        if sym_cnt <= 1 and req.weight_scheme != "raw":
            pa_scheme = "raw"
            if req.weight_scheme == "dollar_neutral":
                work = work.with_columns(pl.col("signal").sign().alias("_bt_sig"))
                notes.append("Single-asset series: mapped 'dollar_neutral' to unit {-1, 0, +1}.")
            else:
                work = work.with_columns(
                    pl.when(pl.col("signal") > 0.0).then(1.0).otherwise(0.0).alias("_bt_sig")
                )
                notes.append(f"Single-asset series: mapped '{req.weight_scheme}' to {{0, +1}}.")
        else:
            work = work.with_columns(pl.col("signal").alias("_bt_sig"))

        flat_expr: pl.Expr | None = None
        if req.intraday_flatten and meta.close_hm is not None:
            ch, cm = meta.close_hm
            mins = pl.col(entry.time_col).dt.hour().cast(pl.Int32) * 60 + pl.col(
                entry.time_col
            ).dt.minute().cast(pl.Int32)
            flat_expr = mins >= (ch * 60 + cm)
            notes.append(f"Intraday EOD flatten active at causal session close {ch:02d}:{cm:02d}.")

        if req.signal_lag == 0:
            notes.append("WARNING: signal_lag=0 executes on same-bar price (look-ahead risk).")

        bt_raw = pa.vectorized_backtest(
            work,
            signal="_bt_sig",
            group_by=gb_arg,
            time_col=entry.time_col,
            fee_rate=0.0,
            slippage_rate=0.0,
            signal_lag=req.signal_lag,
            annualization=ann,
            weight_scheme=pa_scheme,  # type: ignore[arg-type]
            execution_price=req.execution_price,  # type: ignore[arg-type]
            flat_mask=flat_expr,
            vol_target=vol_t,
            no_trade_buffer=req.no_trade_buffer,
            aggregate_portfolio=False,
        )
        adf = bt_raw.data

        if req.limit_lock_skip:
            locked_pos = pl.when(~pl.col("_locked_prev")).then(pl.col("position")).otherwise(None)
            ff_pos = (
                locked_pos.forward_fill().over(gb_arg).fill_null(0.0)
                if gb_arg
                else locked_pos.forward_fill().fill_null(0.0)
            )
            prev_p = (
                ff_pos.shift(1, fill_value=0.0).over(gb_arg)
                if gb_arg
                else ff_pos.shift(1, fill_value=0.0)
            )
            adf = adf.with_columns(ff_pos.alias("position")).with_columns(
                (pl.col("position") - prev_p).abs().alias("turnover"),
                (pl.col("position") * pl.col("asset_return")).alias("gross_return"),
            )
            notes.append("Limit-lock & zero-volume rebalance freeze applied causally (t-1).")

        keep_cols = [entry.time_col, *([sym_col] if sym_col else [])]
        keep_cols.extend(
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "signal",
                "position",
                "turnover",
                "asset_return",
                "gross_return",
                "_cs_half_rate",
                "_ami_half_rate",
            ]
        )
        adf = adf.select(keep_cols)

        if gb_arg:
            port_df = (
                adf.with_columns(
                    (pl.col("turnover") * pl.col("_cs_half_rate")).alias("_cs_cost"),
                    (pl.col("turnover") * pl.col("_ami_half_rate")).alias("_ami_cost"),
                )
                .group_by(entry.time_col)
                .agg(
                    pl.col("position").sum().alias("position"),
                    pl.col("turnover").sum().alias("turnover"),
                    pl.col("asset_return").mean().alias("asset_return"),
                    pl.col("gross_return").sum().alias("gross_return"),
                    pl.col("_cs_cost").sum().alias("_cs_cost"),
                    pl.col("_ami_cost").sum().alias("_ami_cost"),
                )
                .sort(entry.time_col)
            )
        else:
            port_df = adf.select(
                entry.time_col,
                "position",
                "turnover",
                "asset_return",
                "gross_return",
                (pl.col("turnover") * pl.col("_cs_half_rate")).alias("_cs_cost"),
                (pl.col("turnover") * pl.col("_ami_half_rate")).alias("_ami_cost"),
            )

        cached = _CachedPosFrame(asset_df=adf, port_df=port_df, symbol_count=sym_cnt, notes=notes)
        self._pos_cache[key] = cached
        while len(self._pos_cache) > self.max_pos_cache:
            self._pos_cache.popitem(last=False)
        return cached, False

    def run(
        self,
        store: WorkbenchStore,
        ledger: TrialLedgerRegistry,
        req: BacktestRunRequest,
    ) -> BacktestRunResponse:
        t0 = time.perf_counter()
        if req.weight_scheme not in _VALID_SCHEMES:
            raise ValueError(f"weight_scheme must be one of {sorted(_VALID_SCHEMES)}")
        if req.execution_price not in _VALID_PRICES:
            raise ValueError(f"execution_price must be one of {sorted(_VALID_PRICES)}")
        if req.slippage_mode not in _VALID_SLIP_MODES:
            raise ValueError(f"slippage_mode must be one of {sorted(_VALID_SLIP_MODES)}")

        sig_df, plan, _, sig_hit = store.get_or_compute_signal(req.dataset_id, req.formula)
        entry, base_df = store.get_frame(req.dataset_id)
        meta = self._get_meta(entry, base_df)
        ann = float(req.annualization) if req.annualization is not None else meta.annualization

        pos_frame, pos_hit = self._get_or_build_positions(
            entry, sig_df, plan.normalized_formula, plan.notes, meta, req, ann
        )

        base_rate = (req.fee_bps + req.slippage_bps) / 10_000.0
        endo_col = (
            pl.col("_cs_cost")
            if req.slippage_mode == "corwin_schultz"
            else (pl.col("_ami_cost") if req.slippage_mode == "amihud" else pl.lit(0.0))
        )

        full_port = pos_frame.port_df.with_columns(
            (pl.col("turnover") * base_rate + endo_col).alias("cost")
        ).with_columns((pl.col("gross_return") - pl.col("cost")).alias("net_return"))

        is_port = (
            full_port.filter(pl.col(entry.time_col) < meta.split_time)
            if meta.split_time is not None
            else full_port
        )
        is_sr_val = (
            float(is_port.select(pa.sharpe_ratio("net_return", annualization=ann)).item() or 0.0)
            if is_port.height > 1
            else 0.0
        )
        trial_key = (
            f"{plan.normalized_formula}|{req.weight_scheme}|{req.execution_price}|"
            f"lag={req.signal_lag}|vt={req.vol_target}|buf={req.no_trade_buffer}|"
            f"ll={req.limit_lock_skip}|if={req.intraday_flatten}"
        )
        snap = ledger.record_trial(
            req.dataset_id,
            trial_key,
            is_port["net_return"].to_numpy(),
            is_sr_val,
            holdout_locked=req.holdout_locked,
        )

        oos_sr: float | None = None
        if not req.holdout_locked and meta.split_time is not None and meta.oos_bars >= 3:
            oos_slice = full_port.filter(pl.col(entry.time_col) >= meta.split_time)
            if oos_slice.height >= 3:
                oos_sr = clean_num(
                    oos_slice.select(pa.sharpe_ratio("net_return", annualization=ann)).item(),
                    0.0,
                    4,
                )

        eval_port = is_port if (req.holdout_locked and meta.split_time is not None) else full_port
        eval_port = eval_port.with_columns(
            (1.0 + pl.col("net_return")).cum_prod().alias("equity_curve"),
            (1.0 + pl.col("gross_return")).cum_prod().alias("gross_equity"),
            (1.0 + pl.col("asset_return")).cum_prod().alias("benchmark_equity"),
        ).with_columns(
            pa.drawdown_series(pl.col("equity_curve"), is_returns=False).alias("drawdown")
        )

        sym_col = entry.symbol_col
        avail_syms: list[str] = []
        active_sym: str | None = None
        sym_adf = pos_frame.asset_df
        if sym_col and sym_col in sym_adf.columns:
            avail_syms = sorted(str(x) for x in sym_adf[sym_col].drop_nulls().unique().to_list())[
                :200
            ]
            active_sym = (
                req.symbol
                if (req.symbol in avail_syms)
                else (avail_syms[0] if avail_syms else None)
            )
            if active_sym is not None:
                sym_adf = sym_adf.filter(pl.col(sym_col) == active_sym)

        if req.holdout_locked and meta.split_time is not None:
            sym_adf = sym_adf.filter(pl.col(entry.time_col) < meta.split_time)

        sym_endo = (
            pl.col("_cs_half_rate")
            if req.slippage_mode == "corwin_schultz"
            else (pl.col("_ami_half_rate") if req.slippage_mode == "amihud" else pl.lit(0.0))
        )
        sym_bt = sym_adf.with_columns(
            (pl.col("turnover") * (base_rate + sym_endo)).alias("cost")
        ).with_columns((pl.col("gross_return") - pl.col("cost")).alias("net_return"))

        price_col = "open" if req.execution_price == "open" else "close"
        trades_df = pa.extract_trades(sym_bt, price_col=price_col, time_col=entry.time_col)

        metrics = compute_portfolio_metrics(eval_port, trades_df, ann, oos_sr, snap)
        cost_curve = compute_cost_curve(eval_port, ann)

        tot_to = float(eval_port["turnover"].sum() or 0.0)
        tot_cost = float(eval_port["cost"].sum() or 0.0)
        eff_tot_bps = (
            (tot_cost / tot_to * 10_000.0) if tot_to > 1e-12 else (req.fee_bps + req.slippage_bps)
        )
        eff_slip_bps = round(max(0.0, eff_tot_bps - req.fee_bps), 2)

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return BacktestRunResponse(
            dataset_id=req.dataset_id,
            formula=req.formula,
            normalized_formula=plan.normalized_formula,
            elapsed_ms=elapsed_ms,
            signal_cache_hit=sig_hit,
            position_cache_hit=pos_hit,
            active_symbol=active_sym,
            available_symbols=avail_syms,
            holdout_locked=req.holdout_locked,
            is_bars=meta.is_bars,
            oos_bars=meta.oos_bars,
            oos_start_time=str(meta.split_time) if meta.split_time is not None else None,
            annualization_used=ann,
            effective_slippage_bps_mean=eff_slip_bps,
            notes=pos_frame.notes,
            metrics=metrics,
            equity_series=serialize_equity(eval_port, entry.time_col, meta.split_time),
            cost_curve=cost_curve,
            chart_series=serialize_candles(sym_bt, entry.time_col, req.chart_bars),
            trades=serialize_trades(trades_df, active_sym, req.max_trades),
            trial_ledger=snap,
        )
