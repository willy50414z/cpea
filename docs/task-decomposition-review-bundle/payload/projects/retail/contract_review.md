# demo_retail View Contract v3 人工審核

## 狀態與範圍

- 透過唯讀 PostgreSQL 連線檢查 `demo_retail` 的 7 個普通 View、102 個輸出欄位，以及來源表主鍵、唯一約束、CHECK 與預設值；沒有讀取業務資料列或修改資料庫。
- 7 份 YAML 均為**草稿**。本 profile 的 `manifest.yaml` 標記 `status: draft`；正常 `SchemaCatalog` 載入會拒絕，僅明確傳入 `allow_drafts=True` 才可供驗證。不要把此 profile 設為正式查詢來源。
- View Comment 缺少：無。Column Comment 缺少：無。根據欄位註解及型別仍無法合理判斷 Role：無。
- 型別轉換：`integer`、`bigint`、`numeric` → `number`；`text` → `string`；`date` → `date`；`boolean` → `boolean`。本批沒有不支援的 PostgreSQL 型別。

## Grain 與 Keys

| View | 草稿 Keys | 結構證據與待確認事項 |
|---|---|---|
| `v_customer_value` | `customer_id` | `customers` 主鍵是 `customer_id`；View 以該欄及會員屬性 GROUP BY，訂單統計在 JOIN 後聚合成每會員一列。 |
| `v_daily_sales` | `store_id, sales_date` | View 依 `order_date, store_id` 及門市屬性 GROUP BY；`stores.store_id` 主鍵決定門市屬性。`v_order_summary` 的 `store_id` 來自該門市表。 |
| `v_inventory_status` | `store_id, product_id` | `inventory` 的複合主鍵；門市與商品 JOIN 各引用主鍵，`last_30d` 也依這兩欄 GROUP BY。 |
| `v_order_summary` | `order_id` | `orders.order_id` 主鍵；View 依 `o.order_id` 及訂單、門市、會員屬性 GROUP BY，明細在 JOIN 後匯總。 |
| `v_product_monthly` | `store_id, sales_month, product_id` | View 依 `order_month, store_id, product_id` 及門市、商品屬性 GROUP BY；`stores.store_id`、`products.product_id` 均有主鍵，屬性由相應 ID 決定。 |
| `v_sales_detail` | `null` | 來源 `order_items.order_item_id` 是主鍵，但 View 未輸出；`(order_id, product_id)` 沒有唯一約束，同訂單可有多筆同商品明細。**請確認是否可加入 `order_item_id`，或提供其他可證實唯一的輸出欄位。** |
| `v_store_monthly_kpi` | `store_id, sales_month` | `monthly_targets(store_id, target_month)` 是複合主鍵；銷售 CTE 依相同門市／月份 GROUP BY，再 LEFT JOIN 該唯一組合。 |

## 數值指標與重複計算風險

| View／欄位 | 判斷依據 | 建議修正方向 |
|---|---|---|
| `v_sales_detail`／整個 View | View Comment 明示「請勿以 COUNT(*) 當訂單數」；同一 `order_id` 可有多筆明細。 | 計算訂單數時以 `COUNT(DISTINCT order_id)` 或訂單粒度的 `v_order_summary`；請確認目前僅支援 `count` 的全域 SQL 白名單是否需要補充不同粒度的計數能力。此限制無法正確表成單一欄位的無條件黑名單。 |
| `v_sales_detail.unit_price` | 欄位註解明示「不應直接加總單價」。 | 已設 `disallowed_aggregations: [sum]`；跨品項單價若要彙總，請確認加權平均口徑。 |
| `v_customer_value.avg_order_value` | 欄位註解要求跨會員以總金額／總訂單數重算。 | 已禁止直接 `sum`、`avg`；請確認零訂單會員是否納入群體平均分母。 |
| `v_store_monthly_kpi.gross_margin_pct`、`avg_order_value`、`target_achievement_pct` | 欄位註解要求跨門市／月份用各自分子分母重算。 | 已禁止直接 `sum`、`avg`；群體值應由總毛利／總營收、總營收／總訂單數、總營收／總目標計算。 |
| `v_inventory_status.stock_qty` | 欄位註解明示可跨門市加總，但不可跨不同快照日期直接加總。 | 目前來源表主鍵只含 `store_id, product_id`，View 不限制 `snapshot_date`；請確認歷史快照的儲存模式。若未來有多日期快照，需用時間條件／粒度規則表達限制，不能用無條件 `disallowed_aggregations: [sum]`。 |
| `v_inventory_status.estimated_days_of_supply` | View SQL 為 `stock_qty × 30 ÷ sold_qty_30d`，欄位註解稱簡化估計。 | 跨商品或門市的天數應先確認加權／重算方式；現有註解沒有明確禁止特定操作，因此未產生黑名單。 |
| `v_store_monthly_kpi`／月度指標 | View Comment 明示 2026-10 是未完整月份。 | 跨月比較、達標率解讀前，請確認是否必須篩 `is_complete_month=true`；本次未實作 `scope_rules`。 |

## 註解與 SQL 定義的待核對之處

原先 `v_customer_value` 的固定涵蓋期間，以及 `v_inventory_status` 的固定快照日期敘述，已從目前 View YAML 移除；不再把它們當成契約保證或評估題目的前提。以下保留仍需核對的項目。資料庫 Comment 是否同步修改，尚未重新查詢確認。

| View | 證據 | 需要確認的業務問題與方向 |
|---|---|---|
| `v_inventory_status.sold_qty_30d` | 目前欄位 description 仍寫「截至 2026-10-14（含）過去 30 個曆日」；View SQL 的時間窗口需重新核對。 | 確認這是固定業務定義或舊樣本日期；若只是樣本日期，請移除固定日期，改寫為相對時間窗口。 |
| `v_sales_detail` | View Comment 說「每個商品品項」，來源表的唯一鍵是 `order_item_id` 或 `(order_id, line_no)`，不是 `(order_id, product_id)`；View 未輸出明細鍵。 | 請確認同訂單是否允許重複商品行；若允許，建議把粒度措辭改為「每筆訂單明細一列」，並輸出 `order_item_id`。 |

## 啟用前條件

1. 確認 `v_sales_detail` 的唯一鍵或接受其 Keys 為未知，並確認是否要讓沒有可證實 Keys 的 View 進入查詢 Catalog。
2. 核對 `sold_qty_30d` 尚存的固定日期描述與 View SQL，避免將樣本日期當成長期契約。
3. 決定跨粒度比率、單價與訂單數的查詢規則；本批只對註解明示的欄位操作設定黑名單，沒有推定 `default_aggregation`。
4. 完成業務審核後，才移除 `manifest.yaml` 的草稿狀態並作為正式部署 profile；確認 PostgreSQL 資料來源與目前 SQL compiler 的方言配置可實際執行。

## 重跑方式

在專案根目錄執行 `uv run --extra postgres-contracts python scripts/generate_view_contracts.py`。生成器讀取專案 `.env` 指定的 PostgreSQL schema metadata，預設寫入 `projects/retail`；已存在且內容不同的 YAML 或索引會停止並要求人工合併，不會覆寫。相同 metadata 重跑時檔案內容維持不變。
