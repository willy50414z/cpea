## Why

目前 text-to-SQL 流程只能在彙總前篩選資料列，無法回答「依門市分組，只保留營收合計超過門檻的門市」等需求。Retail benchmark 已用每個 View 的拒絕案例追蹤 HAVING；現在要讓這些需求由單一 View 安全產生 SQL，並讓題庫與分層評分反映新能力。

## What Changes

- 讓 MATCH 輸出、Schema Linking、QueryPlan、契約驗證與單一 View SQL Builder 表達彙總後篩選，明確區分 WHERE 與 HAVING。
- 支援對單一欄位的聚合結果與明確常數比較；HAVING 可引用未出現在 SELECT 的聚合指標。保留欄位、聚合、運算子和值的契約限制與原文依據。
- 為新的 MATCH JSON 形狀建立新版本 prompt/schema，保留既有 v2 題目與評估紀錄的版本可追溯性。**BREAKING**：新版本的 MATCH JSON 增加 HAVING 欄位，不能以 v2 形狀解析或評分。
- 更新 Retail benchmark：將七個 HAVING 拒絕案例轉為可執行的正常案例，更新 ground truth、雙層評分、覆蓋報告與審核指紋，並保留基本邊界案例數量與既有案例 ID 的可追溯性。
- JOIN 與跨欄位算式不在此變更的功能實作範圍。

## Capabilities

### New Capabilities

- `single-view-having`: 定義 HAVING 的需求對應、查詢計畫、契約與 SQL 安全規則，以及未顯示聚合指標的篩選能力。

### Modified Capabilities

- `quality-tooling`: 定義 HAVING 題目的產生、驗證、分層評分、版本遷移及人工審核失效規則。

## Impact

- 影響 `src/cpea/workflows/text_to_sql/`、`src/cpea/domain/models.py`、Catalog 契約驗證、`src/cpea/infrastructure/sql_compiler.py` 與 SQL 安全檢查。
- 影響 `evaluations/` 的 Retail 產題、題目模型、驗證與評分，以及 `projects/retail/evaluations/` 的私有題庫和覆蓋報告；既有已核准題目若內容或 prompt 指紋改變，須重新審核。
- 影響 `docs/prompt/benchmark_prompt.md` 和版本化 MATCH_PROMPT；不新增跨 View JOIN 或資料庫寫入能力。
