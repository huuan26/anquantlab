/**
 * Tab 1 Controller: Realtime Cost/Buffer Lab, Market Friction Presets,
 * Holdout Vault (25% OOS Lock), Live Trial Ledger & MAE/MFE Trade Inspector.
 */

import { runBacktest } from "./api.js";
import { TVEquityLabChart } from "./tv_equity_chart.js";

const FRICTION_PRESETS = {
  standard: {
    weight: "dollar_neutral",
    exec: "close",
    slipMode: "fixed",
    fee: 5.0,
    slip: 5.0,
    vol: 0,
    buf: 0.0,
    lag: 1,
    limitLock: false,
    flatten: false,
  },
  vn_cash_limit: {
    weight: "long_only",
    exec: "close",
    slipMode: "corwin_schultz",
    fee: 15.0,
    slip: 0.0,
    vol: 18,
    buf: 0.02,
    lag: 1,
    limitLock: true,
    flatten: false,
  },
  vn30f1m_intraday: {
    weight: "dollar_neutral",
    exec: "close",
    slipMode: "fixed",
    fee: 3.0,
    slip: 2.0,
    vol: 0,
    buf: 0.0,
    lag: 1,
    limitLock: false,
    flatten: true,
  },
  crypto_perp_taker: {
    weight: "dollar_neutral",
    exec: "close",
    slipMode: "corwin_schultz",
    fee: 4.0,
    slip: 1.0,
    vol: 25,
    buf: 0.015,
    lag: 1,
    limitLock: false,
    flatten: false,
  },
};

