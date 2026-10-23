# View YAML v4 契約

v4 將查詢所需語意分開保存，`summary` 只放 view 描述。例如「訂單銷售彙總資料。」；粒度、欄位清單、期間、公式與使用情境各有自己的欄位，不再重複塞入摘要。

## 以 5W1H 檢查資訊是否完整

| 問題 | YAML 欄位 | 審查重點 |
|---|---|---|
| What：這是什麼資料？ | summary、columns | 描述 view 與各輸出欄位。 |
| Who：屬於哪個業務對象？ | columns.entity、description | 會員城市與門市城市必須區分。 |
| Where：資料從哪裡來、涵蓋誰？ | source、scope | 直接來源、母體、內建篩選、缺列與補零。 |
| When：時間代表什麼？ | time | 事件、彙總、快照或累計；固定窗口與動態窗口分開。 |
| Why：可回答什麼問題？ | usage | 不支援的問題必須交代資料不足原因。 |
| How：每列如何形成、如何計算？ | grain、metrics | 唯一鍵、既有指標公式及跨列聚合限制。 |

## 結構與未知值

頂層必填 `version/view/summary/grain/source/scope/time/usage/columns/metrics`，所有物件拒絕未宣告欄位。可機器檢查的結構見 [JSON Schema](view-schema-v4.schema.json)；loader 另驗證欄位引用、日期型別與來源證據的條件關係。

- `version` 為整數 4；仍接受既有 v1、v2、v3 與無版本契約，未知版本拒絕。
- `grain.description` 描述每列對象；不能證實輸出欄位唯一時用 `keys: null`，不能編造複合鍵。
- `source.verification` 是 `metadata_verified` 或 `unknown`。前者須有 qualified `relations` 及 PostgreSQL `pg_get_viewdef(..., true)` 原始 UTF-8 字串的 SHA-256。未知來源使用 `relations: null`、`definition_sha256: null`。
- `scope` 記 population、included、excluded、row_coverage。內建條件是來源事實，不要求模型再對未輸出的狀態欄位建立 WHERE。
- `time.kind` 為 event、aggregate、snapshot、cumulative、mixed 或 unknown；dimensions 引用日期欄，rules.columns 可引用任何現有欄。未保證完整涵蓋期間時 `coverage: null`。
- `usage.supported` 是文字陣列；unsupported 每項須有 question 與 reason。
- `columns` 延續 v3 的 type、role、description、unit 與 disallowed 設定；可選 entity 必須是非空字串。禁止事項不會擴大 SQL compiler 能力。
- `metrics` 可為空物件；每項包含 description、columns、calculation、aggregation_notes。calculation 只作語意說明，從不直接執行或拼接為 SQL。
- 空陣列表示沒有該類規則，不能拿空字串代替未知值。metadata 核對不代表業務核准；source 列出 base tables 也不授予查詢權限，允許來源仍由 catalog 決定。

## 完整範例

以下為 Retail 訂單 view 的完整 v4 定義。來源 hash 與關係應由實際 metadata 核對，不應複製到其他 view。

