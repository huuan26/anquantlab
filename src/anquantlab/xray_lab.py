"""Tab 2 Engine: 4-Stage Causal Alpha Pipeline X-Ray & 5-Factor Spanning Check."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict

import polars as pl
import polars_anta as pa

from .store import DatasetEntry, WorkbenchStore
from .trial_ledger import TrialLedgerRegistry
from .xray_basis import (
    FACTOR_SPECS,
    DatasetFactorBasis,
    build_factor_basis,
    compute_spanning_decomposition,
)
from .xray_schemas import (
    CanonicalFactorKey,
    XRayRunRequest,
    XRayRunResponse,
)
from .xray_stats import evaluate_stage_report

_FACTOR_DSL_MAP: dict[CanonicalFactorKey, str] = {
    "mom_20": "roc(close, 20)",
    "rev_5": "-roc(close, 5)",
    "yz_vol_20": "yang_zhang_volatility(open, high, low, close, 20)",
    "amihud_20": "amihud_illiquidity(close, volume, 20)",
    "mkt_beta_60": "linear_regression_slope(close, 60) / close",
}


def _build_stage_formulas(
    base_formula: str,
    req: XRayRunRequest,
    *,
    is_panel: bool,
    has_sector: bool,
    sector_col: str | None,
) -> tuple[str, str, str, str]:
    f_raw = base_formula
    if is_panel:
        if req.winsor_method == "quantile":
            lo = round(req.winsor_clip, 4)
            hi = round(1.0 - req.winsor_clip, 4)
            f_win = f"cs_winsorize({f_raw}, lower={lo}, upper={hi})"
        else:
            f_win = (
                f"cs_winsorize({f_raw}, method='{req.winsor_method}', "
                f"threshold={round(req.winsor_threshold, 2)})"
            )

        if req.neutralize_mode == "none":
            f_neut = f_win
        elif req.neutralize_mode == "auto" and has_sector and sector_col:
            f_neut = f"neutralize({f_win}, {sector_col}, standardize=True)"
        else:
            f_neut = f"cs_zscore({f_win})"

        f_orth = f_neut
        for fk in req.ortho_factors:
            if fk != "mkt_beta_60":
                f_orth = f"orthogonalize({f_orth}, {_FACTOR_DSL_MAP[fk]})"
    else:
        z_cap = round(req.winsor_threshold, 2)
        f_win = f"ts_zscore({f_raw}, 60)"
        f_neut = f_win if req.neutralize_mode == "none" else f"ts_zscore({f_raw}, 60)"
        f_orth = f"{f_neut}  # causal rolling {z_cap}sd clip + 5-factor projection"
    return f_raw, f_win, f_neut, f_orth


class XRayLabEngine:
    """Two-tier cached 4-stage pipeline analyzer and factor-spanning auditor."""

    def __init__(self, max_basis_entries: int = 12) -> None:
        self.max_basis_entries = max(4, max_basis_entries)
        self._lock = threading.Lock()
        self._basis_cache: OrderedDict[tuple[str, str], DatasetFactorBasis] = OrderedDict()

    def _get_or_build_basis(
        self, entry: DatasetEntry, raw_df: pl.DataFrame
    ) -> tuple[DatasetFactorBasis, bool]:
        key = (entry.dataset_id, entry.sha256_prefix or "")
        with self._lock:
            cached = self._basis_cache.get(key)
            if cached is not None:
                self._basis_cache.move_to_end(key)
                return cached, True

        built = build_factor_basis(
            raw_df,
            time_col=entry.time_col,
            symbol_col=entry.symbol_col,
            sector_col=entry.sector_col,
        )
        with self._lock:
            self._basis_cache[key] = built
            while len(self._basis_cache) > self.max_basis_entries:
                self._basis_cache.popitem(last=False)
        return built, False

    def run(
        self,
        store: WorkbenchStore,
        trial_ledger: TrialLedgerRegistry,
        req: XRayRunRequest,
    ) -> XRayRunResponse:
        t0 = time.perf_counter()
        sig_df, plan, _, sig_hit = store.get_or_compute_signal(req.dataset_id, req.formula)
        entry, raw_df = store.get_frame(req.dataset_id)
        basis, basis_hit = self._get_or_build_basis(entry, raw_df)

        time_col = entry.time_col
        sym_col = entry.symbol_col
        sec_col = entry.sector_col
        notes = list(plan.notes)

        join_keys = [sym_col, time_col] if (sym_col and sym_col in sig_df.columns) else [time_col]
        sig_only = sig_df.select(
            [*join_keys, "close", pl.col("signal").cast(pl.Float64).alias("_s_raw")]
        )
        work = basis.basis_df.join(sig_only, on=join_keys, how="left")
        sort_cols = [sym_col, time_col] if (sym_col and sym_col in work.columns) else [time_col]
        work = work.sort(sort_cols)

        selected_keys: set[CanonicalFactorKey] = set(req.ortho_factors)
        sel_f_cols = [spec[2] for spec in FACTOR_SPECS if spec[0] in selected_keys]

        if basis.is_panel:
            work = work.with_columns(
                pa.cs_winsorize(
                    "_s_raw",
                    over=time_col,
                    method=req.winsor_method,
                    lower=req.winsor_clip,
                    upper=1.0 - req.winsor_clip,
                    threshold=req.winsor_threshold,
                ).alias("_s_win")
            )
            if req.neutralize_mode == "none":
                work = work.with_columns(pl.col("_s_win").alias("_s_neut"))
            elif req.neutralize_mode == "auto" and basis.has_sector and sec_col:
                work = work.with_columns(
                    pa.neutralize("_s_win", by=sec_col, over=time_col, standardize=True).alias(
                        "_s_neut"
                    )
                )
            else:
                if req.neutralize_mode == "auto" and not basis.has_sector:
                    notes.append("No multi-group sector column; Stage 3 used cs_zscore.")
                work = work.with_columns(pa.cs_zscore("_s_win", over=time_col).alias("_s_neut"))

            if not sel_f_cols:
                work = work.with_columns(pl.col("_s_neut").alias("_s_orth"))
            else:
                q_cols: list[str] = []
                for idx, f_col in enumerate(sel_f_cols):
                    q_name = f"_q_{idx}"
                    work = work.with_columns(
                        (pl.col(f_col) - pl.col(f_col).mean().over(time_col)).alias("_tmp_q")
                    )
                    for prev_q in q_cols:
                        work = work.with_columns(
                            (
                                pl.col("_tmp_q")
                                - (pl.col("_tmp_q") * pl.col(prev_q)).mean().over(time_col)
                                * pl.col(prev_q)
                            ).alias("_tmp_q")
                        )
                    work = work.with_columns(
                        pl.when(pl.col("_tmp_q").pow(2).mean().over(time_col).sqrt() > 1e-8)
                        .then(
                            pl.col("_tmp_q") / pl.col("_tmp_q").pow(2).mean().over(time_col).sqrt()
                        )
                        .otherwise(0.0)
                        .alias(q_name)
                    ).drop("_tmp_q")
                    q_cols.append(q_name)

                work = work.with_columns(
                    (pl.col("_s_neut") - pl.col("_s_neut").mean().over(time_col)).alias("_y0")
                )
                proj_expr = pl.lit(0.0)
                for q_name in q_cols:
                    proj_expr = proj_expr + (pl.col("_y0") * pl.col(q_name)).mean().over(
                        time_col
                    ) * pl.col(q_name)
                work = work.with_columns((pl.col("_y0") - proj_expr).alias("_res"))
                work = work.with_columns(
                    pl.when(
                        pl.col("_res").pow(2).mean().over(time_col)
                        > 1e-10 * pl.col("_y0").pow(2).mean().over(time_col)
                    )
                    .then(pa.cs_zscore("_res", over=time_col))
                    .otherwise(0.0)
                    .alias("_s_orth")
                ).drop([*q_cols, "_y0", "_res"])
        else:
            notes.append(
                "Single-asset time-series mode: causal trailing rolling conditioning applied."
            )
            win = min(120, max(12, work.height // 3))
            z_cap = req.winsor_threshold if req.winsor_method != "quantile" else 2.5
            mu = pl.col("_s_raw").rolling_mean(win, min_samples=5)
            sd = pl.col("_s_raw").rolling_std(win, min_samples=5) + 1e-12
            work = work.with_columns(
                pl.min_horizontal(
                    pl.max_horizontal(pl.col("_s_raw"), mu - z_cap * sd), mu + z_cap * sd
                ).alias("_s_win")
            )
            if req.neutralize_mode == "none":
                work = work.with_columns(pl.col("_s_win").alias("_s_neut"))
            else:
                mu_w = pl.col("_s_win").rolling_mean(win, min_samples=5)
                sd_w = pl.col("_s_win").rolling_std(win, min_samples=5) + 1e-12
                work = work.with_columns(((pl.col("_s_win") - mu_w) / sd_w).alias("_s_neut"))

            cur_col = "_s_neut"
            work = work.with_columns(pl.col(cur_col).alias("_tmp_orth"))
            for f_col in sel_f_cols:
                cov = pl.rolling_cov("_tmp_orth", f_col, window_size=win, min_samples=10)
                var = pl.col(f_col).rolling_var(win, min_samples=10) + 1e-6
                work = work.with_columns(
                    (pl.col("_tmp_orth") - (cov / var).fill_null(0.0) * pl.col(f_col)).alias(
                        "_tmp_orth"
                    )
                )
            work = work.rename({"_tmp_orth": "_s_orth"})

        f_raw, f_win, f_neut, f_orth = _build_stage_formulas(
            plan.normalized_formula,
            req,
            is_panel=basis.is_panel,
            has_sector=basis.has_sector,
            sector_col=sec_col,
        )

        stage_defs = [
            ("raw", "1. Raw Signal", f_raw, "_s_raw"),
            ("winsorized", "2. Winsorized", f_win, "_s_win"),
            ("neutralized", "3. Neutralized", f_neut, "_s_neut"),
            ("orthogonalized", "4. Orthogonalized", f_orth, "_s_orth"),
        ]
        stages = [
            evaluate_stage_report(
                work,
                stage_id=sid,
                label=lbl,
                formula_preview=f_prev,
                col=col_name,
                basis=basis,
                time_col=time_col,
                symbol_col=sym_col,
                sector_col=sec_col,
                ic_horizon=req.ic_horizon,
                ic_method=req.ic_method,
                holdout_locked=req.holdout_locked,
            )
            for sid, lbl, f_prev, col_name in stage_defs
        ]

        spanning = compute_spanning_decomposition(
            work,
            basis=basis,
            pre_col="_s_neut",
            post_col="_s_orth",
            selected_keys=selected_keys,
            pre_stage=stages[2],
            post_stage=stages[3],
            holdout_locked=req.holdout_locked,
        )

        peek_key = hashlib.sha256(
            f"xray|{plan.normalized_formula}|{req.winsor_method}|{req.winsor_clip}|"
            f"{req.neutralize_mode}|{sorted(selected_keys)}|{req.ic_horizon}".encode()
        ).hexdigest()[:16]
        ledger_snap = trial_ledger.record_holdout_peek(
            req.dataset_id, peek_key, holdout_locked=req.holdout_locked
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return XRayRunResponse(
            dataset_id=req.dataset_id,
            dataset_name=entry.name,
            formula=req.formula,
            normalized_formula=plan.normalized_formula,
            is_panel=basis.is_panel,
            has_sector=basis.has_sector,
            elapsed_ms=elapsed_ms,
            signal_cache_hit=sig_hit,
            basis_cache_hit=basis_hit,
            holdout_locked=req.holdout_locked,
            is_bars=basis.is_bars,
            oos_bars=basis.oos_bars,
            annualization_used=basis.annualization,
            notes=notes,
            stages=stages,
            spanning=spanning,
            trial_ledger=ledger_snap,
        )
