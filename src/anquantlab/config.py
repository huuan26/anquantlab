"""Stateless environment configuration and HFT-safe resource guards for AnQuantLab."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 1024) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, val))


def _env_float(name: str, default: float, minimum: float = 0.5, maximum: float = 600.0) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, val))


def _parse_readonly_paths(raw: str) -> tuple[Path, ...]:
    if not raw.strip():
        return ()
    sep = ";" if ";" in raw else os.pathsep
    paths: list[Path] = []
    for part in raw.split(sep):
        cleaned = part.strip()
        if cleaned:
            p = Path(cleaned).expanduser()
            if p.is_file():
                paths.append(p.resolve())
    return tuple(paths)


def apply_thread_limits(explicit_threads: int | None = None) -> int:
    """Pin POLARS_MAX_THREADS before Polars initializes its Rust Rayon pool.

    On shared low-latency servers (e.g., hft-server), capping worker threads
    to 2 prevents analytical queries from starving live execution cores.
    """
    threads = (
        max(1, min(64, int(explicit_threads)))
        if explicit_threads is not None
        else _env_int("ANQUANTLAB_MAX_THREADS", default=2, minimum=1, maximum=64)
    )
    if explicit_threads is not None:
        os.environ["POLARS_MAX_THREADS"] = str(threads)
    else:
        os.environ.setdefault("POLARS_MAX_THREADS", str(threads))
    return int(os.environ["POLARS_MAX_THREADS"])


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings populated from ANQUANTLAB_* environment variables."""

    host: str = "127.0.0.1"
    port: int = 8765
    max_threads: int = 2
    max_concurrent: int = 2
    compute_timeout_sec: float = 15.0
    max_upload_mb: int = 50
    max_cached_signals: int = 32
    readonly_paths: tuple[Path, ...] = ()
    auto_discover_sibling_data: bool = True

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def load_settings(
    *,
    host: str | None = None,
    port: int | None = None,
    max_threads: int | None = None,
    max_concurrent: int | None = None,
    extra_readonly_paths: list[Path] | None = None,
) -> Settings:
    """Load portable configuration from environment variables with optional CLI overrides."""
    resolved_threads = apply_thread_limits(max_threads)
    resolved_host = host or os.environ.get("ANQUANTLAB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    resolved_port = (
        max(1, min(65535, int(port)))
        if port is not None
        else _env_int("ANQUANTLAB_PORT", default=8765, minimum=1, maximum=65535)
    )
    resolved_concurrent = (
        max(1, min(32, int(max_concurrent)))
        if max_concurrent is not None
        else _env_int("ANQUANTLAB_MAX_CONCURRENT", default=2, minimum=1, maximum=32)
    )
    compute_timeout = _env_float(
        "ANQUANTLAB_COMPUTE_TIMEOUT_SEC", default=15.0, minimum=1.0, maximum=300.0
    )
    max_upload_mb = _env_int("ANQUANTLAB_MAX_UPLOAD_MB", default=50, minimum=1, maximum=500)
    max_cached = _env_int("ANQUANTLAB_MAX_CACHED_SIGNALS", default=32, minimum=4, maximum=256)

    env_paths = list(_parse_readonly_paths(os.environ.get("ANQUANTLAB_READONLY_PATHS", "")))
    if extra_readonly_paths:
        for p in extra_readonly_paths:
            rp = p.expanduser().resolve()
            if rp.is_file() and rp not in env_paths:
                env_paths.append(rp)

    auto_discover = os.environ.get("ANQUANTLAB_AUTO_DISCOVER_SIBLING", "1").strip() not in {
        "0",
        "false",
        "False",
    }

    return Settings(
        host=resolved_host,
        port=resolved_port,
        max_threads=resolved_threads,
        max_concurrent=resolved_concurrent,
        compute_timeout_sec=compute_timeout,
        max_upload_mb=max_upload_mb,
        max_cached_signals=max_cached,
        readonly_paths=tuple(env_paths),
        auto_discover_sibling_data=auto_discover,
    )
