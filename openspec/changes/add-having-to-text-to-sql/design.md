## Context

目前 MATCH v2 的固定輸出只有 `fields/table/criteria/order/group/ignored`。`criteria` 經 SchemaLink 轉為 QueryPlan 的 `filters`，SQL Builder 只編譯 WHERE；把彙總門檻放進 `criteria` 會改變查詢語意。Retail 的七個 `B-09` 案例已提供明確的分組、SUM 指標及門檻，現為拒絕案例。使用者已確認 HAVING 可篩選未顯示在 SELECT 的聚合指標。

## Goals / Non-Goals

**Goals:**

- 單一 View 的分組查詢可使用彙總後條件，並保留 WHERE 與 HAVING 的不同階段。
- 第一版支援單欄聚合結果與明確數值常數比較；可同時有多個 HAVING 條件，以 AND 組合。HAVING 的聚合欄位不必列在 SELECT。
- 讓 Retail 七個 HAVING 案例由拒絕轉為可編譯的正常案例，且 mapping、QueryPlan、SQL 三層都可驗證。

**Non-Goals:**

- 不加入 JOIN、跨欄位算式、`COUNT(*)`、OR／括號運算、子查詢或沒有 GROUP BY 的整體 HAVING。
- 不執行 Retail 題目的 SQL 或真實模型評估；自動驗證與人工審核分開。

## Decisions

### 1. 用獨立 HAVING 結構保留階段語意

新 MATCH v3 schema 增加必填的 `having` 陣列；每項包含原文片段 `text`、`column`、`aggregation`、`operator`、`value`。v2 與 v3 使用各自的解析 schema，由選用的 prompt 版本決定，避免更改 v2 的 response schema 指紋。QueryPlan 對應 `having` 條件陣列，元素保留相同結構但不含 `text`。空陣列代表沒有 HAVING。`criteria` 仍只表示 WHERE；不把 HAVING 條件轉寫為 WHERE，也不要求 HAVING 指標出現在 `fields` 或 `select_columns`。相較擴充既有 `criteria` 加上階段旗標，獨立陣列可讓既有條件的語意與驗證規則維持清楚。

首版允許 `sum/count/count_distinct/avg/min/max` 中依欄位契約合法且結果為數值的聚合；比較運算子限 `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`，值限原文可追溯的數值常數。禁止 `IN`、`LIKE`、欄位對欄位與公式。若某 View 的 `filter` 能力或運算子政策禁止該欄位／運算子，HAVING 也拒絕；聚合仍受 `disallowed_aggregations` 約束。

### 2. 沿用單一 View 的確定性驗證與編譯路徑

Schema Linking 對 HAVING 建立獨立、可追溯的連結與 request fact，檢查欄位、聚合、運算子、數值門檻與原文片段；不得把門檻標成 ignored。QueryPlan 檢查 HAVING 僅用於有 GROUP BY 的計畫，且每個條件都能由核准連結還原。SQL Builder 以核准的欄位、聚合和安全字面值組成 `WHERE ... GROUP BY ... HAVING ... ORDER BY`；HAVING 內重寫聚合運算式，不引用 SELECT alias。沒有顯示的 HAVING 指標只出現在 HAVING，不新增到 SELECT。被動 SQL 政策仍只允許單一核准 View 與唯讀 SELECT。

### 3. 新版 prompt/schema 與題庫遷移

保留 MATCH v2 的拒絕語意；新增 v3 prompt 和 response schema，將 v3 設為新題庫及新執行預設，並以 prompt/schema 指紋區分舊 run。Retail 七個 `B-09` 保留原 ID，改為難度不適用的正常邊界案例；驗證器允許 `-B-` 正常案例且不套用九宮格 S/M/H 門檻。基本邊界題數與題庫總數仍為 10 題／View、395 題，九宮格 45 題／View 不變。題目增加 `expected_match.having` 與 `expected_sql.having`；其他新版本題目兩處皆為空陣列。

產生器、載入驗證與分層評分必須比較 HAVING 結構與編譯 SQL，包含隱藏聚合指標及 WHERE/HAVING 誤置。重產時保留內容與指紋仍一致的人工審核資料；因 prompt/schema 或案例內容變動而失效的核准回到 `pending`。覆蓋報告將 HAVING 從未解缺口移到已支援驗證，其他範圍外項目照實記錄。舊 v2 題庫與 run 以原版本解讀，不靜默升級。

## Risks / Trade-offs

- [模型把彙總門檻放進 WHERE] → prompt v3 給明確對照，連結與評分分別檢查 `criteria`、`having`；此類輸出不得通過。
- [隱藏指標繞過契約聚合限制] → HAVING 欄位、聚合、運算子與能力單獨驗證，不依賴 SELECT 清單。
- [舊評估資料的 prompt/schema 身分改變] → v2 保留可讀，v3 使用新版本與指紋；新題庫重產且人工核准依既有規則失效。
- [Retail 使用 PostgreSQL，現有 Builder 編譯 MSSQL 語法] → benchmark 仍以離線編譯與政策檢查驗收，不把 PostgreSQL 上的題目執行結果當成已驗證能力。

## Migration Plan

1. 建立 v3 mapping／plan 與驗證，保持 v2 歷史資源可載入。
2. 接通 workflow、SQL Builder 與離線測試，再切換新執行預設。
3. 更新 benchmark 模型、七個 `B-09` 案例、評分與覆蓋報告；重產題庫並跑 `--check`。
4. 若需回退，新執行入口可選 v2；已產生的 v3 題庫不得由 v2 prompt 假裝評分。

## Open Questions

- 無阻擋實作的開放決策。若後續要支援 `COUNT(*)`、無 GROUP BY 的 HAVING 或公式條件，另行擴充契約與題庫。
