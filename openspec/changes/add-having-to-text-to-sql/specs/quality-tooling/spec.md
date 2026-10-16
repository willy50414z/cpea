## ADDED Requirements

### Requirement: HAVING 題庫與雙層評分

Retail View Matching 題庫 SHALL 在 MATCH v3 下為每個 View 提供可執行的 HAVING 正常案例，包含原文門檻、`expected_match.having`、`expected_sql.having` 與可編譯 SQL；七個現有 HAVING 拒絕案例 MUST 更新為正常案例，且不得仍計為未支援缺口。產題驗證與共用評分器 MUST 分別比較 WHERE 與 HAVING 的 mapping、QueryPlan 及編譯結果，包含未顯示於 SELECT 的 HAVING 指標。九宮格每格五題與每 View 十題基本邊界案例的計數 MUST 保持可核對。

#### Scenario: HAVING 題目通過
- **WHEN** 模型對某 View 的 HAVING 題目選對 View、分組、聚合、運算子與門檻，且產生相符的 QueryPlan／SQL
- **THEN** mapping 與 SQL 兩層可各自通過，覆蓋報告將該能力列為已支援

#### Scenario: WHERE/HAVING 階段錯置
- **WHEN** 模型將預期 HAVING 門檻放入 WHERE，或產生的 SQL 遺漏 HAVING
- **THEN** 對應層或 SQL 層失敗，不能因其他欄位正確而算通過

#### Scenario: 既有題目未使用 HAVING
- **WHEN** 重產其他正常與拒絕案例
- **THEN** v3 題目明確記錄空的 HAVING 集合，原有查詢意圖與九宮格數量保持不變

### Requirement: 版本與人工審核遷移

新題庫 MUST 記錄 MATCH v3 的 prompt 與 response schema 指紋，並以新格式自動驗證。既有 v2 題庫與 run MUST 仍可依其原版本解析；不得默默當作 v3 評分。案例內容或 prompt/schema 變更使人工核准失效時，產生器 MUST 將該題返回 `pending`，不得自動沿用舊核准。重產後的覆蓋報告 MUST 分開列出已支援 HAVING 與仍在範圍外的功能。

#### Scenario: 舊版評估紀錄
- **WHEN** 讀取帶有 v2 prompt/schema 指紋的既有題庫或 run
- **THEN** 使用 v2 形狀解讀或明確拒絕混用，不把缺少 HAVING 欄位當成 v3 的合格輸出

#### Scenario: 新版重產
- **WHEN** Retail benchmark 改用 MATCH v3 並重產案例與覆蓋報告
- **THEN** 自動驗證與 `--check` 通過，已失效的人工核准保持待審，且尚未執行真實模型不被報告成模型通過
