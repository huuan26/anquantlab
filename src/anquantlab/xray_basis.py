"""Causal 5-factor OHLCV benchmark basis and Driscoll-Kraay Spanning R^2 solver."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
import polars_anta as pa

from .backtest_metrics import _infer_annualization_and_session
from .xray_schemas import (
    CanonicalFactorKey,
    FactorLoadingItem,
    SpanningCheckReport,
    XRayStageReport,
)

DECAY_HORIZONS: tuple[int, ...] = (1, 2, 5, 10, 20)

FACTOR_SPECS: tuple[tuple[CanonicalFactorKey, str, str], ...] = (
    ("mom_20", "Momentum (20b)", "_f_mom_20"),
    ("rev_5", "Short Reversal (5b)", "_f_rev_5"),
    ("yz_vol_20", "Yang-Zhang Vol (20b)", "_f_yz_vol_20"),
    ("amihud_20", "Amihud Illiq (20b)", "_f_amihud_20"),
    ("mkt_beta_60", "Market Beta (60b)", "_f_mkt_beta_60"),
)


@dataclass
class DatasetFactorBasis:
    is_panel: bool
    has_sector: bool
    n_symbols: int
    split_idx: int
    is_bars: int
    oos_bars: int
    annualization: float
    basis_df: pl.DataFrame


def clean_num(val: Any, default: float = 0.0, digits: int = 6) -> float:
    if val is None:
        return default
    f = float(val)
    return round(f, digits) if math.isfinite(f) else default


def build_factor_basis(
    df: pl.DataFrame,
    time_col: str,
    symbol_col: str | None,
    sector_col: str | None,
) -> DatasetFactorBasis:
    """Build strictly causal 5-factor OHLCV benchmark basis and horizon returns."""
    sort_cols = [symbol_col, time_col] if symbol_col else [time_col]
    work = df.sort(sort_cols)

    u_times = work.select(pl.col(time_col).drop_nulls().unique().sort()).with_row_index("_t_idx")
    n_u = u_times.height
    split_idx = max(2, min(n_u - 1, int(round(0.75 * n_u)))) if n_u >= 8 else n_u
    is_bars = split_idx
    oos_bars = max(0, n_u - split_idx)
    ann, _ = _infer_annualization_and_session(work, time_col, symbol_col)

    n_symbols = int(work[symbol_col].drop_nulls().n_unique()) if symbol_col else 1
    is_panel = n_symbols >= 3
    has_sector = bool(
        sector_col
        and sector_col in work.columns
        and int(work[sector_col].drop_nulls().n_unique()) >= 2
    )

    work = work.join(u_times, on=time_col, how="left")
    over_sym = (lambda e: e.over(symbol_col)) if (symbol_col and n_symbols > 1) else (lambda e: e)

    max_sym_bars = int(work.group_by(symbol_col).len()["len"].max() or 0) if symbol_col else n_u
    p_mom = min(20, max(3, max_sym_bars // 4))
    p_rev = min(5, max(2, max_sym_bars // 8))
    p_beta = min(60, max(10, max_sym_bars // 3))

    work = work.with_columns(
        over_sym(pl.col("close") / pl.col("close").shift(1) - 1.0).alias("_ret1"),
        over_sym(pl.col("close") / pl.col("close").shift(p_mom) - 1.0).alias("_f_mom_20"),
        over_sym(-(pl.col("close") / pl.col("close").shift(p_rev) - 1.0)).alias("_f_rev_5"),
        over_sym(pa.yang_zhang_volatility("open", "high", "low", "close", period=p_mom)).alias(
            "_f_yz_vol_20"
        ),
        over_sym(pa.amihud_illiquidity("close", "volume", period=p_mom).log1p()).alias(
            "_f_amihud_20"
        ),
    )

    f_cols = [spec[2] for spec in FACTOR_SPECS]
    if is_panel:
        work = work.with_columns(pl.col("_ret1").mean().over(time_col).alias("_mkt_ret1"))
        work = work.with_columns(
            (
                over_sym(pl.rolling_cov("_ret1", "_mkt_ret1", window_size=p_beta))
                / (over_sym(pl.col("_mkt_ret1").rolling_var(window_size=p_beta)) + 1e-12)
            ).alias("_f_mkt_beta_60")
        )
        work = work.with_columns(
            [
                pa.cs_winsorize(c, over=time_col, method="quantile", lower=0.02, upper=0.98).alias(
                    c
                )
                for c in f_cols
            ]
        )
        work = work.with_columns(
            [pa.cs_zscore(c, over=time_col).fill_nan(0.0).fill_null(0.0).alias(c) for c in f_cols]
        )
    else:
        work = work.with_columns(
            over_sym(pa.linear_regression_slope("close", period=p_beta) / pl.col("close")).alias(
                "_f_mkt_beta_60"
            )
        )
        win_z = min(120, max(12, max_sym_bars // 2))
        work = work.with_columns(
            [
                over_sym(
                    (
                        (pl.col(c) - pl.col(c).rolling_mean(win_z, min_samples=5))
                        / (pl.col(c).rolling_std(win_z, min_samples=5) + 1e-12)
                    ).clip(-4.0, 4.0)
                )
                .fill_nan(0.0)
                .fill_null(0.0)
                .alias(c)
                for c in f_cols
            ]
        )

    fwd_exprs = [
        over_sym(pl.col("close").shift(-h) / pl.col("close") - 1.0).alias(f"_fwd_{h}")
        for h in DECAY_HORIZONS
    ]
    keep_cols = [time_col, "_t_idx", *f_cols]
    if symbol_col and symbol_col in work.columns:
        keep_cols.append(symbol_col)
    if sector_col and sector_col in work.columns:
        keep_cols.append(sector_col)
    basis_df = work.with_columns(fwd_exprs).select(
        [*keep_cols, *[f"_fwd_{h}" for h in DECAY_HORIZONS]]
    )
    return DatasetFactorBasis(
        is_panel=is_panel,
        has_sector=has_sector,
        n_symbols=n_symbols,
        split_idx=split_idx,
        is_bars=is_bars,
        oos_bars=oos_bars,
        annualization=ann,
        basis_df=basis_df,
    )


def compute_spanning_decomposition(
    df: pl.DataFrame,
    *,
    basis: DatasetFactorBasis,
    pre_col: str,
    post_col: str,
    selected_keys: set[CanonicalFactorKey],
    pre_stage: XRayStageReport,
    post_stage: XRayStageReport,
    holdout_locked: bool,
) -> SpanningCheckReport:
    """Solve multivariate 5-factor spanning OLS with Driscoll-Kraay Newey-West t-stats."""
    eval_df = df.filter(pl.col("_t_idx") < basis.split_idx) if holdout_locked else df
    sub = eval_df.filter(pl.col(pre_col).is_not_null() & pl.col(pre_col).is_finite())
    f_cols = [spec[2] for spec in FACTOR_SPECS]

    if sub.height < 12:
        return SpanningCheckReport(
            spanning_r2=0.0,
            selected_r2=0.0,
            orthogonal_share=1.0,
            pre_ortho_icir=pre_stage.icir,
            post_ortho_icir=post_stage.icir,
            pre_ortho_nw_t=pre_stage.nw_t_stat,
            post_ortho_nw_t=post_stage.nw_t_stat,
            pre_ortho_ls_sharpe=pre_stage.ls_sharpe_approx,
            post_ortho_ls_sharpe=post_stage.ls_sharpe_approx,
            verdict="NOISE_SIGNAL",
            verdict_summary="Insufficient non-null observations for 5-factor spanning regression.",
            loadings=[],
        )

    y_raw = sub[pre_col].to_numpy().astype(np.float64)
    sy = float(np.std(y_raw))
    if sy <= 1e-11:
        return SpanningCheckReport(
            spanning_r2=0.0,
            selected_r2=0.0,
            orthogonal_share=1.0,
            pre_ortho_icir=0.0,
            post_ortho_icir=0.0,
            pre_ortho_nw_t=0.0,
            post_ortho_nw_t=0.0,
            pre_ortho_ls_sharpe=0.0,
            post_ortho_ls_sharpe=0.0,
            verdict="NOISE_SIGNAL",
            verdict_summary="Pre-orthogonalized signal has near-zero variance.",
            loadings=[],
        )

    y = (y_raw - float(np.mean(y_raw))) / sy
    k = len(f_cols)
    x_mat = np.column_stack([sub[c].to_numpy().astype(np.float64) for c in f_cols])
    x_mat = np.nan_to_num(x_mat, nan=0.0, posinf=0.0, neginf=0.0)
    for j in range(k):
        sj = float(np.std(x_mat[:, j]))
        x_mat[:, j] = (x_mat[:, j] - float(np.mean(x_mat[:, j]))) / sj if sj > 1e-11 else 0.0

    n_obs = float(y.size)
    xtx = (x_mat.T @ x_mat) + 1e-6 * np.eye(k)
    xty = x_mat.T @ y
    beta = np.linalg.solve(xtx, xty)
    resid = y - (x_mat @ beta)
    r2_all = float(np.clip(1.0 - float(np.dot(resid, resid)) / max(n_obs, 1.0), 0.0, 1.0))

    sel_idx = [i for i, spec in enumerate(FACTOR_SPECS) if spec[0] in selected_keys]
    if sel_idx:
        xs = x_mat[:, sel_idx]
        bs = np.linalg.solve((xs.T @ xs) + 1e-6 * np.eye(len(sel_idx)), xs.T @ y)
        rs = y - (xs @ bs)
        r2_sel = float(np.clip(1.0 - float(np.dot(rs, rs)) / max(n_obs, 1.0), 0.0, 1.0))
    else:
        r2_sel = 0.0

    # Time-clustered Driscoll-Kraay / Newey-West HAC covariance
    t_arr = sub["_t_idx"].to_numpy()
    _, inv = np.unique(t_arr, return_inverse=True)
    n_t = int(inv.max()) + 1 if inv.size > 0 else 1
    scores = np.zeros((n_t, k), dtype=np.float64)
    np.add.at(scores, inv, x_mat * resid[:, None])
    lag = max(1, min(8, int(4.0 * ((n_t / 100.0) ** (2.0 / 9.0))), max(1, n_t // 4)))
    meat = scores.T @ scores
    for ell in range(1, lag + 1):
        if n_t > ell:
            w = 1.0 - ell / (lag + 1.0)
            cross = scores[ell:].T @ scores[:-ell]
            meat = meat + w * (cross + cross.T)
    xtx_inv = np.linalg.inv(xtx)
    cov_beta = xtx_inv @ meat @ xtx_inv
    se_beta = np.sqrt(np.maximum(np.diag(cov_beta), 1e-18))
    nw_t_vec = beta / se_beta

    post_arr = np.nan_to_num(
        sub[post_col].to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
    sp = float(np.std(post_arr))
    zp = (post_arr - float(np.mean(post_arr))) / sp if sp > 1e-11 else np.zeros_like(y)

    loadings: list[FactorLoadingItem] = []
    for j, (fkey, flabel, _) in enumerate(FACTOR_SPECS):
        lbl = "Trend Slope (60b)" if (fkey == "mkt_beta_60" and not basis.is_panel) else flabel
        marg_c = float(np.dot(y, x_mat[:, j])) / max(n_obs, 1.0)
        post_c = float(np.dot(zp, x_mat[:, j])) / max(n_obs, 1.0) if sp > 1e-11 else 0.0
        pratt = max(0.0, float(beta[j] * marg_c))
        loadings.append(
            FactorLoadingItem(
                factor_key=fkey,
                factor_label=lbl,
                selected=(fkey in selected_keys),
                beta=clean_num(beta[j], 0.0, 4),
                nw_t_stat=clean_num(nw_t_vec[j], 0.0, 2),
                marginal_corr=clean_num(marg_c, 0.0, 4),
                r2_contribution=clean_num(min(1.0, pratt), 0.0, 4),
                post_ortho_corr=clean_num(post_c, 0.0, 5),
            )
        )

    orth_share = round(1.0 - r2_all, 4)
    if r2_all >= 0.65:
        verdict = "FACTOR_CLONE"
        summary = (
            f"Redundancy alert: {r2_all * 100:.1f}% of signal variance is spanned by "
            f"the 5 classic free OHLCV factors ({orth_share * 100:.1f}% orthogonal)."
        )
    elif abs(post_stage.nw_t_stat) >= 1.96 and orth_share >= 0.50:
        verdict = "DISTINCT_ALPHA"
        summary = (
            f"Distinct orthogonal signal: {orth_share * 100:.1f}% novel variance with "
            f"post-orthogonalization NW t = {post_stage.nw_t_stat:+.2f}."
        )
    elif r2_all >= 0.30 or abs(post_stage.nw_t_stat) >= 1.20:
        verdict = "PARTIAL_OVERLAP"
        summary = (
            f"Partial factor overlap ({r2_all * 100:.1f}% spanned, {orth_share * 100:.1f}% pure); "
            f"residual NW t = {post_stage.nw_t_stat:+.2f}."
        )
    else:
        verdict = "NOISE_SIGNAL"
        summary = (
            f"Low classic factor overlap ({r2_all * 100:.1f}%), but residual predictive IC "
            f"is statistically weak (NW t = {post_stage.nw_t_stat:+.2f})."
        )

    return SpanningCheckReport(
        spanning_r2=round(r2_all, 4),
        selected_r2=round(r2_sel, 4),
        orthogonal_share=orth_share,
        pre_ortho_icir=pre_stage.icir,
        post_ortho_icir=post_stage.icir,
        pre_ortho_nw_t=pre_stage.nw_t_stat,
        post_ortho_nw_t=post_stage.nw_t_stat,
        pre_ortho_ls_sharpe=pre_stage.ls_sharpe_approx,
        post_ortho_ls_sharpe=post_stage.ls_sharpe_approx,
        verdict=verdict,  # type: ignore[arg-type]
        verdict_summary=summary,
        loadings=loadings,
    )
