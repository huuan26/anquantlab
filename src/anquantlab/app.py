"""FastAPI application factory, resource guards, and REST endpoints for AnQuantLab."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .config import Settings, apply_thread_limits, load_settings

apply_thread_limits()

import polars as pl  # noqa: E402
import polars_anta as pa  # noqa: E402
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from . import __version__  # noqa: E402
from .catalog import build_catalog  # noqa: E402
from .expr_dsl import FormulaSyntaxError  # noqa: E402
from .schemas import (  # noqa: E402
    CatalogResponse,
    ChartBarPoint,
    DatasetInfo,
    DatasetListResponse,
    DatasetPreviewResponse,
    FormulaPreviewRequest,
    FormulaPreviewResponse,
    HealthResponse,
    SignalSummaryStats,
)
from .store import WorkbenchStore  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _finite_float(val: Any) -> float | None:
    if val is None:
        return None
    fval = float(val)
    if fval != fval or fval in (float("inf"), float("-inf")):
        return None
    return round(fval, 6)


def _compute_signal_stats(sig_df: pl.DataFrame) -> SignalSummaryStats:
    total = sig_df.height
    valid = int(sig_df["signal"].drop_nulls().len())
    nulls = total - valid
    cov = round((100.0 * valid / total), 2) if total > 0 else 0.0
    if valid == 0:
        return SignalSummaryStats(
            total_rows=total,
            valid_count=0,
            null_count=nulls,
            coverage_pct=0.0,
        )
    agg = sig_df.select(
        pl.col("signal").mean().alias("mean"),
        pl.col("signal").std().alias("std"),
        pl.col("signal").min().alias("min"),
        pl.col("signal").quantile(0.25, interpolation="linear").alias("q25"),
        pl.col("signal").median().alias("median"),
        pl.col("signal").quantile(0.75, interpolation="linear").alias("q75"),
        pl.col("signal").max().alias("max"),
    ).row(0, named=True)
    return SignalSummaryStats(
        total_rows=total,
        valid_count=valid,
        null_count=nulls,
        coverage_pct=cov,
        mean=_finite_float(agg["mean"]),
        std=_finite_float(agg["std"]),
        min=_finite_float(agg["min"]),
        q25=_finite_float(agg["q25"]),
        median=_finite_float(agg["median"]),
        q75=_finite_float(agg["q75"]),
        max=_finite_float(agg["max"]),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a stateless, resource-guarded FastAPI instance for AnQuantLab."""
    cfg = settings or load_settings()
    store = WorkbenchStore(cfg)
    semaphore = asyncio.Semaphore(cfg.max_concurrent)

    app = FastAPI(
        title="AnQuantLab",
        description="Interactive Quantitative Alpha & Falsification Workbench on polars-anta",
        version=__version__,
    )
    app.state.settings = cfg
    app.state.store = store

    async def _run_guarded(fn: Any, *args: Any) -> Any:
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(fn, *args),
                    timeout=cfg.compute_timeout_sec,
                )
            except TimeoutError as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"Computation exceeded {cfg.compute_timeout_sec:.1f}s safety timeout.",
                ) from exc

    @app.get("/api/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        cat = build_catalog()
        return HealthResponse(
            status="ok",
            app_version=__version__,
            polars_anta_version=pa.__version__,
            polars_version=pl.__version__,
            polars_max_threads=cfg.max_threads,
            max_concurrent=cfg.max_concurrent,
            compute_timeout_sec=cfg.compute_timeout_sec,
            max_upload_mb=cfg.max_upload_mb,
            catalog_total_exports=cat.total_exports,
            catalog_public_functions=cat.public_functions,
            dataset_count=store.dataset_count(),
            cached_signals=store.cached_signal_count(),
        )

    @app.get("/api/catalog", response_model=CatalogResponse)
    async def get_catalog() -> CatalogResponse:
        return build_catalog()

    @app.get("/api/datasets", response_model=DatasetListResponse)
    async def list_datasets() -> DatasetListResponse:
        items = await _run_guarded(store.list_datasets)
        default_id = items[0].dataset_id if items else "builtin_demo_panel"
        return DatasetListResponse(default_dataset_id=default_id, datasets=items)

    @app.get("/api/datasets/{dataset_id}/preview", response_model=DatasetPreviewResponse)
    async def preview_dataset(dataset_id: str) -> DatasetPreviewResponse:
        try:
            return await _run_guarded(store.build_preview, dataset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/datasets/upload", response_model=DatasetInfo)
    async def upload_dataset(file: UploadFile = File(...)) -> DatasetInfo:  # noqa: B008
        filename = file.filename or "dataset.csv"
        chunks: list[bytes] = []
        total_read = 0
        limit = cfg.max_upload_bytes
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds {cfg.max_upload_mb} MB safety cap.",
                )
            chunks.append(chunk)
        if total_read == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        raw_bytes = b"".join(chunks)
        try:
            return await _run_guarded(store.register_uploaded_bytes, filename, raw_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to parse dataset: {exc}") from exc

    @app.post("/api/formula/preview", response_model=FormulaPreviewResponse)
    async def preview_formula(req: FormulaPreviewRequest) -> FormulaPreviewResponse:
        t0 = time.perf_counter()
        try:
            sig_df, plan, stages, cache_hit = await _run_guarded(
                store.get_or_compute_signal, req.dataset_id, req.formula
            )
            entry, _ = store.get_frame(req.dataset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FormulaSyntaxError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Signal evaluation error: {exc}") from exc

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        stats = _compute_signal_stats(sig_df)

        avail_syms: list[str] = []
        active_sym: str | None = None
        chart_df = sig_df
        if entry.symbol_col and entry.symbol_col in sig_df.columns:
            avail_syms = sorted(
                str(x) for x in sig_df[entry.symbol_col].drop_nulls().unique().to_list()
            )[:200]
            if req.symbol and req.symbol in avail_syms:
                active_sym = req.symbol
            elif avail_syms:
                active_sym = avail_syms[0]
            if active_sym is not None:
                chart_df = sig_df.filter(pl.col(entry.symbol_col) == active_sym)

        chart_slice = chart_df.tail(req.chart_bars).select(
            pl.col(entry.time_col).cast(pl.String).alias("t"),
            pl.col("open").alias("o"),
            pl.col("high").alias("h"),
            pl.col("low").alias("l"),
            pl.col("close").alias("c"),
            pl.col("volume").alias("v"),
            pl.col("signal").alias("s"),
        )
        chart_points = [
            ChartBarPoint(
                t=row["t"],
                o=float(row["o"]),
                h=float(row["h"]),
                l=float(row["l"]),
                c=float(row["c"]),
                v=float(row["v"]),
                s=_finite_float(row["s"]),
            )
            for row in chart_slice.to_dicts()
        ]

        display_cols = [entry.time_col]
        if entry.symbol_col:
            display_cols.append(entry.symbol_col)
        if entry.sector_col:
            display_cols.append(entry.sector_col)
        display_cols.extend(["open", "high", "low", "close", "volume", "signal"])

        valid_tail = (
            sig_df.filter(pl.col("signal").is_not_null())
            .select(display_cols)
            .tail(req.preview_limit)
            .with_columns(
                pl.col(entry.time_col).cast(pl.String),
                pl.col("signal").round(6),
            )
        )
        return FormulaPreviewResponse(
            dataset_id=req.dataset_id,
            formula=req.formula,
            normalized_formula=plan.normalized_formula,
            cache_hit=cache_hit,
            elapsed_ms=elapsed_ms,
            active_symbol=active_sym,
            available_symbols=avail_syms,
            notes=plan.notes,
            stages=stages,
            stats=stats,
            chart_series=chart_points,
            sample_rows=valid_tail.to_dicts(),
        )

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
