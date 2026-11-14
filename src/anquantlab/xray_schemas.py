"""Pydantic wire schemas for Tab 2: Alpha Pipeline X-Ray & 5-Factor Spanning Check."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .schemas import TrialLedgerSnapshot

CanonicalFactorKey = Literal["mom_20", "rev_5", "yz_vol_20", "amihud_20", "mkt_beta_60"]

DEFAULT_ORTHO_FACTORS: list[CanonicalFactorKey] = [
    "mom_20",
    "rev_5",
    "yz_vol_20",
    "amihud_20",
    "mkt_beta_60",
]


class XRayRunRequest(BaseModel):
    dataset_id: str
    formula: str = Field(min_length=1, max_length=2000)
    winsor_method: Literal["quantile", "mad", "zscore"] = "quantile"
    winsor_clip: float = Field(default=0.02, ge=0.001, le=0.20)
    winsor_threshold: float = Field(default=3.0, ge=1.5, le=8.0)
    neutralize_mode: Literal["auto", "demean", "none"] = "auto"
    ortho_factors: list[CanonicalFactorKey] = Field(
        default_factory=lambda: list(DEFAULT_ORTHO_FACTORS)
    )
    ic_horizon: int = Field(default=1, ge=1, le=20)
    ic_method: Literal["spearman", "pearson"] = "spearman"
    holdout_locked: bool = True


class QuantileBucket(BaseModel):
    quantile: int
    count: int
    mean_factor: float
    mean_return_bps: float
    sharpe_ratio: float
    win_rate: float
    cumulative_return: float


class SectorExposureItem(BaseModel):
    sector: str
    ticker_count: int
    net_exposure: float
    mean_signal: float
    gross_share: float


class IcDecayPoint(BaseModel):
    horizon: int
    ic_mean: float
    icir: float
    nw_t_stat: float
    hit_rate: float


class IcSeriesPoint(BaseModel):
    t: str
    ic: float
    cum_ic: float


class XRayStageReport(BaseModel):
    stage_id: Literal["raw", "winsorized", "neutralized", "orthogonalized"]
    label: str
    formula_preview: str
    valid_count: int = 0
    mean: float = 0.0
    std: float = 0.0
    skew: float = 0.0
    excess_kurtosis: float = 0.0
    min: float = 0.0
    q05: float = 0.0
    q25: float = 0.0
    median: float = 0.0
    q75: float = 0.0
    q95: float = 0.0
    max: float = 0.0
    hist_edges: list[float] = Field(default_factory=list)
    hist_counts: list[int] = Field(default_factory=list)
    ic_mean: float = 0.0
    ic_std: float = 0.0
    icir: float = 0.0
    nw_t_stat: float = 0.0
    hit_rate: float = 0.0
    n_ic_periods: int = 0
    top_minus_bottom_bps: float = 0.0
    ls_sharpe_approx: float = 0.0
    quantile_monotonicity: float = 0.0
    turnover_mean: float = 0.0
    rank_autocorr: float = 0.0
    half_life_bars: float | None = None
    max_abs_sector_tilt: float = 0.0
    quantiles: list[QuantileBucket] = Field(default_factory=list)
    sector_exposures: list[SectorExposureItem] = Field(default_factory=list)
    ic_decay: list[IcDecayPoint] = Field(default_factory=list)
    ic_series: list[IcSeriesPoint] = Field(default_factory=list)


class FactorLoadingItem(BaseModel):
    factor_key: CanonicalFactorKey
    factor_label: str
    selected: bool
    beta: float
    nw_t_stat: float
    marginal_corr: float
    r2_contribution: float
    post_ortho_corr: float


class SpanningCheckReport(BaseModel):
    spanning_r2: float
    selected_r2: float
    orthogonal_share: float
    pre_ortho_icir: float
    post_ortho_icir: float
    pre_ortho_nw_t: float
    post_ortho_nw_t: float
    pre_ortho_ls_sharpe: float
    post_ortho_ls_sharpe: float
    verdict: Literal["DISTINCT_ALPHA", "PARTIAL_OVERLAP", "FACTOR_CLONE", "NOISE_SIGNAL"]
    verdict_summary: str
    loadings: list[FactorLoadingItem] = Field(default_factory=list)


class XRayRunResponse(BaseModel):
    dataset_id: str
    dataset_name: str
    formula: str
    normalized_formula: str
    is_panel: bool
    has_sector: bool
    elapsed_ms: float
    signal_cache_hit: bool
    basis_cache_hit: bool
    holdout_locked: bool
    is_bars: int
    oos_bars: int
    annualization_used: float
    notes: list[str] = Field(default_factory=list)
    stages: list[XRayStageReport] = Field(default_factory=list)
    spanning: SpanningCheckReport
    trial_ledger: TrialLedgerSnapshot
