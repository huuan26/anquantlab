/**
 * HiDPI TradingView 4-Quadrant Factor X-Ray & 5-Factor Spanning Canvas.
 * Zero external libraries, zero emojis, pixel-snapped hairlines, Dark/Light theme aware.
 */

import { drawQuadrantHeader, fillVerticalFade, fitCanvasText, readChartPalette, renderFourPanels, snapPx as snap } from "./canvas_utils.js";
import { localizeTag, t } from "./i18n.js";

export class TVXRayChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.stage = null;
    this.spanning = null;
    this.hasSector = false;
    this.bottomLeftMode = "auto"; // "auto" | "sector" | "cum_ic"

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

  setData({ stage, spanning, hasSector }) {
    this.stage = stage || null;
    this.spanning = spanning || null;
    this.hasSector = Boolean(hasSector);
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

    if (!this.stage) {
      ctx.fillStyle = pal.muted;
      ctx.font = "12px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(t("canvas.wait_xray"), w / 2, h / 2);
      ctx.restore();
      return;
    }

    const showSector =
      this.bottomLeftMode === "sector" ||
      (this.bottomLeftMode === "auto" && this.hasSector && (this.stage.sector_exposures || []).length > 0);
    renderFourPanels(ctx, w, h, pal, snap, 0.5, [
      (qx, qy, qw, qh) => this._drawDistribution(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) => this._drawQuantilesAndDecay(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) =>
        showSector ? this._drawSectorTilts(ctx, qx, qy, qw, qh, pal) : this._drawCumIc(ctx, qx, qy, qw, qh, pal),
      (qx, qy, qw, qh) => this._drawSpanning(ctx, qx, qy, qw, qh, pal),
    ]);
    ctx.restore();
  }

  _drawHeader(ctx, x, y, w, title, rightMeta, pal) {
    drawQuadrantHeader(ctx, x, y, w, title, rightMeta, pal, 17);
  }

  _drawDistribution(ctx, x, y, w, h, pal) {
    const st = this.stage;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      t("canvas.dist", { stage: localizeTag("stage", st.label) }),
      `Skew ${st.skew.toFixed(2)} | Kurt ${st.excess_kurtosis.toFixed(2)}`,
      pal
    );

    const counts = st.hist_counts || [];
    const edges = st.hist_edges || [];
    const padL = x + 16;
    const padR = x + w - 16;
    const plotW = Math.max(40, padR - padL);
    const boxY = y + 32;
    const histTop = y + 52;
    const histBot = y + h - 24;
    const histH = Math.max(30, histBot - histTop);

    if (!counts.length || edges.length < 2) return;
    const minE = edges[0];
    const maxE = edges[edges.length - 1];
    const spanE = Math.max(1e-9, maxE - minE);
    const mapX = (val) => padL + Math.max(0, Math.min(1, (val - minE) / spanE)) * plotW;

    // Horizontal Box-and-Whisker (Q05 - Q25 - Med - Q75 - Q95)
    const x05 = mapX(st.q05);
    const x25 = mapX(st.q25);
    const xMed = mapX(st.median);
    const x75 = mapX(st.q75);
    const x95 = mapX(st.q95);

    ctx.strokeStyle = pal.sub;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x05, snap(boxY));
    ctx.lineTo(x95, snap(boxY));
    ctx.moveTo(snap(x05), boxY - 4);
    ctx.lineTo(snap(x05), boxY + 4);
    ctx.moveTo(snap(x95), boxY - 4);
    ctx.lineTo(snap(x95), boxY + 4);
    ctx.stroke();

    ctx.fillStyle = pal.blueSoft;
    ctx.strokeStyle = pal.blueBar;
    const iqrW = Math.max(2, x75 - x25);
    ctx.fillRect(x25, boxY - 4.5, iqrW, 9);
    ctx.strokeRect(snap(x25), snap(boxY - 4.5), Math.floor(iqrW), 9);

    ctx.strokeStyle = pal.warn;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(snap(xMed), boxY - 6);
    ctx.lineTo(snap(xMed), boxY + 6);
    ctx.stroke();

    // Zero reference line if inside domain
    if (minE < 0 && maxE > 0) {
      const xZero = mapX(0);
      ctx.save();
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = pal.borderStrong;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(snap(xZero), histTop);
      ctx.lineTo(snap(xZero), histBot);
      ctx.stroke();
      ctx.restore();
    }

    const maxC = Math.max(1, ...counts);
    const binW = plotW / counts.length;
    for (let i = 0; i < counts.length; i++) {
      const bh = (counts[i] / maxC) * histH;
      const bx = padL + i * binW + 1;
      const by = histBot - bh;
      const midVal = 0.5 * (edges[i] + edges[i + 1]);
      ctx.fillStyle = midVal >= 0 ? pal.blueBar : pal.blueBarSoft;
      ctx.fillRect(bx, by, Math.max(1.5, binW - 2), bh);
    }

    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, snap(histBot));
    ctx.lineTo(padR, snap(histBot));
    ctx.stroke();

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "left";
    ctx.fillText(`Q05 ${st.q05.toFixed(3)}`, padL, y + h - 7);
    ctx.textAlign = "center";
    ctx.fillText(`Med ${st.median.toFixed(3)} | SD ${st.std.toFixed(3)}`, x + w / 2, y + h - 7);
    ctx.textAlign = "right";
    ctx.fillText(`Q95 ${st.q95.toFixed(3)}`, padR, y + h - 7);
  }

  _drawQuantilesAndDecay(ctx, x, y, w, h, pal) {
    const st = this.stage;
    const hlTxt = st.half_life_bars ? `Half-Life ${st.half_life_bars.toFixed(1)}b` : "Half-Life --";
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      t("canvas.quantiles"),
      `Q5-Q1 ${st.top_minus_bottom_bps >= 0 ? "+" : ""}${st.top_minus_bottom_bps.toFixed(1)}bp | ${hlTxt}`,
      pal
    );

    const splitW = Math.floor(w * 0.56);
    const topY = y + 30;
    const botY = y + h - 24;
    const plotH = Math.max(30, botY - topY);

    // Left sub-pane: Q1..Q5 bars
    const qs = st.quantiles || [];
    const qL = x + 14;
    const qR = x + splitW - 10;
    const qW = Math.max(30, qR - qL);
    const zeroY = Math.floor(topY + plotH * 0.5);

    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(qL, snap(zeroY));
    ctx.lineTo(qR, snap(zeroY));
    ctx.stroke();

    if (qs.length > 0) {
      const maxAbs = Math.max(0.5, ...qs.map((q) => Math.abs(q.mean_return_bps)));
      const slotW = qW / qs.length;
      for (let i = 0; i < qs.length; i++) {
        const q = qs[i];
        const val = q.mean_return_bps;
        const barH = (Math.abs(val) / maxAbs) * (plotH * 0.42);
        const bx = qL + i * slotW + slotW * 0.16;
        const bw = Math.max(8, slotW * 0.68);
        ctx.fillStyle = val >= 0 ? pal.upSoft : pal.downSoft;
        if (val >= 0) {
          ctx.fillRect(bx, zeroY - barH, bw, barH);
        } else {
          ctx.fillRect(bx, zeroY, bw, barH);
        }
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillStyle = pal.sub;
        ctx.textAlign = "center";
        ctx.fillText(`Q${q.quantile}`, bx + bw / 2, y + h - 8);
        ctx.fillStyle = pal.text;
        const lblY = val >= 0 ? Math.max(topY + 9, zeroY - barH - 4) : Math.min(botY - 2, zeroY + barH + 10);
        ctx.fillText(`${val >= 0 ? "+" : ""}${val.toFixed(1)}`, bx + bw / 2, lblY);
      }
    } else {
      ctx.font = "11px Inter, sans-serif";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "center";
      ctx.fillText(t("canvas.const_sig"), qL + qW / 2, zeroY - 6);
    }

    // Divider between Quantiles and IC Decay
    ctx.strokeStyle = pal.border;
    ctx.beginPath();
    ctx.moveTo(snap(x + splitW), topY);
    ctx.lineTo(snap(x + splitW), botY);
    ctx.stroke();

    // Right sub-pane: Multi-Horizon IC Decay (1, 2, 5, 10, 20)
    const dec = st.ic_decay || [];
    const dL = x + splitW + 14;
    const dR = x + w - 14;
    const dW = Math.max(30, dR - dL);
    ctx.strokeStyle = pal.borderStrong;
    ctx.beginPath();
    ctx.moveTo(dL, snap(zeroY));
    ctx.lineTo(dR, snap(zeroY));
    ctx.stroke();

    if (dec.length >= 2) {
      const maxIc = Math.max(0.01, ...dec.map((d) => Math.abs(d.ic_mean)));
      ctx.strokeStyle = pal.blue;
      ctx.lineWidth = 1.35;
      ctx.beginPath();
      dec.forEach((d, idx) => {
        const px = dL + (idx / (dec.length - 1)) * dW;
        const py = zeroY - (d.ic_mean / maxIc) * (plotH * 0.4);
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.stroke();

      dec.forEach((d, idx) => {
        const px = dL + (idx / (dec.length - 1)) * dW;
        const py = zeroY - (d.ic_mean / maxIc) * (plotH * 0.4);
        ctx.fillStyle = Math.abs(d.nw_t_stat) >= 1.96 ? pal.up : pal.blue;
        ctx.beginPath();
        ctx.arc(px, py, 2.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillStyle = pal.muted;
        ctx.textAlign = "center";
        ctx.fillText(`${d.horizon}b`, px, y + h - 8);
      });
    }
  }

  _drawSectorTilts(ctx, x, y, w, h, pal) {
    const st = this.stage;
    const items = st.sector_exposures || [];
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      t("canvas.sector_tilt"),
      `Max ${(st.max_abs_sector_tilt * 100).toFixed(2)}%`,
      pal
    );

    const topY = y + 28;
    const botY = y + h - 14;
    const padL = x + 92;
    const padR = x + w - 58;
    const barW = Math.max(40, padR - padL);
    const midX = padL + barW * 0.5;

    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(snap(midX), topY);
    ctx.lineTo(snap(midX), botY);
    ctx.stroke();

    if (!items.length) return;
    const maxTilt = Math.max(0.02, ...items.map((it) => Math.abs(it.net_exposure)));
    const rowH = Math.min(22, (botY - topY) / items.length);

    items.forEach((it, idx) => {
      const ry = topY + idx * rowH + rowH * 0.5;
      ctx.font = "10.5px Inter, sans-serif";
      ctx.fillStyle = pal.sub;
      ctx.textAlign = "right";
      ctx.fillText(String(it.sector).slice(0, 12), padL - 8, ry + 3.5);

      const len = (Math.abs(it.net_exposure) / maxTilt) * (barW * 0.46);
      const bh = Math.max(6, Math.min(12, rowH - 7));
      ctx.fillStyle = it.net_exposure >= 0 ? pal.upSoft : pal.downSoft;
      if (Math.abs(it.net_exposure) < 1e-5) {
        ctx.fillStyle = pal.borderStrong;
        ctx.fillRect(midX - 1, ry - bh / 2, 2, bh);
      } else if (it.net_exposure > 0) {
        ctx.fillRect(midX, ry - bh / 2, len, bh);
      } else {
        ctx.fillRect(midX - len, ry - bh / 2, len, bh);
      }

      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = Math.abs(it.net_exposure) < 1e-4 ? pal.up : pal.text;
      ctx.textAlign = "right";
      const pct = (it.net_exposure * 100).toFixed(2);
      ctx.fillText(`${it.net_exposure >= 0 ? "+" : ""}${pct}%`, x + w - 10, ry + 3.5);
    });
  }

  _drawCumIc(ctx, x, y, w, h, pal) {
    const st = this.stage;
    const pts = st.ic_series || [];
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      t("canvas.cum_ic"),
      `IC ${st.ic_mean >= 0 ? "+" : ""}${st.ic_mean.toFixed(4)} | t ${st.nw_t_stat >= 0 ? "+" : ""}${st.nw_t_stat.toFixed(2)}`,
      pal
    );

    const padL = x + 16;
    const padR = x + w - 16;
    const topY = y + 30;
    const botY = y + h - 20;
    const plotW = Math.max(40, padR - padL);
    const plotH = Math.max(30, botY - topY);

    if (pts.length < 2) {
      ctx.font = "11px Inter, sans-serif";
      ctx.fillStyle = pal.muted;
      ctx.textAlign = "center";
      ctx.fillText(t("canvas.insuff_ic"), x + w / 2, y + h / 2);
      return;
    }

    const cums = pts.map((p) => p.cum_ic);
    const minC = Math.min(0, ...cums);
    const maxC = Math.max(0.01, ...cums);
    const spanC = Math.max(1e-6, maxC - minC);
    const mapY = (v) => botY - ((v - minC) / spanC) * plotH;

    const zeroY = mapY(0);
    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, snap(zeroY));
    ctx.lineTo(padR, snap(zeroY));
    ctx.stroke();

    const lastCum = cums[cums.length - 1];
    ctx.strokeStyle = lastCum >= 0 ? pal.up : pal.down;
    ctx.lineWidth = 1.35;
    ctx.beginPath();
    pts.forEach((p, idx) => {
      const px = padL + (idx / (pts.length - 1)) * plotW;
      const py = mapY(p.cum_ic);
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();

    ctx.lineTo(padL + plotW, zeroY);
    ctx.lineTo(padL, zeroY);
    ctx.closePath();
    ctx.fillStyle = fillVerticalFade(
      ctx,
      topY,
      botY,
      lastCum >= 0 ? "rgba(46, 158, 132, 0.08)" : pal.downTop,
      lastCum >= 0 ? "rgba(46, 158, 132, 0.00)" : pal.downBot
    );
    ctx.fill();

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.muted;
    ctx.textAlign = "left";
    ctx.fillText(String(pts[0].t).slice(0, 10), padL, y + h - 6);
    ctx.textAlign = "right";
    ctx.fillText(
      `${String(pts[pts.length - 1].t).slice(0, 10)} (CumIC ${cums[cums.length - 1].toFixed(2)})`,
      padR,
      y + h - 6
    );
  }

  _drawSpanning(ctx, x, y, w, h, pal) {
    const sp = this.spanning;
    if (!sp) return;
    this._drawHeader(
      ctx,
      x,
      y,
      w,
      t("canvas.spanning"),
      localizeTag("verdict", sp.verdict),
      pal
    );

    const padL = x + 14;
    const padR = x + w - 14;
    const fullW = Math.max(40, padR - padL);

    // Stacked R^2 vs Pure Orthogonal Alpha Meter (slim 9px hairline track)
    const meterY = y + 26;
    const meterH = 9;
    const spanW = Math.round(fullW * Math.max(0, Math.min(1, sp.spanning_r2)));
    const orthW = Math.max(0, fullW - spanW);

    ctx.fillStyle = pal.warnSoft;
    ctx.fillRect(padL, meterY, spanW, meterH);
    ctx.fillStyle = pal.upSoft;
    ctx.fillRect(padL + spanW, meterY, orthW, meterH);

    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = pal.sub;
    ctx.textAlign = "left";
    ctx.fillText(t("canvas.spanned_r2", { pct: (sp.spanning_r2 * 100).toFixed(1) }), padL, meterY + meterH + 12);
    ctx.fillStyle = pal.up;
    ctx.textAlign = "right";
    ctx.fillText(
      t("canvas.pure_alpha", { pct: (sp.orthogonal_share * 100).toFixed(1) }),
      padR,
      meterY + meterH + 12
    );

    // 5 Standardized Factor Loadings (beta + NW t-stat)
    const loads = sp.loadings || [];
    if (!loads.length) return;
    const topY = meterY + meterH + 20;
    const botY = y + h - 10;
    const labelW = Math.min(114, Math.max(72, Math.floor(fullW * 0.25)));
    const statW = Math.min(68, Math.max(54, Math.floor(fullW * 0.16)));
    const barL = padL + labelW;
    const barR = padR - statW;
    const barW = Math.max(30, barR - barL);
    const midX = barL + barW * 0.5;

    ctx.strokeStyle = pal.borderStrong;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(snap(midX), topY);
    ctx.lineTo(snap(midX), botY);
    ctx.stroke();

    const maxBeta = Math.max(0.25, ...loads.map((l) => Math.abs(l.beta)));
    const rowH = Math.min(22, (botY - topY) / loads.length);

    loads.forEach((ld, idx) => {
      const ry = topY + idx * rowH + rowH * 0.5;
      ctx.font = "10.5px Inter, sans-serif";
      ctx.fillStyle = ld.selected ? pal.text : pal.muted;
      ctx.textAlign = "right";
      ctx.fillText(fitCanvasText(ctx, localizeTag("factor", ld.factor_label), labelW - 10), barL - 8, ry + 3.5);

      const len = (Math.abs(ld.beta) / maxBeta) * (barW * 0.46);
      const bh = Math.max(6, Math.min(12, rowH - 7));
      ctx.fillStyle = ld.beta >= 0 ? pal.blueBar : pal.downSoft;
      if (!ld.selected) ctx.globalAlpha = 0.35;
      if (ld.beta >= 0) ctx.fillRect(midX, ry - bh / 2, len, bh);
      else ctx.fillRect(midX - len, ry - bh / 2, len, bh);
      ctx.globalAlpha = 1.0;

      ctx.font = "10px 'JetBrains Mono', monospace";
      ctx.fillStyle = Math.abs(ld.nw_t_stat) >= 1.96 ? pal.warn : pal.sub;
      ctx.textAlign = "right";
      ctx.fillText(
        `${ld.beta >= 0 ? "+" : ""}${ld.beta.toFixed(2)} (${ld.nw_t_stat >= 0 ? "+" : ""}${ld.nw_t_stat.toFixed(1)}t)`,
        padR,
        ry + 3.5
      );
    });
  }
}
