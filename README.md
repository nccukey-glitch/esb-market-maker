# 興櫃 Market Making Analytics (ESB Market Maker)

本系統為專門針對台灣證券櫃檯買賣中心（TPEx）興櫃股票市場開發的籌碼與造市價差損益設算工具。

## 系統核心邏輯

1. **官方日報表解析**：
   - 每日自動取得櫃買中心 `emerging/dss004` 買賣日報表。
   - 區分「有價格的一般經紀據點」與「無成交價的造市自營端（***T）」。
2. **全市場經紀端 VWAP**：
   - 以所有有價格據點之加權平均成交價計算買進與賣出均價（Buy VWAP / Sell VWAP）。
3. **造市端價差獲利設算 (Estimated Market-Making P/L)**：
   - `Matched Qty = min(Customer Buy Qty, Customer Sell Qty)`
   - `Total Estimated MM P/L = (Buy VWAP * 0.9968 - Sell VWAP) * Matched Qty`
   - 包含造市賣出端 0.32% 交易稅費成本。
4. **損益分配模式**：
   - 所有代碼以 `T` 結尾的造市與自營商，依當日造市成交量（買進量+賣出量）比重，分配單股全體造市端損益。
5. **經紀據點籌碼統計**：
   - 彙整各分點據點的買進、賣出、買賣超張數與加權均價，並區分買超與賣超排行。

## 執行方式

### 1. 啟動 Web Dashboard

在專案目錄下：

```bash
cd esb_market_maker
./venv/bin/streamlit run app.py
```

瀏覽器將自動開啟 `http://localhost:8501`。

### 2. 執行自動化測試 (Golden Sample 驗證)

```bash
cd esb_market_maker
# 驗證 Golden Sample A (2026/09/09, 1260 富味鄉)
./venv/bin/python -m unittest tests/test_golden_sample_a.py

# 驗證 Golden Sample B (2026/08/28, 7932 昱鐳應材)
./venv/bin/python -m unittest tests/test_golden_sample_b.py
```

### 3. 目錄結構

```
esb_market_maker/
├── venv/                 # 獨立虛擬環境
├── data_fetcher/         # 官方資料取得 (TPEx 日報表與券商資料)
├── calculation/          # 籌碼、VWAP、損益與損益分配核心演算法
├── database/             # SQLite 本機資料庫 (esb.db)
├── raw_data/             # 官方原始 JSON 下載封裝保留
├── tests/                # Golden Sample A & B 測試
├── app.py                # Streamlit Web Dashboard
├── data_processor.py     # 全市場日資料處理管線
└── requirements.txt      # 模組套件依賴清單
```
