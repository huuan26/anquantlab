"""Single-File Offline HTML Tearsheet & Inline SVG Renderer (Phase 5)."""

from __future__ import annotations

import html

from .crashtest_schemas import CrashTestRunResponse
from .export_schemas import AlphaPassportDocument
from .schemas import BacktestRunResponse
from .xray_schemas import XRayRunResponse


def _svg_equity_curve(bt_res: BacktestRunResponse) -> str:
    pts = bt_res.equity_series
    if len(pts) < 2:
        return '<div class="muted">Insufficient equity points for chart.</div>'
    w, h, pad = 640, 190, 18
    vals = [v for p in pts for v in (p.net_eq, p.gross_eq, p.bench_eq)]
    lo, hi = min(0.96, *vals), max(1.04, *vals)
    span = max(0.02, hi - lo)

    def poly(getter: str) -> str:
        coords: list[str] = []
        for idx, pt in enumerate(pts):
            px = pad + (idx / (len(pts) - 1)) * (w - 2 * pad)
            py = (h - pad) - ((getattr(pt, getter) - lo) / span) * (h - 2 * pad)
            coords.append(f"{px:.1f},{py:.1f}")
        return " ".join(coords)

    par_y = (h - pad) - ((1.0 - lo) / span) * (h - 2 * pad)
    net_col = "#089981" if pts[-1].net_eq >= 1.0 else "#F23645"
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="190" role="img" '
        f'aria-label="Portfolio Equity Curve">'
        f'<rect width="{w}" height="{h}" fill="#131722" rx="4"/>'
        f'<line x1="{pad}" y1="{par_y:.1f}" x2="{w - pad}" y2="{par_y:.1f}" '
        f'stroke="#434651" stroke-dasharray="3,3"/>'
        f'<polyline fill="none" stroke="#868993" stroke-width="1.2" points="{poly("bench_eq")}"/>'
        f'<polyline fill="none" stroke="#2962FF" stroke-width="1.3" stroke-dasharray="4,3" '
        f'points="{poly("gross_eq")}"/>'
        f'<polyline fill="none" stroke="{net_col}" stroke-width="2.1" points="{poly("net_eq")}"/>'
        f"</svg>"
    )


