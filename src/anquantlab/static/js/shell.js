/**
 * TradingView-Style Terminal Controller:
 * Docked Resizable Panes, Dual-Pane Canvas, Ctrl+K fx Modal, 12px/13.5px Scale & Causal DSL.
 */

import {
  fetchCatalog,
  fetchDatasetForensics,
  fetchDatasetPreview,
  fetchDatasets,
  fetchHealth,
  previewFormula,
  uploadDatasetFile,
} from "./api.js";
import { BacktestLabController } from "./backtest_view.js";
import { CrashTestLabController } from "./crashtest_view.js";
import { initExportModal } from "./export_hub.js";
import { initPublicDataModal, renderForensicsPanel } from "./forensics_hub.js";
import { FxCatalogController } from "./fx_modal.js";
import { initGuideHub } from "./guide_hub.js";
import { getLang, initI18nControl, t } from "./i18n.js";
import { TVDualChart } from "./tv_chart.js";
import { XRayLabController } from "./xray_view.js";

const state = {
  activeDatasetId: "builtin_demo_panel",
  activeDatasetName: "Synthetic Panel",
  activeSymbol: null,
  activeTab: "backtest",
  holdoutLocked: true,
  fxCatalog: null,
  lastPreviewMeta: null,
  lastEvalRes: null,
  engineText: "",
  chart: null,
  btLab: null,
  xrayLab: null,
  crashtestLab: null,
};

function fmtNum(val, digits = 4) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "--";
  return Number(val).toFixed(digits);
}

function fmtVol(v) {
  if (v === null || v === undefined) return "--";
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v));
}

function initThemeAndDensity() {
  const savedTheme = localStorage.getItem("anquantlab_theme") || "dark";
  const savedDensity = localStorage.getItem("anquantlab_density") || "compact";
  applyTheme(savedTheme);
  applyDensity(savedDensity);

  document.getElementById("btn-theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("anquantlab_theme", next);
    if (state.chart) state.chart.render();
    if (state.btLab) state.btLab.renderCurrentChart();
    if (state.xrayLab) state.xrayLab.renderCurrentChart();
    if (state.crashtestLab) state.crashtestLab.renderCurrentChart();
  });

  document.getElementById("btn-density-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-density") || "compact";
    const next = cur === "compact" ? "comfort" : "compact";
    applyDensity(next);
    localStorage.setItem("anquantlab_density", next);
    window.requestAnimationFrame(() => {
      if (state.chart) state.chart.render();
      if (state.btLab) state.btLab.renderCurrentChart();
      if (state.xrayLab) state.xrayLab.renderCurrentChart();
      if (state.crashtestLab) state.crashtestLab.renderCurrentChart();
    });
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.getElementById("icon-sun").classList.toggle("hidden", theme !== "dark");
  document.getElementById("icon-moon").classList.toggle("hidden", theme === "dark");
}

function applyDensity(density) {
  document.documentElement.setAttribute("data-density", density);
  document.getElementById("density-label").textContent = density === "compact" ? "12px" : "13.5px";
}

function activateSubTab(target) {
  const drawer = document.getElementById("tv-bottom-drawer");
  drawer.classList.remove("collapsed");
  document.querySelectorAll(".tv-subtab").forEach((b) => {
    const active = b.dataset.subtab === target;
    b.classList.toggle("active", active);
    b.setAttribute("aria-selected", active ? "true" : "false");
  });
  [
    "editor",
    "bt-summary",
    "bt-trades",
    "xray-matrix",
    "ct-candidates",
    "forensics",
    "metrics",
    "table",
  ].forEach((id) => {
    document.getElementById(`subpanel-${id}`).classList.toggle("hidden", id !== target);
  });
}

