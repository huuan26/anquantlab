/**
 * Tab 3 Controller: Overfitting Crash-Test, 200 Stationary Bootstrap Worlds & Delisting Stress.
 */

import { runCrashTest } from "./api.js";
import { TVCrashTestChart } from "./tv_crashtest_chart.js";

function fmtSigned(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

export class CrashTestLabController {
  constructor({ getDatasetId, getFormula, getHoldoutLocked, onError }) {
    this.getDatasetId = getDatasetId;
    this.getFormula = getFormula;
    this.getHoldoutLocked = getHoldoutLocked;
    this.onError = onError;

    this.lastResponse = null;
    this.inFlight = false;
    this.queued = false;
    this.debounceTimer = null;

    const canvas = document.getElementById("tv-crashtest-canvas");
    this.chart = new TVCrashTestChart(canvas);
    this._bindControls();
  }

  _readParams() {
    return {
      dataset_id: this.getDatasetId(),
      formula: this.getFormula(),
      sweep_mode: document.getElementById("ct-sweep-mode").value,
      grid_size: Number(document.getElementById("ct-grid-size").value),
      weight_scheme: document.getElementById("ct-weight-select").value,
      fee_bps: Number(document.getElementById("ct-fee-slider").value),
      slippage_mode: document.getElementById("ct-slip-mode").value,
      slippage_bps: 5.0,
      delisting_penalty_bps_yr: Number(document.getElementById("ct-delist-slider").value),
      n_bootstrap: Number(document.getElementById("ct-boot-select").value),
      cscv_splits: Number(document.getElementById("ct-cscv-splits").value),
      seed: 42,
      holdout_locked: this.getHoldoutLocked(),
    };
  }

  _syncLabels() {
    const fee = Number(document.getElementById("ct-fee-slider").value);
    const delist = Number(document.getElementById("ct-delist-slider").value);
    document.getElementById("ct-fee-val").textContent = `${fee.toFixed(1)} bps`;
    document.getElementById("ct-delist-val").textContent =
      delist > 0 ? `${delist.toFixed(0)} bps/yr` : "OFF (0)";
  }

  _bindControls() {
    ["ct-fee-slider", "ct-delist-slider"].forEach((id) => {
      document.getElementById(id).addEventListener("input", () => {
        this._syncLabels();
        this.scheduleRun(45);
      });
    });

    [
      "ct-sweep-mode",
      "ct-grid-size",
      "ct-cscv-splits",
      "ct-weight-select",
      "ct-slip-mode",
      "ct-boot-select",
    ].forEach((id) => {
      document.getElementById(id).addEventListener("change", () => {
        this._syncLabels();
        this.scheduleRun(0);
      });
    });

    document.getElementById("btn-ct-run").addEventListener("click", () => this.executeNow());

    const btnBoot = document.getElementById("btn-ct-bl-boot");
    const btnCusum = document.getElementById("btn-ct-bl-cusum");
    btnBoot.addEventListener("click", () => {
      btnBoot.classList.add("active");
      btnCusum.classList.remove("active");
      this.chart.setBottomLeftMode("bootstrap");
    });
    btnCusum.addEventListener("click", () => {
      btnCusum.classList.add("active");
      btnBoot.classList.remove("active");
      this.chart.setBottomLeftMode("cusum");
    });

    this._syncLabels();
  }

  renderCurrentChart() {
    this.chart.render();
  }

  scheduleRun(delayMs = 25) {
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
    const btn = document.getElementById("btn-ct-run");
    if (btn) btn.disabled = true;
    try {
      const params = this._readParams();
      const res = await runCrashTest(params);
      this.lastResponse = res;
      this._renderResponse(res);
    } catch (err) {
      if (this.onError) this.onError(err.message || String(err));
    } finally {
      this.inFlight = false;
      if (btn) btn.disabled = false;
      if (this.queued) {
        this.queued = false;
        this.executeNow();
      }
    }
  }

  _renderResponse(res) {
    // Sync Topbar Holdout Vault & Cumulative Session Trial Ledger Pill
    const vaultBtn = document.getElementById("btn-holdout-vault");
    const tl = res.trial_ledger;
    if (res.holdout_locked) {
      vaultBtn.textContent = `Vault: SEALED (${res.is_bars} IS)`;
      vaultBtn.className = "tv-tool-btn tv-vault-sealed num";
    } else {
      vaultBtn.textContent = `Vault: OOS OPEN (Peeks: ${tl.holdout_peeks})`;
      vaultBtn.className = "tv-tool-btn tv-vault-open num";
    }

    const sessBar = res.haircut_bars && res.haircut_bars[2];
    const dsrPct =
      sessBar && sessBar.probability !== null && sessBar.probability !== undefined
        ? `${(sessBar.probability * 100).toFixed(1)}%`
        : "--";
    document.getElementById("trial-ledger-text").textContent =
      `Trials ${tl.unique_trials} | N_eff ${tl.effective_n_trials.toFixed(1)} | DSR ${dsrPct}`;

    document.getElementById("ct-rail-latency").textContent =
      `${res.elapsed_ms.toFixed(1)} ms | ${res.candidates.length} Grid Trials | N_eff ${tl.effective_n_trials.toFixed(1)}`;
    document.getElementById("ct-formula-code").textContent = res.normalized_formula;

    const verdictEl = document.getElementById("ct-verdict-banner");
    verdictEl.textContent = `${res.verdict}: ${res.verdict_summary}`;
    verdictEl.className = `tv-xr-verdict num ${
      res.verdict === "SURVIVES_FALSIFICATION"
        ? "val-pos"
        : res.verdict === "OVERFIT_REJECTED"
          ? "val-neg"
          : "val-warn"
    }`;

    this._renderTopCards(res);
    this.chart.setData(res);
    this._renderCandidatesTable(res);
  }

  _renderTopCards(res) {
    const strip = document.getElementById("ct-summary-strip");
    strip.textContent = "";
    const hm = res.heatmap;
    const pbo = res.pbo;
    const bs = res.bootstrap;
    const cs = res.cusum;
    const rwGate = res.funnel[4] || { survivors: 0, total: 0 };
    const finalGate = res.funnel[6] || { survivors: 0, total: 0 };

    const cards = [
      [
        "1. 2D Surface & Plateau",
        `Base ${fmtSigned(hm.baseline_sharpe, 2)}`,
        hm.baseline_sharpe > 0.5 ? "val-pos" : hm.baseline_sharpe < 0 ? "val-neg" : "",
        `Peak ${fmtSigned(hm.best_sharpe, 2)} | Med ${fmtSigned(hm.median_sharpe, 2)}`,
        `Plateau ${hm.neighbor_plateau_ratio.toFixed(2)} | Pos ${(hm.positive_grid_share * 100).toFixed(0)}%`,
      ],
      [
        "2. CSCV Overfit (PBO)",
        `PBO ${(pbo.pbo * 100).toFixed(1)}%`,
        pbo.pbo < 0.35 ? "val-pos" : pbo.pbo >= 0.55 ? "val-neg" : "val-warn",
        `OOS Loss Prob ${(pbo.prob_oos_loss * 100).toFixed(1)}%`,
        `${pbo.n_combinations.toLocaleString()} Splits | Slope ${pbo.degradation_slope.toFixed(2)}`,
      ],
      [
        "3. Bootstrap & Null World",
        `Null p ${bs.null_p_value.toFixed(3)}`,
        bs.null_p_value <= 0.05 ? "val-pos" : bs.null_p_value > 0.25 ? "val-neg" : "val-warn",
        `Boot Med SR ${fmtSigned(bs.sharpe_median, 2)} | Null95 ${bs.null_sharpe_95.toFixed(2)}`,
        `P(SR>0) ${(bs.prob_positive_world * 100).toFixed(0)}% | P95 DD ${(bs.max_dd_p95_worst * 100).toFixed(1)}%`,
      ],
      [
        "4. Romano-Wolf & CUSUM",
        `RW ${rwGate.survivors}/${rwGate.total}`,
        rwGate.survivors > 0 && !cs.has_break ? "val-pos" : cs.has_break ? "val-warn" : "",
        `All-7 Gate Survivors: ${finalGate.survivors}/${finalGate.total}`,
        `CUSUM Q=${cs.statistic.toFixed(2)} (p=${cs.p_value.toFixed(2)}) ${cs.has_break ? "BREAK" : "STABLE"}`,
      ],
    ];

    for (const [title, tagTxt, tagCls, r1, r2] of cards) {
      const card = document.createElement("div");
      card.className = "tv-xr-stage-card tv-ct-stat-card";

      const hdr = document.createElement("div");
      hdr.className = "tv-xr-card-hdr";
      const sTitle = document.createElement("span");
      sTitle.textContent = title;
      const sTag = document.createElement("span");
      sTag.className = `num ${tagCls}`;
      sTag.textContent = tagTxt;
      hdr.append(sTitle, sTag);

      const d1 = document.createElement("div");
      d1.className = "tv-xr-card-metrics num";
      d1.textContent = r1;

      const d2 = document.createElement("div");
      d2.className = "tv-xr-card-metrics num";
      d2.textContent = r2;

      card.append(hdr, d1, d2);
      strip.appendChild(card);
    }
  }

  _renderCandidatesTable(res) {
    const tbody = document.getElementById("ct-candidates-tbody");
    tbody.textContent = "";
    const badge = document.getElementById("ct-surv-badge");
    const survivedCnt = res.candidates.filter((c) => c.survived_all).length;
    if (badge) badge.textContent = `${survivedCnt}/${res.candidates.length}`;

    for (const row of res.candidates) {
      const tr = document.createElement("tr");
      const cells = [
        [`#${row.rank}`, ""],
        [row.formula_label, "mono"],
        [fmtSigned(row.sharpe, 3), row.sharpe > 0 ? "val-pos" : row.sharpe < 0 ? "val-neg" : ""],
        [`${(row.total_return * 100).toFixed(2)}%`, row.total_return >= 0 ? "val-pos" : "val-neg"],
        [fmtSigned(row.nw_t_stat, 2), row.nw_t_stat >= 1.96 ? "val-pos" : ""],
        [row.p_raw.toFixed(4), ""],
        [row.q_bh.toFixed(4), row.q_bh <= 0.1 ? "val-pos" : ""],
        [row.p_romano_wolf.toFixed(4), row.p_romano_wolf <= 0.05 ? "val-pos" : ""],
        [fmtSigned(row.eb_posterior_sharpe, 3), ""],
        [`${(row.eb_prob_positive * 100).toFixed(1)}%`, row.eb_prob_positive >= 0.8 ? "val-pos" : ""],
        [row.cusum_p.toFixed(3), row.cusum_p < 0.05 ? "val-warn" : ""],
        [row.survived_all ? "PASS" : "REJECT", row.survived_all ? "val-pos" : "val-neg"],
      ];
      for (const [txt, cls] of cells) {
        const td = document.createElement("td");
        td.textContent = txt;
        if (cls) td.className = cls;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }
}
