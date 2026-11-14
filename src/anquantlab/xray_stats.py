"""Per-stage distribution, quantile monotonicity, sector tilt, turnover, and NW IC evaluator."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import polars_anta as pa

from .xray_basis import DECAY_HORIZONS, DatasetFactorBasis, clean_num
from .xray_schemas import (
    IcDecayPoint,
    IcSeriesPoint,
    QuantileBucket,
    SectorExposureItem,
    XRayStageReport,
)


def _newey_west_corr(
    x: np.ndarray, y: np.ndarray, *, spearman: bool, max_lag: int
) -> tuple[float, float]:
    mask = np.isfinite(x) & np.isfinite(y)
    xv, yv = x[mask], y[mask]
    n = xv.size
    if n < 8:
        return 0.0, 0.0
    if spearman:
        xv = np.argsort(np.argsort(xv)).astype(np.float64)
        yv = np.argsort(np.argsort(yv)).astype(np.float64)
    sx, sy = float(np.std(xv)), float(np.std(yv))
    if sx <= 1e-12 or sy <= 1e-12:
        return 0.0, 0.0
    zx = (xv - float(np.mean(xv))) / sx
    zy = (yv - float(np.mean(yv))) / sy
    prod = zx * zy
    rho = float(np.mean(prod))
    centered = prod - rho
    lag = max(1, min(max_lag, int(4.0 * ((n / 100.0) ** (2.0 / 9.0))), n // 4))
    lrv = float(np.dot(centered, centered)) / n
    for k in range(1, lag + 1):
        cov_k = float(np.dot(centered[k:], centered[:-k])) / n
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * cov_k
    se = math.sqrt(max(lrv, 1e-15) / n)
    return rho, (rho / se if se > 1e-12 else 0.0)


def _compute_quantiles(
    valid_ic_df: pl.DataFrame,
    col: str,
    fwd_col: str,
    basis: DatasetFactorBasis,
    time_col: str,
    ic_horizon: int,
) -> tuple[list[QuantileBucket], float, float, float]:
    q_gb = time_col if (basis.is_panel and basis.n_symbols >= 5) else None
    try:
        qa = pa.quantile_analysis(
            valid_ic_df,
            factor_col=col,
            return_col=fwd_col,
            quantiles=5,
            group_by=q_gb,
            annualization=basis.annualization / max(1, ic_horizon),
        ).sort("quantile")
    except Exception:
        return [], 0.0, 0.0, 0.0

    buckets = [
        QuantileBucket(
            quantile=int(r["quantile"]),
            count=int(r["count"]),
            mean_factor=clean_num(r["mean_factor"], 0.0, 4),
            mean_return_bps=clean_num(float(r["mean_return"]) * 10_000.0, 0.0, 2),
            sharpe_ratio=clean_num(r["sharpe_ratio"], 0.0, 3),
            win_rate=clean_num(r["win_rate"], 0.0, 4),
            cumulative_return=clean_num(r["cumulative_return"], 0.0, 4),
        )
        for r in qa.to_dicts()
    ]
    if len(buckets) < 2:
        return buckets, 0.0, 0.0, 0.0

    top_bot_bps = round(buckets[-1].mean_return_bps - buckets[0].mean_return_bps, 2)
    ls_sharpe = round(0.5 * (buckets[-1].sharpe_ratio - buckets[0].sharpe_ratio), 3)
    ranks = np.argsort(np.argsort([q.mean_return_bps for q in buckets])) + 1
    k = len(buckets)
    d2 = float(np.sum((np.arange(1, k + 1) - ranks) ** 2))
    mono = round(1.0 - (6.0 * d2) / max(1, k * (k * k - 1)), 4)
    return buckets, top_bot_bps, ls_sharpe, mono


def _compute_sector_tilts(
    eval_df: pl.DataFrame, col: str, time_col: str, symbol_col: str | None, sector_col: str
) -> tuple[list[SectorExposureItem], float]:
    sec_df = eval_df.filter(pl.col(col).is_not_null() & pl.col(sector_col).is_not_null())
    if sec_df.height == 0:
        return [], 0.0
    sec_df = sec_df.with_columns((pl.col(col) - pl.col(col).mean().over(time_col)).alias("_c"))
    sec_df = sec_df.with_columns(
        pl.when(pl.col("_c").abs().sum().over(time_col) > 1e-12)
        .then(pl.col("_c") / pl.col("_c").abs().sum().over(time_col))
        .otherwise(0.0)
        .alias("_w")
    )
    cnt_expr = pl.col(symbol_col).n_unique() if symbol_col else pl.len()
    agg_sec = (
        sec_df.group_by([time_col, sector_col])
        .agg(
            pl.col("_w").sum().alias("_net_w"),
            pl.col("_w").abs().sum().alias("_gross_w"),
            pl.col(col).mean().alias("_mean_s"),
            cnt_expr.alias("_cnt"),
        )
        .group_by(sector_col)
        .agg(
            pl.col("_net_w").mean().alias("net_exposure"),
            pl.col("_gross_w").mean().alias("gross_share"),
            pl.col("_mean_s").mean().alias("mean_signal"),
            pl.col("_cnt").max().alias("ticker_count"),
        )
        .sort(sector_col)
    )
    items: list[SectorExposureItem] = []
    max_tilt = 0.0
    for r in agg_sec.to_dicts():
        ne = clean_num(r["net_exposure"], 0.0, 5)
        max_tilt = max(max_tilt, abs(ne))
        items.append(
            SectorExposureItem(
                sector=str(r[sector_col]),
                ticker_count=int(r["ticker_count"] or 0),
                net_exposure=ne,
                mean_signal=clean_num(r["mean_signal"], 0.0, 4),
                gross_share=clean_num(r["gross_share"], 0.0, 4),
            )
        )
    return items, round(max_tilt, 5)


def evaluate_stage_report(
    df: pl.DataFrame,
    *,
    stage_id: str,
    label: str,
    formula_preview: str,
    col: str,
    basis: DatasetFactorBasis,
    time_col: str,
    symbol_col: str | None,
    sector_col: str | None,
    ic_horizon: int,
    ic_method: str,
    holdout_locked: bool,
) -> XRayStageReport:
    """Compute distribution, quantile monotonicity, sector tilt, turnover, and NW IC."""
    eval_df = df.filter(pl.col("_t_idx") < basis.split_idx) if holdout_locked else df
    arr = eval_df[col].drop_nulls().drop_nans().to_numpy()
    valid_count = int(arr.size)
    if valid_count == 0:
        return XRayStageReport(
            stage_id=stage_id,  # type: ignore[arg-type]
            label=label,
            formula_preview=formula_preview,
        )

    mean_v, std_v = float(np.mean(arr)), float(np.std(arr))
    q05, q25, med, q75, q95 = [float(x) for x in np.quantile(arr, [0.05, 0.25, 0.50, 0.75, 0.95])]
    min_v, max_v = float(np.min(arr)), float(np.max(arr))
    if std_v > 1e-12:
        z = (arr - mean_v) / std_v
        skew_v, kurt_v = float(np.mean(z**3)), float(np.mean(z**4) - 3.0)
    else:
        skew_v, kurt_v = 0.0, 0.0

    lo_h, hi_h = float(np.quantile(arr, 0.01)), float(np.quantile(arr, 0.99))
    if hi_h - lo_h <= 1e-9:
        lo_h, hi_h = min_v - 0.5, max_v + 0.5
    counts_np, edges_np = np.histogram(np.clip(arr, lo_h, hi_h), bins=24, range=(lo_h, hi_h))

    fwd_col = f"_fwd_{ic_horizon}"
    if fwd_col not in df.columns:
        over_sym = (
            (lambda e: e.over(symbol_col))
            if (symbol_col and basis.n_symbols > 1)
            else (lambda e: e)
        )
        df = df.with_columns(
            over_sym(pl.col("close").shift(-ic_horizon) / pl.col("close") - 1.0).alias(fwd_col)
        )
    ic_slice = (
        df.filter((pl.col("_t_idx") + ic_horizon) < basis.split_idx) if holdout_locked else df
    )
    valid_ic_df = ic_slice.filter(
        pl.col(col).is_not_null()
        & pl.col(col).is_finite()
        & pl.col(fwd_col).is_not_null()
        & pl.col(fwd_col).is_finite()
    )

    if std_v > 1e-11 and valid_ic_df.height >= 15:
        quantiles_out, top_bot_bps, ls_sharpe, mono = _compute_quantiles(
            valid_ic_df, col, fwd_col, basis, time_col, ic_horizon
        )
    else:
        quantiles_out, top_bot_bps, ls_sharpe, mono = [], 0.0, 0.0, 0.0

    ic_mean, ic_std, icir, nw_t, hit_rate, n_per = 0.0, 0.0, 0.0, 0.0, 0.0, 0
    ic_series_out: list[IcSeriesPoint] = []
    decay_out: list[IcDecayPoint] = []
    spearman = ic_method == "spearman"

    if std_v > 1e-11 and valid_ic_df.height >= 12:
        if basis.is_panel:
            ics = pa.ic_summary(
                valid_ic_df,
                factor_col=col,
                return_col=fwd_col,
                group_by=time_col,
                method=ic_method,  # type: ignore[arg-type]
                nw_lags=max(1, ic_horizon),
            )
            ic_mean = clean_num(ics.get("ic_mean"), 0.0, 5)
            ic_std = clean_num(ics.get("ic_std"), 0.0, 5)
            icir = clean_num(ics.get("icir"), 0.0, 4)
            nw_t = clean_num(ics.get("nw_t_stat"), 0.0, 3)
            hit_rate = clean_num(ics.get("hit_rate"), 0.0, 4)
            n_per = int(ics.get("n_periods", 0) or 0)
            ic_ts = (
                pa.information_coefficient(
                    valid_ic_df,
                    factor_col=col,
                    return_col=fwd_col,
                    group_by=time_col,
                    method=ic_method,  # type: ignore[arg-type]
                )
                .drop_nulls("ic")
                .sort(time_col)
            )
            if ic_ts.height > 0:
                ic_ts = ic_ts.with_columns(
                    pl.col(time_col).cast(pl.String).alias("_ts"),
                    pl.col("ic").cum_sum().alias("_cum"),
                )
                sampled = ic_ts.gather_every(max(1, math.ceil(ic_ts.height / 220)))
                ic_series_out = [
                    IcSeriesPoint(
                        t=r["_ts"],
                        ic=clean_num(r["ic"], 0.0, 4),
                        cum_ic=clean_num(r["_cum"], 0.0, 4),
                    )
                    for r in sampled.to_dicts()
                ]
        else:
            rho, t_val = _newey_west_corr(
                valid_ic_df[col].to_numpy(),
                valid_ic_df[fwd_col].to_numpy(),
                spearman=spearman,
                max_lag=max(2, ic_horizon * 2),
            )
            ic_mean, nw_t, n_per = (
                clean_num(rho, 0.0, 5),
                clean_num(t_val, 0.0, 3),
                valid_ic_df.height,
            )
            s_np, r_np = valid_ic_df[col].to_numpy(), valid_ic_df[fwd_col].to_numpy()
            t_strs = valid_ic_df[time_col].cast(pl.String).to_list()
            win = min(40, max(12, n_per // 6))
            step = max(1, (n_per - win) // 120 + 1)
            roll_ics = [
                (
                    t_strs[i - 1],
                    _newey_west_corr(
                        s_np[i - win : i], r_np[i - win : i], spearman=spearman, max_lag=1
                    )[0],
                )
                for i in range(win, n_per + 1, step)
            ]
            if roll_ics:
                vals = np.asarray([v for _, v in roll_ics], dtype=np.float64)
                ic_std = clean_num(float(np.std(vals)), 0.0, 5)
                icir = clean_num(ic_mean / ic_std if ic_std > 1e-9 else 0.0, 0.0, 4)
                hit_rate = clean_num(float(np.mean(vals > 0.0)), 0.0, 4)
                cum = 0.0
                for ts, cv in roll_ics:
                    cum += cv
                    ic_series_out.append(
                        IcSeriesPoint(t=ts, ic=clean_num(cv, 0.0, 4), cum_ic=clean_num(cum, 0.0, 4))
                    )

        for h in DECAY_HORIZONS:
            fh = f"_fwd_{h}"
            h_df = df.filter((pl.col("_t_idx") + h) < basis.split_idx) if holdout_locked else df
            h_df = h_df.filter(
                pl.col(col).is_not_null()
                & pl.col(col).is_finite()
                & pl.col(fh).is_not_null()
                & pl.col(fh).is_finite()
            )
            if h_df.height < 12:
                continue
            if basis.is_panel:
                hs = pa.ic_summary(
                    h_df,
                    factor_col=col,
                    return_col=fh,
                    group_by=time_col,
                    method=ic_method,
                    nw_lags=max(1, h),  # type: ignore[arg-type]
                )
                decay_out.append(
                    IcDecayPoint(
                        horizon=h,
                        ic_mean=clean_num(hs.get("ic_mean"), 0.0, 5),
                        icir=clean_num(hs.get("icir"), 0.0, 4),
                        nw_t_stat=clean_num(hs.get("nw_t_stat"), 0.0, 3),
                        hit_rate=clean_num(hs.get("hit_rate"), 0.0, 4),
                    )
                )
            else:
                hrho, hnw = _newey_west_corr(
                    h_df[col].to_numpy(), h_df[fh].to_numpy(), spearman=spearman, max_lag=max(2, h)
                )
                decay_out.append(
                    IcDecayPoint(
                        horizon=h,
                        ic_mean=clean_num(hrho, 0.0, 5),
                        icir=0.0,
                        nw_t_stat=clean_num(hnw, 0.0, 3),
                        hit_rate=clean_num(0.5 + 0.5 * float(np.sign(hrho)), 0.5, 4),
                    )
                )

    half_life: float | None = None
    if len(decay_out) >= 3 and abs(decay_out[0].ic_mean) > 0.004:
        hs_arr = np.asarray([d.horizon for d in decay_out], dtype=np.float64)
        abs_ic = np.maximum(1e-5, np.asarray([abs(d.ic_mean) for d in decay_out], dtype=np.float64))
        slope = float(np.polyfit(hs_arr, np.log(abs_ic), 1)[0])
        if slope < -1e-4:
            half_life = round(min(250.0, -math.log(2.0) / slope), 2)

    turnover_mean, rank_ac = 0.0, 0.0
    if std_v > 1e-11:
        if basis.is_panel and symbol_col:
            ft = pa.factor_turnover(
                eval_df.drop_nulls(col), factor_col=col, asset_col=symbol_col, time_col=time_col
            )
            if ft.height > 1:
                ft_tail = ft.slice(1)
                turnover_mean = clean_num(ft_tail["turnover"].mean(), 0.0, 4)
                rank_ac = clean_num(ft_tail["rank_autocorr"].mean(), 0.0, 4)
        elif valid_count >= 5:
            rank_ac = clean_num(float(np.corrcoef(arr[1:], arr[:-1])[0, 1]), 0.0, 4)
            norm_w = (arr - mean_v) / max(float(np.mean(np.abs(arr - mean_v))), 1e-12)
            turnover_mean = clean_num(0.5 * float(np.mean(np.abs(np.diff(norm_w)))), 0.0, 4)

    sector_out, max_tilt = (
        _compute_sector_tilts(eval_df, col, time_col, symbol_col, sector_col)
        if (basis.has_sector and sector_col and std_v > 1e-11)
        else ([], 0.0)
    )

    return XRayStageReport(
        stage_id=stage_id,  # type: ignore[arg-type]
        label=label,
        formula_preview=formula_preview,
        valid_count=valid_count,
        mean=clean_num(mean_v, 0.0, 5),
        std=clean_num(std_v, 0.0, 5),
        skew=clean_num(skew_v, 0.0, 3),
        excess_kurtosis=clean_num(kurt_v, 0.0, 3),
        min=clean_num(min_v, 0.0, 5),
        q05=clean_num(q05, 0.0, 5),
        q25=clean_num(q25, 0.0, 5),
        median=clean_num(med, 0.0, 5),
        q75=clean_num(q75, 0.0, 5),
        q95=clean_num(q95, 0.0, 5),
        max=clean_num(max_v, 0.0, 5),
        hist_edges=[round(float(e), 5) for e in edges_np.tolist()],
        hist_counts=[int(c) for c in counts_np.tolist()],
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        nw_t_stat=nw_t,
        hit_rate=hit_rate,
        n_ic_periods=n_per,
        top_minus_bottom_bps=top_bot_bps,
        ls_sharpe_approx=ls_sharpe,
        quantile_monotonicity=mono,
        turnover_mean=turnover_mean,
        rank_autocorr=rank_ac,
        half_life_bars=half_life,
        max_abs_sector_tilt=max_tilt,
        quantiles=quantiles_out,
        sector_exposures=sector_out,
        ic_decay=decay_out,
        ic_series=ic_series_out,
    )
