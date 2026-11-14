"""Bilingual (EN/VI) labels and plain-language executive summary for offline HTML Tearsheets."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .export_schemas import AlphaPassportDocument

_CLEARANCE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "APPROVED_CANDIDATE": "APPROVED CANDIDATE",
        "CONDITIONAL_REVIEW": "CONDITIONAL REVIEW",
        "REJECTED_OVERFIT": "REJECTED OVERFIT",
    },
    "vi": {
        "APPROVED_CANDIDATE": "ĐẠT KIỂM ĐỊNH (APPROVED)",
        "CONDITIONAL_REVIEW": "CẦN XEM XÉT THÊM (CONDITIONAL)",
        "REJECTED_OVERFIT": "CHƯA ĐẠT - RỦI RO OVERFIT",
    },
}

_STAGE_MAP_VI: dict[str, str] = {
    "1. Raw Signal": "1. Tín hiệu gốc",
    "2. Winsorized": "2. Cắt nhiễu biên",
    "3. Neutralized": "3. Trung hòa ngành",
    "4. Orthogonalized": "4. Tách yếu tố trùng",
}

_FACTOR_MAP_VI: dict[str, str] = {
    "Momentum (20b)": "Đà tăng (20 kỳ)",
    "Short Reversal (5b)": "Đảo chiều ngắn (5 kỳ)",
    "Yang-Zhang Vol (20b)": "Biến động YZ (20 kỳ)",
    "Amihud Illiquidity (20b)": "Thanh khoản Amihud (20 kỳ)",
    "Market Beta / Trend (60b)": "Beta / Xu hướng chung (60 kỳ)",
    "Trend Slope (60b)": "Độ dốc xu hướng (60 kỳ)",
}

_GATE_MAP_VI: dict[str, str] = {
    "1. Grid Parameter Sweep": "1. Quét lưới tham số",
    "2. Net Friction Sharpe > 0": "2. Sharpe ròng sau phí > 0",
    "3. Newey-West HAC t >= 1.96": "3. Kiểm định t Newey-West >= 1.96",
    "4. BH-FDR q-val <= 0.10": "4. Kiểm soát sai số BH-FDR <= 0.10",
    "5. Romano-Wolf FWER p <= 0.05": "5. Kiểm định Romano-Wolf p <= 0.05",
    "6. Empirical-Bayes P(SR>0) >= 80%": "6. Xác suất hậu nghiệm EB >= 80%",
    "7. OLS-CUSUM Mean Stability": "7. Độ ổn định cấu trúc CUSUM",
}

_SPANNING_VERDICT_VI: dict[str, str] = {
    "DISTINCT_ALPHA": "TÍN HIỆU ĐỘC LẬP",
    "PARTIAL_OVERLAP": "TRÙNG LẶP MỘT PHẦN",
    "FACTOR_CLONE": "TRÙNG YẾU TỐ PHỔ THÔNG",
}

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "title": "AnQuantLab Quantitative Falsification Tearsheet",
        "expr": "Expr",
        "summary_heading": "Plain-Language Executive Verdict",
        "insufficient_equity": "Insufficient equity points for chart.",
        "svg_aria": "Portfolio Equity Curve",
        "kpi_net_sr": "Net IS Sharpe & Return",
        "kpi_net_sub": "Max DD {dd:.2f}% | Breakeven {be:.1f} bps",
        "kpi_ledger": "Session Trial Ledger & DSR",
        "kpi_ledger_val": "{dsr:.1f}% DSR",
        "kpi_ledger_sub": "Trials {trials} | N_eff {neff:.2f} | OOS Peeks {peeks}",
        "kpi_span": "5-Factor Zoo Spanning",
        "kpi_span_val": "{pure:.1f}% Pure",
        "kpi_span_sub": "Spanned R2 {r2:.1f}% ({verdict})",
        "kpi_ct": "Overfitting Crash-Test",
        "kpi_ct_sub": "Null p={nullp:.3f} | RW {rw}/{k} | EB SR {eb:+.2f}",
        "sec_equity": "Equity Curve (Net vs Gross vs Benchmark - {vault})",
        "vault_locked": "75% IS Vault",
        "vault_full": "Full Sample",
        "ds_foot": (
            "Dataset: {name} (sha256:{sha}) | Health {health:.0f}/100"
            " | Survivorship {surv} | CS Spread {cs:.1f} bps"
        ),
        "sec_funnel": "7-Stage Romano-Wolf Falsification Funnel",
        "th_gate": "Econometric Gate",
        "th_surv": "Survivors",
        "th_share": "Share",
        "sec_xray": "4-Stage Causal Alpha Pipeline X-Ray",
        "th_stage": "Stage",
        "th_ic": "IC Mean",
        "th_icir": "ICIR",
        "th_nwt": "NW t",
        "th_spread": "Q5-Q1",
        "th_tilt": "Tilt",
        "sec_span": "5-Factor Spanning Loadings (Driscoll-Kraay)",
        "th_bench": "Benchmark",
        "th_beta": "Beta",
        "th_dkt": "DK NW t",
        "th_pratt": "Pratt R2",
        "th_post": "Post-Ortho",
        "sec_code": "Production Polars + polars-anta Code (AST Sandbox Clean)",
    },
    "vi": {
        "title": "Báo cáo Kiểm định Chiến lược Định lượng AnQuantLab",
        "expr": "Công thức",
        "summary_heading": "Tóm tắt Kết quả Kiểm định",
        "insufficient_equity": "Chưa đủ điểm dữ liệu để vẽ đường cong vốn.",
        "svg_aria": "Biểu đồ Đường cong Vốn Danh mục",
        "kpi_net_sr": "Sharpe ròng & Lợi nhuận (IS)",
        "kpi_net_sub": "Sụt giảm tối đa {dd:.2f}% | Phí hòa vốn {be:.1f} bps",
        "kpi_ledger": "Sổ Thử nghiệm & Xác suất DSR",
        "kpi_ledger_val": "{dsr:.1f}% DSR",
        "kpi_ledger_sub": "Số lần thử {trials} | Độc lập N_eff {neff:.2f} | Mở OOS {peeks}",
        "kpi_span": "Độ độc lập trước 5 Yếu tố Phổ thông",
        "kpi_span_val": "{pure:.1f}% Độc lập",
        "kpi_span_sub": "Trùng lặp R2 {r2:.1f}% ({verdict})",
        "kpi_ct": "Kiểm định Độ bền & Overfitting",
        "kpi_ct_sub": "Null p={nullp:.3f} | Đạt RW {rw}/{k} | EB SR {eb:+.2f}",
        "sec_equity": "Đường cong Vốn (Lãi ròng vs Gộp vs Tham chiếu - {vault})",
        "vault_locked": "Khóa 25% dữ liệu OOS",
        "vault_full": "Toàn bộ mẫu",
        "ds_foot": (
            "Dữ liệu: {name} (sha256:{sha}) | Chất lượng {health:.0f}/100"
            " | Thiên lệch mã cũ {surv} | Trượt giá CS {cs:.1f} bps"
        ),
        "sec_funnel": "Quy trình Kiểm định 7 Bước (Romano-Wolf)",
        "th_gate": "Tiêu chí Kiểm định",
        "th_surv": "Số đạt",
        "th_share": "Tỷ lệ",
        "sec_xray": "Phân rã Tín hiệu qua 4 Bước Xử lý",
        "th_stage": "Bước",
        "th_ic": "IC TB",
        "th_icir": "ICIR",
        "th_nwt": "NW t",
        "th_spread": "Top-Đáy",
        "th_tilt": "Lệch ngành",
        "sec_span": "Tương quan với 5 Yếu tố Thị trường Phổ thông",
        "th_bench": "Yếu tố Tham chiếu",
        "th_beta": "Hệ số Beta",
        "th_dkt": "DK NW t",
        "th_pratt": "Đóng góp R2",
        "th_post": "Dư sau lọc",
        "sec_code": "Mã Python Polars + polars-anta Sẵn sàng Triển khai (Đã qua AST Sandbox)",
    },
}


def norm_lang(lang: str | None) -> str:
    return "vi" if str(lang or "").lower().startswith("vi") else "en"


def localize_label(kind: str, raw: str, lang: str) -> str:
    if norm_lang(lang) != "vi":
        return raw
    if kind == "clearance":
        return _CLEARANCE_LABELS["vi"].get(raw, raw)
    if kind == "stage":
        return _STAGE_MAP_VI.get(raw, raw)
    if kind == "factor":
        return _FACTOR_MAP_VI.get(raw, raw)
    if kind == "gate":
        return _GATE_MAP_VI.get(raw, raw)
    if kind == "spanning":
        return _SPANNING_VERDICT_VI.get(raw, raw)
    return raw


def build_executive_summary(passport: AlphaPassportDocument, lang: str) -> str:
    """Generate a concise 3-part plain-language verdict for technical and non-technical readers."""
    b = passport.backtest_audit
    x = passport.xray_audit
    f = passport.falsification_audit
    pure_pct = x.orthogonal_share * 100.0
    r2_pct = x.spanning_r2 * 100.0
    ret_pct = b.total_return * 100.0

    rw_s = f"{f.romano_wolf_survivors}/{f.grid_candidates}"
    pbo_pct = f.pbo * 100.0
    if norm_lang(lang) == "vi":
        cost_part = (
            f"1) Hiệu quả sau phí: Lãi ròng đạt {ret_pct:+.2f}% (Sharpe {b.net_sharpe:+.2f}), "
            f"chịu được phí giao dịch tối đa một chiều {b.breakeven_bps:.1f} bps."
        )
        alpha_part = (
            f"2) Thực lực riêng: {pure_pct:.1f}% tín hiệu là độc lập, "
            f"{r2_pct:.1f}% trùng với các yếu tố phổ thông."
        )
        if passport.overall_clearance == "APPROVED_CANDIDATE":
            verdict_part = (
                f"3) Kết luận: ĐẠT kiểm định ({rw_s} biến thể đạt 7 tiêu chí, PBO {pbo_pct:.1f}%)."
            )
        elif passport.overall_clearance == "REJECTED_OVERFIT":
            verdict_part = (
                f"3) Kết luận: CHƯA ĐẠT ({rw_s} biến thể đạt 7 tiêu chí; "
                f"PBO {pbo_pct:.1f}%, rủi ro overfitting hoặc chi phí giao dịch cao)."
            )
        else:
            verdict_part = (
                f"3) Kết luận: CẦN XEM XÉT THÊM ({rw_s} biến thể đạt chuẩn; PBO {pbo_pct:.1f}%)."
            )
        return f"{cost_part} {alpha_part} {verdict_part}"

    cost_part = (
        f"1) Net-of-cost return: {ret_pct:+.2f}% (Sharpe {b.net_sharpe:+.2f}), "
        f"with a 1-way breakeven cost ceiling of {b.breakeven_bps:.1f} bps."
    )
    alpha_part = (
        f"2) Uniqueness: {pure_pct:.1f}% pure independent edge vs "
        f"{r2_pct:.1f}% overlap with standard market factors."
    )
    if passport.overall_clearance == "APPROVED_CANDIDATE":
        verdict_part = (
            f"3) Verdict: APPROVED ({rw_s} variants survived 7 gates; PBO {pbo_pct:.1f}%)."
        )
    elif passport.overall_clearance == "REJECTED_OVERFIT":
        verdict_part = (
            f"3) Verdict: REJECTED ({rw_s} survived 7 gates; PBO {pbo_pct:.1f}% "
            f"- high risk of overfitting or cost drag)."
        )
    else:
        verdict_part = (
            f"3) Verdict: CONDITIONAL REVIEW ({rw_s} survived 7 gates; PBO {pbo_pct:.1f}%)."
        )
    return f"{cost_part} {alpha_part} {verdict_part}"
