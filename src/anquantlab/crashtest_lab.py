"""Small-sample Stationary Bootstrap worlds, CUSUM break, and Tab 3 Crash-Test engine."""

from __future__ import annotations

import math
import time

import numpy as np
import polars_anta as pa

from .backtest_metrics import clean_num
from .crashtest_schemas import (
    BootstrapPathPoint,
    BootstrapWorldsReport,
    CrashTestRunRequest,
    CrashTestRunResponse,
    CusumBreakReport,
    CusumCurvePoint,
)
from .crashtest_stats import build_crashtest_response, compute_sharpe_and_se
from .crashtest_sweep import evaluate_grid_returns
from .store import WorkbenchStore
from .trial_ledger import TrialLedgerRegistry


def build_bootstrap_and_null(
    r_base: np.ndarray, base_sr: float, ann: float, req: CrashTestRunRequest
) -> BootstrapWorldsReport:
    """Generate 200 Stationary Block Bootstrap worlds and 200 Null Block-Rademacher worlds."""
    n_t = r_base.size
    n_boot = int(req.n_bootstrap)
    block_len = max(4, min(max(4, n_t // 3), int(round(max(1.0, float(n_t)) ** (1.0 / 3.0)))))
    if n_t < 8 or float(np.std(r_base)) <= 1e-12:
        return BootstrapWorldsReport(n_worlds=n_boot, mean_block_bars=block_len)

    boot_idx = pa.stationary_bootstrap_indices(
        n_t, n_boot=n_boot, mean_block=float(block_len), seed=req.seed
    )
    boot_rets = r_base[boot_idx]
    b_means = np.mean(boot_rets, axis=1)
    b_stds = np.std(boot_rets, axis=1, ddof=1)
    boot_sr = np.where(b_stds > 1e-12, (b_means / np.maximum(b_stds, 1e-12)) * math.sqrt(ann), 0.0)

    eq_paths = np.cumprod(1.0 + np.clip(boot_rets, -0.95, 5.0), axis=1)
    peaks = np.maximum.accumulate(np.maximum(1.0, eq_paths), axis=1)
    max_dds = np.min((eq_paths - peaks) / peaks, axis=1)

    # Null Permuted World: Stationary Block-Rademacher Sign Permutation
    null_idx = pa.stationary_bootstrap_indices(
        n_t, n_boot=n_boot, mean_block=float(block_len), seed=req.seed + 7919
    )
    new_blk = np.ones((n_boot, n_t), dtype=bool)
    new_blk[:, 1:] = null_idx[:, 1:] != (null_idx[:, :-1] + 1)
    rng_null = np.random.default_rng(req.seed + 104729)
    raw_signs = rng_null.choice(np.array([-1.0, 1.0]), size=(n_boot, n_t))
    col_grid = np.broadcast_to(np.arange(n_t, dtype=np.int64), (n_boot, n_t))
    blk_anchor = np.maximum.accumulate(np.where(new_blk, col_grid, 0), axis=1)
    null_rets = r_base[null_idx] * np.take_along_axis(raw_signs, blk_anchor, axis=1)
    n_means = np.mean(null_rets, axis=1)
    n_stds = np.std(null_rets, axis=1, ddof=1)
    null_sr = np.where(n_stds > 1e-12, (n_means / np.maximum(n_stds, 1e-12)) * math.sqrt(ann), 0.0)
    null_p = float((1 + int(np.sum(null_sr >= base_sr))) / (n_boot + 1))

    lo_s = min(float(np.min(boot_sr)), float(np.percentile(null_sr, 5))) - 0.1
    hi_s = max(float(np.max(boot_sr)), float(np.percentile(null_sr, 95))) + 0.1
    h_cnts, h_edgs = np.histogram(boot_sr, bins=18, range=(lo_s, hi_s))

    real_eq = np.concatenate(([1.0], np.cumprod(1.0 + np.clip(r_base, -0.95, 5.0))))
    full_eq = np.concatenate((np.ones((n_boot, 1), dtype=np.float64), eq_paths), axis=1)
    sample_bars = np.unique(np.linspace(0, n_t, num=min(n_t + 1, 110), dtype=np.int64))
    q_mat = np.percentile(full_eq[:, sample_bars], [10, 25, 50, 75, 90], axis=0)
    fan = [
        BootstrapPathPoint(
            bar=int(b_i),
            p10=clean_num(q_mat[0, j], 1.0, 4),
            p25=clean_num(q_mat[1, j], 1.0, 4),
            p50=clean_num(q_mat[2, j], 1.0, 4),
            p75=clean_num(q_mat[3, j], 1.0, 4),
            p90=clean_num(q_mat[4, j], 1.0, 4),
            realized=clean_num(real_eq[b_i], 1.0, 4),
        )
        for j, b_i in enumerate(sample_bars.tolist())
    ]
    pcts = np.percentile(boot_sr, [5, 25, 50, 75, 95])
    return BootstrapWorldsReport(
        n_worlds=n_boot,
        mean_block_bars=block_len,
        sharpe_p05=clean_num(pcts[0], 0.0, 3),
        sharpe_p25=clean_num(pcts[1], 0.0, 3),
        sharpe_median=clean_num(pcts[2], 0.0, 3),
        sharpe_p75=clean_num(pcts[3], 0.0, 3),
        sharpe_p95=clean_num(pcts[4], 0.0, 3),
        prob_positive_world=clean_num(float(np.mean(boot_sr > 0.0)), 0.0, 4),
        max_dd_median=clean_num(float(np.median(max_dds)), 0.0, 4),
        max_dd_p95_worst=clean_num(float(np.percentile(max_dds, 5)), 0.0, 4),
        null_sharpe_95=clean_num(float(np.percentile(null_sr, 95)), 0.0, 3),
        null_p_value=clean_num(null_p, 1.0, 4),
        sharpe_hist_edges=[clean_num(v, 0.0, 3) for v in h_edgs.tolist()],
        sharpe_hist_counts=[int(c) for c in h_cnts.tolist()],
        fan_chart=fan,
    )


def build_cusum_break(r_base: np.ndarray, times_is: list[str]) -> CusumBreakReport:
    """Compute Ploberger-Kramer OLS-CUSUM structural break test & scaled Brownian bridge."""
    n_t = r_base.size
    if n_t < 10 or float(np.std(r_base)) <= 1e-12:
        return CusumBreakReport(
            statistic=0.0,
            p_value=1.0,
            has_break=False,
            break_index=0,
            break_time=times_is[0] if times_is else None,
            mean_before_bps=0.0,
            mean_after_bps=0.0,
        )
    cs = pa.cusum_mean_test(r_base)
    stat = float(cs["statistic"])
    p_val = float(cs["p_value"])
    brk = max(0, min(n_t - 1, int(round(cs["break_index"]))))
    cum_e = np.cumsum(r_base - float(np.mean(r_base)))
    max_raw = float(np.max(np.abs(cum_e)))
    bridge = cum_e * (stat / max_raw) if (stat > 0.0 and max_raw > 1e-15) else np.zeros(n_t)

    idx_arr = np.unique(np.append(np.linspace(0, n_t - 1, num=min(n_t, 160), dtype=np.int64), brk))
    idx_arr.sort()
    pts = [
        CusumCurvePoint(t=times_is[int(i)], stat=clean_num(bridge[int(i)], 0.0, 4))
        for i in idx_arr.tolist()
    ]
    return CusumBreakReport(
        statistic=clean_num(stat, 0.0, 4),
        p_value=clean_num(p_val, 1.0, 4),
        has_break=bool(p_val < 0.05),
        break_index=brk,
        break_time=times_is[brk] if brk < len(times_is) else None,
        mean_before_bps=clean_num(cs["mean_before"] * 1e4, 0.0, 2),
        mean_after_bps=clean_num(cs["mean_after"] * 1e4, 0.0, 2),
        bridge_series=pts,
    )


class CrashTestLabEngine:
    """Executes 2D parameter sweeps, updates Session Trial Ledger, and runs Crash-Test inference."""

    def run(
        self,
        store: WorkbenchStore,
        trial_ledger: TrialLedgerRegistry,
        req: CrashTestRunRequest,
    ) -> CrashTestRunResponse:
        t0 = time.perf_counter()
        entry, _ = store.get_frame(req.dataset_id)
        bundle = evaluate_grid_returns(store, req)

        ledger_mat = bundle.ret_matrix_ledger_is
        ann = bundle.meta.annualization
        n_is = ledger_mat.shape[0]
        if n_is > 1:
            means = np.mean(ledger_mat, axis=0)
            stds = np.std(ledger_mat, axis=0, ddof=1)
            is_sharpes = np.where(
                stds > 1e-12, (means / np.maximum(stds, 1e-12)) * math.sqrt(ann), 0.0
            )
        else:
            is_sharpes = np.zeros(len(bundle.specs), dtype=np.float64)

        snap = trial_ledger.get_snapshot(req.dataset_id)
        for k_idx, sp in enumerate(bundle.specs):
            t_key = (
                f"ct|{sp.formula}|ema={sp.ema_span}|buf={sp.no_trade_buffer:.4f}|"
                f"{req.weight_scheme}|fee={req.fee_bps:.1f}|"
                f"slip={req.slippage_mode}:{req.slippage_bps:.1f}|delist={req.delisting_penalty_bps_yr:.1f}"
            )
            snap = trial_ledger.record_trial(
                req.dataset_id,
                t_key,
                ledger_mat[:, k_idx],
                float(is_sharpes[k_idx]),
                holdout_locked=req.holdout_locked,
            )

        sharpes, tot_rets, ses = compute_sharpe_and_se(bundle.ret_matrix_is, ann)
        g = int(req.grid_size)
        base_idx = bundle.baseline_row * g + bundle.baseline_col
        r_base = bundle.ret_matrix_is[:, base_idx]
        bootstrap = build_bootstrap_and_null(r_base, float(sharpes[base_idx]), ann, req)
        cusum = build_cusum_break(r_base, bundle.times_is)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return build_crashtest_response(
            entry, bundle, req, snap, bootstrap, cusum, sharpes, tot_rets, ses, elapsed_ms
        )
