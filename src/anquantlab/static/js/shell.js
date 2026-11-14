/**
 * Phase 1 Workbench Controller: Theme, Dynamic 225-Export Catalog, Dataset Store & Causal DSL Preview.
 */

import {
  fetchCatalog,
  fetchDatasetPreview,
  fetchDatasets,
  fetchHealth,
  previewFormula,
  uploadDatasetFile,
} from "./api.js";

const state = {
  catalog: null,
  activeDomain: "all",
  searchQuery: "",
  activeDatasetId: "builtin_demo_panel",
  activeTab: "backtest",
};

function fmtNum(val, digits = 4) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) {
    return "--";
  }
  return Number(val).toFixed(digits);
}

function initTheme() {
  const saved = localStorage.getItem("anquantlab_theme") || "dark";
  applyTheme(saved);
  const btn = document.getElementById("btn-theme-toggle");
  btn.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("anquantlab_theme", next);
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const sun = document.getElementById("icon-sun");
  const moon = document.getElementById("icon-moon");
  if (theme === "dark") {
    sun.classList.remove("hidden");
    moon.classList.add("hidden");
  } else {
    sun.classList.add("hidden");
    moon.classList.remove("hidden");
  }
}

function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      state.activeTab = target;
      buttons.forEach((b) => {
        const active = b.dataset.tab === target;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("hidden", panel.id !== `panel-${target}`);
      });
    });
  });
}

function initMobileSidebar() {
  const btn = document.getElementById("btn-toggle-sidebar");
  const sidebar = document.getElementById("catalog-sidebar");
  btn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed-mobile");
  });
}

function renderDomainChips() {
  const wrap = document.getElementById("domain-chips");
  wrap.textContent = "";
  if (!state.catalog) return;

  const allChip = document.createElement("button");
  allChip.type = "button";
  allChip.className = `domain-chip mono ${state.activeDomain === "all" ? "active" : ""}`;
  allChip.textContent = `All (${state.catalog.total_exports})`;
  allChip.addEventListener("click", () => {
    state.activeDomain = "all";
    renderDomainChips();
    renderCatalogItems();
  });
  wrap.appendChild(allChip);

  for (const dom of state.catalog.domains) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `domain-chip mono ${state.activeDomain === dom.domain ? "active" : ""}`;
    chip.textContent = `${dom.domain} (${dom.count})`;
    chip.title = dom.label;
    chip.addEventListener("click", () => {
      state.activeDomain = dom.domain;
      renderDomainChips();
      renderCatalogItems();
    });
    wrap.appendChild(chip);
  }
}

function renderCatalogItems() {
  const listEl = document.getElementById("catalog-list");
  listEl.textContent = "";
  if (!state.catalog) return;

  const q = state.searchQuery.trim().toLowerCase();
  const filtered = state.catalog.items.filter((item) => {
    if (state.activeDomain !== "all" && item.domain !== state.activeDomain) {
      return false;
    }
    if (!q) return true;
    return (
      item.name.toLowerCase().includes(q) ||
      item.summary.toLowerCase().includes(q) ||
      item.domain.toLowerCase().includes(q)
    );
  });

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted-caption";
    empty.textContent = "No matching exports in polars-anta.";
    listEl.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  for (const item of filtered) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "catalog-item";
    card.setAttribute("role", "listitem");

    const top = document.createElement("div");
    top.className = "catalog-item-top";

    const fnSpan = document.createElement("span");
    fnSpan.className = "catalog-fn-name mono";
    fnSpan.textContent = item.name;

    const kindSpan = document.createElement("span");
    kindSpan.className = "catalog-kind-tag mono";
    kindSpan.textContent = item.kind;

    top.appendChild(fnSpan);
    top.appendChild(kindSpan);

    const sigDiv = document.createElement("div");
    sigDiv.className = "catalog-sig mono";
    sigDiv.textContent = item.signature;

    const descDiv = document.createElement("div");
    descDiv.className = "catalog-desc";
    descDiv.textContent = item.summary;

    card.appendChild(top);
    card.appendChild(sigDiv);
    card.appendChild(descDiv);

    card.addEventListener("click", () => {
      if (item.kind === "expr_ts" || item.kind === "expr_cs") {
        const input = document.getElementById("formula-input");
        input.value = item.sample_formula;
        input.focus();
        runFormulaEvaluation();
      } else {
        showBanner(
          "formula-notes-banner",
          `'${item.name}' (${item.kind}) is a portfolio/inference operator executed automatically in the Evaluation & Crash-Test tabs.`
        );
      }
    });

    frag.appendChild(card);
  }
  listEl.appendChild(frag);
}

