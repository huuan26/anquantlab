/**
 * TradingView-Style Portfolio Backtest Canvas:
 * Left Stage: Gross vs Net vs Benchmark Equity + Underwater Drawdown + OOS Holdout Vault Tint.
 * Right Stage: Breakeven Transaction Cost Curve + Round-Trip MAE/MFE Excursion Scatter.
 */

import { attachCanvasPointerEvents } from "./canvas_utils.js";

function getPalette() {
  const theme = document.documentElement.getAttribute("data-theme") || "dark";
  if (theme === "light") {
    return {
      bg: "#FFFFFF",
      pane: "#F8F9FD",
      grid: "#F0F3FA",
      border: "#E0E3EB",
      text: "#131722",
      muted: "#5D606B",
      blue: "#2962FF",
      blueFill: "rgba(41, 98, 255, 0.10)",
      up: "#089981",
      down: "#F23645",
      downFill: "rgba(242, 54, 69, 0.16)",
      warn: "#D97706",
      oosTint: "rgba(217, 119, 6, 0.06)",
      gross: "#9598A1",
      bench: "#B2B5BE",
    };
  }
  return {
    bg: "#131722",
    pane: "#1E222D",
    grid: "#1E222D",
    border: "#2A2E39",
    text: "#D1D4DC",
    muted: "#868993",
    blue: "#2962FF",
    blueFill: "rgba(41, 98, 255, 0.15)",
    up: "#089981",
    down: "#F23645",
    downFill: "rgba(242, 54, 69, 0.20)",
    warn: "#F7931A",
    oosTint: "rgba(247, 147, 26, 0.08)",
    gross: "#9598A1",
    bench: "#5D606B",
  };
}

