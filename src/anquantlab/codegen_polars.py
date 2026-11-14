"""Pure Polars + polars-anta standalone strategy code generator with AST sandbox verification."""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass

from .catalog import CS_FUNCTIONS, build_catalog, get_expression_functions
from .codegen_template import render_standalone_script
from .export_schemas import ExportBundleRequest
from .expr_dsl import MAX_AST_NODES, MAX_CALL_DEPTH, FormulaSyntaxError

_FORBIDDEN_IMPORTS = {
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
    "ftplib",
    "paramiko",
    "ctypes",
    "multiprocessing",
}
_FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "system",
    "popen",
    "rmtree",
    "remove",
    "unlink",
}


def verify_ast_sandbox_clean(py_code: str) -> list[str]:
    """Verify generated Python source passes strict AST security sandbox rules."""
    tree = ast.parse(py_code)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_IMPORTS:
                    violations.append(f"L{node.lineno}: Forbidden import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _FORBIDDEN_IMPORTS:
                violations.append(f"L{node.lineno}: Forbidden from-import '{node.module}'")
        elif isinstance(node, ast.Call):
            fn = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else (node.func.attr if isinstance(node.func, ast.Attribute) else "")
            )
            if fn in _FORBIDDEN_CALLS:
                violations.append(f"L{node.lineno}: Forbidden call '{fn}()'")
            if fn == "open" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if any(m in str(node.args[1].value) for m in ("w", "a", "x", "+")):
                    violations.append(f"L{node.lineno}: Write-mode open() blocked")
    return violations


