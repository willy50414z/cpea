## 1. 題型與題庫載入

- [x] 1.1 定義共用 View Matching 案例模型，包含 `expected_match`、`expected_sql`、九宮格、契約指紋、`validation_status` 與獨立 `review_status`；保持既有 GMS2 reliability JSONL 可載入。
- [x] 1.2 在模型呼叫前驗證案例 ID、profile／契約指紋、View／Column、MATCH_PROMPT JSON 形狀、所有原文 `text`、難度結構與審核 metadata；錯誤時中止載入。
- [x] 1.3 將 Retail 生成題庫轉為共用專案題型，保留 7 View × 55 題與 Coverage Report；為待審題記錄 `review_status=pending`，不自動標為人工核准。
- [x] 1.4 加入題庫載入與 GMS2 相容性的離線測試，涵蓋過期契約、無效欄位、重複 ID 與原文片段錯誤。

## 2. Prompt 與 workflow trace

- [x] 2.1 將現有 MATCH_PROMPT 原內容移至版本化 UTF-8 套件資源，建立 loader，並確保 wheel 可讀取且預設輸出不變。
- [x] 2.2 讓 workflow 實例固定使用載入的 prompt；移除評估過程對模組全域變數的覆寫，並在 run metadata 記錄 prompt／human 模板／response schema 的版本與指紋。
- [x] 2.3 在私有 workflow trace 保存各次解析後的 `SQLClauseMapping`、嘗試次序、採用狀態與 mapping 不可得原因，維持現有 `calls.jsonl` 原始 request／response 記錄。
- [x] 2.4 加入離線測試，確認版本內容變動可辨、同一 run 的所有呼叫使用同一 prompt，以及多次候選／重試可追蹤至最終 mapping。

## 3. 雙層評分與審核邊界

- [x] 3.1 在共用評分器實作 View Matching 結構評分：View、欄位／聚合、條件與值、分組、排序、原文 grounding、額外條件及拒絕情況。
- [x] 3.2 實作 QueryPlan／SQL 結構評分與整體狀態組合；分清 mapping 錯誤、編譯錯誤、合法拒絕、無法解析及 provider 錯誤。
- [x] 3.3 加入 `pending`／`approved`／`rejected` 審核處理及契約指紋失效規則；正式成績僅納入當前契約已核准題，探索模式另列待審結果。
- [x] 3.4 以 stub 覆蓋正常 S/M/H、L1/L2/L3、拒絕案例、mapping 正確但 SQL 錯、mapping 錯但 workflow 安全拒絕、自由文字理由不同但等價等情境。

## 4. 共用執行入口與停止規則

- [x] 4.1 為 `cpea-eval` 加入僅限評估的明確 draft profile 選項，記錄選項與 profile 狀態；驗證一般查詢入口仍拒絕 draft。
- [x] 4.2 加入每模型實際 LLM 呼叫的原子額度預留與可選私有跨 run ledger，計入 warmup 與重試，避免並行時超額開始新呼叫。
- [x] 4.3 達額度上限或遇 rate limit／認證錯誤時停止該模型新呼叫，保留完成／在途結果，標記剩餘題目 skipped；不得自動重跑或切換模型。
- [x] 4.4 使用離線故障注入測試額度邊界、provider 錯誤、並行在途、planned／completed／skipped 計數及跨 run ledger，不呼叫真實模型。

## 5. 報告與驗收

- [x] 5.1 擴充私有結果與分享型 CSV／Markdown，依模型、View、九宮格及拒絕類別呈現 mapping／SQL／整體結果、待審、錯誤與 skipped；原始 prompt／response 不進分享型報告。
- [x] 5.2 報告全次通過與一致性兩種穩定性指標，確保一致失敗不計入穩定正確，且未執行與待審題不提高正式通過率。
- [x] 5.3 更新評估文件，說明共用 `cpea-eval` 的 Retail exploratory／正式流程、prompt 版本、審核紀錄、額度停止及報告解讀。
- [x] 5.4 執行相關離線單元／整合測試與 OpenSpec 狀態檢查；記錄未進行真實模型或資料庫執行的限制。
