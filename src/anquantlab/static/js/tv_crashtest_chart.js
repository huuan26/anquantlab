/**
 * HiDPI TradingView 4-Quadrant Overfitting Crash-Test & Small-Sample Stress Canvas.
 * Renders: (1) 2D Divergent Parameter Heatmap, (2) Multiple-Testing Sharpe Haircut + CSCV PBO,
 * (3) 200 Stationary Bootstrap Fan Chart / OLS-CUSUM Bridge, (4) 7-Stage Romano-Wolf Funnel.
 */

function readPalette() {
  const cs = getComputedStyle(document.documentElement);
  const g = (k, fb) => cs.getPropertyValue(k).trim() || fb;
  return {
    bg: g("--tv-bg-canvas", "#131722"),
    pane: g("--tv-bg-pane", "#1E222D"),
    elev: g("--tv-bg-elevated", "#2A2E39"),
    border: g("--tv-border", "#2A2E39"),
    borderStrong: g("--tv-border-strong", "#434651"),
    text: g("--tv-text-primary", "#D1D4DC"),
    sub: g("--tv-text-secondary", "#9598A1"),
    muted: g("--tv-text-muted", "#868993"),
    blue: g("--tv-blue", "#2962FF"),
    up: g("--tv-up", "#089981"),
    down: g("--tv-down", "#F23645"),
    warn: g("--tv-warn", "#F7931A"),
  };
}

function snap(v) {
  return Math.floor(v) + 0.5;
}

function heatCellFill(sr, maxAbs) {
  const norm = Math.max(-1, Math.min(1, sr / Math.max(0.4, maxAbs)));
  const alpha = (0.12 + 0.62 * Math.abs(norm)).toFixed(3);
  if (norm >= 0.02) return `rgba(8, 153, 129, ${alpha})`;
  if (norm <= -0.02) return `rgba(242, 54, 69, ${alpha})`;
  return "rgba(134, 137, 147, 0.14)";
}