def slugify_formula(formula: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", formula.strip().lower()).strip("_")
    return (slug[:38] or "alpha_signal").rstrip("_")


@dataclass(frozen=True)
class _CodeExpr:
    code: str
    uses_ts_op: bool = False


class _PolarsCodeEmitter:
    """Transpiles whitelisted DSL AST into standalone Polars + polars-anta expressions."""

    def __init__(
        self, columns: set[str], time_col: str, symbol_col: str | None, has_panel: bool
    ) -> None:
        self.columns = columns
        self.time_col = time_col
        self.symbol_col = symbol_col
        self.has_panel = has_panel
        self.expr_fns = get_expression_functions()
        self.all_catalog_names = {it.name: it.kind for it in build_catalog().items}
        self.stage_lines: list[str] = []
        self.tmp_cols: list[str] = []
        self._tmp_idx = 0

    def _alloc_stage(self, expr_code: str, over_var: str | None) -> str:
        col_name = f"__aql_tmp_{self._tmp_idx}"
        self._tmp_idx += 1
        self.tmp_cols.append(col_name)
        wrapped = f"({expr_code}).over({over_var})" if over_var else f"({expr_code})"
        self.stage_lines.append(f"    work = work.with_columns({wrapped}.alias({col_name!r}))")
        return f"pl.col({col_name!r})"

    def emit(self, formula: str) -> tuple[list[str], str, bool, list[str]]:
        cleaned = formula.strip()
        if not cleaned:
            raise FormulaSyntaxError("Formula must not be empty.")
        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as exc:
            raise FormulaSyntaxError(f"Invalid formula syntax: {exc.msg}") from exc
        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            raise FormulaSyntaxError("Formula exceeds maximum AST complexity.")
        root = self._visit(tree.body, 0)
        return self.stage_lines, root.code, root.uses_ts_op, self.tmp_cols

    def _visit_arg(self, node: ast.AST, depth: int) -> object:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool, str)) or node.value is None:
                return node.value
            raise FormulaSyntaxError(f"Unsupported constant: {type(node.value).__name__}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            if isinstance(node.operand, ast.Constant) and isinstance(
                node.operand.value, (int, float)
            ):
                return -node.operand.value if isinstance(node.op, ast.USub) else +node.operand.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._visit_arg(elt, depth + 1) for elt in node.elts]
        return self._visit(node, depth)

    def _fmt_cs_arg(self, val: object) -> str:
        if isinstance(val, list):
            return "[" + ", ".join(self._fmt_cs_arg(v) for v in val) + "]"
        if isinstance(val, _CodeExpr):
            if val.uses_ts_op and self.has_panel and self.symbol_col:
                return self._alloc_stage(val.code, "SYMBOL_COL")
            return val.code
        return repr(val)

    def _fmt_ts_arg(self, val: object) -> tuple[str, bool]:
        if isinstance(val, _CodeExpr):
            return val.code, val.uses_ts_op
        if isinstance(val, list):
            parts: list[str] = []
            any_ts = False
            for item in val:
                c_str, u_ts = self._fmt_ts_arg(item)
                parts.append(c_str)
                any_ts = any_ts or u_ts
            return "[" + ", ".join(parts) + "]", any_ts
        return repr(val), False

    def _visit(self, node: ast.AST, depth: int) -> _CodeExpr:
        if depth > MAX_CALL_DEPTH:
            raise FormulaSyntaxError("Formula nesting exceeds depth limit.")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool)):
                return _CodeExpr(f"pl.lit({node.value!r})", False)
            if isinstance(node.value, str) and node.value in self.columns:
                return _CodeExpr(f"pl.col({node.value!r})", False)
            raise FormulaSyntaxError(f"Unknown column or literal '{node.value}'.")
        if isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id not in self.columns:
                raise FormulaSyntaxError(f"Unknown or forbidden identifier '{node.id}'.")
            return _CodeExpr(f"pl.col({node.id!r})", False)
        if isinstance(node, ast.UnaryOp):
            op = self._visit(node.operand, depth + 1)
            if isinstance(node.op, ast.USub):
                return _CodeExpr(f"(-({op.code}))", op.uses_ts_op)
            if isinstance(node.op, ast.UAdd):
                return _CodeExpr(op.code, op.uses_ts_op)
            if isinstance(node.op, ast.Invert):
                return _CodeExpr(f"(~({op.code}))", op.uses_ts_op)
            raise FormulaSyntaxError("Unsupported unary operator.")
        if isinstance(node, ast.BinOp):
            lc = self._visit(node.left, depth + 1)
            rc = self._visit(node.right, depth + 1)
            ts = lc.uses_ts_op or rc.uses_ts_op
            sym_map = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Mod: "%",
                ast.BitAnd: "&",
                ast.BitOr: "|",
            }
            if type(node.op) in sym_map:
                return _CodeExpr(f"({lc.code} {sym_map[type(node.op)]} {rc.code})", ts)
            if isinstance(node.op, ast.Div):
                div_s = (
                    f"pl.when(({rc.code}) != 0.0).then(({lc.code}) / ({rc.code})).otherwise(None)"
                )
                return _CodeExpr(div_s, ts)
            if isinstance(node.op, ast.Pow):
                return _CodeExpr(f"({lc.code}).pow({rc.code})", ts)
            raise FormulaSyntaxError("Unsupported binary operator.")
        if isinstance(node, ast.BoolOp):
            parts = [self._visit(v, depth + 1) for v in node.values]
            joiner = " & " if isinstance(node.op, ast.And) else " | "
            expr_s = joiner.join(f"({p.code})" for p in parts)
            return _CodeExpr(f"({expr_s})", any(p.uses_ts_op for p in parts))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            cmp_map = {
                ast.Gt: ">",
                ast.GtE: ">=",
                ast.Lt: "<",
                ast.LtE: "<=",
                ast.Eq: "==",
                ast.NotEq: "!=",
            }
            op_s = cmp_map.get(type(node.ops[0]))
            if op_s is None:
                raise FormulaSyntaxError("Unsupported comparison.")
            lc = self._visit(node.left, depth + 1)
            rc = self._visit(node.comparators[0], depth + 1)
            return _CodeExpr(f"({lc.code} {op_s} {rc.code})", lc.uses_ts_op or rc.uses_ts_op)
        if isinstance(node, ast.Call):
            return self._visit_call(node, depth)
        raise FormulaSyntaxError(f"Unsupported AST construct: {type(node).__name__}")

    def _visit_call(self, node: ast.Call, depth: int) -> _CodeExpr:
        if not isinstance(node.func, ast.Name):
            raise FormulaSyntaxError("Method/attribute calls are forbidden.")
        fn = node.func.id
        builtins = {
            "abs",
            "sign",
            "log",
            "sqrt",
            "clip",
            "where",
            "coalesce",
            "field",
            "shift",
            "pct_change",
        }
        if fn in builtins:
            args: list[str] = []
            any_ts = fn in {"shift", "pct_change"}
            for idx, a in enumerate(node.args):
                if fn == "field" and idx == 1 and isinstance(a, ast.Constant):
                    args.append(repr(str(a.value)))
                else:
                    c_s, u_ts = self._fmt_ts_arg(self._visit_arg(a, depth + 1))
                    args.append(c_s)
                    any_ts = any_ts or u_ts
            templates = {
                "abs": lambda x: f"({x}).abs()",
                "sign": lambda x: f"({x}).sign()",
                "log": lambda x: f"pl.when(({x}) > 0.0).then(({x}).log()).otherwise(None)",
                "sqrt": lambda x: f"pl.when(({x}) >= 0.0).then(({x}).sqrt()).otherwise(None)",
                "clip": lambda x, lo, hi: (
                    f"({x}).clip(lower_bound=float({lo}), upper_bound=float({hi}))"
                ),
                "where": lambda c, a, b: f"pl.when({c}).then({a}).otherwise({b})",
                "coalesce": lambda a, b: f"pl.coalesce([{a}, {b}])",
                "field": lambda s, nm: f"({s}).struct.field({nm})",
                "shift": lambda x, n="1": f"({x}).shift(int({n}))",
                "pct_change": lambda x, n="1": f"({x}).pct_change(n=int({n}))",
            }
            return _CodeExpr(templates[fn](*args), any_ts)

        if fn not in self.expr_fns:
            raise FormulaSyntaxError(f"Function '{fn}' is not a bar-signal expression.")
        target_fn, kind = self.expr_fns[fn]
        sig = inspect.signature(target_fn)

        if kind == "expr_cs" or fn in CS_FUNCTIONS:
            cs_pos = [self._fmt_cs_arg(self._visit_arg(a, depth + 1)) for a in node.args]
            cs_kw: list[str] = []
            seen_over = False
            for kw in node.keywords:
                assert kw.arg is not None
                if kw.arg == "over":
                    seen_over = True
                val_s = (
                    repr(kw.value.id)
                    if (kw.arg == "by" and isinstance(kw.value, ast.Name))
                    else self._fmt_cs_arg(self._visit_arg(kw.value, depth + 1))
                )
                cs_kw.append(f"{kw.arg}={val_s}")
            if "over" in sig.parameters and not seen_over and self.has_panel:
                cs_kw.append("over=TIME_COL")
            call_code = f"pa.{fn}({', '.join(cs_pos + cs_kw)})"
            return _CodeExpr(self._alloc_stage(call_code, None), False)

        ts_pos = [self._fmt_ts_arg(self._visit_arg(a, depth + 1))[0] for a in node.args]
        ts_kw: list[str] = []
        for kw in node.keywords:
            assert kw.arg is not None
            pkey = "open_" if (kw.arg == "open" and "open_" in sig.parameters) else kw.arg
            ts_kw.append(f"{pkey}={self._fmt_ts_arg(self._visit_arg(kw.value, depth + 1))[0]}")
        return _CodeExpr(f"pa.{fn}({', '.join(ts_pos + ts_kw)})", True)