export class TVEquityLabChart {
  constructor(canvas, onHoverPoint) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onHoverPoint = onHoverPoint;
    this.equity = [];
    this.costCurve = [];
    this.trades = [];
    this.meta = { currentCostBps: 10, breakevenBps: 0, holdoutLocked: true };
    this.mousePos = null;
    this._bindEvents();
  }

  _bindEvents() {
    attachCanvasPointerEvents(
      this.canvas,
      (pos) => {
        this.mousePos = { x: pos.x, y: pos.y };
        this.render();
      },
      () => {
        this.mousePos = null;
        this.render();
      }
    );
    if (typeof ResizeObserver !== "undefined") {
      this._rafId = null;
      new ResizeObserver(() => this._scheduleRender()).observe(this.canvas.parentElement);
    } else {
      window.addEventListener("resize", () => this._scheduleRender());
    }
  }

  _scheduleRender() {
    if (this._rafId !== null) return;
    this._rafId = window.requestAnimationFrame(() => {
      this._rafId = null;
      this.render();
    });
  }

  setBacktestData(res, currentCostBps) {
    this.equity = res.equity_series || [];
    this.costCurve = res.cost_curve || [];
    this.trades = res.trades || [];
    this.meta = {
      currentCostBps,
      breakevenBps: res.metrics ? res.metrics.breakeven_bps : 0,
      holdoutLocked: res.holdout_locked,
    };
    this.render();
  }

  render() {
    const parent = this.canvas.parentElement;
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
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pal = getPalette();
    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, w, h);
    ctx.font = '11px "Inter", "IBM Plex Sans", -apple-system, sans-serif';

    const showSide = w >= 660;
    const stackVertical = !showSide && h >= 460;
    if (showSide) {
      const leftW = Math.floor(w * 0.71);
      this._drawEquityAndDrawdown(ctx, pal, 0, 0, leftW, h);

      ctx.strokeStyle = pal.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(leftW + 0.5, 0);
      ctx.lineTo(leftW + 0.5, h);
      ctx.stroke();

      const sideW = w - leftW;
      const topH = Math.floor(h * 0.52);
      this._drawCostCurve(ctx, pal, leftW, 0, sideW, topH);

      ctx.strokeStyle = pal.border;
      ctx.beginPath();
      ctx.moveTo(leftW, topH + 0.5);
      ctx.lineTo(w, topH + 0.5);
      ctx.stroke();

      this._drawMaeMfeScatter(ctx, pal, leftW, topH, sideW, h - topH);
    } else if (stackVertical) {
      const eqH = Math.floor(h * 0.56);
      const midH = Math.floor(h * 0.22);
      this._drawEquityAndDrawdown(ctx, pal, 0, 0, w, eqH);

      ctx.strokeStyle = pal.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, eqH + 0.5);
      ctx.lineTo(w, eqH + 0.5);
      ctx.moveTo(0, eqH + midH + 0.5);
      ctx.lineTo(w, eqH + midH + 0.5);
      ctx.stroke();

      this._drawCostCurve(ctx, pal, 0, eqH, w, midH);
      this._drawMaeMfeScatter(ctx, pal, 0, eqH + midH, w, h - eqH - midH);
    } else {
      this._drawEquityAndDrawdown(ctx, pal, 0, 0, w, h);
    }
  }

  _drawEquityAndDrawdown(ctx, pal, x0, y0, w, h) {
    const n = this.equity.length;
    if (n < 2) {
      ctx.fillStyle = pal.muted;
      ctx.fillText("No portfolio series available.", x0 + 18, y0 + 48);
      return;
    }

    const axisW = 56;
    const bottomH = 22;
    const plotW = Math.max(40, w - axisW);
    const totalPlotH = Math.max(50, h - bottomH);
    const eqH = Math.floor(totalPlotH * 0.68);
    const ddTop = eqH + 6;
    const ddH = Math.max(24, totalPlotH - ddTop - 4);

    let eqMin = Infinity;
    let eqMax = -Infinity;
    let ddMin = -0.02;
    let oosIdx = -1;
    for (let i = 0; i < n; i++) {
      const p = this.equity[i];
      eqMin = Math.min(eqMin, p.net_eq, p.gross_eq, p.bench_eq);
      eqMax = Math.max(eqMax, p.net_eq, p.gross_eq, p.bench_eq);
      ddMin = Math.min(ddMin, p.dd);
      if (oosIdx === -1 && p.is_oos) oosIdx = i;
    }
    const pad = (eqMax - eqMin || 0.05) * 0.08;
    eqMin -= pad;
    eqMax += pad;
    ddMin = Math.min(-0.01, ddMin * 1.1);

    const xAt = (i) => x0 + (i / (n - 1)) * plotW;
    const yEq = (v) => y0 + 10 + (1 - (v - eqMin) / (eqMax - eqMin)) * (eqH - 14);
    const yDd = (v) => ddTop + (1 - (v - ddMin) / (0 - ddMin)) * ddH;

    // OOS Holdout Vault shaded region when unlocked
    if (oosIdx >= 0) {
      const ox = xAt(oosIdx);
      ctx.fillStyle = pal.oosTint;
      ctx.fillRect(ox, y0, x0 + plotW - ox, totalPlotH);
      ctx.strokeStyle = pal.warn;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(Math.round(ox) + 0.5, y0);
      ctx.lineTo(Math.round(ox) + 0.5, totalPlotH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = pal.warn;
      ctx.fillText("OOS VAULT (25%)", ox + 6, y0 + 18);
    }

    // Horizontal grid & axis labels
    ctx.strokeStyle = pal.grid;
    ctx.lineWidth = 1;
    for (let g = 0; g <= 3; g++) {
      const v = eqMin + ((eqMax - eqMin) * g) / 3;
      const y = Math.round(yEq(v)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x0 + plotW, y);
      ctx.stroke();
      ctx.fillStyle = pal.muted;
      ctx.fillText(`${((v - 1) * 100).toFixed(1)}%`, x0 + plotW + 5, y + 3);
    }

    // Separator between Equity and Drawdown
    ctx.strokeStyle = pal.border;
    ctx.beginPath();
    ctx.moveTo(x0, eqH + 0.5);
    ctx.lineTo(x0 + w, eqH + 0.5);
    ctx.stroke();

    // Benchmark curve
    this._strokeLine(ctx, n, xAt, (i) => yEq(this.equity[i].bench_eq), pal.bench, 1.1, []);
    // Gross curve (dashed)
    this._strokeLine(ctx, n, xAt, (i) => yEq(this.equity[i].gross_eq), pal.gross, 1.2, [4, 3]);

    // Net Equity curve + soft fill
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const px = xAt(i);
      const py = yEq(this.equity[i].net_eq);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = pal.blue;
    ctx.lineWidth = 1.9;
    ctx.stroke();

    ctx.lineTo(xAt(n - 1), eqH);
    ctx.lineTo(xAt(0), eqH);
    ctx.closePath();
    ctx.fillStyle = pal.blueFill;
    ctx.fill();

    // Underwater Drawdown fill
    const zeroDdY = yDd(0);
    ctx.beginPath();
    ctx.moveTo(xAt(0), zeroDdY);
    for (let i = 0; i < n; i++) {
      ctx.lineTo(xAt(i), yDd(this.equity[i].dd));
    }
    ctx.lineTo(xAt(n - 1), zeroDdY);
    ctx.closePath();
    ctx.fillStyle = pal.downFill;
    ctx.fill();
    this._strokeLine(ctx, n, xAt, (i) => yDd(this.equity[i].dd), pal.down, 1.2, []);

    ctx.fillStyle = pal.muted;
    ctx.fillText("0.0%", x0 + plotW + 5, zeroDdY + 4);
    ctx.fillText(`${(ddMin * 100).toFixed(1)}%`, x0 + plotW + 5, yDd(ddMin) - 2);

    // X-axis date ticks
    const step = Math.max(1, Math.floor(n / 5));
    for (let i = step; i < n; i += step) {
      const tx = xAt(i);
      ctx.fillStyle = pal.muted;
      ctx.fillText(String(this.equity[i].t).slice(0, 10), tx - 26, totalPlotH + 15);
    }

    // Crosshair hover
    let hoverI = n - 1;
    if (this.mousePos && this.mousePos.x >= x0 && this.mousePos.x <= x0 + plotW) {
      hoverI = Math.max(0, Math.min(n - 1, Math.round(((this.mousePos.x - x0) / plotW) * (n - 1))));
      const hx = Math.round(xAt(hoverI)) + 0.5;
      ctx.strokeStyle = pal.muted;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(hx, y0);
      ctx.lineTo(hx, totalPlotH);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (this.onHoverPoint) {
      this.onHoverPoint(this.equity[hoverI]);
    }
  }

  _strokeLine(ctx, n, xAt, yAt, color, width, dash) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dash);
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const px = xAt(i);
      const py = yAt(i);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.restore();
  }

  _drawCostCurve(ctx, pal, x0, y0, w, h) {
    ctx.fillStyle = pal.text;
    ctx.fillText("Breakeven Cost Curve (Sharpe vs bps)", x0 + 10, y0 + 16);
    if (!this.costCurve || this.costCurve.length < 2) return;

    const padL = 34;
    const padR = 12;
    const padT = 26;
    const padB = 20;
    const pw = Math.max(30, w - padL - padR);
    const ph = Math.max(24, h - padT - padB);

    let sMin = Math.min(0, ...this.costCurve.map((c) => c.sharpe));
    let sMax = Math.max(0.5, ...this.costCurve.map((c) => c.sharpe));
    const sPad = (sMax - sMin || 1) * 0.12;
    sMin -= sPad;
    sMax += sPad;

    const maxBps = this.costCurve[this.costCurve.length - 1].cost_bps || 100;
    const xBps = (b) => x0 + padL + (Math.min(maxBps, Math.max(0, b)) / maxBps) * pw;
    const ySr = (s) => y0 + padT + (1 - (s - sMin) / (sMax - sMin)) * ph;

    // Zero Sharpe line
    const zY = Math.round(ySr(0)) + 0.5;
    ctx.strokeStyle = pal.border;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x0 + padL, zY);
    ctx.lineTo(x0 + padL + pw, zY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = pal.muted;
    ctx.fillText("0.0", x0 + 6, zY + 3);
    ctx.fillText(sMax.toFixed(1), x0 + 6, y0 + padT + 6);
    ctx.fillText("0", x0 + padL - 2, y0 + h - 5);
    ctx.fillText(`${maxBps} bps`, x0 + padL + pw - 36, y0 + h - 5);

    // Cost curve polyline
    ctx.strokeStyle = pal.up;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    this.costCurve.forEach((pt, idx) => {
      const px = xBps(pt.cost_bps);
      const py = ySr(pt.sharpe);
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();

    // Current total cost marker
    const curX = Math.round(xBps(this.meta.currentCostBps)) + 0.5;
    ctx.strokeStyle = pal.warn;
    ctx.beginPath();
    ctx.moveTo(curX, y0 + padT);
    ctx.lineTo(curX, y0 + padT + ph);
    ctx.stroke();
    ctx.fillStyle = pal.warn;
    ctx.fillText(`Now ${this.meta.currentCostBps.toFixed(1)}`, Math.min(x0 + w - 58, curX + 3), y0 + padT + 10);
  }

  _drawMaeMfeScatter(ctx, pal, x0, y0, w, h) {
    ctx.fillStyle = pal.text;
    ctx.fillText("Round-Trip Excursion: |MAE| vs MFE (%)", x0 + 10, y0 + 16);

    const padL = 34;
    const padR = 12;
    const padT = 26;
    const padB = 20;
    const pw = Math.max(30, w - padL - padR);
    const ph = Math.max(24, h - padT - padB);

    if (!this.trades || this.trades.length === 0) {
      ctx.fillStyle = pal.muted;
      ctx.fillText("No closed round-trip trades.", x0 + padL, y0 + padT + 22);
      return;
    }

    let maxExc = 0.01;
    for (const tr of this.trades) {
      maxExc = Math.max(maxExc, Math.abs(tr.mae), Math.abs(tr.mfe));
    }
    maxExc *= 1.1;

    const xMae = (v) => x0 + padL + (Math.min(maxExc, Math.abs(v)) / maxExc) * pw;
    const yMfe = (v) => y0 + padT + (1 - Math.min(maxExc, Math.max(0, v)) / maxExc) * ph;

    // 1:1 diagonal reference
    ctx.strokeStyle = pal.border;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x0 + padL, y0 + padT + ph);
    ctx.lineTo(x0 + padL + pw, y0 + padT);
    ctx.stroke();
    ctx.setLineDash([]);

    for (const tr of this.trades) {
      const px = xMae(tr.mae);
      const py = yMfe(tr.mfe);
      ctx.fillStyle = tr.net_return > 0 ? pal.up : pal.down;
      ctx.beginPath();
      ctx.arc(px, py, 2.8, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = pal.muted;
    ctx.fillText("0%", x0 + padL - 2, y0 + h - 5);
    ctx.fillText(`|MAE| ${(maxExc * 100).toFixed(1)}%`, x0 + padL + pw - 68, y0 + h - 5);
  }
}
