# demo_retail View Contract v4 核對紀錄

## 狀態與範圍

已以唯讀 PostgreSQL metadata 核對 7 個 views、102 個輸出欄位、直接來源、完整 view 定義及來源主鍵／唯一約束；沒有查詢業務資料列或修改資料庫。`source.verification: metadata_verified` 僅表示結構與 DDL 證據已核對。

保留既有 manifest 的 `profile_id: demo_retail_draft` 與 `status: approved`，僅將 contract_version 更新為字串 `4`；此處不宣稱新增業務核准。原始題庫及 v3 快照另存於前後測證據目錄，不因遷移而改寫。

## 粒度與來源

| View | 輸出唯一鍵 | 已核對的來源事實 |
|---|---|---|
| v_customer_value | customer_id | customers 主鍵；LEFT JOIN 訂單再依會員彙總，包含未下單會員。 |
| v_daily_sales | sales_date、store_id | 訂單依門市日期 GROUP BY；只包含有交易的日期，不補零。 |
| v_inventory_status | store_id、product_id | inventory 複合主鍵；門市與商品主檔 JOIN 主鍵；銷量子查詢按相同鍵聚合。 |
| v_order_summary | order_id | orders 主鍵；只含 completed，INNER JOIN 商品明細後依訂單彙總。 |
| v_product_monthly | store_id、sales_month、product_id | 交易明細依門市、月份、商品及其屬性 GROUP BY，無訂單數。 |
| v_sales_detail | null | 未輸出 order_item_id 或 line_no；來源唯一約束是 order_item_id 與 (order_id,line_no)，不能證明 (order_id,product_id) 唯一。 |
| v_store_monthly_kpi | store_id、sales_month | monthly_targets 複合主鍵；以目標表為母體 LEFT JOIN 月實績，無目標組合不出現。 |

## 時間與指標核對

- 會員消費值是可用已完成訂單的累計，SQL 未限制統計日期；registered_on 是註冊時間，不能用來取得指定交易期間消費。活躍旗標只判斷最後訂單日期 >= 2026-07-17，沒有上界，不是動態或完整有上下界的 90 日窗口。
- 庫存 snapshot_date 來自每筆 inventory 紀錄，未限定最新日期或保證全體同日。sold_qty_30d 固定在 2026-09-15～2026-10-14（含首尾），不隨快照或執行日期移動；無銷量時為 0，estimated_days_of_supply 為 null。
- 庫存成本估值使用商品主檔成本；交易成本使用下單明細成本，不能互換。不同快照日期的庫存不可直接相加。
- 月 KPI 的完整月條件固定為 sales_month < 2026-10-01；無實績補零，目標不大於零時達標率為 null。毛利率在營收不大於零時為 0，百分比不是範圍約束。
- 客單價、毛利率與達標率跨群體需用分子分母重算。既有 disallowed_aggregations 保留；本次未擴大 compiler 公式或聚合能力。
- 月彙總的 MIN／MAX／AVG 作用於月彙總列，不能還原明細分布。明細列數不是訂單數。

## 重跑與限制

執行 `uv run --extra postgres-contracts python scripts/generate_view_contracts.py`；明列語意由 canonical YAML 載入，DB 僅核對 metadata，不從混合註解生成摘要。定義、來源、型別或唯一性漂移時拒絕；差異檔案需人工合併，相同內容不改寫。

完整欄位規則見 [v4 契約文件](../../docs/view-schema-v4.md)。本輪模型評估只核對原 mapping／SQL Oracle，不執行 SQL，因此正確率不能當作資料庫結果正確率。
