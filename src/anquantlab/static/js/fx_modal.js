/**
 * Indicators, Metrics & Falsification Function Catalog Modal (Ctrl+K).
 */

import { t } from "./i18n.js";

export class FxCatalogController {
  constructor({ onSelectExpr, onShowBanner }) {
    this.catalog = null;
    this.activeDomain = "all";
    this.searchQuery = "";
    this.onSelectExpr = onSelectExpr;
    this.onShowBanner = onShowBanner;
    this._bindModal();
  }

  setCatalog(catalog) {
    this.catalog = catalog;
    this.render();
  }

  render() {
    this._renderDomainChips();
    this._renderCatalogItems();
  }

  _bindModal() {
    const modal = document.getElementById("fx-modal");
    const searchInput = document.getElementById("catalog-search");
    const openModal = () => {
      modal.classList.remove("hidden");
      searchInput.focus();
      searchInput.select();
    };
    const closeModal = () => modal.classList.add("hidden");

    document.getElementById("btn-open-fx").addEventListener("click", openModal);
    document.getElementById("btn-close-fx").addEventListener("click", closeModal);
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeModal();
    });
    searchInput.addEventListener("input", (ev) => {
      this.searchQuery = ev.target.value;
      this._renderCatalogItems();
    });
    window.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        openModal();
      } else if (ev.key === "Escape" && !modal.classList.contains("hidden")) {
        closeModal();
      }
    });
    window.addEventListener("aql:langchange", () => this.render());
  }

  _renderDomainChips() {
    const wrap = document.getElementById("domain-chips");
    wrap.textContent = "";
    if (!this.catalog) return;

    const mkChip = (key, label, cnt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `domain-chip ${this.activeDomain === key ? "active" : ""}`;
      const s1 = document.createElement("span");
      s1.textContent = label;
      const s2 = document.createElement("span");
      s2.className = "num";
      s2.textContent = String(cnt);
      btn.append(s1, s2);
      btn.addEventListener("click", () => {
        this.activeDomain = key;
        this.render();
      });
      return btn;
    };

    wrap.appendChild(mkChip("all", t("mod.fx_all"), this.catalog.total_exports));
    for (const dom of this.catalog.domains) {
      wrap.appendChild(mkChip(dom.domain, dom.label, dom.count));
    }
  }

  _renderCatalogItems() {
    const listEl = document.getElementById("catalog-list");
    listEl.textContent = "";
    if (!this.catalog) return;

    const q = this.searchQuery.trim().toLowerCase();
    const filtered = this.catalog.items.filter((it) => {
      if (this.activeDomain !== "all" && it.domain !== this.activeDomain) return false;
      if (!q) return true;
      return (
        it.name.toLowerCase().includes(q) ||
        it.summary.toLowerCase().includes(q) ||
        it.domain.toLowerCase().includes(q)
      );
    });

    const frag = document.createDocumentFragment();
    for (const item of filtered) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "catalog-item";
      row.setAttribute("role", "listitem");

      const top = document.createElement("div");
      top.className = "catalog-item-top";
      const fnSpan = document.createElement("span");
      fnSpan.className = "catalog-fn-name mono";
      fnSpan.textContent = item.name;
      const kindSpan = document.createElement("span");
      kindSpan.className = "catalog-kind-tag mono";
      kindSpan.textContent = item.kind;
      top.append(fnSpan, kindSpan);

      const sigDiv = document.createElement("div");
      sigDiv.className = "catalog-sig mono";
      sigDiv.textContent = item.signature;

      const descDiv = document.createElement("div");
      descDiv.className = "catalog-desc";
      descDiv.textContent = item.summary;

      row.append(top, sigDiv, descDiv);
      row.addEventListener("click", () => {
        document.getElementById("fx-modal").classList.add("hidden");
        if (item.kind === "expr_ts" || item.kind === "expr_cs") {
          if (this.onSelectExpr) this.onSelectExpr(item.sample_formula);
        } else if (this.onShowBanner) {
          this.onShowBanner(`'${item.name}' (${item.kind})`);
        }
      });
      frag.appendChild(row);
    }
    listEl.appendChild(frag);
  }
}
