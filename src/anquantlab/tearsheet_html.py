"""Single-File Offline HTML Tearsheet & Inline SVG Renderer (Phase 5)."""

from __future__ import annotations

import html

from .crashtest_schemas import CrashTestRunResponse
from .export_schemas import AlphaPassportDocument
from .schemas import BacktestRunResponse
from .tearsheet_i18n import TEXT, build_executive_summary, localize_label, norm_lang
from .xray_schemas import XRayRunResponse


def _svg_equity_curve(bt_res: BacktestRunResponse, empty_msg: str, aria_lbl: str) -> str:
    pts = bt_res.equity_series
    if len(pts) < 2:
        return f'<div class="muted">{html.escape(empty_msg)}</div>'
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
    net_col = "#2E9E84" if pts[-1].net_eq >= 1.0 else "#C85A62"
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="190" role="img" '
        f'aria-label="{html.escape(aria_lbl)}">'
        f'<rect width="{w}" height="{h}" fill="#0E1117" rx="4"/>'
        f'<line x1="{pad}" y1="{par_y:.1f}" x2="{w - pad}" y2="{par_y:.1f}" '
        f'stroke="#333A4A" stroke-dasharray="3,3"/>'
        f'<polyline fill="none" stroke="#687182" stroke-width="1.1" points="{poly("bench_eq")}"/>'
        f'<polyline fill="none" stroke="#5A8DEE" stroke-width="1.15" stroke-dasharray="4,3" '
        f'points="{poly("gross_eq")}"/>'
        f'<polyline fill="none" stroke="{net_col}" stroke-width="1.6" points="{poly("net_eq")}"/>'
        f"</svg>"
    )


