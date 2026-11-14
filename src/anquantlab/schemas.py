"""Pydantic API schemas for AnQuantLab REST endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_version: str
    polars_anta_version: str
    polars_version: str
    polars_max_threads: int
    max_concurrent: int
    compute_timeout_sec: float
    max_upload_mb: int
    catalog_total_exports: int
    catalog_public_functions: int
    dataset_count: int
    cached_signals: int
    allow_public_fetch: bool = True


class ParameterSpec(BaseModel):
    name: str
    required: bool
    default: str | None = None
    annotation: str | None = None


class CatalogItem(BaseModel):
    name: str
    domain: str
    domain_label: str
    kind: str
    signature: str
    summary: str
    returns_struct: bool = False
    sample_formula: str
    parameters: list[ParameterSpec] = Field(default_factory=list)


class DomainSummary(BaseModel):
    domain: str
    label: str
    count: int
    function_count: int


class CatalogResponse(BaseModel):
    polars_anta_version: str
    total_exports: int
    public_functions: int
    exported_classes: int
    domains: list[DomainSummary]
    items: list[CatalogItem]


class DatasetInfo(BaseModel):
    dataset_id: str
    name: str
    source_kind: str
    description: str
    row_count: int | None = None
    symbol_count: int | None = None
    date_start: str | None = None
    date_end: str | None = None
    time_col: str
    symbol_col: str | None = None
    sector_col: str | None = None
    columns: list[str] = Field(default_factory=list)
    sha256_prefix: str | None = None
    loaded: bool = True


class DatasetListResponse(BaseModel):
    default_dataset_id: str
    datasets: list[DatasetInfo]


class DatasetPreviewResponse(BaseModel):
    info: DatasetInfo
    ohlcv_valid: bool
    ohlcv_issues: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    sample_symbols: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class FormulaPreviewRequest(BaseModel):
    dataset_id: str = Field(default="builtin_demo_panel", min_length=1, max_length=128)
    formula: str = Field(..., min_length=1, max_length=1024)
    symbol: str | None = Field(default=None, max_length=64)
    chart_bars: int = Field(default=160, ge=20, le=600)
    preview_limit: int = Field(default=20, ge=1, le=100)


class SignalSummaryStats(BaseModel):
    total_rows: int
    valid_count: int
    null_count: int
    coverage_pct: float
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    q25: float | None = None
    median: float | None = None
    q75: float | None = None
    max: float | None = None


class ExecutionStageInfo(BaseModel):
    stage_index: int
    scope: str
    window_over: str | None = None
    description: str


class ChartBarPoint(BaseModel):
    t: str
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float
    s: float | None = None


class FormulaPreviewResponse(BaseModel):
    dataset_id: str
    formula: str
    normalized_formula: str
    cache_hit: bool
    elapsed_ms: float
    active_symbol: str | None = None
    available_symbols: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    stages: list[ExecutionStageInfo]
    stats: SignalSummaryStats
    chart_series: list[ChartBarPoint] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]]


class AnomalyEvent(BaseModel):
    symbol: str | None = None
    timestamp: str
    kind: str
    detail: str


class DatasetForensicsResponse(BaseModel):
    dataset_id: str
    health_score: int
    grade: str
    row_count: int
    symbol_count: int
    zero_volume_bars: int
    zero_volume_pct: float
    frozen_bars: int
    frozen_pct: float
    split_suspect_jumps: int
    ohlc_violations: int
    duplicate_rows: int
    late_listings: int
    early_dropouts: int
    survivorship_risk: str
    has_taker_flow: bool
    corwin_schultz_spread_bps_median: float | None = None
    corwin_schultz_spread_bps_p90: float | None = None
    roll_spread_bps_median: float | None = None
    amihud_illiq_median: float | None = None
    recommended_min_slippage_bps: float
    warnings: list[str] = Field(default_factory=list)
    sample_anomalies: list[AnomalyEvent] = Field(default_factory=list)


class PublicPresetInfo(BaseModel):
    preset_id: str
    name: str
    source: str
    interval: str
    symbols: list[str]
    has_taker_flow: bool
    description: str
    cached: bool


class PublicPresetListResponse(BaseModel):
    allow_public_fetch: bool
    cache_dir: str
    presets: list[PublicPresetInfo]


class PublicFetchRequest(BaseModel):
    preset_id: str = Field(..., min_length=1, max_length=128)
    force_refresh: bool = False


class TrialLedgerSnapshot(BaseModel):
    dataset_id: str
    total_evaluations: int
    unique_trials: int
    effective_n_trials: float
    trials_sr_std: float
    best_is_sharpe: float | None = None
    holdout_peeks: int


class BacktestRunRequest(BaseModel):
    dataset_id: str = Field(default="builtin_demo_panel", min_length=1, max_length=128)
    formula: str = Field(..., min_length=1, max_length=1024)
    symbol: str | None = Field(default=None, max_length=64)
    weight_scheme: str = Field(default="dollar_neutral", max_length=32)
    execution_price: str = Field(default="close", max_length=16)
    fee_bps: float = Field(default=5.0, ge=0.0, le=200.0)
    slippage_mode: str = Field(default="fixed", max_length=32)
    slippage_bps: float = Field(default=5.0, ge=0.0, le=300.0)
    signal_lag: int = Field(default=1, ge=0, le=10)
    vol_target: float | None = Field(default=None, ge=0.0, le=2.0)
    no_trade_buffer: float = Field(default=0.0, ge=0.0, le=1.0)
    limit_lock_skip: bool = False
    intraday_flatten: bool = False
    holdout_locked: bool = True
    annualization: float | None = Field(default=None, gt=0.0, le=525_600.0)
    chart_bars: int = Field(default=180, ge=20, le=600)
    max_trades: int = Field(default=80, ge=1, le=300)


class BacktestMetrics(BaseModel):
    total_return: float
    gross_total_return: float
    benchmark_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    gross_sharpe_ratio: float
    oos_sharpe_ratio: float | None = None
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    psr: float
    live_dsr: float
    var_95: float
    cvar_95: float
    omega_ratio: float
    tail_ratio: float
    win_rate: float
    profit_factor: float
    total_turnover: float
    total_cost: float
    n_trades: int
    n_round_trips: int
    avg_holding_bars: float
    avg_mae: float
    avg_mfe: float
    breakeven_bps: float


class EquityPoint(BaseModel):
    t: str
    gross_eq: float
    net_eq: float
    bench_eq: float
    dd: float
    turnover: float
    is_oos: bool = False


class CostCurvePoint(BaseModel):
    cost_bps: float
    sharpe: float
    total_return: float


class TradeRecord(BaseModel):
    trade_id: int
    symbol: str | None = None
    side: str
    entry_time: str
    exit_time: str
    holding_bars: int
    entry_price: float | None = None
    exit_price: float | None = None
    gross_return: float
    cost: float
    net_return: float
    mae: float
    mfe: float


class BacktestRunResponse(BaseModel):
    dataset_id: str
    formula: str
    normalized_formula: str
    elapsed_ms: float
    signal_cache_hit: bool
    position_cache_hit: bool
    active_symbol: str | None = None
    available_symbols: list[str] = Field(default_factory=list)
    holdout_locked: bool
    is_bars: int
    oos_bars: int
    oos_start_time: str | None = None
    annualization_used: float
    effective_slippage_bps_mean: float
    notes: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics
    equity_series: list[EquityPoint] = Field(default_factory=list)
    cost_curve: list[CostCurvePoint] = Field(default_factory=list)
    chart_series: list[ChartBarPoint] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)
    trial_ledger: TrialLedgerSnapshot
