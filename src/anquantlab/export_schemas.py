"""Pydantic schemas for Phase 5: Production Polars Codegen, HTML Tearsheet & Alpha Passport."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExportBundleRequest(BaseModel):
    dataset_id: str
    formula: str = Field(min_length=1, max_length=2000)
    weight_scheme: Literal["dollar_neutral", "long_only", "equal_weight", "raw"] = "dollar_neutral"
    execution_price: Literal["close", "open", "twap", "vwap"] = "close"
    fee_bps: float = Field(default=5.0, ge=0.0, le=200.0)
    slippage_mode: Literal["fixed", "corwin_schultz", "amihud"] = "corwin_schultz"
    slippage_bps: float = Field(default=5.0, ge=0.0, le=300.0)
    vol_target: float | None = Field(default=None, ge=0.0, le=2.0)
    no_trade_buffer: float = Field(default=0.0, ge=0.0, le=0.5)
    signal_lag: int = Field(default=1, ge=0, le=5)
    limit_lock_skip: bool = False
    intraday_flatten: bool = False
    delisting_penalty_bps_yr: float = Field(default=0.0, ge=0.0, le=1000.0)
    holdout_locked: bool = True
    lang: Literal["en", "vi"] = "en"


class PassportDatasetAudit(BaseModel):
    dataset_id: str
    dataset_name: str
    sha256_prefix: str
    row_count: int
    symbol_count: int
    time_col: str
    symbol_col: str | None = None
    sector_col: str | None = None
    is_bars: int
    oos_bars: int
    holdout_locked: bool
    health_score: float
    survivorship_grade: str
    corwin_schultz_median_bps: float
    recommended_min_slippage_bps: float


class PassportSignalSpec(BaseModel):
    raw_formula: str
    normalized_formula: str
    formula_sha256: str
    codegen_sha256: str
    execution_stages: list[str] = Field(default_factory=list)


class PassportBacktestAudit(BaseModel):
    weight_scheme: str
    execution_price: str
    signal_lag: int
    fee_bps: float
    slippage_mode: str
    effective_slippage_bps: float
    net_sharpe: float
    gross_sharpe: float
    oos_sharpe: float | None = None
    total_return: float
    max_drawdown: float
    breakeven_bps: float
    var_95: float
    cvar_95: float
    omega_ratio: float
    tail_ratio: float


class PassportXRayAudit(BaseModel):
    spanning_r2: float
    orthogonal_share: float
    spanning_verdict: str
    orthogonal_ic_mean: float
    orthogonal_nw_t_stat: float
    max_abs_sector_tilt: float


class PassportFalsificationAudit(BaseModel):
    crashtest_verdict: str
    pbo: float
    prob_oos_loss: float
    baseline_grid_sharpe: float
    best_grid_sharpe: float
    neighbor_plateau_ratio: float
    empirical_bayes_sharpe: float
    empirical_bayes_prob_pos: float
    romano_wolf_survivors: int
    grid_candidates: int
    bootstrap_sharpe_median: float
    null_p_value: float
    cusum_p_value: float
    cusum_has_break: bool


class PassportTrialLedgerAudit(BaseModel):
    total_evaluations: int
    unique_trials: int
    effective_n_trials: float
    trials_sr_std: float
    holdout_peeks: int
    live_dsr: float


class AlphaPassportDocument(BaseModel):
    passport_version: str = "1.0"
    generated_at_utc: str
    anquantlab_version: str
    polars_anta_version: str
    polars_version: str
    overall_clearance: Literal["APPROVED_CANDIDATE", "CONDITIONAL_REVIEW", "REJECTED_OVERFIT"]
    dataset_audit: PassportDatasetAudit
    signal_spec: PassportSignalSpec
    backtest_audit: PassportBacktestAudit
    xray_audit: PassportXRayAudit
    falsification_audit: PassportFalsificationAudit
    trial_ledger_audit: PassportTrialLedgerAudit
    passport_sha256: str


class ExportBundleResponse(BaseModel):
    strategy_slug: str
    python_filename: str
    python_code: str
    ast_sandbox_clean: bool
    passport_filename: str
    passport: AlphaPassportDocument
    tearsheet_filename: str
    tearsheet_html: str
    elapsed_ms: float