def render_tearsheet_html(
    passport: AlphaPassportDocument,
    bt_res: BacktestRunResponse,
    xr_res: XRayRunResponse,
    ct_res: CrashTestRunResponse,
    py_code: str,
) -> str:
    """Render a self-contained, zero-network-asset HTML Tearsheet with TradingView styling."""
    esc = html.escape
    b = passport.backtest_audit
    d = passport.dataset_audit
    x = passport.xray_audit
    f = passport.falsification_audit
    tl = passport.trial_ledger_audit
    clr_cls = (
        "pos"
        if passport.overall_clearance == "APPROVED_CANDIDATE"
        else ("neg" if passport.overall_clearance == "REJECTED_OVERFIT" else "warn")
    )
    sr_cls = "pos" if b.net_sharpe > 0 else "neg"
    pbo_cls = "neg" if f.pbo >= 0.5 else "pos"
    vault_lbl = "75% IS Vault" if d.holdout_locked else "Full Sample"
    sha_short = esc(passport.passport_sha256[:24])
    norm_f = esc(passport.signal_spec.normalized_formula)

    funnel_rows = "".join(
        f"<tr><td>{esc(it.gate_label)}</td>"
        f"<td>{it.survivors}/{it.total}</td>"
        f"<td>{it.survival_pct:.1f}%</td></tr>"
        for it in ct_res.funnel
    )
    stage_rows = "".join(
        f"<tr><td>{esc(st.label)}</td><td>{st.ic_mean:+.4f}</td><td>{st.icir:+.3f}</td>"
        f"<td>{st.nw_t_stat:+.2f}</td><td>{st.top_minus_bottom_bps:+.1f} bps</td>"
        f"<td>{st.max_abs_sector_tilt * 100:.2f}%</td></tr>"
        for st in xr_res.stages
    )
    span_rows = "".join(
        f"<tr><td>{esc(ld.factor_label)}</td><td>{ld.beta:+.4f}</td>"
        f"<td>{ld.nw_t_stat:+.2f}</td><td>{ld.r2_contribution * 100:.2f}%</td>"
        f"<td>{ld.post_ortho_corr:+.4f}</td></tr>"
        for ld in xr_res.spanning.loadings
    )
    ds_foot = (
        f"Dataset: {esc(d.dataset_name)} (sha256:{esc(d.sha256_prefix)}) | "
        f"Health {d.health_score:.0f}/100 | Survivorship {esc(d.survivorship_grade)} | "
        f"CS Spread {d.corwin_schultz_median_bps:.1f} bps"
    )
    ct_sub = (
        f"Null p={f.null_p_value:.3f} | "
        f"RW {f.romano_wolf_survivors}/{f.grid_candidates} | "
        f"EB SR {f.empirical_bayes_sharpe:+.2f}"
    )
    tl_sub = (
        f"Trials {tl.unique_trials} | "
        f"N_eff {tl.effective_n_trials:.2f} | "
        f"OOS Peeks {tl.holdout_peeks}"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AnQuantLab Tearsheet - {norm_f}</title>
<style>
  :root {{
    --bg: #131722; --pane: #1E222D; --elev: #2A2E39; --bdr: #2A2E39;
    --txt: #D1D4DC; --sub: #9598A1; --blue: #2962FF;
    --pos: #089981; --neg: #F23645; --warn: #F7931A;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 20px; background: var(--bg); color: var(--txt);
    font: 12.5px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-variant-numeric: tabular-nums;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }}
  .hdr {{
    background: var(--pane); border: 1px solid var(--bdr); border-radius: 4px;
    padding: 14px 16px; display: flex; justify-content: space-between;
    align-items: center; gap: 12px; flex-wrap: wrap;
  }}
  h1 {{ margin: 0 0 4px; font-size: 16px; font-weight: 600; }}
  h2 {{
    margin: 0 0 10px; font-size: 13px; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--sub);
  }}
  .mono {{ font-family: "JetBrains Mono", Consolas, monospace; }}
  .badge {{
    padding: 4px 10px; border-radius: 3px; font-weight: 600;
    font-size: 12px; border: 1px solid currentColor;
  }}
  .pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }}
  .warn {{ color: var(--warn); }} .muted {{ color: var(--sub); }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
  .card {{
    background: var(--pane); border: 1px solid var(--bdr);
    border-radius: 4px; padding: 12px 14px;
  }}
  .kpi-lbl {{ font-size: 11px; color: var(--sub); }}
  .kpi-val {{ font-size: 17px; font-weight: 600; margin: 3px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ padding: 6px 8px; border-bottom: 1px solid var(--bdr); text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: var(--sub); font-weight: 600; font-size: 11px; }}
  pre {{
    margin: 0; padding: 12px; background: #0E111A; border: 1px solid var(--bdr);
    border-radius: 4px; overflow-x: auto; font-size: 11.5px; line-height: 1.4; color: #D1D4DC;
  }}
  @media (max-width: 820px) {{ .grid-4, .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hdr">
    <div>
      <h1>AnQuantLab Quantitative Falsification Tearsheet</h1>
      <div class="mono muted">Expr: {norm_f}</div>
      <div class="mono muted">
        Passport SHA-256: {sha_short}... | UTC: {esc(passport.generated_at_utc)}
      </div>
    </div>
    <div class="badge {clr_cls} mono">{esc(passport.overall_clearance)}</div>
  </header>

  <section class="grid-4">
    <div class="card">
      <div class="kpi-lbl">Net IS Sharpe &amp; Return</div>
      <div class="kpi-val {sr_cls}">{b.net_sharpe:+.2f} ({b.total_return * 100:+.2f}%)</div>
      <div class="muted">
        Max DD {b.max_drawdown * 100:.2f}% | Breakeven {b.breakeven_bps:.1f} bps
      </div>
    </div>
    <div class="card">
      <div class="kpi-lbl">Session Trial Ledger &amp; DSR</div>
      <div class="kpi-val">{tl.live_dsr * 100:.1f}% DSR</div>
      <div class="muted">{tl_sub}</div>
    </div>
    <div class="card">
      <div class="kpi-lbl">5-Factor Zoo Spanning</div>
      <div class="kpi-val">{x.orthogonal_share * 100:.1f}% Pure</div>
      <div class="muted">Spanned R2 {x.spanning_r2 * 100:.1f}% ({esc(x.spanning_verdict)})</div>
    </div>
    <div class="card">
      <div class="kpi-lbl">Overfitting Crash-Test</div>
      <div class="kpi-val {pbo_cls}">PBO {f.pbo * 100:.1f}%</div>
      <div class="muted">{ct_sub}</div>
    </div>
  </section>

  <section class="grid-2">
    <div class="card">
      <h2>Equity Curve (Net vs Gross vs Benchmark - {vault_lbl})</h2>
      {_svg_equity_curve(bt_res)}
      <div class="muted mono">{ds_foot}</div>
    </div>
    <div class="card">
      <h2>7-Stage Romano-Wolf Falsification Funnel</h2>
      <table>
        <thead><tr><th>Econometric Gate</th><th>Survivors</th><th>Share</th></tr></thead>
        <tbody>{funnel_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="grid-2">
    <div class="card">
      <h2>4-Stage Causal Alpha Pipeline X-Ray</h2>
      <table>
        <thead>
          <tr>
            <th>Stage</th><th>IC Mean</th><th>ICIR</th>
            <th>NW t</th><th>Q5-Q1</th><th>Tilt</th>
          </tr>
        </thead>
        <tbody>{stage_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>5-Factor Spanning Loadings (Driscoll-Kraay)</h2>
      <table>
        <thead>
          <tr>
            <th>Benchmark</th><th>Beta</th><th>DK NW t</th>
            <th>Pratt R2</th><th>Post-Ortho</th>
          </tr>
        </thead>
        <tbody>{span_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <h2>Production Polars + polars-anta Code (AST Sandbox Clean)</h2>
    <pre class="mono">{esc(py_code)}</pre>
  </section>
</div>
</body>
</html>
"""