function renderTable(tableId, rows) {
  const table = document.getElementById(tableId);
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.textContent = "";
  tbody.textContent = "";

  if (!rows || rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = "No rows available.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const cols = Object.keys(rows[0]);
  const headTr = document.createElement("tr");
  for (const col of cols) {
    const th = document.createElement("th");
    th.textContent = col;
    headTr.appendChild(th);
  }
  thead.appendChild(headTr);

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const col of cols) {
      const td = document.createElement("td");
      const v = row[col];
      if (typeof v === "number") {
        td.textContent = Number.isInteger(v) ? String(v) : v.toFixed(4);
      } else {
        td.textContent = v === null || v === undefined ? "null" : String(v);
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function showBanner(id, message) {
  const el = document.getElementById(id);
  if (!message) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = message;
  el.classList.remove("hidden");
}

async function loadActiveDatasetPreview() {
  const preview = await fetchDatasetPreview(state.activeDatasetId);
  const info = preview.info;

  document.getElementById("kpi-rows").textContent =
    info.row_count !== null ? info.row_count.toLocaleString() : "--";
  document.getElementById("kpi-span").textContent =
    info.date_start && info.date_end ? `${info.date_start} -> ${info.date_end}` : "--";
  document.getElementById("kpi-symbols").textContent =
    info.symbol_count !== null ? `${info.symbol_count} tickers` : "1 series";
  document.getElementById("kpi-sectors").textContent =
    preview.sectors.length > 0
      ? `${preview.sectors.length} sectors (${preview.sectors.slice(0, 3).join(", ")}${preview.sectors.length > 3 ? "..." : ""})`
      : "No sector column";

  const ohlcvEl = document.getElementById("kpi-ohlcv");
  ohlcvEl.textContent = preview.ohlcv_valid ? "PASS" : "WARN";
  ohlcvEl.style.color = preview.ohlcv_valid ? "var(--positive)" : "var(--warning)";
  document.getElementById("kpi-hash").textContent = `sha256: ${info.sha256_prefix || "--"}`;
  document.getElementById("dataset-columns-caption").textContent = `Columns: ${info.columns.join(", ")}`;

  renderTable("dataset-preview-table", preview.sample_rows);
}

async function runFormulaEvaluation() {
  const btn = document.getElementById("btn-evaluate-formula");
  const formula = document.getElementById("formula-input").value.trim();
  if (!formula) return;

  showBanner("formula-error-banner", "");
  showBanner("formula-notes-banner", "");
  btn.disabled = true;

  try {
    const res = await previewFormula(state.activeDatasetId, formula, 10);
    document.getElementById("kpi-coverage").textContent = `${res.stats.coverage_pct.toFixed(1)}%`;
    document.getElementById("kpi-latency").textContent = `${res.elapsed_ms.toFixed(2)} ms (${res.stats.valid_count.toLocaleString()} valid)`;

    const cacheBadge = document.getElementById("cache-badge");
    cacheBadge.textContent = res.cache_hit ? "LRU HIT" : "COMPUTED";

    if (res.notes && res.notes.length > 0) {
      showBanner("formula-notes-banner", res.notes.join(" | "));
    }

    const stageList = document.getElementById("stage-list");
    stageList.textContent = "";
    for (const st of res.stages) {
      const li = document.createElement("li");
      const scopeSpan = document.createElement("span");
      scopeSpan.className = "stage-scope mono";
      scopeSpan.textContent = st.window_over ? `${st.scope} [.over(${st.window_over})]` : st.scope;
      li.appendChild(scopeSpan);
      li.appendChild(document.createTextNode(st.description));
      stageList.appendChild(li);
    }

    const statsGrid = document.getElementById("signal-stats-grid");
    statsGrid.textContent = "";
    const pairs = [
      ["Mean", fmtNum(res.stats.mean)],
      ["Std Dev", fmtNum(res.stats.std)],
      ["Median", fmtNum(res.stats.median)],
      ["Min", fmtNum(res.stats.min)],
      ["IQR (Q25..Q75)", `${fmtNum(res.stats.q25, 3)} .. ${fmtNum(res.stats.q75, 3)}`],
      ["Max", fmtNum(res.stats.max)],
    ];
    for (const [label, val] of pairs) {
      const cell = document.createElement("div");
      cell.className = "stat-cell";
      const lbl = document.createElement("div");
      lbl.className = "stat-cell-label";
      lbl.textContent = label;
      const vEl = document.createElement("div");
      vEl.className = "stat-cell-val";
      vEl.textContent = val;
      cell.appendChild(lbl);
      cell.appendChild(vEl);
      statsGrid.appendChild(cell);
    }

    renderTable("signal-preview-table", res.sample_rows);
  } catch (err) {
    showBanner("formula-error-banner", err.message || String(err));
  } finally {
    btn.disabled = false;
  }
}

async function refreshDatasetDropdown(selectIdToActivate = null) {
  const dsRes = await fetchDatasets();
  const sel = document.getElementById("dataset-select");
  sel.textContent = "";
  for (const ds of dsRes.datasets) {
    const opt = document.createElement("option");
    opt.value = ds.dataset_id;
    opt.textContent = ds.name;
    sel.appendChild(opt);
  }
  state.activeDatasetId = selectIdToActivate || dsRes.default_dataset_id;
  sel.value = state.activeDatasetId;
}

async function bootstrap() {
  initTheme();
  initTabs();
  initMobileSidebar();

  try {
    const [health, catalog] = await Promise.all([fetchHealth(), fetchCatalog()]);
    state.catalog = catalog;
    document.getElementById("engine-status-text").textContent =
      `polars-anta v${health.polars_anta_version} | threads=${health.polars_max_threads}`;
    document.getElementById("catalog-count-badge").textContent =
      `${catalog.public_functions} fn / ${catalog.total_exports} exp`;

    renderDomainChips();
    renderCatalogItems();

    await refreshDatasetDropdown();
    await loadActiveDatasetPreview();
    await runFormulaEvaluation();
  } catch (err) {
    showBanner("formula-error-banner", `Initialization failed: ${err.message}`);
  }

  document.getElementById("catalog-search").addEventListener("input", (ev) => {
    state.searchQuery = ev.target.value;
    renderCatalogItems();
  });

  document.getElementById("dataset-select").addEventListener("change", async (ev) => {
    state.activeDatasetId = ev.target.value;
    const input = document.getElementById("formula-input");
    if (state.activeDatasetId === "builtin_demo_futures" && input.value.includes("sector")) {
      input.value = "ema(close, 12) - ema(close, 26)";
    }
    await loadActiveDatasetPreview();
    await runFormulaEvaluation();
  });

  document.getElementById("dataset-upload-input").addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    showBanner("formula-error-banner", "");
    try {
      const uploaded = await uploadDatasetFile(file);
      await refreshDatasetDropdown(uploaded.dataset_id);
      await loadActiveDatasetPreview();
      await runFormulaEvaluation();
    } catch (err) {
      showBanner("formula-error-banner", `Upload failed: ${err.message}`);
    } finally {
      ev.target.value = "";
    }
  });

  document.getElementById("formula-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    runFormulaEvaluation();
  });

  document.querySelectorAll(".preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.getElementById("formula-input").value = chip.dataset.formula;
      runFormulaEvaluation();
    });
  });
}

bootstrap();