function initModeAndSubTabs() {
  const modeBtns = document.querySelectorAll(".tv-mode-tab");
  modeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      state.activeTab = target;
      modeBtns.forEach((b) => {
        const active = b.dataset.tab === target;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
      });
      ["backtest", "xray", "crashtest"].forEach((id) => {
        document.getElementById(`panel-${id}`).classList.toggle("hidden", id !== target);
      });
      if (target === "backtest") {
        window.requestAnimationFrame(() => {
          if (state.chart) state.chart.render();
          if (state.btLab) state.btLab.renderCurrentChart();
        });
      } else if (target === "xray" && state.xrayLab) {
        state.xrayLab.executeNow();
        window.requestAnimationFrame(() => state.xrayLab.renderCurrentChart());
      } else if (target === "crashtest" && state.crashtestLab) {
        state.crashtestLab.executeNow();
        window.requestAnimationFrame(() => state.crashtestLab.renderCurrentChart());
      }
    });
  });

  const railBtn = document.getElementById("btn-toggle-rail");
  if (railBtn) {
    railBtn.addEventListener("click", () => {
      const open = document.body.classList.toggle("tv-rail-open");
      railBtn.setAttribute("aria-expanded", open ? "true" : "false");
      railBtn.classList.toggle("active", open);
      window.requestAnimationFrame(() => {
        if (state.chart) state.chart.render();
        if (state.btLab) state.btLab.renderCurrentChart();
        if (state.xrayLab) state.xrayLab.renderCurrentChart();
        if (state.crashtestLab) state.crashtestLab.renderCurrentChart();
      });
    });
  }

  document.querySelectorAll(".tv-subtab").forEach((btn) => {
    btn.addEventListener("click", () => activateSubTab(btn.dataset.subtab));
  });

  const forensicsPill = document.getElementById("forensics-pill");
  if (forensicsPill) {
    forensicsPill.addEventListener("click", () => activateSubTab("forensics"));
  }

  const btnSig = document.getElementById("btn-tbl-signal");
  const btnRaw = document.getElementById("btn-tbl-raw");
  btnSig.addEventListener("click", () => {
    btnSig.classList.add("active");
    btnRaw.classList.remove("active");
    document.getElementById("signal-preview-table").classList.remove("hidden");
    document.getElementById("dataset-preview-table").classList.add("hidden");
  });
  btnRaw.addEventListener("click", () => {
    btnRaw.classList.add("active");
    btnSig.classList.remove("active");
    document.getElementById("dataset-preview-table").classList.remove("hidden");
    document.getElementById("signal-preview-table").classList.add("hidden");
  });
}

function initResizableDrawer() {
  const splitter = document.getElementById("tv-splitter");
  const drawer = document.getElementById("tv-bottom-drawer");
  const savedH = Number(localStorage.getItem("anquantlab_drawer_h"));
  const maxDefaultH = Math.max(150, Math.floor(window.innerHeight * 0.52));
  if (window.innerWidth <= 960) {
    drawer.classList.add("collapsed");
  } else if (savedH >= 120 && savedH <= maxDefaultH) {
    drawer.style.height = `${savedH}px`;
  }

  let dragging = false;
  const startDrag = (ev) => {
    ev.preventDefault();
    dragging = true;
    drawer.classList.remove("collapsed");
    splitter.classList.add("dragging");
  };
  const moveDrag = (ev) => {
    if (!dragging) return;
    const pt = ev.touches && ev.touches[0] ? ev.touches[0] : ev;
    const maxDragH = Math.max(150, window.innerHeight * 0.58);
    const newH = Math.max(110, Math.min(maxDragH, window.innerHeight - pt.clientY));
    drawer.style.height = `${Math.round(newH)}px`;
    if (state.chart) state.chart.render();
    if (state.btLab) state.btLab.renderCurrentChart();
    if (state.xrayLab) state.xrayLab.renderCurrentChart();
    if (state.crashtestLab) state.crashtestLab.renderCurrentChart();
  };
  const endDrag = () => {
    if (!dragging) return;
    dragging = false;
    splitter.classList.remove("dragging");
    localStorage.setItem("anquantlab_drawer_h", String(drawer.offsetHeight));
  };

  splitter.addEventListener("mousedown", startDrag);
  splitter.addEventListener("touchstart", startDrag, { passive: false });
  window.addEventListener("mousemove", moveDrag);
  window.addEventListener("touchmove", moveDrag, { passive: true });
  window.addEventListener("mouseup", endDrag);
  window.addEventListener("touchend", endDrag, { passive: true });

  document.getElementById("btn-toggle-drawer").addEventListener("click", () => {
    drawer.classList.toggle("collapsed");
    setTimeout(() => {
      if (state.chart) state.chart.render();
      if (state.btLab) state.btLab.renderCurrentChart();
      if (state.xrayLab) state.xrayLab.renderCurrentChart();
      if (state.crashtestLab) state.crashtestLab.renderCurrentChart();
    }, 20);
  });
}

