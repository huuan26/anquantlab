/**
 * TradingView-Style Dual-Pane Canvas 2D Renderer (OHLCV Candles + Signal Sub-Pane + Crosshair).
 */

import { attachCanvasPointerEvents, readChartPalette } from "./canvas_utils.js";
import { t } from "./i18n.js";

function fmtPrice(val) {
  if (val === null || val === undefined || Number.isNaN(val)) return "--";
  return Math.abs(val) >= 100 ? val.toFixed(2) : val.toFixed(4);
}

function fmtSig(val) {
  if (val === null || val === undefined || Number.isNaN(val)) return "--";
  return val.toFixed(4);
}

export class TVDualChart {
  constructor(canvas, onHoverBar) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onHoverBar = onHoverBar;
    this.series = [];
    this.tradeMap = new Map();
    this.hoverIdx = null;
    this.mousePos = null;
    this._bindEvents();
  }

  setTrades(trades) {
    this.tradeMap = new Map();
    for (const tr of trades || []) {
      if (tr.entry_time) {
        this.tradeMap.set(String(tr.entry_time), tr.side);
      }
    }
    this.render();
  }

  _bindEvents() {
    attachCanvasPointerEvents(
      this.canvas,
      (pos) => {
        this.mousePos = { x: pos.x, y: pos.y };
        this._updateHoverIndex(pos.width);
        this.render();
      },
      () => {
        this.mousePos = null;
        this.hoverIdx = null;
        if (this.series.length > 0 && this.onHoverBar) {
          const last = this.series.length - 1;
          this.onHoverBar(this.series[last], last > 0 ? this.series[last - 1] : null);
        }
        this.render();
      }
    );

    if (typeof ResizeObserver !== "undefined") {
      this._rafId = null;
      this.ro = new ResizeObserver(() => this._scheduleRender());
      if (this.canvas.parentElement) {
        this.ro.observe(this.canvas.parentElement);
      }
    }
  }

  _scheduleRender() {
    if (this._rafId !== null) return;
    this._rafId = window.requestAnimationFrame(() => {
      this._rafId = null;
      this.render();
    });
  }

  setData(series) {
    this.series = Array.isArray(series) ? series : [];
    this.hoverIdx = null;
    if (this.series.length > 0 && this.onHoverBar) {
      const last = this.series.length - 1;
      this.onHoverBar(this.series[last], last > 0 ? this.series[last - 1] : null);
    }
    this.render();
  }

  _updateHoverIndex(totalWidth) {
    const n = this.series.length;
    const rightAxisW = 68;
    const plotW = Math.max(10, totalWidth - rightAxisW);
    if (!this.mousePos || n === 0 || this.mousePos.x > plotW) {
      this.hoverIdx = null;
      return;
    }
    const step = plotW / n;
    const idx = Math.min(n - 1, Math.max(0, Math.floor(this.mousePos.x / step)));
    this.hoverIdx = idx;
    if (this.onHoverBar) {
      this.onHoverBar(this.series[idx], idx > 0 ? this.series[idx - 1] : null);
    }
  }

  render() {
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const width = parent.clientWidth;
    const height = parent.clientHeight;
    if (width < 40 || height < 40) return;

    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.floor(width * dpr);
    const targetH = Math.floor(height * dpr);
    if (this.canvas.width !== targetW || this.canvas.height !== targetH) {
      this.canvas.width = targetW;
      this.canvas.height = targetH;
    }

    const ctx = this.ctx;
    ctx.save();
    ctx.scale(dpr, dpr);

    const pal = readChartPalette();
    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, width, height);

    const rightW = 68;
    const bottomH = 22;
    const plotW = Math.max(40, width - rightW);
    const totalPlotH = Math.max(60, height - bottomH);
    const priceTop = 8;
    const priceH = Math.floor(totalPlotH * 0.70) - priceTop;
    const sepY = priceTop + priceH;
    const sigTop = sepY + 6;
    const sigH = Math.max(30, totalPlotH - sigTop - 4);

    const n = this.series.length;
    if (n === 0) {
      ctx.fillStyle = pal.axisText;
      ctx.font = '12px "Inter", "IBM Plex Sans", sans-serif';
      ctx.fillText(t("canvas.wait_candle"), 20, 48);
      ctx.restore();
      return;
    }

    let pMin = Infinity;
    let pMax = -Infinity;
    let vMax = 0;
    let sMin = Infinity;
    let sMax = -Infinity;
    for (const b of this.series) {
      if (b.l < pMin) pMin = b.l;
      if (b.h > pMax) pMax = b.h;
      if (b.v > vMax) vMax = b.v;
      if (b.s !== null && b.s !== undefined) {
        if (b.s < sMin) sMin = b.s;
        if (b.s > sMax) sMax = b.s;
      }
    }
    const pPad = (pMax - pMin || 1) * 0.06;
    pMin -= pPad;
    pMax += pPad;
    if (!Number.isFinite(sMin) || !Number.isFinite(sMax)) {
      sMin = -1;
      sMax = 1;
    } else if (Math.abs(sMax - sMin) < 1e-9) {
      sMin -= 1;
      sMax += 1;
    } else {
      const sPad = (sMax - sMin) * 0.1;
      sMin -= sPad;
      sMax += sPad;
    }

    const yPrice = (v) => priceTop + (1 - (v - pMin) / (pMax - pMin)) * priceH;
    const ySig = (v) => sigTop + (1 - (v - sMin) / (sMax - sMin)) * sigH;
    const step = plotW / n;
    const xBar = (i) => (i + 0.5) * step;

    ctx.font = '11px "Inter", "IBM Plex Sans", -apple-system, sans-serif';

    // Horizontal price grid + right axis ticks
    ctx.strokeStyle = pal.grid;
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const val = pMin + ((pMax - pMin) * g) / 4;
      const y = Math.round(yPrice(val)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotW, y);
      ctx.stroke();
      ctx.fillStyle = pal.axisText;
      ctx.fillText(fmtPrice(val), plotW + 6, y + 3);
    }

    // Signal grid + zero line
    for (const g of [0.15, 0.5, 0.85]) {
      const val = sMin + (sMax - sMin) * g;
      const y = Math.round(ySig(val)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotW, y);
      ctx.stroke();
      ctx.fillStyle = pal.axisText;
      ctx.fillText(fmtSig(val), plotW + 6, y + 3);
    }
    if (sMin < 0 && sMax > 0) {
      const zY = Math.round(ySig(0)) + 0.5;
      ctx.strokeStyle = pal.border;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(0, zY);
      ctx.lineTo(plotW, zY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Vertical time grid + labels
    const xTickEvery = Math.max(1, Math.floor(n / 6));
    ctx.strokeStyle = pal.grid;
    for (let i = xTickEvery; i < n; i += xTickEvery) {
      const x = Math.round(xBar(i)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, totalPlotH);
      ctx.stroke();
      ctx.fillStyle = pal.axisText;
      const lbl = String(this.series[i].t).slice(0, 10);
      ctx.fillText(lbl, x - 26, totalPlotH + 15);
    }

    // Volume underlay & Candlesticks
    const candleW = Math.max(1.5, Math.min(11, step * 0.68));
    const volMaxH = priceH * 0.18;
    for (let i = 0; i < n; i++) {
      const b = this.series[i];
      const up = b.c >= b.o;
      const cx = xBar(i);

      if (vMax > 0) {
        const vh = (b.v / vMax) * volMaxH;
        ctx.fillStyle = up ? pal.upVol : pal.downVol;
        ctx.fillRect(cx - candleW / 2, sepY - vh, candleW, vh);
      }

      const yH = yPrice(b.h);
      const yL = yPrice(b.l);
      const yO = yPrice(b.o);
      const yC = yPrice(b.c);
      ctx.strokeStyle = up ? pal.up : pal.down;
      ctx.fillStyle = up ? pal.up : pal.down;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(cx) + 0.5, yH);
      ctx.lineTo(Math.round(cx) + 0.5, yL);
      ctx.stroke();

      const bodyTop = Math.min(yO, yC);
      const bodyH = Math.max(1.2, Math.abs(yC - yO));
      ctx.fillRect(cx - candleW / 2, bodyTop, candleW, bodyH);

      const entrySide = this.tradeMap.get(String(b.t));
      if (entrySide === "LONG") {
        ctx.fillStyle = pal.up;
        ctx.beginPath();
        ctx.moveTo(cx, yL + 3);
        ctx.lineTo(cx - 4, yL + 10);
        ctx.lineTo(cx + 4, yL + 10);
        ctx.closePath();
        ctx.fill();
      } else if (entrySide === "SHORT") {
        ctx.fillStyle = pal.down;
        ctx.beginPath();
        ctx.moveTo(cx, yH - 3);
        ctx.lineTo(cx - 4, yH - 10);
        ctx.lineTo(cx + 4, yH - 10);
        ctx.closePath();
        ctx.fill();
      }
    }

    // Signal sub-pane hairline
    ctx.strokeStyle = pal.blue;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i++) {
      const s = this.series[i].s;
      if (s === null || s === undefined) continue;
      const sx = xBar(i);
      const sy = ySig(s);
      if (!started) {
        ctx.moveTo(sx, sy);
        started = true;
      } else {
        ctx.lineTo(sx, sy);
      }
    }
    ctx.stroke();

    // Pane & axis hairline borders
    ctx.strokeStyle = pal.border;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, sepY + 0.5);
    ctx.lineTo(width, sepY + 0.5);
    ctx.moveTo(plotW + 0.5, 0);
    ctx.lineTo(plotW + 0.5, height);
    ctx.moveTo(0, totalPlotH + 0.5);
    ctx.lineTo(width, totalPlotH + 0.5);
    ctx.stroke();

    // Last price & last signal tags on right axis (muted pill tags)
    const lastB = this.series[n - 1];
    const lpY = Math.max(priceTop + 8, Math.min(sepY - 10, yPrice(lastB.c)));
    ctx.fillStyle = lastB.c >= lastB.o ? pal.upSoft : pal.downSoft;
    ctx.fillRect(plotW + 2, lpY - 7.5, rightW - 4, 15);
    ctx.fillStyle = "#FFFFFF";
    ctx.fillText(fmtPrice(lastB.c), plotW + 6, lpY + 3.5);

    if (lastB.s !== null && lastB.s !== undefined) {
      const lsY = Math.max(sigTop + 8, Math.min(totalPlotH - 10, ySig(lastB.s)));
      ctx.fillStyle = pal.blueBar;
      ctx.fillRect(plotW + 2, lsY - 7.5, rightW - 4, 15);
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(fmtSig(lastB.s), plotW + 6, lsY + 3.5);
    }

    // Crosshair
    if (this.hoverIdx !== null && this.mousePos && this.mousePos.x <= plotW && this.mousePos.y <= totalPlotH) {
      const hx = Math.round(xBar(this.hoverIdx)) + 0.5;
      const hy = Math.round(this.mousePos.y) + 0.5;
      ctx.strokeStyle = pal.crosshair;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(hx, 0);
      ctx.lineTo(hx, totalPlotH);
      ctx.moveTo(0, hy);
      ctx.lineTo(plotW, hy);
      ctx.stroke();
      ctx.setLineDash([]);

      const tText = String(this.series[this.hoverIdx].t).slice(0, 16);
      const tw = ctx.measureText(tText).width + 12;
      const tx = Math.max(2, Math.min(plotW - tw, hx - tw / 2));
      ctx.fillStyle = pal.tagBg;
      ctx.fillRect(tx, totalPlotH + 2, tw, 18);
      ctx.fillStyle = pal.tagText;
      ctx.fillText(tText, tx + 6, totalPlotH + 14.5);
    }

    ctx.restore();
  }
}
