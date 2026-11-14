"""Dynamic introspection catalog for all public exports in polars-anta."""

from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Any

import polars_anta as pa

from .schemas import CatalogItem, CatalogResponse, DomainSummary, ParameterSpec

DOMAIN_MODULES: tuple[tuple[str, str], ...] = (
    ("trend", "Trend & Overlays"),
    ("momentum", "Momentum Oscillators"),
    ("volatility", "Volatility & Channels"),
    ("volume", "Volume & Flow"),
    ("stats", "Quantitative Statistics"),
    ("alpha", "Alpha & Microstructure"),
    ("evaluation", "Evaluation & Risk Metrics"),
    ("backtest", "Vectorized Backtesting"),
    ("resample", "Resampling & Bars"),
    ("inference", "Econometric Inference"),
)

CS_FUNCTIONS: frozenset[str] = frozenset(
    {
        "cs_rank",
        "cs_zscore",
        "cs_winsorize",
        "neutralize",
        "orthogonalize",
        "ts_scale",
    }
)

REDUCTION_FUNCTIONS: frozenset[str] = frozenset(
    {
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "profit_factor",
        "win_rate",
        "value_at_risk",
        "conditional_var",
        "omega_ratio",
        "tail_ratio",
        "probabilistic_sharpe_ratio",
        "deflated_sharpe_ratio",
    }
)

KNOWN_STRUCT_FUNCTIONS: frozenset[str] = frozenset(
    {
        "macd",
        "ppo",
        "stochastic",
        "stoch_rsi",
        "bollinger_bands",
        "keltner_channels",
        "donchian_channels",
        "adx",
        "aroon",
        "ichimoku",
        "supertrend",
        "ssl_channel",
        "heikin_ashi",
        "pivot_points",
        "chandelier_exit",
        "vwap_bands",
        "squeeze_momentum",
        "trix",
        "tsi",
        "kst",
        "oi_regime",
        "triple_barrier_labels",
        "trend_scanning_labels",
    }
)

_PARAM_SAMPLE_MAP: dict[str, str] = {
    "close": "close",
    "open": "open",
    "open_": "open",
    "high": "high",
    "low": "low",
    "volume": "volume",
    "expr": "close",
    "x": "close",
    "y": "volume",
    "a": "close",
    "b": "sma(close, 20)",
    "asset_returns": "pct_change(close, 1)",
    "benchmark_returns": "pct_change(open, 1)",
    "returns_or_equity": "pct_change(close, 1)",
    "returns": "pct_change(close, 1)",
    "by": "sector",
    "factors": "[volume]",
    "spot": "close",
    "futures": "open",
    "open_interest": "volume",
    "entries": "crosses_above(ema(close, 10), ema(close, 30))",
    "exits": "crosses_below(ema(close, 10), ema(close, 30))",
}


def _first_doc_line(obj: Any) -> str:
    doc = inspect.getdoc(obj) or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.rstrip(".")
    return obj.__name__


def _format_default(val: Any) -> str | None:
    if val is inspect.Parameter.empty:
        return None
    if isinstance(val, str):
        return f'"{val}"'
    return repr(val)


def _classify_export(name: str, obj: Any, sig: inspect.Signature | None) -> str:
    if inspect.isclass(obj):
        return "class"
    ret = str(sig.return_annotation) if sig is not None else ""
    if "Expr" in ret:
        if name in CS_FUNCTIONS:
            return "expr_cs"
        if name in REDUCTION_FUNCTIONS:
            return "expr_reduction"
        return "expr_ts"
    return "frame"


def _build_sample_formula(
    name: str, kind: str, params: list[ParameterSpec], returns_struct: bool
) -> str:
    if kind not in {"expr_ts", "expr_cs"}:
        return f"{name}(...)"
    if name == "cs_rank":
        return "cs_rank(rsi(close, 14))"
    if name == "cs_zscore":
        return "cs_zscore(ts_delta(close, 5))"
    if name == "cs_winsorize":
        return "cs_winsorize(rsi(close, 14))"
    if name == "neutralize":
        return "neutralize(cs_winsorize(rsi(close, 14)), sector)"
    if name == "orthogonalize":
        return "orthogonalize(rsi(close, 14), [amihud_illiquidity(close, volume, 20)])"

    req_args: list[str] = []
    for p in params:
        if p.required:
            req_args.append(_PARAM_SAMPLE_MAP.get(p.name, "close"))
    if not req_args and params:
        first_p = params[0]
        req_args.append(_PARAM_SAMPLE_MAP.get(first_p.name, "close"))

    call_str = f"{name}({', '.join(req_args)})"
    if returns_struct:
        return call_str
    return call_str


@lru_cache(maxsize=1)
def build_catalog() -> CatalogResponse:
    """Scan polars_anta submodules and return structured metadata for all exports."""
    items: list[CatalogItem] = []
    domains: list[DomainSummary] = []
    seen: set[str] = set()

    for domain_key, domain_label in DOMAIN_MODULES:
        mod = getattr(pa, domain_key)
        mod_exports: list[str] = list(getattr(mod, "__all__", ()))
        fn_count = 0

        for name in mod_exports:
            if name in seen:
                continue
            seen.add(name)
            obj = getattr(pa, name)
            is_cls = inspect.isclass(obj)
            if not is_cls:
                fn_count += 1

            sig: inspect.Signature | None = None
            params: list[ParameterSpec] = []
            sig_text = f"{name}(...)"
            if not is_cls:
                sig = inspect.signature(obj)
                sig_Parts: list[str] = []
                for p in sig.parameters.values():
                    dflt = _format_default(p.default)
                    req = p.default is inspect.Parameter.empty and p.kind not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                    ann = None if p.annotation is inspect.Parameter.empty else str(p.annotation)
                    params.append(
                        ParameterSpec(
                            name=p.name,
                            required=req,
                            default=dflt,
                            annotation=ann,
                        )
                    )
                    sig_Parts.append(f"{p.name}={dflt}" if dflt is not None else p.name)
                sig_text = f"{name}({', '.join(sig_Parts)})"
            else:
                sig_text = f"class {name}"

            kind = _classify_export(name, obj, sig)
            doc_full = inspect.getdoc(obj) or ""
            returns_struct = (name in KNOWN_STRUCT_FUNCTIONS) or ("Struct(" in doc_full)
            sample = _build_sample_formula(name, kind, params, returns_struct)

            items.append(
                CatalogItem(
                    name=name,
                    domain=domain_key,
                    domain_label=domain_label,
                    kind=kind,
                    signature=sig_text,
                    summary=_first_doc_line(obj),
                    returns_struct=returns_struct,
                    sample_formula=sample,
                    parameters=params,
                )
            )

        domains.append(
            DomainSummary(
                domain=domain_key,
                label=domain_label,
                count=len(mod_exports),
                function_count=fn_count,
            )
        )

    total_exports = len(items)
    exported_classes = sum(1 for it in items if it.kind == "class")
    public_functions = total_exports - exported_classes

    return CatalogResponse(
        polars_anta_version=pa.__version__,
        total_exports=total_exports,
        public_functions=public_functions,
        exported_classes=exported_classes,
        domains=domains,
        items=items,
    )


def get_expression_functions() -> dict[str, tuple[Any, str]]:
    """Return mapping of {fn_name: (callable, kind)} for DSL-eligible Polars expressions."""
    cat = build_catalog()
    out: dict[str, tuple[Any, str]] = {}
    for item in cat.items:
        if item.kind in {"expr_ts", "expr_cs"}:
            out[item.name] = (getattr(pa, item.name), item.kind)
    return out
