/**
 * Onboarding Guide Modal (? Guide), 1-Click Case Studies & Tab Plain-Language Verdict Strips.
 */

import { GUIDE_CONTENT } from "./guide_data.js";
import { getLang, t } from "./i18n.js";

let activeGuideTab = "overview";
let guideCallbacks = null;
const lastTabPayloads = { backtest: null, xray: null, crashtest: null };

function mkEl(tag, cls, text = "") {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text) el.textContent = text;
  return el;
}

function setVerdictDom(id, tone, badgeText, summaryText) {
  const bar = document.getElementById(id);
  if (!bar) return;
  bar.textContent = "";

  const left = mkEl("div", "tv-verdict-left");
  const badge = mkEl("span", `tv-verdict-pill tv-verdict-${tone}`, badgeText);
  const text = mkEl("span", "tv-verdict-text", summaryText);
  text.title = summaryText;
  left.append(badge, text);

  const link = mkEl("button", "tv-verdict-link", `? ${t("verdict.more")}`);
  link.type = "button";
  link.addEventListener("click", () => openGuideModal("overview"));
  bar.append(left, link);
}

export function renderPlainVerdict(tabKey, res, params = null) {
  lastTabPayloads[tabKey] = { res, params };
  const lang = getLang();

  if (tabKey === "backtest" && res && res.metrics) {
    const m = res.metrics;
    const netPct = (m.total_return * 100).toFixed(1);
    const grossPct = (m.gross_total_return * 100).toFixed(1);
    const dragPct = ((m.gross_total_return - m.total_return) * 100).toFixed(1);
    const be = Number(m.breakeven_bps || 0).toFixed(1);
    const tone = m.sharpe_ratio >= 0.8 && m.total_return > 0 ? "pos" : m.total_return > 0 ? "warn" : "neg";
    const badge = tone === "pos" ? t("verdict.pass") : tone === "warn" ? t("verdict.warn") : t("verdict.fail");
    const msg =
      lang === "vi"
        ? `Lãi gộp ${grossPct}%, phí & trượt giá lấy đi ${dragPct}% -> Lãi thực ${netPct}% (chịu được phí tối đa ${be} bps/chiều).`
        : `Gross return ${grossPct}%, fees & slippage took ${dragPct}% -> Net ${netPct}% (breaks even around ${be} bps 1-way).`;
    setVerdictDom("bt-plain-verdict", tone, badge, msg);
    return;
  }

  if (tabKey === "xray" && res && res.spanning) {
    const sp = res.spanning;
    const spanPct = (sp.spanning_r2 * 100).toFixed(1);
    const purePct = (sp.orthogonal_share * 100).toFixed(1);
    const tone = sp.verdict === "DISTINCT_ALPHA" ? "pos" : sp.verdict === "FACTOR_CLONE" ? "neg" : "warn";
    const badge = tone === "pos" ? t("verdict.pass") : tone === "neg" ? t("verdict.fail") : t("verdict.warn");
    const msg =
      lang === "vi"
        ? `Tín hiệu trùng ${spanPct}% với các yếu tố phổ thông (Momentum/Beta), giữ lại ${purePct}% lợi thế độc lập thực sự.`
        : `${spanPct}% of signal moves like standard market factors; ${purePct}% remains pure independent alpha.`;
    setVerdictDom("xr-plain-verdict", tone, badge, msg);
    return;
  }

  if (tabKey === "crashtest" && res) {
    const pboPct = (res.pbo.pbo * 100).toFixed(0);
    const gate = (res.funnel && res.funnel[res.funnel.length - 1]) || { survivors: 0, total: 0 };
    const tone =
      res.verdict === "SURVIVES_FALSIFICATION" ? "pos" : res.verdict === "OVERFIT_REJECTED" ? "neg" : "warn";
    const badge = tone === "pos" ? t("verdict.pass") : tone === "neg" ? t("verdict.fail") : t("verdict.warn");
    const msg =
      lang === "vi"
        ? `${gate.survivors}/${gate.total} biến thể qua đủ 7 hàng rào thống kê (xác suất ăn may PBO ${pboPct}%). ${
            tone === "pos" ? "Có thể xem xét bước tiếp." : tone === "neg" ? "Nguy cơ overfit cao, chưa nên dùng tiền thật." : "Bằng chứng còn yếu, cần kiểm tra thêm."
          }`
        : `${gate.survivors}/${gate.total} variants passed all 7 statistical gates (PBO luck risk ${pboPct}%). ${
            tone === "pos" ? "Resilient against overfitting." : tone === "neg" ? "High overfit risk - avoid live deployment." : "Borderline robustness - inspect further."
          }`;
    setVerdictDom("ct-plain-verdict", tone, badge, msg);
  }
}

