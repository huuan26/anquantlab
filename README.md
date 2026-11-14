# AnQuantLab

Interactive Quantitative Alpha & Falsification Workbench built on [polars-anta](https://pypi.org/project/polars-anta/).

## Overview

`anquantlab` provides a zero-Node.js, offline-capable quantitative research workbench combining:

1. **Dynamic 223-Function API Catalog & Safe Causal Formula DSL**: AST-whitelisted expression compiler with automatic multi-pass `.over(symbol)` and `.over(timestamp)` causal staging.
2. **Backtest & Realtime Cost/Buffer Lab**: Interactive cost, slippage, volatility target, and hysteresis buffer evaluation.
3. **Alpha Pipeline X-Ray**: Step-by-step cross-sectional diagnostics (`Raw -> cs_winsorize -> neutralize -> orthogonalize`).
4. **Overfitting & Falsification Crash-Test**: Parameter sweep heatmaps, CSCV Probability of Backtest Overfitting, Deflated Sharpe Ratio, Empirical-Bayes shrinkage, and Romano-Wolf falsification funnels.

## Quick Start

```bash
pip install anquantlab
anquantlab --port 8765
```

## Resource Safety Configuration

All operational bounds are controlled via environment variables (`ANQUANTLAB_*`) for safe co-location on shared research or low-latency servers:

- `ANQUANTLAB_HOST` (default `127.0.0.1`)
- `ANQUANTLAB_PORT` (default `8765`)
- `ANQUANTLAB_MAX_THREADS` (default `2`, pins `POLARS_MAX_THREADS` before Polars initializes)
- `ANQUANTLAB_MAX_CONCURRENT` (default `2`)
- `ANQUANTLAB_COMPUTE_TIMEOUT_SEC` (default `15.0`)
- `ANQUANTLAB_MAX_UPLOAD_MB` (default `50`)
- `ANQUANTLAB_READONLY_PATHS` (optional semicolon/colon-separated `.parquet`/`.csv` file paths)
