# Retail 穩定性測試群組

群組固定案例成員，不代表所有題目已通過。原題庫與預期答案不變。

- `test group 1`：沿用先前14題；原版14×3已測，修復版只對原未通過6題各3次重測。
- `test group 2`：排除group1後固定抽取30題，各3次，共90次。24題正常查詢（SQL與語意難度各8題），另3題不支援、2題歧義、1題安全。七個View各4–5題。
- 抽樣種子20261020；只依既有分類與難度抽樣，不依本輪模型結果重抽。這是既有題庫的新測試組，不視為從未接觸的盲測資料。
- 凍結產品、prompt、契約、群組與原Oracle；待確認不代選，每次使用空白隔離詞彙檔。
- 分別記錄正確率與三次結果一致性；一致失敗不視為通過。安全拒絕可符合原預期，另列生成狀態與HILP待確認狀態。
- 未執行DB，正式人工審核仍pending，屬探索性結果。

| 群組 | 名單 | 執行紀錄 |
|---|---|---|
| test group 1 | [14題](test_group_1.json) | [既有修復驗證](../../../../evidence-driven-dev/tasks/fix-14-regressions/final-report.md) |
| test group 2 | [30題](test_group_2.json) | [EDD Task](../../../../evidence-driven-dev/tasks/retail-test-group-2/task.md) |

## Test group 2 題目

| 案例 | View | 類型 | SQL／語意難度 |
|---|---|---|
| `RETAIL-SALES_DETAIL-S1-01` | `demo_retail.v_sales_detail` | normal | S／L1 |
| `RETAIL-ORDER_SUMMARY-S1-01` | `demo_retail.v_order_summary` | normal | S／L1 |
| `RETAIL-STORE_MONTHLY_KPI-S1-01` | `demo_retail.v_store_monthly_kpi` | normal | S／L1 |
| `RETAIL-INVENTORY_STATUS-S2-04` | `demo_retail.v_inventory_status` | normal | S／L2 |
| `RETAIL-CUSTOMER_VALUE-S2-02` | `demo_retail.v_customer_value` | normal | S／L2 |
| `RETAIL-PRODUCT_MONTHLY-S2-05` | `demo_retail.v_product_monthly` | normal | S／L2 |
| `RETAIL-DAILY_SALES-S3-03` | `demo_retail.v_daily_sales` | normal | S／L3 |
| `RETAIL-CUSTOMER_VALUE-S3-03` | `demo_retail.v_customer_value` | normal | S／L3 |
| `RETAIL-DAILY_SALES-M1-05` | `demo_retail.v_daily_sales` | normal | M／L1 |
| `RETAIL-STORE_MONTHLY_KPI-G-02` | `demo_retail.v_store_monthly_kpi` | normal | M／L1 |
| `RETAIL-INVENTORY_STATUS-M2-05` | `demo_retail.v_inventory_status` | normal | M／L2 |
| `RETAIL-SALES_DETAIL-M2-02` | `demo_retail.v_sales_detail` | normal | M／L2 |
| `RETAIL-ORDER_SUMMARY-M2-03` | `demo_retail.v_order_summary` | normal | M／L2 |
| `RETAIL-PRODUCT_MONTHLY-M3-04` | `demo_retail.v_product_monthly` | normal | M／L3 |
| `RETAIL-ORDER_SUMMARY-M3-01` | `demo_retail.v_order_summary` | normal | M／L3 |
| `RETAIL-DAILY_SALES-M3-05` | `demo_retail.v_daily_sales` | normal | M／L3 |
| `RETAIL-PRODUCT_MONTHLY-H1-04` | `demo_retail.v_product_monthly` | normal | H／L1 |
| `RETAIL-CUSTOMER_VALUE-H1-02` | `demo_retail.v_customer_value` | normal | H／L1 |
| `RETAIL-INVENTORY_STATUS-H1-01` | `demo_retail.v_inventory_status` | normal | H／L1 |
| `RETAIL-STORE_MONTHLY_KPI-H2-04` | `demo_retail.v_store_monthly_kpi` | normal | H／L2 |
| `RETAIL-SALES_DETAIL-H2-03` | `demo_retail.v_sales_detail` | normal | H／L2 |
| `RETAIL-ORDER_SUMMARY-H3-03` | `demo_retail.v_order_summary` | normal | H／L3 |
| `RETAIL-STORE_MONTHLY_KPI-H3-01` | `demo_retail.v_store_monthly_kpi` | normal | H／L3 |
| `RETAIL-INVENTORY_STATUS-H3-05` | `demo_retail.v_inventory_status` | normal | H／L3 |
| `RETAIL-SALES_DETAIL-B-03` | `demo_retail.v_sales_detail` | unsupported | —／— |
| `RETAIL-CUSTOMER_VALUE-B-02` | `demo_retail.v_customer_value` | unsupported | —／— |
| `RETAIL-DAILY_SALES-B-06` | `demo_retail.v_daily_sales` | unsupported | —／— |
| `RETAIL-PRODUCT_MONTHLY-B-04` | `demo_retail.v_product_monthly` | ambiguous | —／— |
| `RETAIL-INVENTORY_STATUS-B-05` | `demo_retail.v_inventory_status` | ambiguous | —／— |
| `RETAIL-STORE_MONTHLY_KPI-B-10` | `demo_retail.v_store_monthly_kpi` | security | —／— |
