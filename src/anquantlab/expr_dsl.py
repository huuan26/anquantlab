"""Safe AST-whitelisted formula DSL compiler with causal multi-pass Polars staging."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from .catalog import CS_FUNCTIONS, build_catalog, get_expression_functions
from .schemas import ExecutionStageInfo

MAX_AST_NODES = 160
MAX_CALL_DEPTH = 12

_NUMERIC_DTYPES = (
    pl.Float64,
    pl.Float32,
    pl.Int64,
    pl.Int32,
    pl.Int16,
    pl.Int8,
    pl.UInt64,
    pl.UInt32,
    pl.UInt16,
    pl.UInt8,
)

_BIN_OPS: dict[type[ast.operator], Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: pl.when(b != 0.0).then(a / b).otherwise(None),
    ast.Pow: lambda a, b: a.pow(b),
    ast.Mod: lambda a, b: a % b,
    ast.BitAnd: lambda a, b: a & b,
    ast.BitOr: lambda a, b: a | b,
}

_CMP_OPS: dict[type[ast.cmpop], Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


class FormulaSyntaxError(ValueError):
    """Raised when a user formula violates AST whitelist or signature constraints."""


@dataclass(frozen=True)
class _CompiledNode:
    expr: pl.Expr
    uses_ts_op: bool = False


@dataclass
class CompiledFormulaPlan:
    formula: str
    normalized_formula: str
    stages: list[tuple[str, pl.Expr, str, str | None, str]] = field(default_factory=list)
    final_expr: pl.Expr = field(default_factory=lambda: pl.lit(0.0))
    final_uses_ts: bool = False
    notes: list[str] = field(default_factory=list)

    def stage_infos(self, final_window: str | None) -> list[ExecutionStageInfo]:
        infos = [
            ExecutionStageInfo(stage_index=idx, scope=scope, window_over=win, description=desc)
            for idx, (_, _, scope, win, desc) in enumerate(self.stages, start=1)
        ]
        infos.append(
            ExecutionStageInfo(
                stage_index=len(infos) + 1,
                scope="final_signal",
                window_over=final_window,
                description=f"Materialize output column 'signal' ({self.normalized_formula})",
            )
        )
        return infos


def _safe_primitives() -> dict[str, tuple[Any, bool]]:
    return {
        "abs": (lambda x: x.abs(), False),
        "sign": (lambda x: x.sign(), False),
        "log": (lambda x: pl.when(x > 0.0).then(x.log()).otherwise(None), False),
        "sqrt": (lambda x: pl.when(x >= 0.0).then(x.sqrt()).otherwise(None), False),
        "clip": (lambda x, lo, hi: x.clip(lower_bound=float(lo), upper_bound=float(hi)), False),
        "where": (lambda cond, a, b: pl.when(cond).then(a).otherwise(b), False),
        "coalesce": (lambda a, b: pl.coalesce([a, b]), False),
        "field": (lambda s, name: s.struct.field(str(name)), False),
        "shift": (lambda x, n=1: x.shift(int(n)), True),
        "pct_change": (lambda x, n=1: x.pct_change(n=int(n)), True),
    }


class _ASTFormulaCompiler:
    def __init__(
        self, columns: set[str], time_col: str | None, symbol_col: str | None, has_panel: bool
    ) -> None:
        self.columns = columns
        self.time_col = time_col
        self.symbol_col = symbol_col
        self.has_panel = has_panel
        self.expr_fns = get_expression_functions()
        self.primitives = _safe_primitives()
        self.all_catalog_names = {it.name: it.kind for it in build_catalog().items}
        self.stages: list[tuple[str, pl.Expr, str, str | None, str]] = []
        self.notes: list[str] = []
        self._tmp_counter = 0

    def _alloc_stage(
        self, expr: pl.Expr, scope: str, window_over: str | None, desc: str
    ) -> pl.Expr:
        col_name = f"__aql_tmp_{self._tmp_counter}"
        self._tmp_counter += 1
        staged_expr = expr.over(window_over) if window_over is not None else expr
        self.stages.append((col_name, staged_expr.alias(col_name), scope, window_over, desc))
        return pl.col(col_name)

    def compile_root(self, formula: str) -> CompiledFormulaPlan:
        cleaned = formula.strip()
        if not cleaned:
            raise FormulaSyntaxError("Formula must not be empty.")
        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as exc:
            raise FormulaSyntaxError(f"Invalid formula syntax: {exc.msg}") from exc

        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > MAX_AST_NODES:
            raise FormulaSyntaxError(
                f"Formula exceeds maximum AST complexity ({node_count} > {MAX_AST_NODES} nodes)."
            )
        root = self._visit(tree.body, depth=0)
        return CompiledFormulaPlan(
            formula=formula,
            normalized_formula=ast.unparse(tree.body),
            stages=self.stages,
            final_expr=root.expr,
            final_uses_ts=root.uses_ts_op,
            notes=self.notes,
        )

    def _visit_arg_value(self, node: ast.AST, depth: int) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool, str)) or node.value is None:
                return node.value
            raise FormulaSyntaxError(f"Unsupported constant type: {type(node.value).__name__}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            if isinstance(node.operand, ast.Constant) and isinstance(
                node.operand.value, (int, float)
            ):
                return -node.operand.value if isinstance(node.op, ast.USub) else +node.operand.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._visit_arg_value(elt, depth + 1) for elt in node.elts]
        return self._visit(node, depth + 1)

    def _materialize_for_cs(self, val: Any, fn_name: str) -> Any:
        if isinstance(val, list):
            return [self._materialize_for_cs(v, fn_name) for v in val]
        if isinstance(val, _CompiledNode):
            if val.uses_ts_op and self.has_panel and self.symbol_col:
                return self._alloc_stage(
                    val.expr,
                    scope="time_series",
                    window_over=self.symbol_col,
                    desc=f"Pre-stage time-series input for {fn_name}(...)",
                )
            return val.expr
        return val

    def _unwrap_ts_arg(self, val: Any) -> tuple[Any, bool]:
        if isinstance(val, _CompiledNode):
            return val.expr, val.uses_ts_op
        if isinstance(val, list):
            items: list[Any] = []
            any_ts = False
            for item in val:
                u_val, u_ts = self._unwrap_ts_arg(item)
                items.append(u_val)
                any_ts = any_ts or u_ts
            return items, any_ts
        return val, False

    def _visit(self, node: ast.AST, depth: int) -> _CompiledNode:
        if depth > MAX_CALL_DEPTH:
            raise FormulaSyntaxError(f"Formula nesting exceeds depth limit ({MAX_CALL_DEPTH}).")

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool)):
                return _CompiledNode(pl.lit(node.value), uses_ts_op=False)
            if isinstance(node.value, str) and node.value in self.columns:
                return _CompiledNode(pl.col(node.value), uses_ts_op=False)
            raise FormulaSyntaxError(
                f"Unknown column or unsupported literal '{node.value}'. "
                f"Columns: {sorted(self.columns)}"
            )

        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise FormulaSyntaxError("Private/dunder identifiers are forbidden.")
            if node.id in self.columns:
                return _CompiledNode(pl.col(node.id), uses_ts_op=False)
            raise FormulaSyntaxError(
                f"Unknown column '{node.id}'. Available columns: {sorted(self.columns)}"
            )

        if isinstance(node, ast.UnaryOp):
            operand = self._visit(node.operand, depth + 1)
            if isinstance(node.op, ast.USub):
                return _CompiledNode(-operand.expr, operand.uses_ts_op)
            if isinstance(node.op, ast.UAdd):
                return _CompiledNode(operand.expr, operand.uses_ts_op)
            if isinstance(node.op, ast.Invert):
                return _CompiledNode(~operand.expr, operand.uses_ts_op)
            raise FormulaSyntaxError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BinOp):
            fn = _BIN_OPS.get(type(node.op))
            if fn is None:
                raise FormulaSyntaxError(f"Unsupported binary operator: {type(node.op).__name__}")
            left = self._visit(node.left, depth + 1)
            right = self._visit(node.right, depth + 1)
            return _CompiledNode(fn(left.expr, right.expr), left.uses_ts_op or right.uses_ts_op)

        if isinstance(node, ast.BoolOp):
            vals = [self._visit(v, depth + 1) for v in node.values]
            acc, uses_ts = vals[0].expr, vals[0].uses_ts_op
            for nxt in vals[1:]:
                uses_ts = uses_ts or nxt.uses_ts_op
                acc = (acc & nxt.expr) if isinstance(node.op, ast.And) else (acc | nxt.expr)
            return _CompiledNode(acc, uses_ts)

        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise FormulaSyntaxError("Chained comparisons are not supported; combine with &.")
            cmp_fn = _CMP_OPS.get(type(node.ops[0]))
            if cmp_fn is None:
                raise FormulaSyntaxError(f"Unsupported comparison: {type(node.ops[0]).__name__}")
            left = self._visit(node.left, depth + 1)
            right = self._visit(node.comparators[0], depth + 1)
            return _CompiledNode(cmp_fn(left.expr, right.expr), left.uses_ts_op or right.uses_ts_op)

        if isinstance(node, ast.Call):
            return self._visit_call(node, depth)

        raise FormulaSyntaxError(
            f"Forbidden AST construct '{type(node).__name__}'. Only column identifiers, "
            "arithmetic/logical operators, and whitelisted polars-anta functions are allowed."
        )

    def _visit_call(self, node: ast.Call, depth: int) -> _CompiledNode:
        if not isinstance(node.func, ast.Name):
            raise FormulaSyntaxError(
                "Method/attribute calls are disabled. Use functions or field(expr, 'name')."
            )
        fn_name = node.func.id
        if any(kw.arg is None for kw in node.keywords) or any(
            isinstance(a, ast.Starred) for a in node.args
        ):
            raise FormulaSyntaxError("Starred *args / **kwargs unpacking is forbidden.")

        if fn_name in self.primitives:
            prim_fn, any_ts = self.primitives[fn_name]
            p_args: list[Any] = []
            for a in node.args:
                raw_v = (
                    a.value
                    if (fn_name == "field" and isinstance(a, ast.Constant))
                    else self._visit_arg_value(a, depth + 1)
                )
                u_val, u_ts = self._unwrap_ts_arg(raw_v)
                p_args.append(u_val)
                any_ts = any_ts or u_ts
            try:
                return _CompiledNode(prim_fn(*p_args), uses_ts_op=any_ts)
            except Exception as exc:
                raise FormulaSyntaxError(f"Error in {fn_name}(...): {exc}") from exc

        if fn_name not in self.expr_fns:
            cat_kind = self.all_catalog_names.get(fn_name)
            if cat_kind in {"expr_reduction", "frame", "class"}:
                raise FormulaSyntaxError(
                    f"'{fn_name}' ({cat_kind}) is a portfolio/inference routine, not a bar signal."
                )
            raise FormulaSyntaxError(f"Function '{fn_name}' is not in the polars-anta whitelist.")

        target_fn, kind = self.expr_fns[fn_name]
        sig = inspect.signature(target_fn)

        if kind == "expr_cs" or fn_name in CS_FUNCTIONS:
            cs_args = [
                self._materialize_for_cs(self._visit_arg_value(a, depth + 1), fn_name)
                for a in node.args
            ]
            cs_kwargs: dict[str, Any] = {}
            for kw in node.keywords:
                assert kw.arg is not None
                cs_kwargs[kw.arg] = (
                    kw.value.id
                    if (kw.arg == "by" and isinstance(kw.value, ast.Name))
                    else self._materialize_for_cs(
                        self._visit_arg_value(kw.value, depth + 1), fn_name
                    )
                )
            if (
                "over" in sig.parameters
                and "over" not in cs_kwargs
                and self.time_col
                and self.has_panel
            ):
                cs_kwargs["over"] = self.time_col
            try:
                cs_expr = target_fn(*cs_args, **cs_kwargs)
            except Exception as exc:
                raise FormulaSyntaxError(f"Invalid arguments to {fn_name}(...): {exc}") from exc
            staged_ref = self._alloc_stage(
                cs_expr,
                scope="cross_section",
                window_over=None,
                desc=f"Cross-sectional transform {fn_name}(...) grouped by {self.time_col}",
            )
            return _CompiledNode(staged_ref, uses_ts_op=False)

        ts_args = [self._unwrap_ts_arg(self._visit_arg_value(a, depth + 1))[0] for a in node.args]
        ts_kwargs: dict[str, Any] = {}
        for kw in node.keywords:
            assert kw.arg is not None
            pkey = "open_" if (kw.arg == "open" and "open_" in sig.parameters) else kw.arg
            ts_kwargs[pkey] = self._unwrap_ts_arg(self._visit_arg_value(kw.value, depth + 1))[0]

        try:
            return _CompiledNode(target_fn(*ts_args, **ts_kwargs), uses_ts_op=True)
        except Exception as exc:
            raise FormulaSyntaxError(f"Invalid arguments to {fn_name}(...): {exc}") from exc


def evaluate_formula(
    df: pl.DataFrame,
    formula: str,
    *,
    time_col: str,
    symbol_col: str | None = None,
) -> tuple[pl.DataFrame, CompiledFormulaPlan, list[ExecutionStageInfo]]:
    """Compile and causally evaluate a DSL formula onto a sorted copy of ``df``."""
    sort_cols = [symbol_col, time_col] if symbol_col and symbol_col in df.columns else [time_col]
    work = df.sort(sort_cols)
    has_panel = bool(symbol_col and symbol_col in work.columns and work[symbol_col].n_unique() > 1)

    plan = _ASTFormulaCompiler(
        columns=set(work.columns),
        time_col=time_col,
        symbol_col=symbol_col if has_panel else None,
        has_panel=has_panel,
    ).compile_root(formula)

    tmp_cols: list[str] = []
    for col_name, staged_expr, _, _, _ in plan.stages:
        work = work.with_columns(staged_expr)
        tmp_cols.append(col_name)

    final_win = symbol_col if (plan.final_uses_ts and has_panel and symbol_col) else None
    raw_final = plan.final_expr.over(final_win) if final_win is not None else plan.final_expr
    work = work.with_columns(raw_final.alias("__aql_raw_sig"))
    tmp_cols.append("__aql_raw_sig")

    sig_dtype = work.schema["__aql_raw_sig"]
    if isinstance(sig_dtype, pl.Struct):
        num_fields = [f.name for f in sig_dtype.fields if f.dtype in _NUMERIC_DTYPES]
        chosen = num_fields[0] if num_fields else sig_dtype.fields[0].name
        all_fields = [f.name for f in sig_dtype.fields]
        plan.notes.append(f"Struct output auto-extracted field '{chosen}' (fields: {all_fields}).")
        sig_col = pl.col("__aql_raw_sig").struct.field(chosen).cast(pl.Float64)
    else:
        sig_col = pl.col("__aql_raw_sig").cast(pl.Float64)

    work = work.with_columns(
        pl.when(sig_col.is_finite()).then(sig_col).otherwise(None).alias("signal")
    ).drop(tmp_cols)
    return work, plan, plan.stage_infos(final_win)
