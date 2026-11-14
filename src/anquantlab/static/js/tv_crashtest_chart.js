/**
 * HiDPI TradingView 4-Quadrant Overfitting Crash-Test & Small-Sample Stress Canvas.
 * Renders: (1) 2D Divergent Parameter Heatmap, (2) Multiple-Testing Sharpe Haircut + CSCV PBO,
 * (3) 200 Stationary Bootstrap Fan Chart / OLS-CUSUM Bridge, (4) 7-Stage Romano-Wolf Funnel.
 */

import { drawQuadrantHeader, fitCanvasText, readChartPalette, renderFourPanels, snapPx as snap } from "./canvas_utils.js";

function heatCellFill(sr, maxAbs) {
  const norm = Math.max(-1, Math.min(1, sr / Math.max(0.4, maxAbs)));
  const alpha = (0.05 + 0.28 * Math.abs(norm)).toFixed(3);
  if (norm >= 0.02) return `rgba(46, 158, 132, ${alpha})`;
  if (norm <= -0.02) return `rgba(200, 90, 98, ${alpha})`;
  return "rgba(134, 137, 147, 0.07)";
}

export class TVCrashTestChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.report = null;
    this.bottomLeftMode = "bootstrap"; // "bootstrap" | "cusum"

    this._rafId = null;
    this._ro = new ResizeObserver(() => this._scheduleRender());
    if (this.canvas && this.canvas.parentElement) {
      this._ro.observe(this.canvas.parentElement);
    }
  }

  _scheduleRender() {
    if (this._rafId !== null) return;
    this._rafId = window.requestAnimationFrame(() => {
      this._rafId = null;
      this.render();
    });
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
    const parent = this.canvas ? this.canvas.parentElement : null;
    if (!parent) return;
    const w = parent.clientWidth;
    const h = parent.clientHeight;
    if (w < 40 || h < 40) return;

    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.floor(w * dpr);
    const targetH = Math.floor(h * dpr);
    if (this.canvas.width !== targetW || this.canvas.height !== targetH) {
      this.canvas.width = targetW;
      this.canvas.height = targetH;
    }

    const ctx = this.ctx;
    ctx.save();
    ctx.scale(dpr, dpr);
    const pal = readChartPalette();

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

    renderFourPanels(ctx, w, h, pal, snap, 0.48, [
      (qx, qy, qw, qh) => this._drawHeatmap(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) => this._drawHaircutAndPbo(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) =>
        this.bottomLeftMode === "cusum"
          ? this._drawCusum(ctx, qx, qy, qw, qh, pal)
          : this._drawBootstrapFan(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) => this._drawFunnel(ctx, qx, qy, qw, qh, pal),
    ]);
    ctx.restore();
  }

  _drawHeader(ctx, x, y, w, title, rightMeta, pal) {
    drawQuadrantHeader(ctx, x, y, w, title, rightMeta, pal, 16);
  }

  _drawHeatmap(ctx, x, y, w, h, pal) {
    const hm = this.report.heatmap;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      `2D Sharpe Surface (${hm.y_name} x ${hm.x_name})`,
      `Plateau ${hm.neighbor_plateau_ratio.toFixed(2)}`,
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
          ctx.strokeStyle = pal.sub;
          ctx.lineWidth = 1.1;
          ctx.strokeRect(
            snap(cx + 1.5),
            snap(cy + 1.5),
            Math.max(2, Math.floor(cellW - 3)),
            Math.max(2, Math.floor(cellH - 3))
          );
        }

        ctx.font = nCols >= 5 ? "500 10px 'JetBrains Mono', monospace" : "500 11px 'JetBrains Mono', monospace";
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
      "Sharpe Haircut",
      "",
      pal
    );
    this._drawHeader(
      ctx,
      x + splitW,
      y,
      w - splitW,
      "PBO Logits",
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
    const hSpan = Math.max(60, hR - hL);
    const labelW = Math.min(112, Math.max(68, Math.floor(hSpan * 0.34)));
    const statW = Math.min(52, Math.max(38, Math.floor(hSpan * 0.16)));
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
        ctx.textAlign = "left";
        const rawStage = b.stage.replace(/^\d+\.\s*/, "");
        ctx.fillText(fitCanvasText(ctx, rawStage, labelW - 6), hL, ry + 3.5);

        const targetX = bL + ((b.sharpe_equiv - minV) / span) * bW;
        const bh = Math.max(6, Math.min(12, rowH - 8));
        ctx.fillStyle = idx === 0 ? pal.blueBar : b.sharpe_equiv >= 0 ? pal.upSoft : pal.downSoft;
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
        ctx.fillStyle = mid < 0 ? pal.downSoft : pal.upSoft;
        ctx.fillRect(bx, by, Math.max(1.5, binW - 1.5), bh);
      }

      if (minE < 0 && maxE > 0) {
        const zX = pL + ((0 - minE) / spanE) * pW;
        ctx.save();
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = pal.warnSoft;
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

      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "left";
      ctx.fillText(minE.toFixed(1), pL, y + h - 6);
      ctx.textAlign = "right";
      ctx.fillText(maxE.toFixed(1), pR, y + h - 6);
    } else {
      ctx.font = "10.5px Inter, sans-serif";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "center";
      ctx.fillText("Flat / zero-variance grid", pL + pW / 2, topY + plotH / 2);
    }
  }

  _drawBootstrapFan(ctx, x, y, w, h, pal) {
    const bs = this.report.bootstrap;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      `Bootstrap Fan (${bs.mean_block_bars}b block)`,
      `Null95 ${bs.null_sharpe_95.toFixed(2)}`,
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
    ctx.fillStyle = pal.fanOuter;
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.p90)) : ctx.lineTo(mapX(i), mapY(p.p90))));
    for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(mapX(i), mapY(pts[i].p10));
    ctx.closePath();
    ctx.fill();

    // P25 - P75 Inner Cone
    ctx.fillStyle = pal.fanInner;
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
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = pal.gross;
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(mapX(i), mapY(p.p50)) : ctx.lineTo(mapX(i), mapY(p.p50))));
    ctx.stroke();
    ctx.restore();

    // Realized IS Equity Curve
    const endReal = pts[pts.length - 1].realized;
    ctx.strokeStyle = endReal >= 1.0 ? pal.up : pal.down;
    ctx.lineWidth = 1.35;
    ctx.beginPath();
    pts.forEach((p, i) =>
      i === 0 ? ctx.moveTo(mapX(i), mapY(p.realized)) : ctx.lineTo(mapX(i), mapY(p.realized))
    );
    ctx.stroke();

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "left";
    ctx.fillText(
      `SR P05..P95 [${bs.sharpe_p05.toFixed(2)}, ${bs.sharpe_p95.toFixed(2)}]`,
      padL,
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
      "OLS-CUSUM Break Bridge",
      `Q=${cs.statistic.toFixed(2)} (p=${cs.p_value.toFixed(2)})`,
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
    ctx.strokeStyle = pal.downSoft;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, snap(mapY(crit)));
    ctx.lineTo(padR, snap(mapY(crit)));
    ctx.moveTo(padL, snap(mapY(-crit)));
    ctx.lineTo(padR, snap(mapY(-crit)));
    ctx.stroke();
    ctx.restore();

    ctx.strokeStyle = cs.has_break ? pal.warn : pal.blue;
    ctx.lineWidth = 1.35;
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
      "Romano-Wolf Funnel",
      `Survived ${last.survivors}/${last.total}`,
      pal
    );

    if (!items.length) return;
    const topY = y + 26;
    const botY = y + h - 10;
    const padL = x + 12;
    const padR = x + w - 12;
    const spanW = Math.max(80, padR - padL);
    const labelW = Math.min(176, Math.max(104, Math.floor(spanW * 0.36)));
    const statW = Math.min(74, Math.max(56, Math.floor(spanW * 0.16)));
    const barL = padL + labelW;
    const barR = padR - statW;
    const barMaxW = Math.max(30, barR - barL);
    const rowH = Math.min(24, (botY - topY) / items.length);

    items.forEach((it, idx) => {
      const ry = topY + idx * rowH + rowH * 0.5;
      ctx.font = "10px Inter, sans-serif";
      ctx.fillStyle = it.survivors > 0 ? pal.text : pal.muted;
      ctx.textAlign = "left";
      ctx.fillText(fitCanvasText(ctx, it.gate_label, labelW - 8), padL, ry + 3.5);

      const frac = Math.max(0, Math.min(1, it.survival_pct / 100.0));
      const bh = Math.max(6, Math.min(12, rowH - 7));
      ctx.fillStyle = pal.elev;
      ctx.fillRect(barL, ry - bh / 2, barMaxW, bh);

      if (frac > 0) {
        ctx.fillStyle = idx === items.length - 1 ? pal.upSoft : pal.blueBar;
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