function renderGuideModalBody() {
  const lang = getLang();
  const c = GUIDE_CONTENT[lang] || GUIDE_CONTENT.en;
  const titleEl = document.getElementById("guide-modal-title");
  const subEl = document.getElementById("guide-modal-sub");
  const tabsEl = document.getElementById("guide-tabs-bar");
  const bodyEl = document.getElementById("guide-modal-body");
  if (!titleEl || !tabsEl || !bodyEl) return;

  titleEl.textContent = c.modalTitle;
  if (subEl) subEl.textContent = c.modalSub;

  tabsEl.textContent = "";
  for (const tb of c.tabs) {
    const btn = mkEl("button", `tv-seg-btn ${activeGuideTab === tb.id ? "active" : ""}`, tb.label);
    btn.type = "button";
    btn.addEventListener("click", () => {
      activeGuideTab = tb.id;
      renderGuideModalBody();
    });
    tabsEl.appendChild(btn);
  }

  bodyEl.textContent = "";
  if (activeGuideTab === "overview") {
    const probBox = mkEl("div", "guide-section");
    probBox.append(mkEl("h3", "guide-h3", c.problemTitle), mkEl("p", "guide-p", c.problemDesc));

    const stepsRow = mkEl("div", "guide-steps-grid");
    for (const st of c.steps) {
      const card = mkEl("div", "guide-step-card");
      card.append(mkEl("div", "guide-step-num", st.num), mkEl("div", "guide-step-txt", st.text));
      stepsRow.appendChild(card);
    }
    probBox.appendChild(stepsRow);

    const demoBox = mkEl("div", "guide-section");
    demoBox.appendChild(mkEl("h3", "guide-h3", c.demosTitle));
    const demoGrid = mkEl("div", "guide-demo-grid");
    for (const dm of c.demos) {
      const card = mkEl("div", "guide-demo-card");
      const top = mkEl("div", "guide-demo-top");
      top.append(mkEl("span", "tv-micro-tag tag-blue", dm.badge), mkEl("span", "guide-demo-title", dm.title));
      const desc = mkEl("p", "guide-p", dm.desc);
      const act = mkEl("button", "tv-btn-primary guide-demo-btn", dm.actionLabel);
      act.type = "button";
      act.addEventListener("click", async () => {
        closeGuideModal();
        if (guideCallbacks && guideCallbacks.onRunDemo) {
          await guideCallbacks.onRunDemo(dm);
        }
      });
      card.append(top, desc, act);
      demoGrid.appendChild(card);
    }
    demoBox.appendChild(demoGrid);
    bodyEl.append(probBox, demoBox);
  } else if (activeGuideTab === "realdata") {
    const sec = mkEl("div", "guide-section");
    sec.append(mkEl("h3", "guide-h3", c.dataTitle), mkEl("p", "guide-p", c.dataIntro));
    const ul = mkEl("ul", "guide-list");
    for (const line of c.dataSteps) {
      ul.appendChild(mkEl("li", "guide-li", line));
    }
    const openPub = mkEl("button", "tv-btn-primary guide-open-pub", c.openPublicBtn);
    openPub.type = "button";
    openPub.addEventListener("click", () => {
      closeGuideModal();
      const pubBtn = document.getElementById("btn-open-public-data");
      if (pubBtn) pubBtn.click();
    });
    sec.append(ul, openPub);
    bodyEl.appendChild(sec);
  } else {
    const sec = mkEl("div", "guide-section");
    sec.appendChild(mkEl("h3", "guide-h3", c.archTitle));
    const grid = mkEl("div", "guide-arch-grid");
    for (const item of c.archItems) {
      const card = mkEl("div", "guide-step-card");
      card.append(mkEl("div", "guide-step-num", item.tag), mkEl("div", "guide-step-txt", item.text));
      grid.appendChild(card);
    }
    sec.appendChild(grid);
    bodyEl.appendChild(sec);
  }
}

export function openGuideModal(tabId = "overview") {
  activeGuideTab = tabId;
  renderGuideModalBody();
  const modal = document.getElementById("guide-modal");
  if (modal) modal.classList.remove("hidden");
}

export function closeGuideModal() {
  const modal = document.getElementById("guide-modal");
  if (modal) modal.classList.add("hidden");
}

export function initGuideHub(callbacks) {
  guideCallbacks = callbacks;
  const openBtn = document.getElementById("btn-open-guide");
  const closeBtn = document.getElementById("btn-close-guide");
  const modal = document.getElementById("guide-modal");

  if (openBtn) openBtn.addEventListener("click", () => openGuideModal("overview"));
  if (closeBtn) closeBtn.addEventListener("click", closeGuideModal);
  if (modal) {
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeGuideModal();
    });
  }
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && modal && !modal.classList.contains("hidden")) {
      closeGuideModal();
    }
  });
  window.addEventListener("aql:langchange", () => {
    if (modal && !modal.classList.contains("hidden")) renderGuideModalBody();
    for (const key of ["backtest", "xray", "crashtest"]) {
      const p = lastTabPayloads[key];
      if (p) renderPlainVerdict(key, p.res, p.params);
    }
  });
}