def render_tearsheet_html(
    passport: AlphaPassportDocument,
    bt_res: BacktestRunResponse,
    xr_res: XRayRunResponse,
    ct_res: CrashTestRunResponse,
    py_code: str,
    lang: str = "en",
) -> str:
    """Render a self-contained, zero-network-asset HTML Tearsheet in EN or VI."""
    esc = html.escape
    lcode = norm_lang(lang)
    tr = TEXT[lcode]
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
    vault_lbl = tr["vault_locked"] if d.holdout_locked else tr["vault_full"]
    sha_short = esc(passport.passport_sha256[:24])
    norm_f = esc(passport.signal_spec.normalized_formula)
    clr_txt = esc(localize_label("clearance", passport.overall_clearance, lcode))
    span_verdict_txt = esc(localize_label("spanning", x.spanning_verdict, lcode))
    exec_summary = esc(build_executive_summary(passport, lcode))

    funnel_rows = "".join(
        f"<tr><td>{esc(localize_label('gate', it.gate_label, lcode))}</td>"
        f"<td>{it.survivors}/{it.total}</td>"
        f"<td>{it.survival_pct:.1f}%</td></tr>"
        for it in ct_res.funnel
    )
    stage_rows = "".join(
        f"<tr><td>{esc(localize_label('stage', st.label, lcode))}</td>"
        f"<td>{st.ic_mean:+.4f}</td><td>{st.icir:+.3f}</td>"
        f"<td>{st.nw_t_stat:+.2f}</td><td>{st.top_minus_bottom_bps:+.1f} bps</td>"
        f"<td>{st.max_abs_sector_tilt * 100:.2f}%</td></tr>"
        for st in xr_res.stages
    )
    span_rows = "".join(
        f"<tr><td>{esc(localize_label('factor', ld.factor_label, lcode))}</td>"
        f"<td>{ld.beta:+.4f}</td><td>{ld.nw_t_stat:+.2f}</td>"
        f"<td>{ld.r2_contribution * 100:.2f}%</td>"
        f"<td>{ld.post_ortho_corr:+.4f}</td></tr>"
        for ld in xr_res.spanning.loadings
    )
    ds_foot = esc(
        tr["ds_foot"].format(
            name=d.dataset_name,
            sha=d.sha256_prefix,
            health=d.health_score,
            surv=d.survivorship_grade,
            cs=d.corwin_schultz_median_bps,
        )
    )
    ct_sub = esc(
        tr["kpi_ct_sub"].format(
            nullp=f.null_p_value,
            rw=f.romano_wolf_survivors,
            k=f.grid_candidates,
            eb=f.empirical_bayes_sharpe,
        )
    )
    tl_sub = esc(
        tr["kpi_ledger_sub"].format(
            trials=tl.unique_trials,
            neff=tl.effective_n_trials,
            peeks=tl.holdout_peeks,
        )
    )

    return f"""<!DOCTYPE html>
<html lang="{lcode}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{esc(tr["title"])} - {norm_f}</title>
<style>
  :root {{
    --bg: #0E1117; --pane: #141821; --elev: #1B202C; --bdr: #232A38;
    --txt: #D8DEE9; --sub: #8F98A8; --blue: #5A8DEE;
    --pos: #2E9E84; --neg: #C85A62; --warn: #D48A3B;
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
  .summary-box {{
    background: var(--pane); border-left: 3px solid var(--blue); border-radius: 4px;
    padding: 10px 14px; font-size: 13px; line-height: 1.5;
  }}
  .summary-lbl {{
    font-size: 11px; color: var(--sub); text-transform: uppercase;
    letter-spacing: 0.04em; margin-bottom: 3px;
  }}
  h1 {{ margin: 0 0 4px; font-size: 16px; font-weight: 600; }}
  h2 {{
    margin: 0 0 10px; font-size: 12px; text-transform: uppercase;
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
    margin: 0; padding: 12px; background: #0B0E14; border: 1px solid var(--bdr);
    border-radius: 4px; overflow-x: auto; font-size: 11.5px; line-height: 1.4; color: #D8DEE9;
  }}
  @media (max-width: 820px) {{ .grid-4, .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hdr">
    <div>
      <h1>{esc(tr["title"])}</h1>
      <div class="mono muted">{esc(tr["expr"])}: {norm_f}</div>
      <div class="mono muted">
        Passport SHA-256: {sha_short}... | UTC: {esc(passport.generated_at_utc)}
      </div>
    </div>
    <div class="badge {clr_cls} mono">{clr_txt}</div>
  </header>

  <section class="summary-box">
    <div class="summary-lbl">{esc(tr["summary_heading"])}</div>
    <div>{exec_summary}</div>
  </section>

  <section class="grid-4">
    <div class="card">
      <div class="kpi-lbl">{esc(tr["kpi_net_sr"])}</div>
      <div class="kpi-val {sr_cls}">{b.net_sharpe:+.2f} ({b.total_return * 100:+.2f}%)</div>
      <div class="muted">{
        esc(tr["kpi_net_sub"].format(dd=b.max_drawdown * 100, be=b.breakeven_bps))
    }</div>
    </div>
    <div class="card">
      <div class="kpi-lbl">{esc(tr["kpi_ledger"])}</div>
      <div class="kpi-val">{esc(tr["kpi_ledger_val"].format(dsr=tl.live_dsr * 100))}</div>
      <div class="muted">{tl_sub}</div>
    </div>
    <div class="card">
      <div class="kpi-lbl">{esc(tr["kpi_span"])}</div>
      <div class="kpi-val">{esc(tr["kpi_span_val"].format(pure=x.orthogonal_share * 100))}</div>
      <div class="muted">{
        esc(tr["kpi_span_sub"].format(r2=x.spanning_r2 * 100, verdict=span_verdict_txt))
    }</div>
    </div>
    <div class="card">
      <div class="kpi-lbl">{esc(tr["kpi_ct"])}</div>
      <div class="kpi-val {pbo_cls}">PBO {f.pbo * 100:.1f}%</div>
      <div class="muted">{ct_sub}</div>
    </div>
  </section>

  <section class="grid-2">
    <div class="card">
      <h2>{esc(tr["sec_equity"].format(vault=vault_lbl))}</h2>
      {_svg_equity_curve(bt_res, tr["insufficient_equity"], tr["svg_aria"])}
      <div class="muted mono">{ds_foot}</div>
    </div>
    <div class="card">
      <h2>{esc(tr["sec_funnel"])}</h2>
      <table>
        <thead><tr><th>{esc(tr["th_gate"])}</th><th>{esc(tr["th_surv"])}</th><th>{
        esc(tr["th_share"])
    }</th></tr></thead>
        <tbody>{funnel_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="grid-2">
    <div class="card">
      <h2>{esc(tr["sec_xray"])}</h2>
      <table>
        <thead>
          <tr>
            <th>{esc(tr["th_stage"])}</th><th>{esc(tr["th_ic"])}</th><th>{esc(tr["th_icir"])}</th>
            <th>{esc(tr["th_nwt"])}</th><th>{esc(tr["th_spread"])}</th><th>{esc(tr["th_tilt"])}</th>
          </tr>
        </thead>
        <tbody>{stage_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>{esc(tr["sec_span"])}</h2>
      <table>
        <thead>
          <tr>
            <th>{esc(tr["th_bench"])}</th><th>{esc(tr["th_beta"])}</th><th>{esc(tr["th_dkt"])}</th>
            <th>{esc(tr["th_pratt"])}</th><th>{esc(tr["th_post"])}</th>
          </tr>
        </thead>
        <tbody>{span_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <h2>{esc(tr["sec_code"])}</h2>
    <pre class="mono">{esc(py_code)}</pre>
  </section>
</div>
</body>
</html>
"""
