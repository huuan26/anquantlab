/**
 * TradingView-Style Dual-Pane Canvas 2D Renderer (OHLCV Candles + Signal Sub-Pane + Crosshair).
 */

function readThemePalette() {
  const theme = document.documentElement.getAttribute("data-theme") || "dark";
  if (theme === "light") {
    return {
      bg: "#FFFFFF",
      grid: "#F0F3FA",
      border: "#E0E3EB",
      axisText: "#5D606B",
      crosshair: "#787B86",
      tagBg: "#131722",
      tagText: "#FFFFFF",
      up: "#089981",
      upVol: "rgba(8, 153, 129, 0.22)",
      down: "#F23645",
      downVol: "rgba(242, 54, 69, 0.22)",
      blue: "#2962FF",
      blueFill: "rgba(41, 98, 255, 0.12)",
    };
  }
  return {
    bg: "#131722",
    grid: "#1E222D",
    border: "#2A2E39",
    axisText: "#868993",
    crosshair: "#787B86",
    tagBg: "#363A45",
    tagText: "#D1D4DC",
    up: "#089981",
    upVol: "rgba(8, 153, 129, 0.20)",
    down: "#F23645",
    downVol: "rgba(242, 54, 69, 0.20)",
    blue: "#2962FF",
    blueFill: "rgba(41, 98, 255, 0.14)",
  };
}

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
    this.hoverIdx = null;
    this.mousePos = null;
    this._bindEvents();
  }

  _bindEvents() {
    this.canvas.addEventListener("mousemove", (ev) => {
      const rect = this.canvas.getBoundingClientRect();
      this.mousePos = { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
      this._updateHoverIndex(rect.width);
      this.render();
    });

    this.canvas.addEventListener("mouseleave", () => {
      this.mousePos = null;
      this.hoverIdx = null;
      if (this.series.length > 0 && this.onHoverBar) {
        const last = this.series.length - 1;
        this.onHoverBar(this.series[last], last > 0 ? this.series[last - 1] : null);
      }
      this.render();
    });

    if (typeof ResizeObserver !== "undefined") {
      this.ro = new ResizeObserver(() => this.render());
      if (this.canvas.parentElement) {
        this.ro.observe(this.canvas.parentElement);
      }
    }
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
    if (width <= 0 || height <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    if (this.canvas.width !== Math.floor(width * dpr) || this.canvas.height !== Math.floor(height * dpr)) {
      this.canvas.width = Math.floor(width * dpr);
      this.canvas.height = Math.floor(height * dpr);
      this.canvas.style.width = `${width}px`;
      this.canvas.style.height = `${height}px`;
    }

    const ctx = this.ctx;
    ctx.save();
    ctx.scale(dpr, dpr);

    const pal = readThemePalette();
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
      ctx.fillText("Compile a formula to render OHLCV & Signal panes", 20, 48);
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
    }

    // Signal sub-pane line + subtle area
    ctx.strokeStyle = pal.blue;
    ctx.lineWidth = 1.6;
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

    // Last price & last signal tags on right axis
    const lastB = this.series[n - 1];
    const lpY = Math.max(priceTop + 8, Math.min(sepY - 10, yPrice(lastB.c)));
    ctx.fillStyle = lastB.c >= lastB.o ? pal.up : pal.down;
    ctx.fillRect(plotW + 1, lpY - 8, rightW - 2, 16);
    ctx.fillStyle = "#FFFFFF";
    ctx.fillText(fmtPrice(lastB.c), plotW + 6, lpY + 3.5);

    if (lastB.s !== null && lastB.s !== undefined) {
      const lsY = Math.max(sigTop + 8, Math.min(totalPlotH - 10, ySig(lastB.s)));
      ctx.fillStyle = pal.blue;
      ctx.fillRect(plotW + 1, lsY - 8, rightW - 2, 16);
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