function updateLegendBar(bar, prevBar) {
  if (!bar) return;
  const ohlcEl = document.getElementById("legend-ohlc");
  const up = bar.c >= bar.o;
  const chgPct = prevBar && prevBar.c ? (((bar.c - prevBar.c) / prevBar.c) * 100).toFixed(2) : "0.00";
  const sign = Number(chgPct) >= 0 ? "+" : "";
  ohlcEl.textContent = `O ${fmtNum(bar.o, 2)}  H ${fmtNum(bar.h, 2)}  L ${fmtNum(bar.l, 2)}  C ${fmtNum(bar.c, 2)} (${sign}${chgPct}%)  Vol ${fmtVol(bar.v)}`;
  ohlcEl.style.color = up ? "var(--tv-up)" : "var(--tv-down)";
  document.getElementById("legend-sig-val").textContent = bar.s !== null && bar.s !== undefined ? fmtNum(bar.s, 4) : "null";
}

function renderTable(tableId, rows) {
  const table = document.getElementById(tableId);
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.textContent = "";
  tbody.textContent = "";
  if (!rows || rows.length === 0) return;

  const cols = Object.keys(rows[0]);
  const hTr = document.createElement("tr");
  for (const col of cols) {
    const th = document.createElement("th");
    th.textContent = col;
    hTr.appendChild(th);
  }
  thead.appendChild(hTr);

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const col of cols) {
      const td = document.createElement("td");
      const v = row[col];
      if (typeof v === "number") {
        td.textContent = Number.isInteger(v) ? String(v) : v.toFixed(4);
        if (col === "signal") {
          td.className = v > 0 ? "val-pos" : v < 0 ? "val-neg" : "";
        }
      } else {
        td.textContent = v === null || v === undefined ? "null" : String(v);
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function showBanner(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function renderDatasetMetaUi() {
  const preview = state.lastPreviewMeta;
  if (!preview) return;
  const info = preview.info;
  const vi = getLang() === "vi";
  document.getElementById("legend-dataset").textContent = info.name;
  document.getElementById("kpi-rows").textContent = info.row_count ? info.row_count.toLocaleString() : "--";
  document.getElementById("kpi-span").textContent = info.date_start && info.date_end ? `${info.date_start} -> ${info.date_end}` : "--";
  document.getElementById("kpi-symbols").textContent = info.symbol_count
    ? `${info.symbol_count} ${vi ? "mã" : "tickers"}`
    : vi ? "1 chuỗi" : "1 series";
  document.getElementById("kpi-sectors").textContent = preview.sectors.length
    ? `${preview.sectors.length} ${vi ? "nhóm ngành" : "sectors"}`
    : vi ? "Đơn ngành / Chưa phân loại" : "Single / Unclassified";

  const ohlcvEl = document.getElementById("kpi-ohlcv");
  ohlcvEl.textContent = preview.ohlcv_valid ? t("verdict.pass") : vi ? "CẢNH BÁO" : "WARN";
  ohlcvEl.style.color = preview.ohlcv_valid ? "var(--tv-up)" : "var(--tv-warn)";
  document.getElementById("kpi-hash").textContent = `sha256: ${info.sha256_prefix || "--"}`;
  document.getElementById("dataset-columns-caption").textContent = `${vi ? "Cột dữ liệu" : "Schema"}: [${info.columns.join(", ")}]`;
}

async function loadActiveDatasetPreview() {
  const [preview, forensics] = await Promise.all([
    fetchDatasetPreview(state.activeDatasetId),
    fetchDatasetForensics(state.activeDatasetId),
  ]);
  state.activeDatasetName = preview.info.name;
  state.lastPreviewMeta = preview;
  renderDatasetMetaUi();
  renderTable("dataset-preview-table", preview.sample_rows);
  renderForensicsPanel(forensics);
  return { preview, forensics };
}

function syncSymbolSelect(availSyms, activeSym) {
  const symSel = document.getElementById("symbol-select");
  symSel.textContent = "";
  for (const s of availSyms || []) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    symSel.appendChild(opt);
  }
  state.activeSymbol = activeSym;
  if (activeSym) symSel.value = activeSym;
  document.getElementById("legend-symbol").textContent = activeSym || state.activeDatasetId;
}

function renderEvalStatsUi(res) {
  if (!res) return;
  const vi = getLang() === "vi";
  document.getElementById("kpi-coverage").textContent = `${res.stats.coverage_pct.toFixed(1)}%`;
  document.getElementById("kpi-latency").textContent = `${res.elapsed_ms.toFixed(2)} ms (${res.stats.valid_count.toLocaleString()} ${vi ? "dòng" : "rows"})`;

  const distGrid = document.getElementById("signal-stats-grid");
  distGrid.textContent = "";
  const cells = [
    [vi ? "Trung bình" : "Mean", fmtNum(res.stats.mean)],
    [vi ? "Độ lệch chuẩn" : "Std Dev", fmtNum(res.stats.std)],
    ["Min", fmtNum(res.stats.min)],
    ["Q25", fmtNum(res.stats.q25)],
    [vi ? "Trung vị" : "Median", fmtNum(res.stats.median)],
    ["Max", fmtNum(res.stats.max)],
  ];
  for (const [lbl, val] of cells) {
    const box = document.createElement("div");
    box.className = "stat-cell";
    box.innerHTML = `<div class="stat-cell-label">${lbl}</div><div class="stat-cell-val">${val}</div>`;
    distGrid.appendChild(box);
  }
}

async function runFormulaEvaluation() {
  const btn = document.getElementById("btn-evaluate-formula");
  const formula = document.getElementById("formula-input").value.trim();
  if (!formula) return;

  showBanner("formula-error-banner", "");
  showBanner("formula-notes-banner", "");
  btn.disabled = true;

  try {
    const res = await previewFormula(state.activeDatasetId, formula, {
      symbol: state.activeSymbol,
      chartBars: 160,
      previewLimit: 24,
    });
    state.lastEvalRes = res;

    syncSymbolSelect(res.available_symbols, res.active_symbol);
    document.getElementById("legend-formula").textContent = res.normalized_formula;
    document.getElementById("cache-badge").textContent = res.cache_hit ? "LRU" : "LIVE";
    document.getElementById("editor-latency-hint").textContent = `${res.elapsed_ms.toFixed(2)} ms`;

    if (res.notes && res.notes.length > 0) {
      showBanner("formula-notes-banner", res.notes.join(" | "));
    }

    const stageList = document.getElementById("stage-list");
    stageList.textContent = "";
    for (const st of res.stages) {
      const li = document.createElement("li");
      const tag = document.createElement("span");
      tag.className = "stage-scope mono";
      tag.textContent = st.window_over ? `${st.scope}:.over(${st.window_over})` : st.scope;
      li.append(tag, document.createTextNode(st.description));
      stageList.appendChild(li);
    }

    renderEvalStatsUi(res);
    renderTable("signal-preview-table", res.sample_rows);
    if (state.chart) state.chart.setData(res.chart_series);
    if (state.btLab) await state.btLab.executeNow();
    if (state.xrayLab && state.activeTab === "xray") {
      await state.xrayLab.executeNow();
    }
    if (state.crashtestLab && state.activeTab === "crashtest") {
      await state.crashtestLab.executeNow();
    }
  } catch (err) {
    showBanner("formula-error-banner", err.message || String(err));
  } finally {
    btn.disabled = false;
  }
}

async function refreshDatasetDropdown(selectId = null) {
  const dsRes = await fetchDatasets();
  const sel = document.getElementById("dataset-select");
  sel.textContent = "";
  for (const ds of dsRes.datasets) {
    const opt = document.createElement("option");
    opt.value = ds.dataset_id;
    opt.textContent = ds.name;
    sel.appendChild(opt);
  }
  state.activeDatasetId = selectId || dsRes.default_dataset_id;
  sel.value = state.activeDatasetId;
}

async function bootstrap() {
  initI18nControl();
  initThemeAndDensity();
  initModeAndSubTabs();
  initResizableDrawer();
  state.fxCatalog = new FxCatalogController({
    onSelectExpr: (formula) => {
      document.getElementById("formula-input").value = formula;
      runFormulaEvaluation();
    },
    onShowBanner: (txt) => {
      const msg =
        getLang() === "vi"
          ? `Hàm ${txt} chạy tự động trong Kiểm thử Danh mục & Crash-Test.`
          : `${txt} executes in the Portfolio Evaluation & Crash-Test workflows.`;
      showBanner("formula-notes-banner", msg);
    },
  });
  initPublicDataModal({
    onDatasetFetched: async (dsInfo) => {
      state.activeSymbol = null;
      await refreshDatasetDropdown(dsInfo.dataset_id);
      const { preview } = await loadActiveDatasetPreview();
      const input = document.getElementById("formula-input");
      if (dsInfo.columns.includes("taker_buy_ratio")) {
        input.value =
          dsInfo.symbol_count && dsInfo.symbol_count > 1
            ? "cs_rank(ema(taker_buy_ratio - 0.5, 12))"
            : "ema(taker_buy_ratio - 0.5, 12)";
      } else if (!preview.sectors.length && input.value.includes("sector")) {
        input.value = "ema(close, 12) - ema(close, 26)";
      }
      await runFormulaEvaluation();
    },
  });

  const getHoldoutLocked = () => state.holdoutLocked;
  getHoldoutLocked._externalManaged = true;

  const canvas = document.getElementById("tv-main-canvas");
  state.chart = new TVDualChart(canvas, updateLegendBar);
  state.btLab = new BacktestLabController({
    getDatasetId: () => state.activeDatasetId,
    getFormula: () => document.getElementById("formula-input").value.trim(),
    getSymbol: () => state.activeSymbol,
    getHoldoutLocked,
    setSymbolDropdown: syncSymbolSelect,
    candleChart: state.chart,
    onError: (msg) => showBanner("formula-error-banner", msg),
  });
  state.xrayLab = new XRayLabController({
    getDatasetId: () => state.activeDatasetId,
    getFormula: () => document.getElementById("formula-input").value.trim(),
    getHoldoutLocked,
    onPromoteFormula: (expr) => {
      document.getElementById("formula-input").value = expr;
      runFormulaEvaluation();
    },
    onError: (msg) => showBanner("formula-error-banner", msg),
  });
  state.crashtestLab = new CrashTestLabController({
    getDatasetId: () => state.activeDatasetId,
    getFormula: () => document.getElementById("formula-input").value.trim(),
    getHoldoutLocked,
    onError: (msg) => showBanner("formula-error-banner", msg),
  });
  initExportModal({
    getExportPayload: () => {
      const vt = Number(document.getElementById("bt-vol-slider").value);
      return {
        dataset_id: state.activeDatasetId,
        formula: document.getElementById("formula-input").value.trim(),
        weight_scheme: document.getElementById("bt-weight-select").value,
        execution_price: document.getElementById("bt-exec-select").value,
        fee_bps: Number(document.getElementById("bt-fee-slider").value),
        slippage_mode: document.getElementById("bt-slip-mode").value,
        slippage_bps: Number(document.getElementById("bt-slip-slider").value),
        vol_target: vt > 0 ? Number((vt / 100.0).toFixed(4)) : null,
        no_trade_buffer: Number(document.getElementById("bt-buf-slider").value),
        signal_lag: Number(document.getElementById("bt-lag-slider").value),
        limit_lock_skip: document.getElementById("bt-limit-lock").checked,
        intraday_flatten: document.getElementById("bt-intraday-flat").checked,
        delisting_penalty_bps_yr: Number(document.getElementById("ct-delist-slider").value),
        holdout_locked: state.holdoutLocked,
        lang: getLang(),
      };
    },
  });
  initGuideHub({
    onRunDemo: async (demo) => {
      const input = document.getElementById("formula-input");
      if (input && demo.formula) input.value = demo.formula;
      if (demo.preset && state.btLab) {
        const p = demo.preset;
        if (p.weight) document.getElementById("bt-weight-select").value = p.weight;
        if (p.slipMode) document.getElementById("bt-slip-mode").value = p.slipMode;
        if (p.fee !== undefined) document.getElementById("bt-fee-slider").value = String(p.fee);
        if (p.slip !== undefined) document.getElementById("bt-slip-slider").value = String(p.slip);
        if (p.buf !== undefined) document.getElementById("bt-buf-slider").value = String(p.buf);
        if (p.lag !== undefined) document.getElementById("bt-lag-slider").value = String(p.lag);
        document.getElementById("bt-preset-select").value = "custom";
        state.btLab._syncSliderLabels();
      }
      await runFormulaEvaluation();
      if (demo.tab && demo.tab !== state.activeTab) {
        const tabBtn = document.querySelector(`.tv-mode-tab[data-tab="${demo.tab}"]`);
        if (tabBtn) tabBtn.click();
      }
    },
  });

  window.addEventListener("aql:langchange", () => {
    renderDatasetMetaUi();
    renderEvalStatsUi(state.lastEvalRes);
    const engPill = document.getElementById("engine-status-pill");
    if (engPill && state.engineText) {
      engPill.title = t("nav.engine_title", { text: state.engineText });
    }
    if (state.chart) state.chart.render();
  });

  document.getElementById("btn-holdout-vault").addEventListener("click", () => {
    state.holdoutLocked = !state.holdoutLocked;
    if (state.btLab) state.btLab.scheduleRun(0);
    if (state.xrayLab && state.activeTab === "xray") state.xrayLab.scheduleRun(0);
    if (state.crashtestLab && state.activeTab === "crashtest") state.crashtestLab.scheduleRun(0);
  });

  try {
    const [health, catalog] = await Promise.all([fetchHealth(), fetchCatalog()]);
    state.engineText = `polars-anta ${health.polars_anta_version} (${health.polars_max_threads}T)`;
    document.getElementById("engine-status-text").textContent = state.engineText;
    const engPill = document.getElementById("engine-status-pill");
    if (engPill) engPill.title = t("nav.engine_title", { text: state.engineText });
    document.getElementById("catalog-count-badge").textContent = String(catalog.public_functions);
    state.fxCatalog.setCatalog(catalog);

    await refreshDatasetDropdown();
    await loadActiveDatasetPreview();
    await runFormulaEvaluation();
  } catch (err) {
    showBanner("formula-error-banner", `Startup error: ${err.message}`);
  }

  document.getElementById("dataset-select").addEventListener("change", async (ev) => {
    state.activeDatasetId = ev.target.value;
    state.activeSymbol = null;
    const { preview } = await loadActiveDatasetPreview();
    const input = document.getElementById("formula-input");
    const cols = preview.info.columns || [];
    if (input.value.includes("sector") && !cols.includes("sector")) {
      input.value = "ema(close, 12) - ema(close, 26)";
    } else if (input.value.includes("taker_buy") && !cols.includes("taker_buy_ratio")) {
      input.value = cols.includes("sector")
        ? "cs_rank(rsi(close, 14))"
        : "ema(close, 12) - ema(close, 26)";
    }
    await runFormulaEvaluation();
  });

  document.getElementById("symbol-select").addEventListener("change", (ev) => {
    state.activeSymbol = ev.target.value;
    runFormulaEvaluation();
  });

  document.getElementById("dataset-upload-input").addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    try {
      const uploaded = await uploadDatasetFile(file);
      state.activeSymbol = null;
      await refreshDatasetDropdown(uploaded.dataset_id);
      await loadActiveDatasetPreview();
      await runFormulaEvaluation();
    } catch (err) {
      showBanner("formula-error-banner", `Upload failed: ${err.message}`);
    } finally {
      ev.target.value = "";
    }
  });

  document.getElementById("btn-evaluate-formula").addEventListener("click", runFormulaEvaluation);
  document.getElementById("formula-input").addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey || !ev.shiftKey) && ev.key === "Enter") {
      ev.preventDefault();
      runFormulaEvaluation();
    }
  });

  document.querySelectorAll(".tv-preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.getElementById("formula-input").value = chip.dataset.formula;
      runFormulaEvaluation();
    });
  });
}

bootstrap();
