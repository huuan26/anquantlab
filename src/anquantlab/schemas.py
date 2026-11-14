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