```yaml
version: 4
view: demo_retail.v_order_summary
summary: 訂單銷售彙總資料。
grain:
  description: 每筆訂單一列
  keys:
  - order_id
source:
  verification: metadata_verified
  relations:
  - demo_retail.customers
  - demo_retail.order_items
  - demo_retail.orders
  - demo_retail.stores
  definition_sha256: 9c611d5e71b6f178e1ef35eadb64f672b33cfbe717f4e5dd5ad7d91bdb4fb859
scope:
  population: 有商品明細且能連結門市與會員的已完成訂單。
  included:
  - 訂單狀態為 completed
  excluded:
  - 未完成訂單
  - 沒有商品明細的訂單
  row_coverage: 明細經 INNER JOIN 後彙總成訂單列；不是所有訂單主檔紀錄。
time:
  kind: event
  dimensions:
    order_date: 訂單成立時間轉為曆日。
    order_month: 訂單成立月份首日。
  coverage: null
  rules:
  - columns:
    - order_date
    - order_month
    description: 兩欄都來自訂單成立時間，不代表付款日期。
usage:
  supported:
  - 訂單筆數與訂單金額分析
  - 訂單通路、會員等級與門市分析
  unsupported:
  - question: 商品層級銷售分析
    reason: 商品明細已彙總，未輸出商品維度。
  - question: 取消或未完成訂單分析
    reason: 內建已排除未完成訂單。
columns:
  order_id:
    type: number
    role: identifier
    description: 已完成訂單的唯一識別碼；本 View 每筆訂單只有一列。
    entity: 訂單
  order_no:
    type: string
    role: identifier
    description: 訂單編號；本 View 每筆已完成訂單只有一列。
    entity: 訂單
  order_date:
    type: date
    role: dimension
    description: 訂單成立日期（曆日），不含時間。
  order_month:
    type: date
    role: dimension
    description: 訂單成立月份的第一天，供月份統計與篩選。
  store_id:
    type: number
    role: identifier
    description: 訂單所屬門市識別碼。
    entity: 門市
  store_name:
    type: string
    role: dimension
    description: 訂單所屬門市名稱。
    entity: 門市
  region:
    type: string
    role: dimension
    description: 訂單門市所屬區域；北部、中部、南部。
    entity: 門市
  store_city:
    type: string
    role: dimension
    description: 訂單門市所在城市，不是會員居住城市。
    entity: 門市
  sales_channel:
    type: string
    role: dimension
    description: 訂單銷售通路；in_store=實體門市，online=線上。
  customer_id:
    type: number
    role: identifier
    description: 下單會員識別碼。
    entity: 會員
  customer_name:
    type: string
    role: dimension
    description: 下單會員名稱；為虛構測試資料。
    entity: 會員
  membership_tier:
    type: string
    role: dimension
    description: 下單會員等級；一般、銀卡、金卡、VIP。
    entity: 會員
  item_lines:
    type: number
    role: measure
    description: 此訂單的商品明細列數（COUNT order_item_id）；不是總銷售件數。
  total_quantity:
    type: number
    role: measure
    description: 此訂單全部明細的商品銷售件數加總；單位件。
    unit: 件
  order_amount:
    type: number
    role: measure
    description: 此訂單折扣後的總銷售金額（各明細 quantity × unit_price − discount），單位 TWD。
    unit: TWD
  cost_amount:
    type: number
    role: measure
    description: 此訂單全部明細的商品成本總額，單位 TWD。
    unit: TWD
  gross_profit:
    type: number
    role: measure
    description: 此訂單毛利，order_amount − cost_amount，單位 TWD。
    unit: TWD
metrics:
  orders:
    description: 訂單筆數
    columns:
    - order_id
    calculation: 每列代表一筆訂單，可計算列數。
    aggregation_notes: 不可將 item_lines 或 total_quantity 當作訂單筆數。
  lines:
    description: 商品明細列數
    columns:
    - item_lines
    calculation: COUNT order_item_id。
    aggregation_notes: 跨訂單可加總；與銷售件數不同。
  units:
    description: 銷售件數
    columns:
    - total_quantity
    calculation: SUM 明細 quantity。
    aggregation_notes: 跨訂單可加總。
  net_sales:
    description: 訂單折扣後銷售額
    columns:
    - order_amount
    calculation: SUM 明細 quantity × unit_price − discount。
    aggregation_notes: 跨訂單可加總；單列最大值是訂單金額最大值。
  cost:
    description: 訂單成本
    columns:
    - cost_amount
    calculation: SUM 明細 quantity × 下單時 unit_cost。
    aggregation_notes: 跨訂單可加總。
  profit:
    description: 訂單毛利
    columns:
    - gross_profit
    - order_amount
    - cost_amount
    calculation: order_amount − cost_amount。
    aggregation_notes: 跨訂單可加總，不是毛利率。
```

## 生成與審核

`projects/retail` 的七份 YAML 是明列語意的唯一來源；generator 不再從混合 DB comment 推測 summary 或 grain。執行：

```bash
uv run --extra postgres-contracts python scripts/generate_view_contracts.py
# 使用不同輸出目錄時，該目錄需提供資料庫設定 .env
uv run --extra postgres-contracts python scripts/generate_view_contracts.py --root /path/to/output --semantic-profile projects/retail
```

generator 僅讀 PostgreSQL metadata，在唯讀交易核對定義 hash、直接來源、欄位名稱／型別及來源唯一約束。缺少顯式語意或 DDL 漂移即拒絕。既有內容不同須人工合併，相同內容不改寫；新 profile 為 draft，既有 profile 的核准狀態不因重跑升級。

契約語意會傳到檢索、候選 schema、候選比較與詳細 context；既有檢索權重、MATCH prompt 與候選策略保持原設定。契約指紋變更會使舊 mapping 失效；評估案例需保留原 Oracle，只用 pending 副本核對新契約，不能將舊核准狀態沿用為新版本業務核准。
