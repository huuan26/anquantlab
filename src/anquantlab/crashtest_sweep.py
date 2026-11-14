"""2D parameter perturbation grid and vectorized net-return matrix builder for Tab 3."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

import numpy as np
import polars as pl

from .backtest_metrics import DatasetMicroMeta, build_micro_meta
from .crashtest_schemas import CrashTestRunRequest
from .store import WorkbenchStore


@dataclass
class GridCandidateSpec:
    row: int
    col: int
    name: str
    formula: str
    ema_span: int
    no_trade_buffer: float
    label: str


@dataclass
class GridSweepBundle:
    x_name: str
    y_name: str
    x_labels: list[str]
    y_labels: list[str]
    baseline_row: int
    baseline_col: int
    specs: list[GridCandidateSpec]
    times_is: list[str]
    ret_matrix_is: np.ndarray
    ret_matrix_ledger_is: np.ndarray
    meta: DatasetMicroMeta
    normalized_formula: str
    notes: list[str]


def _find_lookback_constants(tree: ast.Expression) -> list[tuple[ast.Constant, int, str]]:
    """Locate positive integer lookback literals (>= 3) inside AST function arguments."""
    found: list[tuple[ast.Constant, int, str]] = []

    def _walk(node: ast.AST, parent_fn: str | None = None) -> None:
        if isinstance(node, ast.Call):
            fn_name = node.func.id if isinstance(node.func, ast.Name) else "fn"
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, int)
                    and not isinstance(arg.value, bool)
                    and 3 <= arg.value <= 500
                ):
                    found.append((arg, int(arg.value), fn_name))
                else:
                    _walk(arg, fn_name)
            for kw in node.keywords:
                if (
                    isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, int)
                    and not isinstance(kw.value.value, bool)
                    and 3 <= kw.value.value <= 500
                ):
                    found.append((kw.value, int(kw.value.value), f"{fn_name}.{kw.arg}"))
                else:
                    _walk(kw.value, fn_name)
            return
        for child in ast.iter_child_nodes(node):
            _walk(child, parent_fn)

    _walk(tree.body)
    return found


def _make_distinct_int_axis(base_val: int, g: int) -> tuple[list[int], int]:
    mults_map = {
        3: [0.65, 1.0, 1.40],
        4: [0.60, 0.82, 1.0, 1.35],
        5: [0.55, 0.78, 1.0, 1.25, 1.55],
    }
    mults = mults_map[g]
    base_idx = mults.index(1.0)
    raw = [max(2, int(round(base_val * m))) for m in mults]
    raw[base_idx] = base_val
    # Enforce strictly increasing distinct integers around base_idx
    for i in range(base_idx - 1, -1, -1):
        if raw[i] >= raw[i + 1]:
            raw[i] = max(2, raw[i + 1] - 1)
    for i in range(base_idx + 1, g):
        if raw[i] <= raw[i - 1]:
            raw[i] = raw[i - 1] + 1
    return raw, base_idx


def _mutate_formula_ints(formula: str, replacements: dict[int, int]) -> str:
    tree = ast.parse(formula, mode="eval")
    cloned = copy.deepcopy(tree)
    slots = _find_lookback_constants(cloned)
    for slot_idx, new_val in replacements.items():
        if 0 <= slot_idx < len(slots):
            slots[slot_idx][0].value = int(new_val)
    return ast.unparse(cloned)


def build_2d_parameter_grid(
    formula: str, req: CrashTestRunRequest
) -> tuple[
    str,
    str,
    list[str],
    list[str],
    int,
    int,
    list[GridCandidateSpec],
]:
    """Construct a G x G 2D parameter grid for any valid formula."""
    g = int(req.grid_size)
    spans_map = {3: [1, 4, 12], 4: [1, 3, 7, 15], 5: [1, 3, 6, 12, 20]}
    bufs_map = {
        3: [0.0, 0.015, 0.04],
        4: [0.0, 0.01, 0.025, 0.05],
        5: [0.0, 0.01, 0.02, 0.04, 0.07],
    }
    spans = spans_map[g]
    bufs = bufs_map[g]

    tree = ast.parse(formula, mode="eval")
    slots = _find_lookback_constants(tree) if req.sweep_mode == "auto_2d" else []

    specs: list[GridCandidateSpec] = []
    if len(slots) >= 2:
        _, v0, fn0 = slots[0]
        _, v1, fn1 = slots[1]
        xs, bx = _make_distinct_int_axis(v0, g)
        ys, by = _make_distinct_int_axis(v1, g)
        x_name = f"{fn0} ({v0})"
        y_name = f"{fn1} ({v1})"
        x_labels = [str(v) for v in xs]
        y_labels = [str(v) for v in ys]
        for r_i, yv in enumerate(ys):
            for c_j, xv in enumerate(xs):
                f_mut = _mutate_formula_ints(formula, {0: xv, 1: yv})
                specs.append(
                    GridCandidateSpec(
                        row=r_i,
                        col=c_j,
                        name=f"G_{r_i}_{c_j}",
                        formula=f_mut,
                        ema_span=1,
                        no_trade_buffer=0.0,
                        label=f"{fn0}={xv}, {fn1}={yv}",
                    )
                )
        return x_name, y_name, x_labels, y_labels, by, bx, specs

    if len(slots) == 1:
        _, v0, fn0 = slots[0]
        xs, bx = _make_distinct_int_axis(v0, g)
        x_name = f"{fn0} ({v0})"
        y_name = "EMA Smooth"
        x_labels = [str(v) for v in xs]
        y_labels = [f"{s}b" for s in spans]
        for r_i, sp in enumerate(spans):
            for c_j, xv in enumerate(xs):
                f_mut = _mutate_formula_ints(formula, {0: xv})
                specs.append(
                    GridCandidateSpec(
                        row=r_i,
                        col=c_j,
                        name=f"G_{r_i}_{c_j}",
                        formula=f_mut,
                        ema_span=sp,
                        no_trade_buffer=0.0,
                        label=f"{fn0}={xv}, ema={sp}b",
                    )
                )
        return x_name, y_name, x_labels, y_labels, 0, bx, specs

    x_name = "EMA Smooth"
    y_name = "No-Trade Buf"
    x_labels = [f"{s}b" for s in spans]
    y_labels = [f"{b:.3f}" for b in bufs]
    for r_i, bf in enumerate(bufs):
        for c_j, sp in enumerate(spans):
            specs.append(
                GridCandidateSpec(
                    row=r_i,
                    col=c_j,
                    name=f"G_{r_i}_{c_j}",
                    formula=formula,
                    ema_span=sp,
                    no_trade_buffer=bf,
                    label=f"ema={sp}b, buf={bf:.3f}",
                )
            )
    return x_name, y_name, x_labels, y_labels, 0, 0, specs


def _apply_hysteresis_buffer(weights: np.ndarray, buf: float) -> np.ndarray:
    """Apply causal no-trade deadzone across (T, N_assets) weight matrix."""
    if buf <= 1e-9 or weights.shape[0] <= 1:
        return weights
    out = weights.copy()
    prev = out[0].copy()
    for t in range(1, out.shape[0]):
        cur = out[t]
        hold_mask = np.abs(cur - prev) < buf
        cur = np.where(hold_mask, prev, cur)
        out[t] = cur
        prev = cur
    return out


def evaluate_grid_returns(
    store: WorkbenchStore,
    req: CrashTestRunRequest,
) -> GridSweepBundle:
    """Evaluate all G x G candidate configurations into a causal (T_eval, K) return matrix."""
    _, base_plan, _, _ = store.get_or_compute_signal(req.dataset_id, req.formula)
    entry, raw_df = store.get_frame(req.dataset_id)
    time_col = entry.time_col
    sym_col = entry.symbol_col

    sort_cols = [sym_col, time_col] if (sym_col and sym_col in raw_df.columns) else [time_col]
    base_sorted = raw_df.sort(sort_cols)
    meta = build_micro_meta(base_sorted, time_col, sym_col)

    x_name, y_name, x_labels, y_labels, b_row, b_col, specs = build_2d_parameter_grid(
        base_plan.normalized_formula, req
    )
    notes = list(base_plan.notes)

    # Pivot asset returns and endogenous half-spread onto (T, N_assets) dense matrices
    u_times_df = base_sorted.select(pl.col(time_col).drop_nulls().unique().sort()).with_row_index(
        "_t_i"
    )
    n_t = u_times_df.height
    u_syms = (
        sorted(str(s) for s in base_sorted[sym_col].drop_nulls().unique().to_list())
        if sym_col
        else ["_single"]
    )
    sym_map = {s: idx for idx, s in enumerate(u_syms)}
    n_s = len(u_syms)

    over_sym = (lambda e: e.over(sym_col)) if (sym_col and n_s > 1) else (lambda e: e)
    with_ret = base_sorted.with_columns(
        over_sym(pl.col("close") / pl.col("close").shift(1) - 1.0).fill_null(0.0).alias("_ret"),
        meta.micro_df["_cs_half_rate"],
    ).join(u_times_df, on=time_col, how="left")

    t_idx_arr = with_ret["_t_i"].to_numpy()
    s_idx_arr = (
        np.asarray([sym_map[str(v)] for v in with_ret[sym_col].to_list()], dtype=np.int32)
        if sym_col
        else np.zeros(with_ret.height, dtype=np.int32)
    )

    ret_2d = np.zeros((n_t, n_s), dtype=np.float64)
    ret_2d[t_idx_arr, s_idx_arr] = np.nan_to_num(with_ret["_ret"].to_numpy(), nan=0.0)

    fee_r = req.fee_bps * 1e-4
    base_slip_r = req.slippage_bps * 1e-4
    cost_2d = np.full((n_t, n_s), fee_r + base_slip_r, dtype=np.float64)
    if req.slippage_mode == "corwin_schultz":
        cs_2d = np.zeros((n_t, n_s), dtype=np.float64)
        cs_2d[t_idx_arr, s_idx_arr] = np.nan_to_num(
            with_ret["_cs_half_rate"].to_numpy(), nan=0.0005
        )
        cost_2d = cost_2d + cs_2d

    # Evaluate unique formulas once
    unique_formulas = list(dict.fromkeys(sp.formula for sp in specs))
    sig_2d_map: dict[str, np.ndarray] = {}
    join_keys = [sym_col, time_col] if sym_col else [time_col]
    for f_str in unique_formulas:
        s_df, _, _, _ = store.get_or_compute_signal(req.dataset_id, f_str)
        aligned = base_sorted.select(join_keys).join(
            s_df.select([*join_keys, "signal"]), on=join_keys, how="left"
        )
        mat = np.full((n_t, n_s), np.nan, dtype=np.float64)
        mat[t_idx_arr, s_idx_arr] = aligned["signal"].cast(pl.Float64).to_numpy()
        sig_2d_map[f_str] = mat

    delist_per_bar = (req.delisting_penalty_bps_yr * 1e-4) / max(1.0, meta.annualization)
    scheme = req.weight_scheme

    k_total = len(specs)
    port_rets_full = np.zeros((n_t, k_total), dtype=np.float64)

    for k_idx, sp in enumerate(specs):
        s_mat = sig_2d_map[sp.formula].copy()
        if sp.ema_span > 1 and n_t > 1:
            alpha = 2.0 / (sp.ema_span + 1.0)
            for t in range(1, n_t):
                prev_row = s_mat[t - 1]
                cur_row = s_mat[t]
                both = np.isfinite(prev_row) & np.isfinite(cur_row)
                s_mat[t] = np.where(both, alpha * cur_row + (1.0 - alpha) * prev_row, cur_row)

        # Convert signal at t -> target weight, then lag by 1 bar (strict causal execution!)
        w_target = np.zeros((n_t, n_s), dtype=np.float64)
        finite = np.isfinite(s_mat)
        if scheme == "dollar_neutral":
            if n_s >= 2:
                row_cnt = np.sum(finite, axis=1, keepdims=True)
                s_zero = np.where(finite, s_mat, 0.0)
                row_mean = np.sum(s_zero, axis=1, keepdims=True) / np.maximum(1, row_cnt)
                dem = np.where(finite & (row_cnt >= 2), s_mat - row_mean, 0.0)
                l1 = np.sum(np.abs(dem), axis=1, keepdims=True)
                w_target = np.where(l1 > 1e-12, dem / np.maximum(l1, 1e-12), 0.0)
            else:
                w_target = np.where(finite & (np.abs(s_mat) > 1e-12), np.sign(s_mat), 0.0)
        elif scheme == "long_only":
            pos = np.where(finite & (s_mat > 0.0), s_mat, 0.0)
            if n_s >= 2:
                s_pos = np.sum(pos, axis=1, keepdims=True)
                w_target = np.where(s_pos > 1e-12, pos / np.maximum(s_pos, 1e-12), 0.0)
            else:
                w_target = np.where(pos > 0.0, 1.0, 0.0)
        elif scheme == "equal_weight":
            if n_s >= 2:
                act = np.where(finite & (np.abs(s_mat) > 1e-12), np.sign(s_mat), 0.0)
                cnt = np.sum(np.abs(act) > 0, axis=1, keepdims=True)
                w_target = np.where(cnt > 0, act / np.maximum(cnt, 1), 0.0)
            else:
                w_target = np.where(finite & (s_mat > 0.0), 1.0, 0.0)
        else:
            clipped = np.where(finite, np.clip(s_mat, -1.0, 1.0), 0.0)
            w_target = clipped / max(1, n_s)

        w_exec = np.zeros_like(w_target)
        if n_t > 1:
            w_exec[1:] = w_target[:-1]
        if sp.no_trade_buffer > 1e-9:
            w_exec = _apply_hysteresis_buffer(w_exec, sp.no_trade_buffer)

        dw = np.zeros_like(w_exec)
        dw[0] = np.abs(w_exec[0])
        if n_t > 1:
            dw[1:] = np.abs(w_exec[1:] - w_exec[:-1])

        gross_r = np.sum(w_exec * ret_2d, axis=1)
        fric_c = np.sum(dw * cost_2d, axis=1)
        long_gross = np.sum(np.maximum(w_exec, 0.0), axis=1)
        port_rets_full[:, k_idx] = gross_r - fric_c - (long_gross * delist_per_bar)

    ledger_is_end = meta.is_bars if meta.split_time is not None else n_t
    eval_end = ledger_is_end if req.holdout_locked else n_t
    times_all = u_times_df[time_col].cast(pl.String).to_list()
    return GridSweepBundle(
        x_name=x_name,
        y_name=y_name,
        x_labels=x_labels,
        y_labels=y_labels,
        baseline_row=b_row,
        baseline_col=b_col,
        specs=specs,
        times_is=times_all[:eval_end],
        ret_matrix_is=port_rets_full[:eval_end, :],
        ret_matrix_ledger_is=port_rets_full[:ledger_is_end, :],
        meta=meta,
        normalized_formula=base_plan.normalized_formula,
        notes=notes,
    )
