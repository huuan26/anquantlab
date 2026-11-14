"""Cryptographic Alpha Passport builder & Export Bundle orchestrator (Phase 5)."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

import polars as pl
import polars_anta as pa

from . import __version__
from .backtest_lab import BacktestLabEngine
from .backtest_metrics import build_micro_meta, clean_num
from .codegen_polars import generate_polars_script, slugify_formula, verify_ast_sandbox_clean
from .crashtest_lab import CrashTestLabEngine
from .crashtest_schemas import CrashTestRunRequest
from .export_schemas import (
    AlphaPassportDocument,
    ExportBundleRequest,
    ExportBundleResponse,
    PassportBacktestAudit,
    PassportDatasetAudit,
    PassportFalsificationAudit,
    PassportSignalSpec,
    PassportTrialLedgerAudit,
    PassportXRayAudit,
)
from .schemas import BacktestRunRequest
from .store import WorkbenchStore
from .tearsheet_html import render_tearsheet_html
from .trial_ledger import TrialLedgerRegistry
from .xray_lab import XRayLabEngine
from .xray_schemas import XRayRunRequest


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ExportBundleEngine:
    """Assembles 1-Click Production Polars .py, Alpha Passport JSON, and HTML Tearsheet."""

    def build_bundle(
        self,
        store: WorkbenchStore,
        trial_ledger: TrialLedgerRegistry,
        bt_engine: BacktestLabEngine,
        xray_engine: XRayLabEngine,
        ct_engine: CrashTestLabEngine,
        req: ExportBundleRequest,
    ) -> ExportBundleResponse:
        t0 = time.perf_counter()
        entry, raw_df = store.get_frame(req.dataset_id)
        has_panel = bool(
            entry.symbol_col
            and entry.symbol_col in raw_df.columns
            and raw_df[entry.symbol_col].n_unique() > 1
        )
        sort_cols = (
            [entry.symbol_col, entry.time_col]
            if (entry.symbol_col and entry.symbol_col in raw_df.columns)
            else [entry.time_col]
        )
        meta = build_micro_meta(raw_df.sort(sort_cols), entry.time_col, entry.symbol_col)
        _, plan, stage_infos, _ = store.get_or_compute_signal(req.dataset_id, req.formula)

        py_code = generate_polars_script(
            req,
            columns=set(raw_df.columns),
            time_col=entry.time_col,
            symbol_col=entry.symbol_col,
            has_panel=has_panel,
            annualization=meta.annualization,
            close_hm=meta.close_hm,
            dataset_sha256=entry.sha256_prefix or "in_memory",
        )
        sandbox_clean = len(verify_ast_sandbox_clean(py_code)) == 0

        forensics = store.build_forensics(req.dataset_id)
        bt_res = bt_engine.run(
            store,
            trial_ledger,
            BacktestRunRequest(
                dataset_id=req.dataset_id,
                formula=req.formula,
                weight_scheme=req.weight_scheme,
                execution_price=req.execution_price,
                fee_bps=req.fee_bps,
                slippage_mode=req.slippage_mode,
                slippage_bps=req.slippage_bps,
                vol_target=req.vol_target,
                no_trade_buffer=req.no_trade_buffer,
                signal_lag=req.signal_lag,
                limit_lock_skip=req.limit_lock_skip,
                intraday_flatten=req.intraday_flatten,
                holdout_locked=req.holdout_locked,
            ),
        )
        xr_res = xray_engine.run(
            store,
            trial_ledger,
            XRayRunRequest(
                dataset_id=req.dataset_id,
                formula=req.formula,
                holdout_locked=req.holdout_locked,
            ),
        )
        ct_slip = "corwin_schultz" if req.slippage_mode != "fixed" else "fixed"
        ct_res = ct_engine.run(
            store,
            trial_ledger,
            CrashTestRunRequest(
                dataset_id=req.dataset_id,
                formula=req.formula,
                grid_size=3,
                weight_scheme=req.weight_scheme,
                fee_bps=req.fee_bps,
                slippage_mode=ct_slip,
                slippage_bps=req.slippage_bps,
                delisting_penalty_bps_yr=req.delisting_penalty_bps_yr,
                n_bootstrap=150,
                cscv_splits=8,
                seed=42,
                holdout_locked=req.holdout_locked,
            ),
        )

        m = bt_res.metrics
        orth_st = xr_res.stages[-1]
        base_name = f"G_{ct_res.heatmap.baseline_row}_{ct_res.heatmap.baseline_col}"
        base_cand = next(
            (c for c in ct_res.candidates if c.name == base_name),
            ct_res.candidates[0],
        )
        rw_surv = ct_res.funnel[4].survivors if len(ct_res.funnel) >= 5 else 0

        if (
            ct_res.verdict == "SURVIVES_FALSIFICATION"
            and xr_res.spanning.verdict != "FACTOR_CLONE"
            and m.sharpe_ratio > 0.50
        ):
            clearance = "APPROVED_CANDIDATE"
        elif ct_res.verdict == "OVERFIT_REJECTED" or m.sharpe_ratio <= 0.0:
            clearance = "REJECTED_OVERFIT"
        else:
            clearance = "CONDITIONAL_REVIEW"

        ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cs_med = forensics.corwin_schultz_spread_bps_median or 0.0
        draft_dict = {
            "passport_version": "1.0",
            "generated_at_utc": ts_utc,
            "anquantlab_version": __version__,
            "polars_anta_version": pa.__version__,
            "polars_version": pl.__version__,
            "overall_clearance": clearance,
            "dataset_audit": PassportDatasetAudit(
                dataset_id=entry.dataset_id,
                dataset_name=entry.name,
                sha256_prefix=entry.sha256_prefix or "",
                row_count=raw_df.height,
                symbol_count=(int(raw_df[entry.symbol_col].n_unique()) if entry.symbol_col else 1),
                time_col=entry.time_col,
                symbol_col=entry.symbol_col,
                sector_col=entry.sector_col,
                is_bars=bt_res.is_bars,
                oos_bars=bt_res.oos_bars,
                holdout_locked=req.holdout_locked,
                health_score=clean_num(float(forensics.health_score), 0.0, 1),
                survivorship_grade=forensics.survivorship_risk,
                corwin_schultz_median_bps=clean_num(cs_med, 0.0, 2),
                recommended_min_slippage_bps=clean_num(
                    forensics.recommended_min_slippage_bps, 0.0, 2
                ),
            ).model_dump(),
            "signal_spec": PassportSignalSpec(
                raw_formula=req.formula,
                normalized_formula=plan.normalized_formula,
                formula_sha256=_sha256_hex(plan.normalized_formula),
                codegen_sha256=_sha256_hex(py_code),
                execution_stages=[f"{s.scope}: {s.description}" for s in stage_infos],
            ).model_dump(),
            "backtest_audit": PassportBacktestAudit(
                weight_scheme=req.weight_scheme,
                execution_price=req.execution_price,
                signal_lag=req.signal_lag,
                fee_bps=req.fee_bps,
                slippage_mode=req.slippage_mode,
                effective_slippage_bps=bt_res.effective_slippage_bps_mean,
                net_sharpe=m.sharpe_ratio,
                gross_sharpe=m.gross_sharpe_ratio,
                oos_sharpe=m.oos_sharpe_ratio,
                total_return=m.total_return,
                max_drawdown=m.max_drawdown,
                breakeven_bps=m.breakeven_bps,
                var_95=m.var_95,
                cvar_95=m.cvar_95,
                omega_ratio=m.omega_ratio,
                tail_ratio=m.tail_ratio,
            ).model_dump(),
            "xray_audit": PassportXRayAudit(
                spanning_r2=xr_res.spanning.spanning_r2,
                orthogonal_share=xr_res.spanning.orthogonal_share,
                spanning_verdict=xr_res.spanning.verdict,
                orthogonal_ic_mean=orth_st.ic_mean,
                orthogonal_nw_t_stat=orth_st.nw_t_stat,
                max_abs_sector_tilt=orth_st.max_abs_sector_tilt,
            ).model_dump(),
            "falsification_audit": PassportFalsificationAudit(
                crashtest_verdict=ct_res.verdict,
                pbo=ct_res.pbo.pbo,
                prob_oos_loss=ct_res.pbo.prob_oos_loss,
                baseline_grid_sharpe=ct_res.heatmap.baseline_sharpe,
                best_grid_sharpe=ct_res.heatmap.best_sharpe,
                neighbor_plateau_ratio=ct_res.heatmap.neighbor_plateau_ratio,
                empirical_bayes_sharpe=base_cand.eb_posterior_sharpe,
                empirical_bayes_prob_pos=base_cand.eb_prob_positive,
                romano_wolf_survivors=rw_surv,
                grid_candidates=len(ct_res.candidates),
                bootstrap_sharpe_median=ct_res.bootstrap.sharpe_median,
                null_p_value=ct_res.bootstrap.null_p_value,
                cusum_p_value=ct_res.cusum.p_value,
                cusum_has_break=ct_res.cusum.has_break,
            ).model_dump(),
            "trial_ledger_audit": PassportTrialLedgerAudit(
                total_evaluations=ct_res.trial_ledger.total_evaluations,
                unique_trials=ct_res.trial_ledger.unique_trials,
                effective_n_trials=ct_res.trial_ledger.effective_n_trials,
                trials_sr_std=ct_res.trial_ledger.trials_sr_std,
                holdout_peeks=ct_res.trial_ledger.holdout_peeks,
                live_dsr=m.live_dsr,
            ).model_dump(),
        }
        canonical_json = json.dumps(draft_dict, sort_keys=True, separators=(",", ":"))
        passport = AlphaPassportDocument(**draft_dict, passport_sha256=_sha256_hex(canonical_json))
        tearsheet_html = render_tearsheet_html(passport, bt_res, xr_res, ct_res, py_code)

        slug = slugify_formula(plan.normalized_formula)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ExportBundleResponse(
            strategy_slug=slug,
            python_filename=f"strategy_{slug}.py",
            python_code=py_code,
            ast_sandbox_clean=sandbox_clean,
            passport_filename=f"alpha_passport_{slug}.json",
            passport=passport,
            tearsheet_filename=f"tearsheet_{slug}.html",
            tearsheet_html=tearsheet_html,
            elapsed_ms=elapsed_ms,
        )
