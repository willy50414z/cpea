## 1. HAVING 資料模型與版本

- [x] 1.1 建立 HAVING mapping／QueryPlan 條件型別，定義單欄聚合、數值常數、比較運算子及多條件 AND；加入隱藏聚合指標案例的模型測試。
- [x] 1.2 建立 MATCH v3 prompt 與版本化 response schema；保留 v2 解析形狀及其原有指紋，確認 runtime 和評估器依版本選用相同 schema。

## 2. Text-to-SQL 端到端流程

- [x] 2.1 讓 MATCH 與 Schema Linking 分別保留 WHERE、HAVING，檢查原文片段、聚合欄位與門檻值；錯置或遺漏時拒絕或進入既有有界重試。
- [x] 2.2 將核准 HAVING 連結轉為 QueryPlan，驗證有 GROUP BY、來源單一、欄位／聚合／運算子符合契約，且不要求 HAVING 指標出現在 SELECT。
- [x] 2.3 讓單一 View Builder 依 `WHERE → GROUP BY → HAVING → ORDER BY` 編譯安全 SQL，包含多條件 AND 與未顯示指標；驗證 SQL 政策與既有非 HAVING 查詢相容。
- [x] 2.4 增加離線測試：WHERE/HAVING 同時存在、隱藏指標、禁止聚合、未授權值、錯置條件、超出首版範圍、v2 相容及 SQL 服務入口。

## 3. Benchmark 與審核遷移

- [x] 3.1 擴充 View Matching 題目模型、ground truth 驗證與共用雙層評分，分別比較 `having` mapping、QueryPlan 及編譯 SQL；確認 WHERE/HAVING 誤置會失敗。
- [x] 3.2 將 Retail 七個 HAVING `B-09` 案例保留原 ID 並轉為正常邊界題，加入正式 `expected_match.having` 和 `expected_sql.having`；其他 v3 題目使用空陣列。
- [x] 3.3 更新產題數量與難度驗證，使正常邊界題不誤套九宮格門檻；更新 Coverage Report 與 `docs/prompt/benchmark_prompt.md`，分開呈現已支援 HAVING 和仍在範圍外的能力。
- [x] 3.4 重產 Retail 題庫及報告，核對 prompt/schema/契約指紋與審核狀態，執行 benchmark `--check` 與相關離線測試；不將自動驗證當作人工核准或真實模型成績。