def generate_polars_script(
    req: ExportBundleRequest,
    *,
    columns: set[str],
    time_col: str,
    symbol_col: str | None,
    has_panel: bool,
    annualization: float,
    close_hm: tuple[int, int] | None,
    dataset_sha256: str,
) -> str:
    """Emit a self-contained, AST-sandbox-verified Polars + polars-anta strategy module."""
    emitter = _PolarsCodeEmitter(
        columns=columns,
        time_col=time_col,
        symbol_col=symbol_col if has_panel else None,
        has_panel=has_panel,
    )
    stage_lines, final_code, final_uses_ts, tmp_cols = emitter.emit(req.formula)
    final_wrapped = (
        f"({final_code}).over(SYMBOL_COL)"
        if (final_uses_ts and has_panel and symbol_col)
        else final_code
    )
    script = render_standalone_script(
        req,
        time_col=time_col,
        symbol_col=symbol_col,
        has_panel=has_panel,
        annualization=annualization,
        close_hm=close_hm,
        dataset_sha256=dataset_sha256,
        stage_lines=stage_lines,
        final_wrapped=final_wrapped,
        all_tmps=[*tmp_cols, "__aql_raw_sig"],
    )
    violations = verify_ast_sandbox_clean(script)
    if violations:
        raise RuntimeError(f"Generated code violated AST sandbox: {violations}")
    return script