export class TVCrashTestChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.report = null;
    this.bottomLeftMode = "bootstrap"; // "bootstrap" | "cusum"

    this._ro = new ResizeObserver(() => this.render());
    if (this.canvas && this.canvas.parentElement) {
      this._ro.observe(this.canvas.parentElement);
    }
  }

  setData(report) {
    this.report = report || null;
    this.render();
  }

  setBottomLeftMode(mode) {
    this.bottomLeftMode = mode;
    this.render();
  }

  render() {
    if (!this.canvas || !this.canvas.parentElement) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const w = Math.max(320, Math.floor(rect.width));
    const h = Math.max(220, Math.floor(rect.height));
    const dpr = window.devicePixelRatio || 1;
    if (this.canvas.width !== Math.floor(w * dpr) || this.canvas.height !== Math.floor(h * dpr)) {
      this.canvas.width = Math.floor(w * dpr);
      this.canvas.height = Math.floor(h * dpr);
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
    }

    const ctx = this.ctx;
    ctx.save();
    ctx.scale(dpr, dpr);
    const pal = readPalette();

    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, w, h);

    if (!this.report) {
      ctx.fillStyle = pal.muted;
      ctx.font = "12px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Running 2D parameter sweep & Romano-Wolf falsification...", w / 2, h / 2);
      ctx.restore();
      return;
    }

    const midX = Math.floor(w * 0.48);
    const midY = Math.floor(h * 0.5);

    ctx.strokeStyle = pal.border;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(snap(midX), 0);
    ctx.lineTo(snap(midX), h);
    ctx.moveTo(0, snap(midY));
    ctx.lineTo(w, snap(midY));
    ctx.stroke();

    this._drawHeatmap(ctx, 0, 0, midX, midY, pal);
    this._drawHaircutAndPbo(ctx, midX, 0, w - midX, midY, pal);
    if (this.bottomLeftMode === "cusum") {
      this._drawCusum(ctx, 0, midY, midX, h - midY, pal);
    } else {
      this._drawBootstrapFan(ctx, 0, midY, midX, h - midY, pal);
    }
    this._drawFunnel(ctx, midX, midY, w - midX, h - midY, pal);
    ctx.restore();
  }

  _drawHeader(ctx, x, y, w, title, rightMeta, pal) {
    ctx.font = "600 11px Inter, sans-serif";
    ctx.fillStyle = pal.text;
    ctx.textAlign = "left";
    ctx.fillText(title, x + 12, y + 16);
    if (rightMeta) {
      ctx.font = "10.5px 'JetBrains Mono', monospace";
      ctx.fillStyle = pal.sub;
      ctx.textAlign = "right";
      ctx.fillText(rightMeta, x + w - 12, y + 16);
    }
  }

  _drawHeatmap(ctx, x, y, w, h, pal) {
    const hm = this.report.heatmap;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      `2D Net Sharpe Surface (${hm.y_name} x ${hm.x_name})`,
      `Plateau ${hm.neighbor_plateau_ratio.toFixed(2)} | Pos ${(hm.positive_grid_share * 100).toFixed(0)}%`,
      pal
    );

    const mat = hm.sharpe_matrix || [];
    const nRows = mat.length;
    const nCols = nRows ? mat[0].length : 0;
    if (!nRows || !nCols) return;

    const padL = x + 52;
    const padR = x + w - 14;
    const topY = y + 26;
    const botY = y + h - 22;
    const gridW = Math.max(40, padR - padL);
    const gridH = Math.max(40, botY - topY);
    const cellW = gridW / nCols;
    const cellH = gridH / nRows;

    let maxAbs = 0.5;
    for (const row of mat) {
      for (const v of row) maxAbs = Math.max(maxAbs, Math.abs(v));
    }

    for (let r = 0; r < nRows; r++) {
      const cy = topY + r * cellH;
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = pal.sub;
      ctx.textAlign = "right";
      ctx.fillText(String(hm.y_labels[r] || ""), padL - 6, cy + cellH * 0.5 + 3.5);

      for (let c = 0; c < nCols; c++) {
        const cx = padL + c * cellW;
        const val = mat[r][c];
        ctx.fillStyle = heatCellFill(val, maxAbs);
        ctx.fillRect(cx + 1, cy + 1, Math.max(2, cellW - 2), Math.max(2, cellH - 2));

        if (r === hm.baseline_row && c === hm.baseline_col) {
          ctx.strokeStyle = pal.blue;
          ctx.lineWidth = 1.8;
          ctx.strokeRect(
            snap(cx + 1.5),
            snap(cy + 1.5),
            Math.max(2, Math.floor(cellW - 3)),
            Math.max(2, Math.floor(cellH - 3))
          );
        }

        ctx.font = nCols >= 5 ? "600 10px 'JetBrains Mono', monospace" : "600 11px 'JetBrains Mono', monospace";
        ctx.fillStyle = pal.text;
        ctx.textAlign = "center";
        ctx.fillText(`${val >= 0 ? "+" : ""}${val.toFixed(2)}`, cx + cellW * 0.5, cy + cellH * 0.5 + 3.5);
      }
    }

    for (let c = 0; c < nCols; c++) {
      const cx = padL + c * cellW + cellW * 0.5;
      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = pal.sub;
      ctx.textAlign = "center";
      ctx.fillText(String(hm.x_labels[c] || ""), cx, y + h - 7);
    }
  }

  _drawHaircutAndPbo(ctx, x, y, w, h, pal) {
    const pbo = this.report.pbo;
    const splitW = Math.floor(w * 0.56);
    this._drawHeader(
      ctx,
      x,
      y,
      splitW,
      "Multiple-Testing Sharpe Haircut",
      "",
      pal
    );
    this._drawHeader(
      ctx,
      x + splitW,
      y,
      w - splitW,
      "CSCV PBO Logits",
      `PBO ${(pbo.pbo * 100).toFixed(1)}%`,
      pal
    );

    const topY = y + 28;
    const botY = y + h - 20;
    const plotH = Math.max(30, botY - topY);

    // Left: 4 Haircut Bars
    const bars = this.report.haircut_bars || [];
    const hL = x + 12;
    const hR = x + splitW - 12;
    const labelW = 112;
    const statW = 52;
    const bL = hL + labelW;
    const bR = hR - statW;
    const bW = Math.max(24, bR - bL);

    if (bars.length > 0) {
      const vals = bars.map((b) => b.sharpe_equiv);
      const minV = Math.min(0, ...vals);
      const maxV = Math.max(0.4, ...vals);
      const span = Math.max(0.4, maxV - minV);
      const zeroX = bL + ((0 - minV) / span) * bW;

      ctx.strokeStyle = pal.borderStrong;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(snap(zeroX), topY);
      ctx.lineTo(snap(zeroX), botY);
      ctx.stroke();

      const rowH = plotH / bars.length;
      bars.forEach((b, idx) => {
        const ry = topY + idx * rowH + rowH * 0.5;
        ctx.font = "10px Inter, sans-serif";
        ctx.fillStyle = pal.sub;
        ctx.textAlign = "right";
        ctx.fillText(b.stage.replace(/^\d+\.\s*/, ""), bL - 6, ry + 3.5);

        const targetX = bL + ((b.sharpe_equiv - minV) / span) * bW;
        const bh = Math.max(7, Math.min(16, rowH - 8));
        ctx.fillStyle = idx === 0 ? pal.blue : b.sharpe_equiv >= 0 ? pal.up : pal.down;
        if (targetX >= zeroX) {
          ctx.fillRect(zeroX, ry - bh / 2, Math.max(1.5, targetX - zeroX), bh);
        } else {
          ctx.fillRect(targetX, ry - bh / 2, Math.max(1.5, zeroX - targetX), bh);
        }

        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillStyle = pal.text;
        ctx.textAlign = "right";
        ctx.fillText(
          `${b.sharpe_equiv >= 0 ? "+" : ""}${b.sharpe_equiv.toFixed(2)}`,
          hR,
          ry + 3.5
        );
      });
    }

    // Divider
    ctx.strokeStyle = pal.border;
    ctx.beginPath();
    ctx.moveTo(snap(x + splitW), topY - 4);
    ctx.lineTo(snap(x + splitW), botY);
    ctx.stroke();

    // Right: CSCV PBO Logit Histogram
    const pL = x + splitW + 12;
    const pR = x + w - 12;
    const pW = Math.max(30, pR - pL);
    const counts = pbo.logit_hist_counts || [];
    const edges = pbo.logit_hist_edges || [];

    if (counts.length > 0 && edges.length >= 2) {
      const minE = edges[0];
      const maxE = edges[edges.length - 1];
      const spanE = Math.max(1e-6, maxE - minE);
      const maxC = Math.max(1, ...counts);
      const binW = pW / counts.length;

      for (let i = 0; i < counts.length; i++) {
        const bh = (counts[i] / maxC) * (plotH - 8);
        const bx = pL + i * binW + 0.5;
        const by = botY - bh;
        const mid = 0.5 * (edges[i] + edges[i + 1]);
        ctx.fillStyle = mid < 0 ? "rgba(242, 54, 69, 0.72)" : "rgba(8, 153, 129, 0.72)";
        ctx.fillRect(bx, by, Math.max(1.5, binW - 1.5), bh);
      }

      if (minE < 0 && maxE > 0) {
        const zX = pL + ((0 - minE) / spanE) * pW;
        ctx.save();
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = pal.warn;
        ctx.beginPath();
        ctx.moveTo(snap(zX), topY);
        ctx.lineTo(snap(zX), botY);
        ctx.stroke();
        ctx.restore();
      }

      ctx.strokeStyle = pal.borderStrong;
      ctx.beginPath();
      ctx.moveTo(pL, snap(botY));
      ctx.lineTo(pR, snap(botY));
      ctx.stroke();
    } else {
      ctx.font = "10.5px Inter, sans-serif";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "center";
      ctx.fillText("Flat / zero-variance grid", pL + pW / 2, topY + plotH / 2);
    }

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pbo.pbo >= 0.5 ? pal.down : pal.sub;
    ctx.textAlign = "center";
    ctx.fillText(
      `Loss Prob ${(pbo.prob_oos_loss * 100).toFixed(1)}% | Slope ${pbo.degradation_slope.toFixed(2)}`,
      pL + pW / 2,
      y + h - 6
    );
  }

  _drawBootstrapFan(ctx, x, y, w, h, pal) {
    const bs = this.report.bootstrap;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      `200 Stationary Bootstrap Worlds (Block ${bs.mean_block_bars}b)`,
      `Null 95% SR ${bs.null_sharpe_95.toFixed(2)} | Null p=${bs.null_p_value.toFixed(3)}`,
      pal
    );

    const pts = bs.fan_chart || [];
    const padL = x + 16;
    const padR = x + w - 16;
    const topY = y + 28;
    const botY = y + h - 22;
    const plotW = Math.max(40, padR - padL);
    const plotH = Math.max(30, botY - topY);

    if (pts.length < 2) {
      ctx.font = "11px Inter, sans-serif";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "center";
      ctx.fillText("Insufficient bars for stationary bootstrap fan", x + w / 2, y + h / 2);
      return;
    }

    let minEq = 0.98;
    let maxEq = 1.02;
    for (const p of pts) {
      minEq = Math.min(minEq, p.p10, p.realized);
      maxEq = Math.max(maxEq, p.p90, p.realized);
    }
    const span = Math.max(0.02, maxEq - minEq);
    const mapX = (i) => padL + (i / (pts.length - 1)) * plotW;
    const mapY = (v) => botY - ((v - minEq) / span) * plotH;

    // P10 - P90 Outer Cone
    ctx.fillStyle = "rgba(41, 98, 255, 0.12)";
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.p90)) : ctx.lineTo(mapX(i), mapY(p.p90))));
    for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(mapX(i), mapY(pts[i].p10));
    ctx.closePath();
    ctx.fill();

    // P25 - P75 Inner Cone
    ctx.fillStyle = "rgba(41, 98, 255, 0.22)";
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.p75)) : ctx.lineTo(mapX(i), mapY(p.p75))));
    for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(mapX(i), mapY(pts[i].p25));
    ctx.closePath();
    ctx.fill();

    // 1.0 Par Reference Line
    const parY = mapY(1.0);
    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, snap(parY));
    ctx.lineTo(padR, snap(parY));
    ctx.stroke();

    // P50 Median Dashed Curve
    ctx.save();
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = pal.blue;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.p50)) : ctx.lineTo(mapX(i), mapY(p.p50))));
    ctx.stroke();
    ctx.restore();

    // Realized IS Equity Curve
    const endReal = pts[pts.length - 1].realized;
    ctx.strokeStyle = endReal >= 1.0 ? pal.up : pal.down;
    ctx.lineWidth = 1.9;
    ctx.beginPath();
    pts.forEach((p, i) =>
      i === 0 ? ctx.moveTo(mapX(i), mapY(p.realized)) : ctx.lineTo(mapX(i), mapY(p.realized))
    );
    ctx.stroke();

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "left";
    ctx.fillText(
      `SR P05..P95: [${bs.sharpe_p05.toFixed(2)}, ${bs.sharpe_p95.toFixed(2)}]`,
      padL,
      y + h - 6
    );
    ctx.textAlign = "right";
    ctx.fillText(
      `P(SR>0) ${(bs.prob_positive_world * 100).toFixed(0)}% | P95 DD ${(bs.max_dd_p95_worst * 100).toFixed(1)}%`,
      padR,
      y + h - 6
    );
  }

  _drawCusum(ctx, x, y, w, h, pal) {
    const cs = this.report.cusum;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      "OLS-CUSUM Structural Break Bridge",
      `Q=${cs.statistic.toFixed(3)} (p=${cs.p_value.toFixed(3)}) ${cs.has_break ? "BREAK" : "STABLE"}`,
      pal
    );

    const pts = cs.bridge_series || [];
    const padL = x + 16;
    const padR = x + w - 16;
    const topY = y + 28;
    const botY = y + h - 22;
    const plotW = Math.max(40, padR - padL);
    const plotH = Math.max(30, botY - topY);
    if (pts.length < 2) return;

    const crit = cs.critical_5pct || 1.3581;
    const maxAbs = Math.max(crit * 1.15, ...pts.map((p) => Math.abs(p.stat)));
    const mapX = (i) => padL + (i / (pts.length - 1)) * plotW;
    const mapY = (v) => topY + plotH * 0.5 - (v / maxAbs) * (plotH * 0.46);

    ctx.strokeStyle = pal.borderStrong;
    ctx.beginPath();
    ctx.moveTo(padL, snap(mapY(0)));
    ctx.lineTo(padR, snap(mapY(0)));
    ctx.stroke();

    // +/- 1.3581 5% Kolmogorov Critical Lines
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = pal.down;
    ctx.beginPath();
    ctx.moveTo(padL, snap(mapY(crit)));
    ctx.lineTo(padR, snap(mapY(crit)));
    ctx.moveTo(padL, snap(mapY(-crit)));
    ctx.lineTo(padR, snap(mapY(-crit)));
    ctx.stroke();
    ctx.restore();

    ctx.strokeStyle = cs.has_break ? pal.warn : pal.blue;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.stat)) : ctx.lineTo(mapX(i), mapY(p.stat))));
    ctx.stroke();

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "left";
    ctx.fillText(`Break @ ${String(cs.break_time || "--").slice(0, 10)}`, padL, y + h - 6);
    ctx.textAlign = "right";
    ctx.fillText(
      `Pre ${cs.mean_before_bps >= 0 ? "+" : ""}${cs.mean_before_bps.toFixed(1)}bp -> Post ${cs.mean_after_bps >= 0 ? "+" : ""}${cs.mean_after_bps.toFixed(1)}bp`,
      padR,
      y + h - 6
    );
  }

  _drawFunnel(ctx, x, y, w, h, pal) {
    const items = this.report.funnel || [];
    const last = items.length ? items[items.length - 1] : { survivors: 0, total: 0, survival_pct: 0 };
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      "7-Stage Romano-Wolf Falsification Funnel",
      `Survived ${last.survivors}/${last.total} (${last.survival_pct.toFixed(0)}%)`,
      pal
    );

    if (!items.length) return;
    const topY = y + 26;
    const botY = y + h - 10;
    const padL = x + 12;
    const padR = x + w - 12;
    const labelW = 178;
    const statW = 74;
    const barL = padL + labelW;
    const barR = padR - statW;
    const barMaxW = Math.max(30, barR - barL);
    const rowH = Math.min(24, (botY - topY) / items.length);

    items.forEach((it, idx) => {
      const ry = topY + idx * rowH + rowH * 0.5;
      ctx.font = "10px Inter, sans-serif";
      ctx.fillStyle = it.survivors > 0 ? pal.text : pal.muted;
      ctx.textAlign = "left";
      ctx.fillText(it.gate_label, padL, ry + 3.5);

      const frac = Math.max(0, Math.min(1, it.survival_pct / 100.0));
      const bh = Math.max(7, rowH - 7);
      ctx.fillStyle = pal.elev;
      ctx.fillRect(barL, ry - bh / 2, barMaxW, bh);

      if (frac > 0) {
        ctx.fillStyle = idx === items.length - 1 ? pal.up : idx >= 4 ? pal.blue : "rgba(41, 98, 255, 0.72)";
        ctx.fillRect(barL, ry - bh / 2, Math.max(2, barMaxW * frac), bh);
      }

      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = it.survivors > 0 ? pal.text : pal.muted;
      ctx.textAlign = "right";
      ctx.fillText(
        `${it.survivors}/${it.total} (${it.survival_pct.toFixed(0)}%)`,
        padR,
        ry + 3.5
      );
    });
  }
}
