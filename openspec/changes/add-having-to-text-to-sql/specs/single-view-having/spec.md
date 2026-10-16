## ADDED Requirements

### Requirement: 獨立辨識彙總後篩選

MATCH v3 SHALL 以獨立的 `having` 陣列表示彙總後篩選，並以 `criteria` 表示彙總前的 WHERE 條件。每個 HAVING 條件 MUST 保留需求原文片段、來源欄位、聚合函數、比較運算子與常數值。workflow MUST NOT 把 HAVING 條件移到 WHERE、`ignored`，或在無法完整表示時產生部分 SQL。v2 的既有輸出形狀與指紋 MUST 保持可追溯。

#### Scenario: WHERE 與 HAVING 同時存在
- **WHEN** 使用者要求先限定訂單日期，再依門市分組且只保留營收合計大於 100 的門市
- **THEN** mapping 將日期條件放入 `criteria`，將 `SUM(revenue) > 100` 放入 `having`，兩個條件都不能遺失

#### Scenario: 彙總門檻被誤當成列篩選
- **WHEN** 模型把「營收合計大於 100」對應為 `criteria` 中的 `revenue > 100`
- **THEN** workflow 拒絕該對應或在既有有界重試內修正，且不輸出語意錯誤的 SQL

### Requirement: 可驗證的 HAVING 查詢計畫

QueryPlan SHALL 有獨立的 HAVING 條件集合。首版每個條件 MUST 對單一核准 View 欄位使用合法且結果為數值的 `sum`、`count`、`count_distinct`、`avg`、`min` 或 `max` 聚合，並與需求明示的數值常數比較；運算子限 `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`。多個 HAVING 條件 SHALL 以 AND 組合。欄位的 filter 能力、允許的運算子與聚合限制 MUST 同樣適用於 HAVING。條件 MUST 可追溯至原文與核准的連結，且計畫 MUST 有 GROUP BY。HAVING 引用的指標 MAY 不在 SELECT 清單。

#### Scenario: 隱藏聚合指標
- **WHEN** 使用者只要顯示門市名稱，並只保留銷售金額合計大於 100 的門市
- **THEN** 計畫可以對 `SUM(revenue)` 設 HAVING 門檻，而 `revenue` 不必出現在 `select_columns`

#### Scenario: 不受契約允許的聚合
- **WHEN** HAVING 要求對禁止加總的比率欄位使用 SUM，或使用該欄位不允許的運算子
- **THEN** 契約驗證拒絕計畫，不產生 SQL

#### Scenario: 超出首版條件範圍
- **WHEN** 需求需要 OR、跨欄位公式、`COUNT(*)` 或沒有 GROUP BY 的整體 HAVING
- **THEN** workflow 明確回報不支援，且不改寫成 WHERE 或不完整的 HAVING

### Requirement: 確定性編譯與安全界限

單一 View SQL Builder SHALL 依序編譯 WHERE、GROUP BY、HAVING、ORDER BY，HAVING MUST 使用核准欄位的聚合運算式與安全轉義的常數值，MUST NOT 依賴 SELECT alias。最終 SQL MUST 符合唯讀、單一核准 View 與現有列數上限政策；非 HAVING 查詢的既有輸出 MUST 保持相容。

#### Scenario: 編譯隱藏聚合指標
- **WHEN** QueryPlan 顯示門市欄位、依門市分組，且以未顯示的 `SUM(revenue) > 100` 篩選群組
- **THEN** SQL 在 GROUP BY 後產生 `HAVING SUM([revenue]) > 100`，SELECT 不額外顯示 `revenue`

#### Scenario: 多個條件
- **WHEN** 同一計畫有兩個經核准的 HAVING 條件
- **THEN** SQL 以 AND 組合，且條件都出現在 ORDER BY 之前

#### Scenario: 惡意欄位或字面值
- **WHEN** HAVING 引用未核准欄位，或常數值無法通過型別與原文驗證
- **THEN** 查詢在編譯前被拒絕，不把模型原文當成 SQL 片段插入
