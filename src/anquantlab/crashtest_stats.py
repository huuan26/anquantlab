"""Multiple-testing grid falsification (Heatmap, CSCV PBO, DSR, EB, Romano-Wolf) for Tab 3."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import polars as pl
import polars_anta as pa

from .backtest_metrics import clean_num
from .crashtest_schemas import (
    BootstrapWorldsReport,
    CrashTestCandidateRow,
    CrashTestRunRequest,
    CrashTestRunResponse,
    CusumBreakReport,
    FunnelStageItem,
    HaircutBar,
    HeatmapGridReport,
    PboReport,
    PboScatterPoint,
)
from .crashtest_sweep import GridSweepBundle
from .schemas import TrialLedgerSnapshot
from .store import DatasetEntry

_STD_NORM = NormalDist(0.0, 1.0)
_EULER_GAMMA = 0.5772156649015329


def _benjamini_hochberg(p_vals: np.ndarray) -> np.ndarray:
    k = p_vals.size
    if k == 0:
        return np.zeros(0, dtype=np.float64)
    clean_p = np.clip(np.nan_to_num(p_vals, nan=1.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
    order = np.argsort(clean_p)
    ranks = np.arange(1, k + 1, dtype=np.float64)
    q_sorted = np.minimum.accumulate(((k / ranks) * clean_p[order])[::-1])[::-1]
    q_out = np.empty(k, dtype=np.float64)
    q_out[order] = np.clip(q_sorted, 0.0, 1.0)
    return q_out


def compute_sharpe_and_se(
    ret_mat: np.ndarray, ann: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized annualized Sharpe, total return, and Mertens non-normal Sharpe SE."""
    n_t, k = ret_mat.shape
    if n_t < 2 or k == 0:
        z = np.zeros(k, dtype=np.float64)
        return z, z, np.ones(k, dtype=np.float64)

    tot_rets = np.prod(1.0 + np.clip(ret_mat, -0.95, 5.0), axis=0) - 1.0
    means = np.mean(ret_mat, axis=0)
    stds = np.std(ret_mat, axis=0, ddof=1)
    active = stds > 1e-12
    safe_stds = np.where(active, stds, 1.0)
    sr_per = np.where(active, means / safe_stds, 0.0)
    sharpes = sr_per * math.sqrt(ann)

    z_scores = np.where(active[None, :], (ret_mat - means[None, :]) / safe_stds[None, :], 0.0)
    skew = np.mean(z_scores**3, axis=0)
    kurt = np.where(active, np.mean(z_scores**4, axis=0), 3.0)
    var_adj = np.maximum(0.05, 1.0 - skew * sr_per + 0.25 * (kurt - 1.0) * (sr_per**2))
    ses = np.sqrt(var_adj * (ann / max(2.0, float(n_t - 1))))
    return sharpes, tot_rets, ses


def _expected_max_null_sr(n_eff: float, sr_std: float) -> float:
    if n_eff <= 1.05 or sr_std <= 1e-9:
        return 0.0
    p1 = max(0.5, min(0.999999, 1.0 - 1.0 / n_eff))
    p2 = max(0.5, min(0.999999, 1.0 - 1.0 / (n_eff * math.e)))
    z_max = (1.0 - _EULER_GAMMA) * _STD_NORM.inv_cdf(p1) + _EULER_GAMMA * _STD_NORM.inv_cdf(p2)
    return max(0.0, float(sr_std * z_max))


def _build_heatmap(
    bundle: GridSweepBundle, sharpes: np.ndarray, tot_rets: np.ndarray, g: int
) -> tuple[HeatmapGridReport, int, int]:
    sr_2d = sharpes.reshape((g, g))
    ret_2d = tot_rets.reshape((g, g))
    base_idx = bundle.baseline_row * g + bundle.baseline_col
    best_idx = int(np.argmax(sharpes))
    br, bc = divmod(best_idx, g)
    best_sr = float(sharpes[best_idx])

    neigh = [
        float(sr_2d[br + dr, bc + dc])
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr != 0 or dc != 0) and 0 <= br + dr < g and 0 <= bc + dc < g
    ]
    plateau = (
        float(np.clip(np.mean(neigh) / max(abs(best_sr), 0.15), -1.0, 1.5))
        if (neigh and best_sr > 1e-6)
        else 0.0
    )
    report = HeatmapGridReport(
        x_name=bundle.x_name,
        y_name=bundle.y_name,
        x_labels=bundle.x_labels,
        y_labels=bundle.y_labels,
        sharpe_matrix=[[clean_num(v, 0.0, 3) for v in row] for row in sr_2d.tolist()],
        return_matrix=[[clean_num(v, 0.0, 4) for v in row] for row in ret_2d.tolist()],
        baseline_row=bundle.baseline_row,
        baseline_col=bundle.baseline_col,
        baseline_sharpe=clean_num(sharpes[base_idx], 0.0, 3),
        best_sharpe=clean_num(best_sr, 0.0, 3),
        median_sharpe=clean_num(float(np.median(sharpes)), 0.0, 3),
        neighbor_plateau_ratio=clean_num(plateau, 0.0, 3),
        positive_grid_share=clean_num(float(np.mean(sharpes > 0.0)), 0.0, 4),
    )
    return report, base_idx, best_idx


