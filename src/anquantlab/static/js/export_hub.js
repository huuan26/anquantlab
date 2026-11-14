/**
 * 1-Click Production Polars Codegen, HTML Tearsheet & Cryptographic Alpha Passport Hub.
 */

import { fetchExportBundle } from "./api.js";
import { getLang, localizeTag, t } from "./i18n.js";

function triggerDownload(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function initExportModal({ getExportPayload }) {
  const modal = document.getElementById("export-modal");
  const openBtn = document.getElementById("btn-open-export");
  const closeBtn = document.getElementById("btn-close-export");
  const errBanner = document.getElementById("export-error-banner");
  const codePre = document.getElementById("export-preview-pre");
  const tabPy = document.getElementById("btn-exp-tab-py");
  const tabJson = document.getElementById("btn-exp-tab-json");

  let currentBundle = null;
  let previewMode = "py";

  const syncPreview = () => {
    if (!currentBundle) return;
    tabPy.classList.toggle("active", previewMode === "py");
    tabJson.classList.toggle("active", previewMode === "json");
    codePre.textContent =
      previewMode === "py"
        ? currentBundle.python_code
        : JSON.stringify(currentBundle.passport, null, 2);
  };

  const renderBundle = (b) => {
    currentBundle = b;
    const p = b.passport;
    const vi = getLang() === "vi";
    const metaEl = document.getElementById("export-passport-meta");
    const sandboxTxt = b.ast_sandbox_clean
      ? vi ? "AST SANDBOX ĐẠT" : "AST SANDBOX PASS"
      : vi ? "CẢNH BÁO SANDBOX" : "SANDBOX WARN";
    const clearLabel = localizeTag("verdict", p.overall_clearance);
    metaEl.textContent =
      `${clearLabel} | ${sandboxTxt} | sha256:${p.passport_sha256.slice(0, 16)}... | ${b.elapsed_ms.toFixed(1)} ms`;
    metaEl.className = `tv-muted-meta mono ${
      p.overall_clearance === "APPROVED_CANDIDATE"
        ? "val-pos"
        : p.overall_clearance === "REJECTED_OVERFIT"
          ? "val-neg"
          : "val-warn"
    }`;

    const kpiWrap = document.getElementById("export-kpi-strip");
    kpiWrap.textContent = "";
    const cells = vi
      ? [
          [
            "Dữ liệu & Sức khỏe",
            `${p.dataset_audit.health_score.toFixed(0)}/100`,
            `sha256:${p.dataset_audit.sha256_prefix || "mem"} | Rủi ro ${p.dataset_audit.survivorship_grade}`,
          ],
          [
            "Sharpe Ròng (IS)",
            `${p.backtest_audit.net_sharpe >= 0 ? "+" : ""}${p.backtest_audit.net_sharpe.toFixed(2)}`,
            `Hòa vốn ${p.backtest_audit.breakeven_bps.toFixed(1)} bps | Sụt ${(p.backtest_audit.max_drawdown * 100).toFixed(1)}%`,
          ],
          [
            "Sổ Thử nghiệm & DSR",
            `${(p.trial_ledger_audit.live_dsr * 100).toFixed(1)}%`,
            `Thử ${p.trial_ledger_audit.unique_trials} | N_eff ${p.trial_ledger_audit.effective_n_trials.toFixed(1)} | Mở OOS ${p.trial_ledger_audit.holdout_peeks}`,
          ],
          [
            "Độc lập & PBO",
            `PBO ${(p.falsification_audit.pbo * 100).toFixed(1)}%`,
            `Độc lập ${(p.xray_audit.orthogonal_share * 100).toFixed(0)}% | Null p=${p.falsification_audit.null_p_value.toFixed(3)}`,
          ],
        ]
      : [
          [
            "Dataset & Forensics",
            `${p.dataset_audit.health_score.toFixed(0)}/100`,
            `sha256:${p.dataset_audit.sha256_prefix || "mem"} | Surv ${p.dataset_audit.survivorship_grade}`,
          ],
          [
            "Net IS Sharpe",
            `${p.backtest_audit.net_sharpe >= 0 ? "+" : ""}${p.backtest_audit.net_sharpe.toFixed(2)}`,
            `BE ${p.backtest_audit.breakeven_bps.toFixed(1)} bps | DD ${(p.backtest_audit.max_drawdown * 100).toFixed(1)}%`,
          ],
          [
            "Trial Ledger & DSR",
            `${(p.trial_ledger_audit.live_dsr * 100).toFixed(1)}%`,
            `Trials ${p.trial_ledger_audit.unique_trials} | N_eff ${p.trial_ledger_audit.effective_n_trials.toFixed(1)} | Peeks ${p.trial_ledger_audit.holdout_peeks}`,
          ],
          [
            "Spanning & PBO",
            `PBO ${(p.falsification_audit.pbo * 100).toFixed(1)}%`,
            `Pure ${(p.xray_audit.orthogonal_share * 100).toFixed(0)}% | Null p=${p.falsification_audit.null_p_value.toFixed(3)}`,
          ],
        ];

    for (const [lbl, val, sub] of cells) {
      const c = document.createElement("div");
      c.className = "tv-kpi-cell";
      const lEl = document.createElement("div");
      lEl.className = "tv-kpi-lbl";
      lEl.textContent = lbl;
      const vEl = document.createElement("div");
      vEl.className = "tv-kpi-val num";
      vEl.textContent = val;
      const sEl = document.createElement("div");
      sEl.className = "tv-kpi-sub num";
      sEl.textContent = sub;
      c.append(lEl, vEl, sEl);
      kpiWrap.appendChild(c);
    }

    syncPreview();
  };

  const openAndBuild = async () => {
    modal.classList.remove("hidden");
    errBanner.classList.add("hidden");
    codePre.textContent =
      getLang() === "vi"
        ? "Đang biên dịch mã Python độc lập, Báo cáo HTML & Chứng chỉ SHA-256..."
        : "Compiling standalone Polars + polars-anta script & Alpha Passport...";
    try {
      const res = await fetchExportBundle(getExportPayload());
      renderBundle(res);
    } catch (err) {
      errBanner.textContent = err.message || String(err);
      errBanner.classList.remove("hidden");
      codePre.textContent = "";
    }
  };

  window.addEventListener("aql:langchange", () => {
    if (!modal.classList.contains("hidden")) {
      openAndBuild();
    } else {
      currentBundle = null;
    }
  });

  const closeModal = () => modal.classList.add("hidden");
  openBtn.addEventListener("click", openAndBuild);
  closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) closeModal();
  });

  tabPy.addEventListener("click", () => {
    previewMode = "py";
    syncPreview();
  });
  tabJson.addEventListener("click", () => {
    previewMode = "json";
    syncPreview();
  });

  document.getElementById("btn-dl-py").addEventListener("click", () => {
    if (!currentBundle) return;
    triggerDownload(currentBundle.python_filename, currentBundle.python_code, "text/x-python;charset=utf-8");
  });

  document.getElementById("btn-copy-py").addEventListener("click", async (ev) => {
    if (!currentBundle || !navigator.clipboard) return;
    await navigator.clipboard.writeText(currentBundle.python_code);
    const btn = ev.currentTarget;
    btn.textContent = t("mod.exp_copied");
    setTimeout(() => {
      btn.textContent = t("mod.exp_copy");
    }, 1200);
  });

  document.getElementById("btn-dl-html").addEventListener("click", () => {
    if (!currentBundle) return;
    triggerDownload(currentBundle.tearsheet_filename, currentBundle.tearsheet_html, "text/html;charset=utf-8");
  });

  document.getElementById("btn-dl-passport").addEventListener("click", () => {
    if (!currentBundle) return;
    triggerDownload(
      currentBundle.passport_filename,
      `${JSON.stringify(currentBundle.passport, null, 2)}\n`,
      "application/json;charset=utf-8"
    );
  });
}
