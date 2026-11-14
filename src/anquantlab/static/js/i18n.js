/**
 * Lightweight Bilingual (VI / EN) i18n runtime:
 * Auto-detects browser language on first visit, translates static DOM, canvas & backend tags.
 */

import { EN } from "./i18n_en.js";
import { VI } from "./i18n_vi.js";

const STORAGE_KEY = "anquantlab_lang";
const DICTS = { en: EN, vi: VI };

const STAGE_VI = {
  "1. Raw Signal": "1. Tín hiệu Gốc",
  "2. Winsorized": "2. Cắt nhiễu Biên",
  "3. Neutralized": "3. Trung hòa Ngành",
  "4. Orthogonalized": "4. Tách Yếu tố Trùng",
};

const FACTOR_VI = {
  "Momentum (20b)": "Đà tăng (20 kỳ)",
  "Short Reversal (5b)": "Đảo chiều (5 kỳ)",
  "Yang-Zhang Vol (20b)": "Biến động YZ (20 kỳ)",
  "Amihud Illiquidity (20b)": "Thanh khoản (20 kỳ)",
  "Market Beta / Trend (60b)": "Beta Thị trường (60 kỳ)",
  "Trend Slope (60b)": "Xu hướng Giá (60 kỳ)",
};

const GATE_VI = {
  "1. Grid Parameter Sweep": "1. Quét lưới Tham số",
  "2. Net Friction Sharpe > 0": "2. Sharpe Ròng > 0",
  "3. Newey-West HAC t >= 1.96": "3. Kiểm định t >= 1.96",
  "4. BH-FDR q-val <= 0.10": "4. Lọc sai số FDR <= 0.10",
  "5. Romano-Wolf FWER p <= 0.05": "5. Romano-Wolf p <= 0.05",
  "6. Empirical-Bayes P(SR>0) >= 80%": "6. Hậu nghiệm >= 80%",
  "7. OLS-CUSUM Mean Stability": "7. Ổn định Cấu trúc CUSUM",
};

const HAIRCUT_VI = {
  "Observed Peak SR": "Sharpe Đỉnh",
  "Grid DSR Haircut": "Trừ Quét lưới",
  "Session Ledger DSR": "Trừ Nhiều lần",
  "Empirical-Bayes SR": "Hậu nghiệm EB",
};

const VERDICT_VI = {
  DISTINCT_ALPHA: "TÍN HIỆU ĐỘC LẬP",
  PARTIAL_OVERLAP: "TRÙNG LẶP MỘT PHẦN",
  FACTOR_CLONE: "SAO CHÉP YẾU TỐ PHỔ THÔNG",
  SURVIVES_FALSIFICATION: "ĐẠT KIỂM ĐỊNH THỐNG KÊ",
  MIXED_EVIDENCE: "CHƯA RÕ RÀNG (CẨN TRỌNG)",
  OVERFIT_REJECTED: "LOẠI - NGUY CƠ OVERFIT",
  APPROVED_CANDIDATE: "ĐẠT CHUẨN XUẤT BẢN",
  CONDITIONAL_REVIEW: "CẦN XEM XÉT THÊM",
  REJECTED_OVERFIT: "LOẠI - RỦI RO OVERFIT",
};

export function detectInitialLang() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "vi" || saved === "en") return saved;
  const navLangs = Array.isArray(navigator.languages) && navigator.languages.length
    ? navigator.languages
    : [navigator.language || "en"];
  return navLangs.some((l) => /^vi\b/i.test(String(l))) ? "vi" : "en";
}

let currentLang = detectInitialLang();

export function getLang() {
  return currentLang;
}

export function t(key, vars = null) {
  const dict = DICTS[currentLang] || EN;
  let txt = dict[key] !== undefined ? dict[key] : EN[key] !== undefined ? EN[key] : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      txt = txt.replaceAll(`{${k}}`, String(v));
    }
  }
  return txt;
}

export function localizeTag(kind, raw) {
  const s = String(raw || "");
  if (currentLang !== "vi") return s;
  if (kind === "stage") return STAGE_VI[s] || s;
  if (kind === "factor") return FACTOR_VI[s] || s;
  if (kind === "gate") return GATE_VI[s] || s;
  if (kind === "haircut") return HAIRCUT_VI[s] || s;
  if (kind === "verdict") return VERDICT_VI[s] || s.replace(/_/g, " ");
  return s;
}

export function applyDomTranslations(root = document) {
  document.documentElement.lang = currentLang;
  document.title = t("app.title");

  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    if (el.getAttribute("data-i18n-html") === "true") {
      el.innerHTML = t(key);
    } else {
      el.textContent = t(key);
    }
  });

  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.title = t(key);
  });

  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.placeholder = t(key);
  });

  const langLbl = document.getElementById("lang-label");
  if (langLbl) langLbl.textContent = currentLang.toUpperCase();
}

export function setLang(nextLang) {
  currentLang = nextLang === "vi" ? "vi" : "en";
  localStorage.setItem(STORAGE_KEY, currentLang);
  applyDomTranslations();
  window.dispatchEvent(new CustomEvent("aql:langchange", { detail: { lang: currentLang } }));
}

export function initI18nControl() {
  applyDomTranslations();
  const btn = document.getElementById("btn-lang-toggle");
  if (btn) {
    btn.addEventListener("click", () => {
      setLang(currentLang === "vi" ? "en" : "vi");
    });
  }
}
