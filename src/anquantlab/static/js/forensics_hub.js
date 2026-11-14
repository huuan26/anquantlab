/**
 * Free-Data Forensics, Implicit OHLCV Spread Audit & Zero-Key Public Data Hub UI.
 */

import { fetchPublicDataset, fetchPublicPresets } from "./api.js";

function fmtBps(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "--";
  return `${Number(val).toFixed(2)} bps`;
}

function gradeTone(grade) {
  if (grade === "A") return "var(--tv-up)";
  if (grade === "B") return "var(--tv-blue)";
  if (grade === "C") return "var(--tv-warn)";
  return "var(--tv-down)";
}

export function renderForensicsPanel(f) {
  if (!f) return;

  const pill = document.getElementById("forensics-pill");
  if (pill) {
    pill.textContent = `Health ${f.health_score} (${f.grade}) | Min Slip ${f.recommended_min_slippage_bps.toFixed(1)} bps`;
    pill.style.borderColor = gradeTone(f.grade);
    pill.style.color = gradeTone(f.grade);
  }

  const tabBadge = document.getElementById("forensics-badge");
  if (tabBadge) {
    tabBadge.textContent = `${f.health_score}/${f.grade}`;
    tabBadge.style.color = gradeTone(f.grade);
  }

  const healthEl = document.getElementById("fkpi-health");
  healthEl.textContent = `${f.health_score} / 100 (${f.grade})`;
  healthEl.style.color = gradeTone(f.grade);
  document.getElementById("fkpi-health-sub").textContent =
    `${f.ohlc_violations} OHLC err | ${f.duplicate_rows} dup`;

  document.getElementById("fkpi-cs").textContent = fmtBps(f.corwin_schultz_spread_bps_median);
  document.getElementById("fkpi-cs-sub").textContent =
    `P90 tail: ${fmtBps(f.corwin_schultz_spread_bps_p90)}`;

  document.getElementById("fkpi-roll").textContent = fmtBps(f.roll_spread_bps_median);
  document.getElementById("fkpi-roll-sub").textContent =
    `Amihud: ${f.amihud_illiq_median !== null && f.amihud_illiq_median !== undefined ? Number(f.amihud_illiq_median).toFixed(4) : "--"}`;

  const slipEl = document.getElementById("fkpi-slip");
  slipEl.textContent = `${f.recommended_min_slippage_bps.toFixed(2)} bps`;
  slipEl.style.color = f.recommended_min_slippage_bps > 15 ? "var(--tv-warn)" : "var(--tv-up)";
  document.getElementById("fkpi-slip-sub").textContent = "1-way half-spread floor";

  const survEl = document.getElementById("fkpi-surv");
  survEl.textContent = f.survivorship_risk;
  survEl.style.color =
    f.survivorship_risk === "HIGH"
      ? "var(--tv-warn)"
      : f.survivorship_risk === "LOW"
        ? "var(--tv-up)"
        : "var(--tv-text-primary)";
  document.getElementById("fkpi-surv-sub").textContent =
    `Late: ${f.late_listings} | Dropouts: ${f.early_dropouts}`;

  const dirtyEl = document.getElementById("fkpi-dirty");
  dirtyEl.textContent = `${f.split_suspect_jumps} jumps | ${f.zero_volume_bars} 0-vol`;
  dirtyEl.style.color =
    f.split_suspect_jumps > 0 || f.ohlc_violations > 0 ? "var(--tv-warn)" : "var(--tv-text-primary)";
  document.getElementById("fkpi-dirty-sub").textContent =
    `Frozen: ${f.frozen_bars} (${f.frozen_pct}%) | Taker Flow: ${f.has_taker_flow ? "YES" : "NO"}`;

  const takerChip = document.getElementById("btn-taker-preset");
  if (takerChip) {
    takerChip.classList.toggle("hidden", !f.has_taker_flow);
  }

  const warnList = document.getElementById("forensics-warnings-list");
  warnList.textContent = "";
  if (!f.warnings || f.warnings.length === 0) {
    const li = document.createElement("li");
    li.className = "forensics-ok-item";
    li.textContent = "All automated free-data quality and survivorship checks passed.";
    warnList.appendChild(li);
  } else {
    for (const w of f.warnings) {
      const li = document.createElement("li");
      li.className = "forensics-warn-item";
      li.textContent = w;
      warnList.appendChild(li);
    }
  }

  const tbody = document.getElementById("forensics-anomalies-body");
  tbody.textContent = "";
  if (!f.sample_anomalies || f.sample_anomalies.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "tv-muted-meta";
    td.textContent = "No bar-level OHLC, split-jump, zero-volume, or frozen-bar anomalies detected.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    for (const ev of f.sample_anomalies) {
      const tr = document.createElement("tr");
      const cells = [ev.symbol || "--", ev.timestamp, ev.kind, ev.detail];
      cells.forEach((val, idx) => {
        const td = document.createElement("td");
        td.textContent = val;
        if (idx === 2) td.className = "mono val-warn";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }
  }
}

export function initPublicDataModal({ onDatasetFetched }) {
  const modal = document.getElementById("public-data-modal");
  const openBtn = document.getElementById("btn-open-public-data");
  const closeBtn = document.getElementById("btn-close-public-data");
  const listEl = document.getElementById("public-preset-list");
  const errEl = document.getElementById("public-data-error");
  const cacheMeta = document.getElementById("public-cache-meta");

  const setErr = (msg) => {
    errEl.textContent = msg || "";
    errEl.classList.toggle("hidden", !msg);
  };

  const closeModal = () => modal.classList.add("hidden");

  async function refreshPresets() {
    setErr("");
    listEl.textContent = "";
    try {
      const res = await fetchPublicPresets();
      cacheMeta.textContent = res.allow_public_fetch
        ? `Cache outside Git repo: ${res.cache_dir}`
        : "Public network fetch disabled (ANQUANTLAB_ALLOW_PUBLIC_FETCH=0); cached presets only.";

      for (const p of res.presets) {
        const card = document.createElement("div");
        card.className = "public-preset-card";

        const top = document.createElement("div");
        top.className = "public-preset-top";

        const titleWrap = document.createElement("div");
        titleWrap.className = "public-preset-title-wrap";
        const nameEl = document.createElement("span");
        nameEl.className = "public-preset-name";
        nameEl.textContent = p.name;

        const tags = document.createElement("div");
        tags.className = "public-preset-tags mono num";

        const srcTag = document.createElement("span");
        srcTag.className = "tv-micro-tag";
        srcTag.textContent = `${p.source.toUpperCase()} ${p.interval}`;
        tags.appendChild(srcTag);

        const symTag = document.createElement("span");
        symTag.className = "tv-micro-tag";
        symTag.textContent = `${p.symbols.length} sym`;
        tags.appendChild(symTag);

        if (p.has_taker_flow) {
          const flowTag = document.createElement("span");
          flowTag.className = "tv-micro-tag tag-blue";
          flowTag.textContent = "TAKER FLOW";
          tags.appendChild(flowTag);
        }

        if (p.cached) {
          const cacheTag = document.createElement("span");
          cacheTag.className = "tv-micro-tag tag-up";
          cacheTag.textContent = "CACHED";
          tags.appendChild(cacheTag);
        }

        titleWrap.append(nameEl, tags);

        const btnGroup = document.createElement("div");
        btnGroup.className = "public-preset-actions";

        const loadBtn = document.createElement("button");
        loadBtn.type = "button";
        loadBtn.className = "tv-btn-primary";
        loadBtn.disabled = !res.allow_public_fetch && !p.cached;
        loadBtn.textContent = p.cached ? "Load Cached" : "Fetch Free";

        const triggerFetch = async (forceRefresh) => {
          setErr("");
          loadBtn.disabled = true;
          const origLabel = loadBtn.textContent;
          loadBtn.textContent = forceRefresh ? "Refreshing..." : "Loading...";
          try {
            const dsInfo = await fetchPublicDataset(p.preset_id, forceRefresh);
            closeModal();
            if (onDatasetFetched) await onDatasetFetched(dsInfo);
          } catch (err) {
            setErr(err.message || String(err));
            loadBtn.textContent = origLabel;
            loadBtn.disabled = false;
          }
        };

        loadBtn.addEventListener("click", () => triggerFetch(false));
        btnGroup.appendChild(loadBtn);

        if (p.cached && res.allow_public_fetch) {
          const refBtn = document.createElement("button");
          refBtn.type = "button";
          refBtn.className = "tv-tool-btn";
          refBtn.textContent = "Refresh";
          refBtn.addEventListener("click", () => triggerFetch(true));
          btnGroup.appendChild(refBtn);
        }

        top.append(titleWrap, btnGroup);

        const desc = document.createElement("div");
        desc.className = "public-preset-desc";
        desc.textContent = `${p.description} Tickers: ${p.symbols.join(", ")}.`;

        card.append(top, desc);
        listEl.appendChild(card);
      }
    } catch (err) {
      setErr(err.message || String(err));
    }
  }

  openBtn.addEventListener("click", () => {
    modal.classList.remove("hidden");
    refreshPresets();
  });
  closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) closeModal();
  });
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !modal.classList.contains("hidden")) {
      closeModal();
    }
  });
}
