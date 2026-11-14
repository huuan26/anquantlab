"""Pydantic wire schemas for Tab 3: Overfitting Crash-Test & Small-Sample Stress Suite."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .schemas import TrialLedgerSnapshot


class CrashTestRunRequest(BaseModel):
    dataset_id: str
    formula: str = Field(min_length=1, max_length=2000)
    sweep_mode: Literal["auto_2d", "execution_2d"] = "auto_2d"
    grid_size: Literal[3, 4, 5] = 5
    weight_scheme: Literal["dollar_neutral", "long_only", "equal_weight", "raw"] = "dollar_neutral"
    fee_bps: float = Field(default=5.0, ge=0.0, le=200.0)
    slippage_mode: Literal["fixed", "corwin_schultz"] = "corwin_schultz"
    slippage_bps: float = Field(default=5.0, ge=0.0, le=300.0)
    delisting_penalty_bps_yr: float = Field(default=0.0, ge=0.0, le=1000.0)
    n_bootstrap: int = Field(default=200, ge=50, le=500)
    cscv_splits: Literal[8, 10, 12, 16] = 12
    seed: int = Field(default=42, ge=0, le=1_000_000)
    holdout_locked: bool = True


class HeatmapGridReport(BaseModel):
    x_name: str
    y_name: str
    x_labels: list[str]
    y_labels: list[str]
    sharpe_matrix: list[list[float]]
    return_matrix: list[list[float]]
    baseline_row: int
    baseline_col: int
    baseline_sharpe: float
    best_sharpe: float
    median_sharpe: float
    neighbor_plateau_ratio: float
    positive_grid_share: float


class PboScatterPoint(BaseModel):
    is_sr: float
    oos_sr: float


class PboReport(BaseModel):
    pbo: float
    prob_oos_loss: float
    degradation_slope: float
    n_combinations: int
    logit_hist_edges: list[float] = Field(default_factory=list)
    logit_hist_counts: list[int] = Field(default_factory=list)
    is_oos_scatter: list[PboScatterPoint] = Field(default_factory=list)


class HaircutBar(BaseModel):
    stage: str
    sharpe_equiv: float
    probability: float | None = None
    note: str


class FunnelStageItem(BaseModel):
    step: int
    gate_label: str
    survivors: int
    total: int
    survival_pct: float


class BootstrapPathPoint(BaseModel):
    bar: int
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    realized: float


class BootstrapWorldsReport(BaseModel):
    n_worlds: int
    mean_block_bars: int
    sharpe_p05: float = 0.0
    sharpe_p25: float = 0.0
    sharpe_median: float = 0.0
    sharpe_p75: float = 0.0
    sharpe_p95: float = 0.0
    prob_positive_world: float = 0.0
    max_dd_median: float = 0.0
    max_dd_p95_worst: float = 0.0
    null_sharpe_95: float = 0.0
    null_p_value: float = 1.0
    sharpe_hist_edges: list[float] = Field(default_factory=list)
    sharpe_hist_counts: list[int] = Field(default_factory=list)
    fan_chart: list[BootstrapPathPoint] = Field(default_factory=list)


class CusumCurvePoint(BaseModel):
    t: str
    stat: float


class CusumBreakReport(BaseModel):
    statistic: float
    critical_5pct: float = 1.3581
    p_value: float
    has_break: bool
    break_index: int
    break_time: str | None = None
    mean_before_bps: float
    mean_after_bps: float
    bridge_series: list[CusumCurvePoint] = Field(default_factory=list)


class CrashTestCandidateRow(BaseModel):
    rank: int
    name: str
    formula_label: str
    sharpe: float
    total_return: float
    nw_t_stat: float
    p_raw: float
    q_bh: float
    p_romano_wolf: float
    eb_posterior_sharpe: float
    eb_prob_positive: float
    cusum_p: float
    survived_all: bool


class CrashTestRunResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    formula: str
    normalized_formula: str
    elapsed_ms: float
    holdout_locked: bool
    is_bars: int
    oos_bars: int
    annualization_used: float
    delisting_penalty_bps_yr: float
    verdict: Literal["SURVIVES_FALSIFICATION", "BORDERLINE_FRAGILE", "OVERFIT_REJECTED"]
    verdict_summary: str
    notes: list[str] = Field(default_factory=list)
    heatmap: HeatmapGridReport
    pbo: PboReport
    haircut_bars: list[HaircutBar] = Field(default_factory=list)
    funnel: list[FunnelStageItem] = Field(default_factory=list)
    bootstrap: BootstrapWorldsReport
    cusum: CusumBreakReport
    candidates: list[CrashTestCandidateRow] = Field(default_factory=list)
    trial_ledger: TrialLedgerSnapshot
