# 任務：PostgreSQL View Contract 自動探索與 YAML 生成

你是一名資深資料架構師與資料工程師。

請根據我提供的 PostgreSQL Connection String 和 Schema，自動探索指定 Schema 下的所有 Views，依據 View Definition、View Comment、Column Comment 及資料型別，產生符合專案 View Contract v3 規格的初版 YAML。

## 一、輸入

- PostgreSQL Connection String：已經放在.env的RETAILER_CONNECTION_STRING。
- Target Schema：已經放在.env的RETAILER_DB_SCHEMA。
- 輸出：`views/{schema}/{view}.yaml`

請先閱讀現有專案的 Contract Loader、YAML 格式及 MATCH_PROMPT，確保產出可以被目前系統載入。

## 二、資料庫探索

使用唯讀連線，透過 PostgreSQL `pg_catalog` 取得：

1. Schema / View 名稱。
2. `pg_get_viewdef()`：View SQL 定義。
3. `obj_description()`：View Comment。
4. `col_description()`：每個 Column 的 Comment。
5. 欄位名稱、順序、實際型別。
6. 可用於確認 Grain Keys 的來源表主鍵、唯一約束與 View 聚合規則。

僅探索指定 Schema，不修改資料庫，不讀取業務資料列。不得將 Connection String、密碼或其他憑證輸出到 Log、YAML 或報告。

## 三、View Contract v3 規則

### View 層級

- `version`：固定為 3。
- `view`：完整 Schema.View 名稱。
- `summary`：優先使用 View Comment，必要時根據 View Definition 整理，不得虛構用途。
- `grain.description`：每筆資料代表的業務粒度。
- `grain.keys`：可唯一辨識一列的欄位組合。

Grain Keys 必須能根據 View Definition、主鍵或唯一約束證實。不可因欄位名稱包含 ID 就推定唯一。

無法確認時使用 `null` 並列入人工審核報告。

### Column 層級

每個欄位必須包含：

- `type`：依 PostgreSQL 型別轉換為專案支援的契約型別。
- `role`：identifier / dimension / measure。
- `description`：優先使用 Column Comment。
- `unit`：可選，僅在註解明確指出單位時設定。

### Role 判斷規則

每個欄位必須根據 Column Comment、資料型別、
View Definition 及 Grain，判定以下角色：

- identifier：識別實體或紀錄的欄位，例如訂單編號、
  客戶 ID、商品代碼；即使是數字型別也不屬於 measure。
- dimension：描述分類、日期、地區、狀態等業務特徵，
  用於理解資料的分析維度。
- measure：表示金額、數量、單價、比率等可衡量數值，
  包含原始數值及計算後的指標。

role 僅描述業務語意，不代表 SQL 操作權限。
不得僅依 role 決定欄位是否可聚合、分組或排序。

若無法確認 role，應列入人工審核，
不得猜測或啟用未確認的正式契約。

### SQL 操作限制

採用黑名單設計，支援以下可選屬性：

- `disallowed_aggregations`
- `disallowed_operators`
- `disallowed_capabilities`

只有 Column Comment 或其他可信契約證據明確指出限制時才設定。

未宣告代表沒有額外的欄位業務限制，但所有操作仍須符合全域 SQL 支援白名單。

不得僅因欄位是 measure 就禁止 GROUP BY，也不得僅因欄位是 number 就預設 SUM。

View Contract v3 不產生 `default_aggregation`；聚合函數由查詢需求與欄位允許的聚合決定。

本次不實作 `scope_rules`、`term_mappings`。

## 四、YAML 範例

以下是部分欄位示意，正式產出時必須包含 View 的所有欄位。

```yaml
version: 3
view: demo_retail.v_store_monthly_kpi
summary: 每間門市每月的營收與業績統計

grain:
  description: 每筆代表一間門市某個月份的業績
  keys: [store_id, sales_month]

columns:
  store_id:
    type: number
    role: identifier
    description: 門市識別碼

  sales_month:
    type: date
    role: dimension
    description: 業績統計月份

  revenue:
    type: number
    role: measure
    description: 當月折扣後營收
    unit: TWD

  gross_margin_pct:
    type: number
    role: measure
    description: 當月毛利率，跨月份應重新計算
    unit: "%"
    disallowed_aggregations: [sum, avg]
```

## 五、生成與驗證

1. 保留 PostgreSQL 原始 View 和 Column 名稱，不做繁簡轉換。
2. 每個 View 產生獨立 YAML。
3. 不得省略資料庫存在的欄位。
4. 檢查每個 YAML 的欄位名稱、數量及型別是否與資料庫一致。
5. 確認 Grain Keys 引用的欄位存在且唯一性有證據支持。
6. 確認產生的限制都有對應證據。
7. 依專案現有 Catalog 格式新增索引，不任意改變既有結構。
8. 現有 YAML 不得直接覆寫人工確認的內容，須先比對並保留差異。
9. 使用現有 Loader 與 Validator 驗證；不支援的型別或設定應列入審核，不得靜默轉換。
10. 重複執行時，相同 Metadata 應產生相同結果。

## 六、人工審核報告

產生 `contract_review.md`，集中列出：

- 缺少 View / Column Comment。
- Role 無法確認的欄位。
- Grain 或 Keys 無法確認的 View。
- 可能存在重複計算風險的數值欄位。
- 註解與 View Definition 不一致之處。
- 需要使用者確認的具體業務問題。

每項都應附上判斷依據與建議修正方向。

未完成必要驗證的 YAML 保留為草稿，不得直接啟用為正式查詢契約。

## 七、完成標準

- 已探索指定 Schema 下所有可讀取的普通 Views。
- 每個 View 都有對應的初版 YAML 或明確失敗原因。
- 所有欄位與資料庫 Metadata 一致。
- 不確定的語意已列入人工審核報告。
- 產出能與現有 View Contract Loader 相容的檔案。
- 未修改任何資料庫物件或業務資料。

完成後請列出產生的檔案、驗證結果，以及仍待人工確認的項目。
