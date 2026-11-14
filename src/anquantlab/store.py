"""In-memory dataset registry, read-only file loader, and LRU signal cache."""

from __future__ import annotations

import hashlib
import io
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import polars_anta as pa

from .config import Settings
from .demo_data import generate_demo_panel, generate_demo_single_futures
from .expr_dsl import CompiledFormulaPlan, evaluate_formula
from .schemas import DatasetInfo, DatasetPreviewResponse, ExecutionStageInfo

_TIME_CANDIDATES = ("date", "timestamp", "datetime", "time")
_SYMBOL_CANDIDATES = ("ticker", "symbol", "asset", "code")
_SECTOR_CANDIDATES = ("sector", "industry", "group")


@dataclass
class DatasetEntry:
    dataset_id: str
    name: str
    source_kind: str
    description: str
    time_col: str
    symbol_col: str | None
    sector_col: str | None
    df: pl.DataFrame | None = None
    readonly_path: Path | None = None
    sha256_prefix: str | None = None


def _hash_bytes_prefix(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _hash_file_prefix(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _detect_col(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    lower_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    return None


def _normalize_ohlcv_frame(df: pl.DataFrame) -> tuple[pl.DataFrame, str, str | None, str | None]:
    rename_map = {
        c: c.strip().lower()
        for c in df.columns
        if c.strip().lower() in {"open", "high", "low", "close", "volume"}
        and c != c.strip().lower()
    }
    if rename_map:
        df = df.rename(rename_map)

    missing = [req for req in ("open", "high", "low", "close", "volume") if req not in df.columns]
    if missing:
        raise ValueError(f"Dataset missing required OHLCV columns: {missing}")

    time_col = _detect_col(df.columns, _TIME_CANDIDATES)
    if time_col is None:
        raise ValueError(f"Dataset must include a time column named one of {_TIME_CANDIDATES}")
    symbol_col = _detect_col(df.columns, _SYMBOL_CANDIDATES)
    sector_col = _detect_col(df.columns, _SECTOR_CANDIDATES)

    casts: list[pl.Expr] = [
        pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume")
    ]
    if df.schema[time_col] == pl.String:
        casts.append(pl.col(time_col).str.to_datetime(strict=False).alias(time_col))
    if symbol_col is not None:
        casts.append(pl.col(symbol_col).cast(pl.String))
    if sector_col is not None:
        casts.append(pl.col(sector_col).cast(pl.String))

    out = df.with_columns(casts)
    sort_keys = [symbol_col, time_col] if symbol_col else [time_col]
    return out.sort(sort_keys), time_col, symbol_col, sector_col


class WorkbenchStore:
    """In-memory store for OHLCV datasets and bounded LRU-cached alpha signals."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._datasets: dict[str, DatasetEntry] = {}
        self._signal_cache: OrderedDict[
            tuple[str, str], tuple[pl.DataFrame, CompiledFormulaPlan, list[ExecutionStageInfo]]
        ] = OrderedDict()
        self._register_builtins()
        self._register_readonly_paths()

    def _register_builtins(self) -> None:
        self._datasets["builtin_demo_panel"] = DatasetEntry(
            dataset_id="builtin_demo_panel",
            name="Synthetic Multi-Asset Panel (24 Tickers, 6 Sectors)",
            source_kind="builtin",
            description="Deterministic 504-day cross-sectional equity universe (seed=42).",
            time_col="date",
            symbol_col="ticker",
            sector_col="sector",
            df=generate_demo_panel(),
            sha256_prefix=_hash_bytes_prefix(b"builtin_demo_panel_v1_seed42_24x504"),
        )
        self._datasets["builtin_demo_futures"] = DatasetEntry(
            dataset_id="builtin_demo_futures",
            name="Synthetic Intraday Futures (5m, 1,200 Bars)",
            source_kind="builtin",
            description="Single-contract 5m intraday series for candlestick & MAE/MFE testing.",
            time_col="timestamp",
            symbol_col="ticker",
            sector_col=None,
            df=generate_demo_single_futures(),
            sha256_prefix=_hash_bytes_prefix(b"builtin_demo_futures_v1_seed104_1200"),
        )

    def _register_readonly_paths(self) -> None:
        candidates = list(self.settings.readonly_paths)
        if self.settings.auto_discover_sibling_data:
            repo_root = Path(__file__).resolve().parents[2]
            sibling_vn = repo_root.parent / "polars-anta" / "research" / "data" / "vn_daily.parquet"
            if sibling_vn.is_file() and sibling_vn not in candidates:
                candidates.append(sibling_vn)

        for path in candidates:
            slug = re.sub(r"[^a-z0-9_]+", "_", f"preset_{path.stem.lower()}").strip("_")
            if slug in self._datasets:
                continue
            try:
                schema = (
                    pl.read_parquet_schema(path)
                    if path.suffix.lower() == ".parquet"
                    else pl.read_csv(path, n_rows=5).schema
                )
                cols = list(schema.keys())
                self._datasets[slug] = DatasetEntry(
                    dataset_id=slug,
                    name=f"Read-Only Preset: {path.name}",
                    source_kind="readonly_file",
                    description=f"Lazy-loaded read-only local file ({path.name}).",
                    time_col=_detect_col(cols, _TIME_CANDIDATES) or "date",
                    symbol_col=_detect_col(cols, _SYMBOL_CANDIDATES),
                    sector_col=_detect_col(cols, _SECTOR_CANDIDATES),
                    df=None,
                    readonly_path=path,
                    sha256_prefix=_hash_file_prefix(path),
                )
            except Exception:
                continue

    def _ensure_loaded(self, entry: DatasetEntry) -> pl.DataFrame:
        if entry.df is not None:
            return entry.df
        if entry.readonly_path is None or not entry.readonly_path.is_file():
            raise KeyError(f"Backing file unavailable for dataset '{entry.dataset_id}'.")
        raw = (
            pl.read_parquet(entry.readonly_path)
            if entry.readonly_path.suffix.lower() == ".parquet"
            else pl.read_csv(entry.readonly_path, try_parse_dates=True)
        )
        norm_df, t_col, s_col, sec_col = _normalize_ohlcv_frame(raw)
        entry.df = norm_df
        entry.time_col = t_col
        entry.symbol_col = s_col
        entry.sector_col = sec_col
        return norm_df

    def _to_info(self, entry: DatasetEntry) -> DatasetInfo:
        if entry.df is None:
            cols = (
                list(pl.read_parquet_schema(entry.readonly_path).keys())
                if (entry.readonly_path and entry.readonly_path.suffix.lower() == ".parquet")
                else []
            )
            return DatasetInfo(
                dataset_id=entry.dataset_id,
                name=entry.name,
                source_kind=entry.source_kind,
                description=entry.description,
                time_col=entry.time_col,
                symbol_col=entry.symbol_col,
                sector_col=entry.sector_col,
                columns=cols,
                sha256_prefix=entry.sha256_prefix,
                loaded=False,
            )
        df = entry.df
        sym_cnt = int(df[entry.symbol_col].n_unique()) if entry.symbol_col else 1
        return DatasetInfo(
            dataset_id=entry.dataset_id,
            name=entry.name,
            source_kind=entry.source_kind,
            description=entry.description,
            row_count=df.height,
            symbol_count=sym_cnt,
            date_start=str(df[entry.time_col].min()) if df.height else None,
            date_end=str(df[entry.time_col].max()) if df.height else None,
            time_col=entry.time_col,
            symbol_col=entry.symbol_col,
            sector_col=entry.sector_col,
            columns=list(df.columns),
            sha256_prefix=entry.sha256_prefix,
            loaded=True,
        )

    def list_datasets(self) -> list[DatasetInfo]:
        return [self._to_info(e) for e in self._datasets.values()]

    def dataset_count(self) -> int:
        return len(self._datasets)

    def cached_signal_count(self) -> int:
        return len(self._signal_cache)

    def get_frame(self, dataset_id: str) -> tuple[DatasetEntry, pl.DataFrame]:
        entry = self._datasets.get(dataset_id)
        if entry is None:
            raise KeyError(f"Unknown dataset_id '{dataset_id}'.")
        return entry, self._ensure_loaded(entry)

    def register_uploaded_bytes(self, filename: str, raw_bytes: bytes) -> DatasetInfo:
        lower = filename.lower()
        buf = io.BytesIO(raw_bytes)
        if lower.endswith(".parquet"):
            raw_df = pl.read_parquet(buf)
        elif lower.endswith(".csv"):
            raw_df = pl.read_csv(buf, try_parse_dates=True)
        else:
            raise ValueError("Only .parquet and .csv uploads are supported.")

        norm_df, t_col, s_col, sec_col = _normalize_ohlcv_frame(raw_df)
        digest = _hash_bytes_prefix(raw_bytes)
        stem = re.sub(r"[^a-z0-9_]+", "_", Path(filename).stem.lower()).strip("_") or "upload"
        ds_id = f"upload_{stem}_{digest[:6]}"
        entry = DatasetEntry(
            dataset_id=ds_id,
            name=f"Uploaded: {filename}",
            source_kind="upload",
            description=f"In-memory uploaded dataset ({len(raw_bytes) / 1024:.1f} KB).",
            time_col=t_col,
            symbol_col=s_col,
            sector_col=sec_col,
            df=norm_df,
            sha256_prefix=digest,
        )
        self._datasets[ds_id] = entry
        return self._to_info(entry)

    def build_preview(self, dataset_id: str, sample_size: int = 10) -> DatasetPreviewResponse:
        entry, df = self.get_frame(dataset_id)
        report = pa.validate_ohlcv(
            df,
            time_col=entry.time_col,
            open_col="open",
            high_col="high",
            low_col="low",
            close_col="close",
            volume_col="volume",
            group_by=entry.symbol_col,
            return_report=True,
        )
        valid = bool(report["valid"]) if isinstance(report, dict) else True
        issues = [str(e) for e in report.get("errors", ())] if isinstance(report, dict) else []

        sectors = (
            sorted(str(x) for x in df[entry.sector_col].drop_nulls().unique().to_list())
            if entry.sector_col
            else []
        )
        symbols = (
            sorted(str(x) for x in df[entry.symbol_col].drop_nulls().unique().to_list())[:20]
            if entry.symbol_col
            else []
        )
        head_df = df.head(sample_size).with_columns(pl.col(entry.time_col).cast(pl.String))
        return DatasetPreviewResponse(
            info=self._to_info(entry),
            ohlcv_valid=valid,
            ohlcv_issues=issues,
            sectors=sectors,
            sample_symbols=symbols,
            sample_rows=head_df.to_dicts(),
        )

    def get_or_compute_signal(
        self, dataset_id: str, formula: str
    ) -> tuple[pl.DataFrame, CompiledFormulaPlan, list[ExecutionStageInfo], bool]:
        entry, df = self.get_frame(dataset_id)
        key = (dataset_id, formula.strip())
        if key in self._signal_cache:
            self._signal_cache.move_to_end(key)
            sig_df, plan, stages = self._signal_cache[key]
            return sig_df, plan, stages, True

        sig_df, plan, stages = evaluate_formula(
            df,
            formula,
            time_col=entry.time_col,
            symbol_col=entry.symbol_col,
        )
        self._signal_cache[key] = (sig_df, plan, stages)
        while len(self._signal_cache) > self.settings.max_cached_signals:
            self._signal_cache.popitem(last=False)
        return sig_df, plan, stages, False
