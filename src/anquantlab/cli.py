"""Command-line entrypoint for launching the AnQuantLab workbench server."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from .config import apply_thread_limits, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anquantlab",
        description="AnQuantLab - Interactive Quantitative Alpha & Falsification Workbench.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve",),
        default="serve",
        help="Optional command alias ('serve' starts the web workbench, default behavior).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind host address (default: ANQUANTLAB_HOST or 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind TCP port (default: ANQUANTLAB_PORT or 8765).",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=None,
        help="Pin POLARS_MAX_THREADS to protect shared server CPU cores (default: 2).",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=None,
        help="Maximum concurrent compute requests (default: 2).",
    )
    parser.add_argument(
        "--data",
        type=Path,
        action="append",
        default=None,
        help="Optional read-only .parquet or .csv file path(s) to register as presets.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a web browser automatically on startup.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print AnQuantLab version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        from . import __version__

        print(f"anquantlab {__version__}")
        return 0

    apply_thread_limits(args.max_threads)
    settings = load_settings(
        host=args.host,
        port=args.port,
        max_threads=args.max_threads,
        max_concurrent=args.max_concurrent,
        extra_readonly_paths=args.data,
    )

    import uvicorn

    from .app import create_app

    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    print(
        f"AnQuantLab listening on {url} "
        f"(POLARS_MAX_THREADS={settings.max_threads}, max_concurrent={settings.max_concurrent})"
    )

    if not args.no_browser and settings.host in {"127.0.0.1", "localhost"}:
        timer = threading.Timer(0.8, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