function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const p = Number(v) * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(digits)}%`;
}

function fmtDec(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  return Number(v).toFixed(digits);
}

export class BacktestLabController {
  constructor({
    getDatasetId,
    getFormula,
    getSymbol,
    getHoldoutLocked,
    setSymbolDropdown,
    candleChart,
    onError,
  }) {
    this.getDatasetId = getDatasetId;
    this.getFormula = getFormula;
    this.getSymbol = getSymbol;
    this.getHoldoutLocked = getHoldoutLocked || (() => this.holdoutLocked);
    this.setSymbolDropdown = setSymbolDropdown;
    this.candleChart = candleChart;
    this.onError = onError;

    this.holdoutLocked = true;
    this.chartMode = "equity"; // "equity" | "candles"
    this.inFlight = false;
    this.queued = false;
    this.debounceTimer = null;

    const eqCanvas = document.getElementById("tv-bt-canvas");
    this.eqChart = new TVEquityLabChart(eqCanvas, (pt) => this._updateEquityLegend(pt));
    this._bindControls();
  }

  _readParams() {
    const volPct = Number(document.getElementById("bt-vol-slider").value);
    return {
      dataset_id: this.getDatasetId(),
      formula: this.getFormula(),
      symbol: this.getSymbol(),
      weight_scheme: document.getElementById("bt-weight-select").value,
      execution_price: document.getElementById("bt-exec-select").value,
      slippage_mode: document.getElementById("bt-slip-mode").value,
      fee_bps: Number(document.getElementById("bt-fee-slider").value),
      slippage_bps: Number(document.getElementById("bt-slip-slider").value),
      vol_target: volPct > 0 ? volPct / 100.0 : null,
      no_trade_buffer: Number(document.getElementById("bt-buf-slider").value),
      signal_lag: Number(document.getElementById("bt-lag-slider").value),
      limit_lock_skip: document.getElementById("bt-limit-lock").checked,
      intraday_flatten: document.getElementById("bt-intraday-flat").checked,
      holdout_locked: this.getHoldoutLocked(),
      chart_bars: 180,
      max_trades: 80,
    };
  }

  _syncSliderLabels() {
    const fee = Number(document.getElementById("bt-fee-slider").value);
    const slip = Number(document.getElementById("bt-slip-slider").value);
    const vol = Number(document.getElementById("bt-vol-slider").value);
    const buf = Number(document.getElementById("bt-buf-slider").value);
    const lag = Number(document.getElementById("bt-lag-slider").value);

    document.getElementById("bt-fee-val").textContent = `${fee.toFixed(1)} bps`;
    document.getElementById("bt-slip-val").textContent = `${slip.toFixed(1)} bps`;
    document.getElementById("bt-vol-val").textContent = vol > 0 ? `${vol}%` : "OFF";
    document.getElementById("bt-buf-val").textContent = buf.toFixed(3);
    const lagEl = document.getElementById("bt-lag-val");
    lagEl.textContent = lag === 0 ? "0 (LOOKAHEAD!)" : `${lag} bar`;
    lagEl.style.color = lag === 0 ? "var(--tv-down)" : "var(--tv-text-primary)";
  }

  _applyPreset(key) {
    const p = FRICTION_PRESETS[key];
    if (!p) return;
    document.getElementById("bt-weight-select").value = p.weight;
    document.getElementById("bt-exec-select").value = p.exec;
    document.getElementById("bt-slip-mode").value = p.slipMode;
    document.getElementById("bt-fee-slider").value = String(p.fee);
    document.getElementById("bt-slip-slider").value = String(p.slip);
    document.getElementById("bt-vol-slider").value = String(p.vol);
    document.getElementById("bt-buf-slider").value = String(p.buf);
    document.getElementById("bt-lag-slider").value = String(p.lag);
    document.getElementById("bt-limit-lock").checked = p.limitLock;
    document.getElementById("bt-intraday-flat").checked = p.flatten;
    this._syncSliderLabels();
    this.scheduleRun(0);
  }

  _bindControls() {
    document.getElementById("bt-preset-select").addEventListener("change", (ev) => {
      this._applyPreset(ev.target.value);
    });

    const markCustomAndRun = (delayMs) => {
      document.getElementById("bt-preset-select").value = "custom";
      this._syncSliderLabels();
      this.scheduleRun(delayMs);
    };

    ["bt-fee-slider", "bt-slip-slider", "bt-vol-slider", "bt-buf-slider", "bt-lag-slider"].forEach(
      (id) => {
        document.getElementById(id).addEventListener("input", () => markCustomAndRun(16));
      }
    );

    ["bt-weight-select", "bt-exec-select", "bt-slip-mode", "bt-limit-lock", "bt-intraday-flat"].forEach(
      (id) => {
        document.getElementById(id).addEventListener("change", () => markCustomAndRun(0));
      }
    );

    if (!this.getHoldoutLocked._externalManaged) {
      document.getElementById("btn-holdout-vault").addEventListener("click", () => {
        this.holdoutLocked = !this.holdoutLocked;
        this.scheduleRun(0);
      });
    }

    const btnEq = document.getElementById("btn-view-equity");
    const btnCd = document.getElementById("btn-view-candles");
    btnEq.addEventListener("click", () => this._setChartMode("equity"));
    btnCd.addEventListener("click", () => this._setChartMode("candles"));

    this._syncSliderLabels();
  }

  _setChartMode(mode) {
    this.chartMode = mode;
    document.getElementById("btn-view-equity").classList.toggle("active", mode === "equity");
    document.getElementById("btn-view-candles").classList.toggle("active", mode === "candles");
    document.getElementById("bt-equity-wrap").classList.toggle("hidden", mode !== "equity");
    document.getElementById("bt-candle-wrap").classList.toggle("hidden", mode !== "candles");
    document.getElementById("legend-eq-row").classList.toggle("hidden", mode !== "equity");
    document.getElementById("legend-ohlc-row").classList.toggle("hidden", mode !== "candles");
    if (mode === "equity") this.eqChart.render();
    else if (this.candleChart) this.candleChart.render();
  }

  renderCurrentChart() {
    if (this.chartMode === "equity") this.eqChart.render();
    else if (this.candleChart) this.candleChart.render();
  }

  scheduleRun(delayMs = 16) {
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => this.executeNow(), delayMs);
  }

  async executeNow() {
    const formula = this.getFormula();
    if (!formula) return;
    if (this.inFlight) {
      this.queued = true;
      return;
    }
    this.inFlight = true;
    try {
      const params = this._readParams();
      const res = await runBacktest(params);
      this._renderResponse(res, params);
    } catch (err) {
      if (this.onError) this.onError(err.message || String(err));
    } finally {
      this.inFlight = false;
      if (this.queued) {
        this.queued = false;
        this.executeNow();
      }
    }
  }

  _updateEquityLegend(pt) {
    if (!pt) return;
    const el = document.getElementById("legend-eq-vals");
    if (!el) return;
    const netPct = ((pt.net_eq - 1) * 100).toFixed(2);
    const grossPct = ((pt.gross_eq - 1) * 100).toFixed(2);
    const benchPct = ((pt.bench_eq - 1) * 100).toFixed(2);
    const ddPct = (pt.dd * 100).toFixed(2);
    el.textContent = `${String(pt.t).slice(0, 16)} | Net ${netPct}% | Gross ${grossPct}% | Bench ${benchPct}% | DD ${ddPct}%`;
    el.style.color = pt.net_eq >= 1.0 ? "var(--tv-up)" : "var(--tv-down)";
  }

  _renderResponse(res, params) {
    if (this.setSymbolDropdown) {
      this.setSymbolDropdown(res.available_symbols, res.active_symbol);
    }

    const totalCostBps = params.fee_bps + res.effective_slippage_bps_mean;
    this.eqChart.setBacktestData(res, totalCostBps);
    if (this.candleChart) {
      this.candleChart.setData(res.chart_series);
      this.candleChart.setTrades(res.trades);
    }

    // Topbar Holdout Vault button & Trial Ledger pill
    const vaultBtn = document.getElementById("btn-holdout-vault");
    const tl = res.trial_ledger;
    if (res.holdout_locked) {
      vaultBtn.textContent = "Vault: SEALED";
      vaultBtn.title = `Holdout Vault Sealed (${res.is_bars} IS bars)`;
      vaultBtn.className = "tv-tool-btn tv-vault-sealed num";
    } else {
      vaultBtn.textContent = `Vault: OPEN (${tl.holdout_peeks})`;
      vaultBtn.title = `OOS Holdout Unsealed (Peeks: ${tl.holdout_peeks})`;
      vaultBtn.className = "tv-tool-btn tv-vault-open num";
    }

    const m = res.metrics;
    const ledgerText = document.getElementById("trial-ledger-text");
    ledgerText.textContent =
      `Trials ${tl.unique_trials} | N_eff ${tl.effective_n_trials.toFixed(1)} | DSR ${(m.live_dsr * 100).toFixed(1)}%`;

    // Sidebar latency & effective spread footer
    const hitTag = res.position_cache_hit ? "POS HIT" : res.signal_cache_hit ? "SIG HIT" : "COLD";
    document.getElementById("bt-rail-latency").textContent =
      `${res.elapsed_ms.toFixed(1)} ms (${hitTag}) | Eff Slip ${res.effective_slippage_bps_mean.toFixed(1)} bps`;

    // Bottom Drawer Subpanel: Performance & Tail Risk (12 KPI cells)
    this._renderSummaryCards(m, res);
    // Bottom Drawer Subpanel: List of Trades (MAE/MFE)
    this._renderTradesTable(res.trades);
  }

  _renderSummaryCards(m, res) {
    const grid = document.getElementById("bt-kpi-grid");
    grid.textContent = "";
    const oosLabel =
      m.oos_sharpe_ratio !== null && m.oos_sharpe_ratio !== undefined
        ? `OOS SR: ${fmtDec(m.oos_sharpe_ratio, 2)}`
        : "OOS Vault Sealed";

    const cards = [
      ["Net Return", fmtPct(m.total_return), `Gross: ${fmtPct(m.gross_total_return)}`, m.total_return >= 0 ? "up" : "down"],
      ["Net Sharpe", fmtDec(m.sharpe_ratio, 2), `Gross SR: ${fmtDec(m.gross_sharpe_ratio, 2)} | ${oosLabel}`, m.sharpe_ratio >= 1 ? "up" : m.sharpe_ratio < 0 ? "down" : ""],
      ["Live Session DSR", `${(m.live_dsr * 100).toFixed(1)}%`, `PSR: ${(m.psr * 100).toFixed(1)}% (N_eff ${res.trial_ledger.effective_n_trials.toFixed(1)})`, m.live_dsr >= 0.8 ? "up" : "warn"],
      ["Max Drawdown", fmtPct(m.max_drawdown), `Calmar: ${fmtDec(m.calmar_ratio, 2)}`, "down"],
      ["Sortino & Profit Factor", fmtDec(m.sortino_ratio, 2), `PF: ${fmtDec(m.profit_factor, 2)} | Win: ${(m.win_rate * 100).toFixed(1)}%`, ""],
      ["Breakeven Cost (1-Way)", `${fmtDec(m.breakeven_bps, 1)} bps`, `Turnover: ${fmtDec(m.total_turnover, 1)}x`, m.breakeven_bps > 15 ? "up" : "warn"],
      ["VaR (95%, 1-Bar)", fmtPct(m.var_95), `Ann Vol: ${fmtPct(m.annualized_volatility)}`, ""],
      ["CVaR / Expected Shortfall", fmtPct(m.cvar_95), "5% Left Tail Mean", "down"],
      ["Omega & Tail Ratio", fmtDec(m.omega_ratio, 2), `Tail Ratio (95/5): ${fmtDec(m.tail_ratio, 2)}`, ""],
      ["Round-Trip Trades", String(m.n_round_trips), `Hold: ${fmtDec(m.avg_holding_bars, 1)} bars | MAE ${fmtPct(m.avg_mae)} / MFE ${fmtPct(m.avg_mfe)}`, ""],
    ];

    for (const [lbl, val, sub, tone] of cards) {
      const cell = document.createElement("div");
      cell.className = "tv-kpi-cell";
      const lEl = document.createElement("div");
      lEl.className = "tv-kpi-lbl";
      lEl.textContent = lbl;
      const vEl = document.createElement("div");
      vEl.className = `tv-kpi-val num ${tone === "up" ? "val-pos" : tone === "down" ? "val-neg" : tone === "warn" ? "val-warn" : ""}`;
      vEl.textContent = val;
      const sEl = document.createElement("div");
      sEl.className = "tv-kpi-sub num";
      sEl.textContent = sub;
      cell.append(lEl, vEl, sEl);
      grid.appendChild(cell);
    }

    const badge = document.getElementById("trades-count-badge");
    if (badge) badge.textContent = String(m.n_round_trips);
  }

  _renderTradesTable(trades) {
    const tbody = document.getElementById("bt-trades-body");
    tbody.textContent = "";
    if (!trades || trades.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 12;
      td.className = "tv-muted-meta";
      td.textContent = "No closed round-trip trades in active evaluation window.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    for (const t of trades) {
      const tr = document.createElement("tr");
      const cols = [
        [`#${t.trade_id}`, ""],
        [t.symbol || "--", "mono"],
        [t.side, t.side === "LONG" ? "val-pos" : "val-neg"],
        [String(t.entry_time).slice(0, 16), ""],
        [String(t.exit_time).slice(0, 16), ""],
        [String(t.holding_bars), ""],
        [t.entry_price !== null ? fmtDec(t.entry_price, 2) : "--", ""],
        [t.exit_price !== null ? fmtDec(t.exit_price, 2) : "--", ""],
        [fmtPct(t.gross_return), t.gross_return >= 0 ? "val-pos" : "val-neg"],
        [fmtPct(-t.cost), ""],
        [fmtPct(t.net_return), t.net_return >= 0 ? "val-pos" : "val-neg"],
        [`${fmtPct(t.mae)} / ${fmtPct(t.mfe)}`, ""],
      ];
      for (const [txt, cls] of cols) {
        const td = document.createElement("td");
        td.textContent = txt;
        if (cls) td.className = cls;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }
}
