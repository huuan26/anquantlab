/**
 * Tab 2 Controller: 4-Stage Causal Alpha Pipeline X-Ray & 5-Factor Spanning Check.
 */

import { runXRay } from "./api.js";
import { syncVaultAndLedgerUi } from "./forensics_hub.js";
import { TVXRayChart } from "./tv_xray_chart.js";

function fmtSigned(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

export class XRayLabController {
  constructor({ getDatasetId, getFormula, getHoldoutLocked, onPromoteFormula, onError }) {
    this.getDatasetId = getDatasetId;
    this.getFormula = getFormula;
    this.getHoldoutLocked = getHoldoutLocked;
    this.onPromoteFormula = onPromoteFormula;
    this.onError = onError;

    this.activeStageIdx = 3; // Default inspect Stage 4: Orthogonalized
    this.lastResponse = null;
    this.inFlight = false;
    this.queued = false;
    this.debounceTimer = null;

    const canvas = document.getElementById("tv-xray-canvas");
    this.chart = new TVXRayChart(canvas);
    this._bindControls();
  }

  _readParams() {
    const method = document.getElementById("xr-winsor-method").value;
    const clipPct = Number(document.getElementById("xr-winsor-slider").value);
    const orthoFactors = [];
    document.querySelectorAll(".xr-factor-chk").forEach((chk) => {
      if (chk.checked) orthoFactors.push(chk.value);
    });

    return {
      dataset_id: this.getDatasetId(),
      formula: this.getFormula(),
      winsor_method: method,
      winsor_clip: Math.max(0.005, Math.min(0.2, clipPct / 100.0)),
      winsor_threshold: Number((1.5 + clipPct * 0.25).toFixed(2)),
      neutralize_mode: document.getElementById("xr-neutral-mode").value,
      ortho_factors: orthoFactors,
      ic_horizon: Number(document.getElementById("xr-ic-horizon").value),
      ic_method: document.getElementById("xr-ic-method").value,
      holdout_locked: this.getHoldoutLocked(),
    };
  }

  _syncLabels() {
    const method = document.getElementById("xr-winsor-method").value;
    const clipPct = Number(document.getElementById("xr-winsor-slider").value);
    const outEl = document.getElementById("xr-winsor-val");
    if (method === "quantile") {
      outEl.textContent = `${clipPct.toFixed(1)}% / ${(100 - clipPct).toFixed(1)}%`;
    } else {
      outEl.textContent = `${(1.5 + clipPct * 0.25).toFixed(2)} sd`;
    }
  }

  _bindControls() {
    const slider = document.getElementById("xr-winsor-slider");
    slider.addEventListener("input", () => {
      this._syncLabels();
      this.scheduleRun(30);
    });

    ["xr-winsor-method", "xr-neutral-mode", "xr-ic-horizon", "xr-ic-method"].forEach((id) => {
      document.getElementById(id).addEventListener("change", () => {
        this._syncLabels();
        this.scheduleRun(0);
      });
    });

    document.querySelectorAll(".xr-factor-chk").forEach((chk) => {
      chk.addEventListener("change", () => this.scheduleRun(0));
    });

    const btnSec = document.getElementById("btn-xr-bl-sector");
    const btnCic = document.getElementById("btn-xr-bl-cumic");
    btnSec.addEventListener("click", () => {
      btnSec.classList.add("active");
      btnCic.classList.remove("active");
      this.chart.setBottomLeftMode("sector");
    });
    btnCic.addEventListener("click", () => {
      btnCic.classList.add("active");
      btnSec.classList.remove("active");
      this.chart.setBottomLeftMode("cum_ic");
    });

    document.getElementById("btn-xr-promote").addEventListener("click", () => {
      if (!this.lastResponse || !this.lastResponse.stages[this.activeStageIdx]) return;
      const st = this.lastResponse.stages[this.activeStageIdx];
      const expr = st.formula_preview.split("#")[0].trim();
      if (expr && this.onPromoteFormula) {
        this.onPromoteFormula(expr);
      }
    });

    this._syncLabels();
  }

  renderCurrentChart() {
    this.chart.render();
  }

  scheduleRun(delayMs = 20) {
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
      const res = await runXRay(params);
      this.lastResponse = res;
      this._renderResponse(res);
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

  _selectStage(idx) {
    this.activeStageIdx = idx;
    if (!this.lastResponse) return;
    this._renderStageStrip(this.lastResponse);
    const st = this.lastResponse.stages[this.activeStageIdx];
    this.chart.setData({
      stage: st,
      spanning: this.lastResponse.spanning,
      hasSector: this.lastResponse.has_sector,
    });
    document.getElementById("xr-stage-formula").textContent = st.formula_preview;
  }

  _renderResponse(res) {
    // Sync bottom-left toggle default if dataset lacks sectors
    const btnSec = document.getElementById("btn-xr-bl-sector");
    const btnCic = document.getElementById("btn-xr-bl-cumic");
    if (!res.has_sector && this.chart.bottomLeftMode !== "cum_ic") {
      btnCic.classList.add("active");
      btnSec.classList.remove("active");
      this.chart.setBottomLeftMode("cum_ic");
    } else if (res.has_sector && this.chart.bottomLeftMode === "auto") {
      btnSec.classList.add("active");
      btnCic.classList.remove("active");
    }

    syncVaultAndLedgerUi(res);

    const hitTag = res.basis_cache_hit ? "BASIS" : "COLD";
    document.getElementById("xr-rail-latency").textContent =
      `${res.elapsed_ms.toFixed(1)}ms | ${hitTag} | ${res.is_panel ? "Panel CS" : "Single TS"}`;

    const sp = res.spanning;
    const verdictEl = document.getElementById("xr-verdict-banner");
    verdictEl.textContent = sp.verdict.replace(/_/g, " ");
    verdictEl.title = `${sp.verdict}: ${sp.verdict_summary}`;
    verdictEl.className = `tv-xr-verdict num ${
      sp.verdict === "DISTINCT_ALPHA"
        ? "val-pos"
        : sp.verdict === "FACTOR_CLONE"
          ? "val-neg"
          : "val-warn"
    }`;

    this._renderStageStrip(res);
    const st = res.stages[this.activeStageIdx] || res.stages[0];
    if (st) {
      document.getElementById("xr-stage-formula").textContent = st.formula_preview;
      this.chart.setData({
        stage: st,
        spanning: res.spanning,
        hasSector: res.has_sector,
      });
    }
    this._renderBottomMatrices(res);
  }

  _renderStageStrip(res) {
    const strip = document.getElementById("xr-stage-strip");
    strip.textContent = "";
    res.stages.forEach((st, idx) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `tv-xr-stage-card ${idx === this.activeStageIdx ? "active" : ""}`;
      card.addEventListener("click", () => this._selectStage(idx));

      const hdr = document.createElement("div");
      hdr.className = "tv-xr-card-hdr";
      const title = document.createElement("span");
      title.textContent = st.label;
      const tTag = document.createElement("span");
      tTag.className = `num ${Math.abs(st.nw_t_stat) >= 1.96 ? "val-pos" : ""}`;
      tTag.textContent = `NW t ${fmtSigned(st.nw_t_stat, 2)}`;
      hdr.append(title, tTag);

      const row1 = document.createElement("div");
      row1.className = "tv-xr-card-metrics num";
      row1.textContent = `IC ${fmtSigned(st.ic_mean, 4)} | ICIR ${fmtSigned(st.icir, 2)}`;

      const row2 = document.createElement("div");
      row2.className = "tv-xr-card-metrics num";
      row2.textContent = `Q5-Q1 ${fmtSigned(st.top_minus_bottom_bps, 1)}bp | Turn ${st.turnover_mean.toFixed(2)}`;

      card.append(hdr, row1, row2);
      strip.appendChild(card);
    });
  }

  _renderBottomMatrices(res) {
    const stBody = document.getElementById("xr-stages-tbody");
    stBody.textContent = "";
    for (const st of res.stages) {
      const tr = document.createElement("tr");
      const cells = [
        st.label,
        fmtSigned(st.ic_mean, 4),
        fmtSigned(st.icir, 3),
        fmtSigned(st.nw_t_stat, 2),
        `${fmtSigned(st.top_minus_bottom_bps, 2)} bps`,
        fmtSigned(st.quantile_monotonicity, 2),
        st.turnover_mean.toFixed(3),
        `${(st.max_abs_sector_tilt * 100).toFixed(2)}%`,
        `${st.skew.toFixed(2)} / ${st.excess_kurtosis.toFixed(2)}`,
      ];
      cells.forEach((txt, i) => {
        const td = document.createElement("td");
        td.textContent = txt;
        if (i === 3 && Math.abs(st.nw_t_stat) >= 1.96) td.className = "val-pos";
        tr.appendChild(td);
      });
      stBody.appendChild(tr);
    }

    const spBody = document.getElementById("xr-spanning-tbody");
    spBody.textContent = "";
    for (const ld of res.spanning.loadings) {
      const tr = document.createElement("tr");
      const cells = [
        ld.factor_label,
        ld.selected ? "ON" : "OFF",
        fmtSigned(ld.beta, 4),
        fmtSigned(ld.nw_t_stat, 2),
        fmtSigned(ld.marginal_corr, 4),
        `${(ld.r2_contribution * 100).toFixed(2)}%`,
        fmtSigned(ld.post_ortho_corr, 4),
      ];
      cells.forEach((txt, i) => {
        const td = document.createElement("td");
        td.textContent = txt;
        if (i === 3 && Math.abs(ld.nw_t_stat) >= 1.96) td.className = "val-warn";
        if (i === 6 && Math.abs(ld.post_ortho_corr) < 1e-3) td.className = "val-pos";
        tr.appendChild(td);
      });
      spBody.appendChild(tr);
    }
  }
}
