/**
 * Bilingual content for the 30-second Onboarding Guide, 3 Case Studies,
 * Binance/Stooq Free Real-Data Guide, and Recruiter Architecture Highlights.
 */

export const GUIDE_CONTENT = {
  en: {
    modalTitle: "AnQuantLab Guide: Problem, Live Demos & Real Market Data",
    modalSub: "Understand what this terminal proves in 30 seconds or run a 1-click scenario.",
    tabs: [
      { id: "overview", label: "Overview & 3 Demos" },
      { id: "realdata", label: "Real Data (Binance / Stooq)" },
      { id: "arch", label: "Technical Architecture" },
    ],
    problemTitle: "Why AnQuantLab exists (What problem does it solve?)",
    problemDesc:
      "Most trading formulas found online look profitable on paper because backtests ignore real fees, copy well-known market trends, or get tuned until lucky on past noise. AnQuantLab stress-tests any formula before real money is risked, then exports standalone Python code and a signed audit report.",
    steps: [
      { num: "1. Backtest", text: "Does profit survive realistic broker fees, bid-ask spread & execution lag?" },
      { num: "2. Factor X-Ray", text: "Is profit real independent skill, or just disguised Momentum / Market Beta?" },
      { num: "3. Crash-Test", text: "Does it pass 7 overfitting defenses & 200 randomized worlds, not just luck?" },
    ],
    demosTitle: "Try 3 Real-World Traps (1-Click Interactive Demos)",
    demos: [
      {
        id: "fee_trap",
        badge: "Tab 1 Demo",
        title: "Trap 1: Eaten Alive by Trading Costs",
        desc: "Runs a noisy short-term z-score signal under realistic Corwin-Schultz spread + 10 bps fee. Notice Gross profit fades while Net Equity sinks.",
        actionLabel: "Run Trap 1",
        tab: "backtest",
        formula: "cs_rank(ts_zscore(close, 5))",
        preset: { weight: "dollar_neutral", slipMode: "corwin_schultz", fee: 10, slip: 0, buf: 0, lag: 1 },
      },
      {
        id: "fake_alpha",
        badge: "Tab 2 Demo",
        title: "Trap 2: Disguised Market Factor",
        desc: "Audits cs_rank(rsi(close, 14)) in Factor X-Ray. Watch the 5-Factor Spanning chart expose how much variance overlaps Momentum & Reversal.",
        actionLabel: "Inspect in X-Ray",
        tab: "xray",
        formula: "cs_rank(rsi(close, 14))",
      },
      {
        id: "overfit_guard",
        badge: "Tab 3 Demo",
        title: "Trap 3: Luck vs True Edge",
        desc: "Sweeps 25 nearby parameter variants in Crash-Test with CSCV Overfitting Probability (PBO), 200 Bootstrap worlds & 7 Romano-Wolf gates.",
        actionLabel: "Run Crash-Test",
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
    modalTitle: "Hướng dẫn AnQuantLab: Công dụng, Demo 1-Click & Tải Dữ liệu Thật",
    modalSub: "Hiểu rõ giá trị sản phẩm trong 30 giây hoặc bấm chạy thử ngay 3 kịch bản thực tế.",
    tabs: [
      { id: "overview", label: "Tổng quan & 3 Demo" },
      { id: "realdata", label: "Lấy Dữ liệu Thật (Binance/Stooq)" },
      { id: "arch", label: "Điểm nhấn Kỹ thuật" },
    ],
    problemTitle: "AnQuantLab giải quyết bài toán gì?",
    problemDesc:
      "Phần lớn công thức giao dịch thấy lãi cao khi test trên mạng sẽ thua ngoài đời thực vì 3 lý do: (1) quên phí & trượt giá, (2) thực chất chỉ ăn theo xu hướng chung của thị trường, hoặc (3) tinh chỉnh quá đà dẫn đến 'ăn may' trên dữ liệu cũ (overfitting). AnQuantLab đóng vai trò máy kiểm định sự thật trước khi chạy tiền thật, sau đó xuất ra mã Python chạy độc lập.",
    steps: [
      { num: "1. Kiểm thử (Backtest)", text: "Lãi có sống nổi qua phí sàn, độ lệch giá mua-bán (spread) và độ trễ lệnh không?" },
      { num: "2. Giải phẫu (X-Ray)", text: "Lợi nhuận đến từ thực lực riêng hay chỉ đang ăn theo Đà tăng / Thị trường chung?" },
      { num: "3. Chống ảo (Crash-Test)", text: "Có vượt qua 7 hàng rào chống ăn may & 200 kịch bản ngẫu nhiên không?" },
    ],
    demosTitle: "Tự kiểm chứng 3 cái bẫy phổ biến (Bấm 1-Click chạy ngay)",
    demos: [
      {
        id: "fee_trap",
        badge: "Demo Tab 1",
        title: "Bẫy 1: Bị Phí & Trượt giá ăn mòn sạch lãi",
        desc: "Chạy tín hiệu đảo chiều ngắn ngày dưới mức phí 10 bps + trượt giá Corwin-Schultz thực tế. Quan sát đường lãi gộp vs lãi ròng và biểu đồ Cost Curve.",
        actionLabel: "Chạy Bẫy 1",
        tab: "backtest",
        formula: "cs_rank(ts_zscore(close, 5))",
        preset: { weight: "dollar_neutral", slipMode: "corwin_schultz", fee: 10, slip: 0, buf: 0, lag: 1 },
      },
      {
        id: "fake_alpha",
        badge: "Demo Tab 2",
        title: "Bẫy 2: Lãi ảo do trùng yếu tố thị trường",
        desc: "Đưa công thức cs_rank(rsi(close, 14)) vào Tab Giải phẫu. Đồ thị bên phải bóc trần tỷ lệ % tín hiệu bị trùng với yếu tố Momentum & Đảo chiều phổ thông.",
        actionLabel: "Xem Giải phẫu",
        tab: "xray",
        formula: "cs_rank(rsi(close, 14))",
      },
      {
        id: "overfit_guard",
        badge: "Demo Tab 3",
        title: "Bẫy 3: Máy dò Ăn may (Overfitting Crash-Test)",
        desc: "Quét đồng thời 25 biến thể tham số lân cận, chấm xác suất Overfit (CSCV PBO), chạy 200 thế giới ngẫu nhiên và lọc qua 7 cổng Romano-Wolf.",
        actionLabel: "Chạy Crash-Test",
        tab: "crashtest",
        formula: "neutralize(cs_winsorize(ts_zscore(close, 20)), sector)",
      },
    ],
    dataTitle: "Hướng dẫn tải Dữ liệu Thị trường Thật miễn phí (Binance & Stooq)",
    dataIntro:
      "Bạn không cần tạo tài khoản sàn hay trả phí API. AnQuantLab kết nối hợp pháp trực tiếp tới dữ liệu công khai của Binance và Stooq, tự lưu cache an toàn ngoài thư mục Git.",
    dataSteps: [
      "Bước 1: Bấm nút 'Mở Kho Dữ liệu Công khai' ngay bên dưới (hoặc nút 'Dữ liệu' trên thanh công cụ trên cùng).",
      "Bước 2 (Crypto + Dòng tiền Orderflow): Chọn Binance Crypto Major (khung 1d/1h gồm 8 đồng BTC, ETH, SOL...) hoặc BTCUSDT 5m. Có sẵn cột taker_buy_ratio để test chiến lược dòng tiền mua chủ động.",
      "Bước 3 (Cổ phiếu / Luân chuyển Ngành): Chọn Stooq US S&P Sector ETFs (khung 1d, ~3 năm qua 9 quỹ ngành XLK..XLB). Rất chuẩn để thử lọc trung tính theo nhóm ngành neutralize(..., sector).",
      "Bước 4 (Dữ liệu cá nhân VN30 / Cổ phiếu VN): Bấm nút 'Nhập' trên thanh trên cùng để tải file .csv hoặc .parquet có các cột date/timestamp, open, high, low, close, volume (có thể thêm ticker, sector).",
      "Bước 5 (Kiểm định Sức khỏe Dữ liệu tự động): Ngay sau khi tải xong, bấm badge 'Dữ liệu ...' phía trên đồ thị hoặc tab 'Sức khỏe Dữ liệu' ở dưới để xem điểm sạch 0-100, lỗi nhảy giá chia tách và trượt giá khuyến nghị.",
    ],
    openPublicBtn: "Mở Kho Dữ liệu Công khai Ngay",
    archTitle: "Điểm nhấn Kiến trúc Kỹ thuật (Dành cho Nhà tuyển dụng / Reviewer)",
    archItems: [
      {
        tag: "Bảo mật & Nhân quả tuyệt đối",
        text: "AST Whitelist Sandbox không dùng eval/exec: biên dịch biểu thức thành nhiều bước Polars .over(ticker) & .over(date), loại bỏ triệt để lỗi nhìn trộm dữ liệu tương lai.",
      },
      {
        tag: "Hiệu năng < 30ms",
        text: "Xây dựng trên lõi Rust Polars & polars-anta kết hợp Cache 2 tầng (tách cache ma trận tín hiệu và mô phỏng phí để kéo thanh trượt phản hồi tức thì).",
      },
      {
        tag: "Kinh tế lượng Không cần Sổ lệnh",
        text: "Ước lượng spread mua-bán ngầm và tác động thanh khoản trực tiếp từ dữ liệu nến OHLCV miễn phí qua Corwin-Schultz, Roll và Amihud + quét lỗi nến tự động.",
      },
      {
        tag: "Phòng thủ Đa kiểm định & Xuất mã",
        text: "Khóa 25% dữ liệu OOS, Sổ thử nghiệm chỉnh theo trị riêng (DSR), CSCV PBO, Romano-Wolf FWER, sinh mã .py độc lập khớp số < 1e-11 và chứng chỉ SHA-256.",
      },
    ],
  },
};
