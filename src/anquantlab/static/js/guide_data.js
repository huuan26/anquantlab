/**
 * Bilingual content for the 30-second Onboarding Guide, 3 Case Studies,
 * Binance/Stooq Free Real-Data Guide, and Recruiter Architecture Highlights.
 */

export const GUIDE_CONTENT = {
  en: {
    modalTitle: "AnQuantLab Guide: Workflow, Examples & Real Market Data",
    modalSub: "Understand the validation workflow, run 3 interactive examples, and fetch free Binance / Stooq data.",
    tabs: [
      { id: "overview", label: "Overview & Examples" },
      { id: "realdata", label: "Real Data (Binance / Stooq)" },
      { id: "arch", label: "Architecture" },
    ],
    problemTitle: "What problem does AnQuantLab solve?",
    problemDesc:
      "Many trading strategies perform well in initial backtests but underperform live due to three recurring issues: underestimating fees and slippage, unintended exposure to common market factors, or parameter overfitting on historical noise. AnQuantLab checks all three systematically before generating standalone Python code and an audit report.",
    steps: [
      { num: "1. Backtest", text: "Measure net performance after commissions, estimated bid-ask spread, and execution lag." },
      { num: "2. Factor X-Ray", text: "Decompose signal returns into independent alpha vs Momentum, Volatility, and Market Beta." },
      { num: "3. Crash-Test", text: "Evaluate parameter sensitivity, CSCV PBO, Bootstrap worlds, and 7 Romano-Wolf checks." },
    ],
    demosTitle: "3 Common Backtest Pitfalls (1-Click Scenarios)",
    demos: [
      {
        id: "fee_trap",
        badge: "Case 1",
        title: "Case 1: Trading Fee & Slippage Drag",
        desc: "Runs a noisy short-term z-score signal under realistic Corwin-Schultz spread + 10 bps fee. Notice Gross profit fades while Net Equity declines.",
        actionLabel: "Run Case 1",
        tab: "backtest",
        formula: "cs_rank(ts_zscore(close, 5))",
        preset: { weight: "dollar_neutral", slipMode: "corwin_schultz", fee: 10, slip: 0, buf: 0, lag: 1 },
      },
      {
        id: "fake_alpha",
        badge: "Case 2",
        title: "Case 2: Standard Factor Overlap",
        desc: "Audits cs_rank(rsi(close, 14)) in Factor X-Ray. Watch the 5-Factor Spanning chart quantify how much variance overlaps Momentum & Reversal.",
        actionLabel: "Inspect Factor X-Ray",
        tab: "xray",
        formula: "cs_rank(rsi(close, 14))",
      },
      {
        id: "overfit_guard",
        badge: "Case 3",
        title: "Case 3: Parameter Stability & Overfitting",
        desc: "Sweeps 25 nearby parameter variants in Crash-Test with CSCV Overfitting Probability (PBO), 200 Bootstrap worlds & 7 Romano-Wolf gates.",
        actionLabel: "Run Validation",
        tab: "crashtest",
        formula: "neutralize(cs_winsorize(ts_zscore(close, 20)), sector)",
      },
    ],
    dataTitle: "How to Fetch Free Real Market Data (Binance & Stooq - 0 API Keys)",
    dataIntro:
      "You do not need an exchange account or paid data subscription. AnQuantLab connects legally to public HTTPS endpoints from Binance Vision and Stooq and caches files safely outside the Git repo.",
    dataSteps: [
      "Step 1: Click the button below (or 'Public' on the top toolbar) to open the Zero-Key Public Data Hub.",
      "Step 2 (Crypto + Orderflow): Choose Binance Crypto Major (1d or 1h across 8 coins like BTC, ETH, SOL) or BTCUSDT 5m. Includes free taker_buy_ratio orderflow to test buyer/seller pressure.",
      "Step 3 (Stocks / Sector Rotation): Choose Stooq US S&P Sector ETFs (1d, ~3 years across 9 sector ETFs XLK..XLB). Great for testing sector neutralization via neutralize(..., sector).",
      "Step 4 (Your own CSV / Parquet): Click 'Import' on the toolbar to load VN stocks, VN30F1M futures, or custom files containing date/timestamp, open, high, low, close, volume (plus optional ticker & sector columns).",
      "Step 5 (Automatic Forensics Check): Once loaded, check the Health badge above the chart or the 'Forensics' tab below to spot split jumps, zero-volume bars, and recommended minimum slippage.",
    ],
    openPublicBtn: "Open Free Public Data Hub Now",
    archTitle: "Key Engineering Highlights (For Technical Reviewers & Recruiters)",
    archItems: [
      {
        tag: "Security & Causality",
        text: "Zero eval/exec AST Whitelist Sandbox: parses user formulas safely and automatically stages .over(ticker) and .over(timestamp) passes with strict zero look-ahead bias.",
      },
      {
        tag: "Sub-30ms Compute",
        text: "Powered by Polars (Rust) & polars-anta with a 2-tier LRU cache (signal matrix cached separately from friction weights for instant slider interaction).",
      },
      {
        tag: "Zero-Orderbook Microstructure",
        text: "Estimates implicit bid-ask spread and price impact directly from free OHLCV candles using Corwin-Schultz, Roll, and Amihud estimators + automated dirty-bar forensics.",
      },
      {
        tag: "Multiple-Testing Defense & Export",
        text: "25% Sealed OOS Holdout Vault, eigenvalue-adjusted Trial Ledger (DSR), CSCV PBO, Romano-Wolf FWER, 1-click standalone .py codegen parity-verified (<1e-11), and SHA-256 Alpha Passport.",
      },
    ],
  },
  vi: {
    modalTitle: "Hướng dẫn Sử dụng AnQuantLab & Cách lấy Dữ liệu Thật",
    modalSub: "Tổng quan quy trình kiểm định, 3 ví dụ chạy thử và hướng dẫn tải dữ liệu Binance / Stooq.",
    tabs: [
      { id: "overview", label: "Tổng quan & Ví dụ" },
      { id: "realdata", label: "Lấy Dữ liệu Thật (Binance/Stooq)" },
      { id: "arch", label: "Kiến trúc Hệ thống" },
    ],
    problemTitle: "AnQuantLab giải quyết bài toán gì?",
    problemDesc:
      "Nhiều chiến lược giao dịch cho kết quả tốt khi backtest nhưng giảm hiệu quả ngoài thực tế do 3 nguyên nhân phổ biến: chưa tính đủ phí và trượt giá, lợi nhuận thực chất chỉ đi theo xu hướng chung của thị trường, hoặc tinh chỉnh tham số quá sát dữ liệu quá khứ (overfitting). AnQuantLab hỗ trợ kiểm tra cả 3 yếu tố này theo từng bước trước khi xuất ra mã Python độc lập.",
    steps: [
      { num: "1. Kiểm thử (Backtest)", text: "Đo lường lợi nhuận ròng sau khi trừ phí giao dịch, ước lượng spread mua-bán và độ trễ khớp lệnh." },
      { num: "2. Tách Yếu tố (X-Ray)", text: "Phân rã xem tín hiệu mang lại lợi thế độc lập hay đang trùng với đà tăng (Momentum) và xu hướng chung." },
      { num: "3. Kiểm định (Overfitting)", text: "Thử nghiệm độ nhạy tham số, kiểm định PBO, Bootstrap và 7 tiêu chí thống kê Romano-Wolf." },
    ],
    demosTitle: "3 Kịch bản Minh họa Phổ biến (Chạy thử 1-Click)",
    demos: [
      {
        id: "fee_trap",
        badge: "Ví dụ Tab 1",
        title: "Ảnh hưởng của Phí & Trượt giá lên Tín hiệu Ngắn hạn",
        desc: "Chạy tín hiệu đảo chiều 5 kỳ với phí 10 bps và mô hình trượt giá Corwin-Schultz để so sánh đường lợi nhuận gộp và lợi nhuận ròng.",
        actionLabel: "Chạy Ví dụ 1",
        tab: "backtest",
        formula: "cs_rank(ts_zscore(close, 5))",
        preset: { weight: "dollar_neutral", slipMode: "corwin_schultz", fee: 10, slip: 0, buf: 0, lag: 1 },
      },
      {
        id: "fake_alpha",
        badge: "Ví dụ Tab 2",
        title: "Kiểm tra Mức độ Trùng lặp Yếu tố Thị trường",
        desc: "Đưa công thức cs_rank(rsi(close, 14)) vào Tab Tách Yếu tố để xem tỷ lệ đóng góp độc lập so với nhóm yếu tố Momentum & Đảo chiều.",
        actionLabel: "Xem Tách Yếu tố",
        tab: "xray",
        formula: "cs_rank(rsi(close, 14))",
      },
      {
        id: "overfit_guard",
        badge: "Ví dụ Tab 3",
        title: "Đánh giá Độ ổn định Tham số & Overfitting",
        desc: "Quét đồng thời 25 bộ tham số lân cận, tính xác suất overfitting (CSCV PBO), chạy 200 mẫu Bootstrap và lọc qua 7 tiêu chí Romano-Wolf.",
        actionLabel: "Chạy Kiểm định",
        tab: "crashtest",
        formula: "neutralize(cs_winsorize(ts_zscore(close, 20)), sector)",
      },
    ],
    dataTitle: "Hướng dẫn tải Dữ liệu Thị trường Thật miễn phí (Binance & Stooq)",
    dataIntro:
      "Bạn không cần tạo tài khoản sàn hay trả phí API. AnQuantLab kết nối trực tiếp tới nguồn dữ liệu công khai của Binance và Stooq, tự lưu cache an toàn ngoài thư mục Git.",
    dataSteps: [
      "Bước 1: Bấm nút 'Mở Kho Dữ liệu Công khai' ngay bên dưới (hoặc nút 'Dữ liệu' trên thanh công cụ trên cùng).",
      "Bước 2 (Crypto + Dòng tiền Orderflow): Chọn Binance Crypto Major (khung 1d/1h gồm 8 đồng BTC, ETH, SOL...) hoặc BTCUSDT 5m. Có sẵn cột taker_buy_ratio để kiểm thử chiến lược dòng tiền mua chủ động.",
      "Bước 3 (Cổ phiếu / Luân chuyển Ngành): Chọn Stooq US S&P Sector ETFs (khung 1d, ~3 năm qua 9 quỹ ngành XLK..XLB), phù hợp để kiểm tra lọc trung tính theo nhóm ngành neutralize(..., sector).",
      "Bước 4 (Dữ liệu cá nhân VN30 / Cổ phiếu VN): Bấm nút 'Nhập' trên thanh trên cùng để tải file .csv hoặc .parquet có các cột date/timestamp, open, high, low, close, volume (có thể thêm ticker, sector).",
      "Bước 5 (Kiểm tra Chất lượng Dữ liệu tự động): Sau khi tải xong, bấm badge 'Dữ liệu ...' phía trên đồ thị hoặc tab 'Sức khỏe Dữ liệu' ở dưới để xem điểm chất lượng 0-100, lỗi nhảy giá chia tách và trượt giá khuyến nghị.",
    ],
    openPublicBtn: "Mở Kho Dữ liệu Công khai",
    archTitle: "Điểm nhấn Kiến trúc Kỹ thuật",
    archItems: [
      {
        tag: "Xử lý Nhân quả & Bảo mật",
        text: "AST Sandbox không dùng eval/exec: tự động tách bước tính theo mã (.over(ticker)) và theo ngày (.over(date)) để đảm bảo không dùng dữ liệu tương lai.",
      },
      {
        tag: "Hiệu năng Tính toán (< 30ms)",
        text: "Xây dựng trên lõi Rust Polars & polars-anta kết hợp cache 2 tầng (tách bộ nhớ đệm tín hiệu và chi phí giao dịch để thao tác tham số mượt mà).",
      },
      {
        tag: "Ước lượng Vi cấu trúc từ Nến OHLCV",
        text: "Ước lượng spread ngầm và tác động thanh khoản trực tiếp từ dữ liệu OHLCV miễn phí qua Corwin-Schultz, Roll và Amihud kèm quét lỗi nến tự động.",
      },
      {
        tag: "Kiểm định Đa thử nghiệm & Xuất mã",
        text: "Khóa 25% dữ liệu OOS, Nhật ký thử nghiệm chỉnh theo trị riêng (DSR), CSCV PBO, Romano-Wolf FWER, sinh mã .py độc lập (sai số < 1e-11) và chứng chỉ SHA-256.",
      },
    ],
  },
};