def _build_pbo(ret_mat: np.ndarray, ann: float, req: CrashTestRunRequest) -> PboReport:
    n_t, k = ret_mat.shape
    if n_t < 16 or k < 2 or float(np.std(ret_mat)) <= 1e-12:
        return PboReport(pbo=0.5, prob_oos_loss=0.5, degradation_slope=0.0, n_combinations=0)

    s_splits = min(int(req.cscv_splits), max(4, (n_t // 6) * 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = pa.pbo_cscv(ret_mat, n_splits=s_splits, max_combinations=8000, seed=req.seed)

    logits = np.asarray(raw["logits"], dtype=np.float64)
    finite_logits = np.clip(logits[np.isfinite(logits)], -8.0, 8.0)
    if finite_logits.size >= 2:
        lo_e = min(-2.0, float(np.min(finite_logits)) - 0.1)
        hi_e = max(2.0, float(np.max(finite_logits)) + 0.1)
        counts, edges = np.histogram(finite_logits, bins=16, range=(lo_e, hi_e))
        h_edges = [clean_num(v, 0.0, 3) for v in edges.tolist()]
        h_counts = [int(c) for c in counts.tolist()]
    else:
        h_edges, h_counts = [], []

    scale = math.sqrt(ann)
    is_best = np.nan_to_num(np.asarray(raw["is_sharpe_best"], dtype=np.float64) * scale, nan=0.0)
    oos_best = np.nan_to_num(np.asarray(raw["oos_sharpe_best"], dtype=np.float64) * scale, nan=0.0)
    step = max(1, math.ceil(is_best.size / 160))
    scatter = [
        PboScatterPoint(is_sr=clean_num(is_best[i], 0.0, 3), oos_sr=clean_num(oos_best[i], 0.0, 3))
        for i in range(0, is_best.size, step)
    ]
    return PboReport(
        pbo=clean_num(raw["pbo"], 0.5, 4),
        prob_oos_loss=clean_num(raw["prob_oos_loss"], 0.5, 4),
        degradation_slope=clean_num(raw["degradation_slope"], 0.0, 4),
        n_combinations=int(raw["n_combinations"]),
        logit_hist_edges=h_edges,
        logit_hist_counts=h_counts,
        is_oos_scatter=scatter,
    )


def _build_haircuts(
    ret_mat: np.ndarray,
    sharpes: np.ndarray,
    best_idx: int,
    base_sr: float,
    ann: float,
    eb_post: np.ndarray,
    eb_prob: np.ndarray,
    eb_shrink: np.ndarray,
    ledger_snap: TrialLedgerSnapshot,
) -> list[HaircutBar]:
    n_t, k_total = ret_mat.shape
    focus_sr = float(sharpes[best_idx])
    focus_col = pl.DataFrame({"r": ret_mat[:, best_idx]})
    grid_sr_std = max(0.15, float(np.std(sharpes, ddof=1))) if k_total >= 2 else 0.5
    sess_n_eff = max(float(k_total) ** 0.5, float(ledger_snap.effective_n_trials))
    sess_n_int = max(2, int(round(max(sess_n_eff, float(ledger_snap.unique_trials)))))

    if n_t > 2:
        p_val, g_val, s_val = focus_col.select(
            pa.probabilistic_sharpe_ratio("r", benchmark_sr=0.0, annualization=ann).alias("p"),
            pa.deflated_sharpe_ratio(
                "r", n_trials=max(2, k_total), trials_sr_std=grid_sr_std, annualization=ann
            ).alias("g"),
            pa.deflated_sharpe_ratio(
                "r",
                n_trials=sess_n_int,
                trials_sr_std=max(0.15, ledger_snap.trials_sr_std),
                annualization=ann,
            ).alias("s"),
        ).row(0)
        psr_1, dsr_grid, dsr_sess = float(p_val or 0.0), float(g_val or 0.0), float(s_val or 0.0)
    else:
        psr_1, dsr_grid, dsr_sess = 0.5, 0.0, 0.0

    h_grid = _expected_max_null_sr(float(k_total), grid_sr_std)
    h_sess = _expected_max_null_sr(max(float(k_total), sess_n_eff), ledger_snap.trials_sr_std)
    return [
        HaircutBar(
            stage="1. Observed Peak SR",
            sharpe_equiv=clean_num(focus_sr, 0.0, 3),
            probability=clean_num(psr_1, 0.0, 4),
            note=f"Base SR {base_sr:+.2f} | PSR {psr_1 * 100:.1f}%",
        ),
        HaircutBar(
            stage="2. Grid DSR Haircut",
            sharpe_equiv=clean_num(focus_sr - h_grid, 0.0, 3),
            probability=clean_num(dsr_grid, 0.0, 4),
            note=f"Hurdle -{h_grid:.2f} ({k_total} cells) | DSR {dsr_grid * 100:.1f}%",
        ),
        HaircutBar(
            stage="3. Session Ledger DSR",
            sharpe_equiv=clean_num(focus_sr - h_sess, 0.0, 3),
            probability=clean_num(dsr_sess, 0.0, 4),
            note=(
                f"N_eff {ledger_snap.effective_n_trials:.1f} "
                f"({ledger_snap.unique_trials} trials) | DSR {dsr_sess * 100:.1f}%"
            ),
        ),
        HaircutBar(
            stage="4. Empirical-Bayes SR",
            sharpe_equiv=clean_num(eb_post[best_idx], 0.0, 3),
            probability=clean_num(eb_prob[best_idx], 0.5, 4),
            note=(
                f"Shrinkage {eb_shrink[best_idx] * 100:.0f}% | "
                f"P(SR>0) {eb_prob[best_idx] * 100:.1f}%"
            ),
        ),
    ]


def build_crashtest_response(
    entry: DatasetEntry,
    bundle: GridSweepBundle,
    req: CrashTestRunRequest,
    ledger_snap: TrialLedgerSnapshot,
    bootstrap: BootstrapWorldsReport,
    cusum: CusumBreakReport,
    sharpes: np.ndarray,
    tot_rets: np.ndarray,
    ses: np.ndarray,
    elapsed_ms: float,
) -> CrashTestRunResponse:
    """Assemble full Phase 4 Crash-Test report across all econometric falsification pillars."""
    ret_mat = bundle.ret_matrix_is
    ann = bundle.meta.annualization
    n_t, k_total = ret_mat.shape
    g = int(req.grid_size)

    heatmap, base_idx, best_idx = _build_heatmap(bundle, sharpes, tot_rets, g)
    pbo = _build_pbo(ret_mat, ann, req)
    names = [sp.name for sp in bundle.specs]

    with np.errstate(divide="ignore", invalid="ignore"):
        eb_df = pa.empirical_bayes_shrinkage(sharpes, ses, names=names, prior="zero")
        rw_df = (
            pa.romano_wolf(
                ret_mat,
                n_boot=min(400, max(150, req.n_bootstrap * 2)),
                alternative="greater",
                seed=req.seed,
            )
            if n_t >= 12
            else pl.DataFrame(
                {
                    "name": names,
                    "t_stat": np.zeros(k_total),
                    "p_raw": np.ones(k_total),
                    "p_rw": np.ones(k_total),
                }
            )
        )

    nw_t = np.nan_to_num(rw_df["t_stat"].to_numpy(), nan=0.0)
    p_raw = np.nan_to_num(rw_df["p_raw"].to_numpy(), nan=1.0)
    p_rw = np.nan_to_num(rw_df["p_rw"].to_numpy(), nan=1.0)
    q_bh = _benjamini_hochberg(p_raw)
    eb_post = np.nan_to_num(eb_df["posterior_mean"].to_numpy(), nan=0.0)
    eb_prob = np.nan_to_num(eb_df["prob_positive"].to_numpy(), nan=0.5)
    eb_shrink = np.nan_to_num(eb_df["shrinkage"].to_numpy(), nan=1.0)
    cusum_ps = np.array(
        [
            float(pa.cusum_mean_test(ret_mat[:, i])["p_value"])
            if (n_t >= 10 and float(np.std(ret_mat[:, i])) > 1e-12)
            else 1.0
            for i in range(k_total)
        ],
        dtype=np.float64,
    )

    haircuts = _build_haircuts(
        ret_mat,
        sharpes,
        best_idx,
        heatmap.baseline_sharpe,
        ann,
        eb_post,
        eb_prob,
        eb_shrink,
        ledger_snap,
    )

    m1 = np.ones(k_total, dtype=bool)
    m2 = m1 & (sharpes > 0.0)
    m3 = m2 & (nw_t >= 1.96)
    m4 = m3 & (q_bh <= 0.10)
    m5 = m4 & (p_rw <= 0.05)
    m6 = m5 & (eb_prob >= 0.80)
    m7 = m6 & (cusum_ps >= 0.05)
    gates = [
        ("1. Grid Parameter Sweep", m1),
        ("2. Net Friction Sharpe > 0", m2),
        ("3. Newey-West HAC t >= 1.96", m3),
        ("4. BH-FDR q-val <= 0.10", m4),
        ("5. Romano-Wolf FWER p <= 0.05", m5),
        ("6. Empirical-Bayes P(SR>0) >= 80%", m6),
        ("7. OLS-CUSUM Mean Stability", m7),
    ]
    funnel = [
        FunnelStageItem(
            step=idx + 1,
            gate_label=lbl,
            survivors=int(np.sum(msk)),
            total=k_total,
            survival_pct=clean_num(100.0 * float(np.sum(msk)) / max(1, k_total), 0.0, 1),
        )
        for idx, (lbl, msk) in enumerate(gates)
    ]

    order = np.argsort(-sharpes)
    candidates = [
        CrashTestCandidateRow(
            rank=r_i + 1,
            name=bundle.specs[int(k_i)].name,
            formula_label=bundle.specs[int(k_i)].label,
            sharpe=clean_num(sharpes[int(k_i)], 0.0, 3),
            total_return=clean_num(tot_rets[int(k_i)], 0.0, 4),
            nw_t_stat=clean_num(nw_t[int(k_i)], 0.0, 2),
            p_raw=clean_num(p_raw[int(k_i)], 1.0, 4),
            q_bh=clean_num(q_bh[int(k_i)], 1.0, 4),
            p_romano_wolf=clean_num(p_rw[int(k_i)], 1.0, 4),
            eb_posterior_sharpe=clean_num(eb_post[int(k_i)], 0.0, 3),
            eb_prob_positive=clean_num(eb_prob[int(k_i)], 0.5, 4),
            cusum_p=clean_num(cusum_ps[int(k_i)], 1.0, 4),
            survived_all=bool(m7[int(k_i)]),
        )
        for r_i, k_i in enumerate(order.tolist())
    ]

    base_sr = float(sharpes[base_idx])
    rw_surv = int(np.sum(m5))
    if (
        pbo.pbo < 0.40
        and base_sr > 0.50
        and bootstrap.null_p_value <= 0.10
        and float(eb_prob[base_idx]) >= 0.75
    ):
        verdict = "SURVIVES_FALSIFICATION"
        summary = (
            f"PBO {pbo.pbo * 100:.1f}% | Null p={bootstrap.null_p_value:.3f} | "
            f"RW Survivors {rw_surv}/{k_total} | Plateau {heatmap.neighbor_plateau_ratio:.2f}"
        )
    elif pbo.pbo >= 0.55 or base_sr <= 0.0 or bootstrap.null_p_value > 0.35:
        verdict = "OVERFIT_REJECTED"
        summary = (
            f"High overfit risk: PBO {pbo.pbo * 100:.1f}%, Base SR {base_sr:+.2f}, "
            f"Null Permuted p={bootstrap.null_p_value:.3f}"
        )
    else:
        verdict = "BORDERLINE_FRAGILE"
        summary = (
            f"Mixed robustness: PBO {pbo.pbo * 100:.1f}%, Null p={bootstrap.null_p_value:.3f}, "
            f"RW Survivors {rw_surv}/{k_total}"
        )

    return CrashTestRunResponse(
        dataset_id=entry.dataset_id,
        dataset_name=entry.name,
        formula=req.formula,
        normalized_formula=bundle.normalized_formula,
        elapsed_ms=elapsed_ms,
        holdout_locked=req.holdout_locked,
        is_bars=bundle.meta.is_bars,
        oos_bars=bundle.meta.oos_bars,
        annualization_used=ann,
        delisting_penalty_bps_yr=req.delisting_penalty_bps_yr,
        verdict=verdict,
        verdict_summary=summary,
        notes=bundle.notes,
        heatmap=heatmap,
        pbo=pbo,
        haircut_bars=haircuts,
        funnel=funnel,
        bootstrap=bootstrap,
        cusum=cusum,
        candidates=candidates,
        trial_ledger=ledger_snap,
    )
