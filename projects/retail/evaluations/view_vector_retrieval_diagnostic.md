# Retail Vector View 檢索診斷

使用目前 Retail 設定；只比較初步 vector 排名與 lexical rerank 排名，不呼叫生成模型或資料庫。

正常題：330；View：7；初步候選上限：15；rerank 輸出上限：4。
Embedding 模型：`nomic-embed-text`；契約指紋與目前 YAML 不一致：330。

| View | 題數 | vector top-1 | rerank top-1 | vector top-4 | rerank top-4 |
|---|---:|---:|---:|---:|---:|
| `demo_retail.v_customer_value` | 47 | 16 | 24 | 44 | 47 |
| `demo_retail.v_daily_sales` | 47 | 17 | 9 | 38 | 34 |
| `demo_retail.v_inventory_status` | 47 | 15 | 36 | 33 | 47 |
| `demo_retail.v_order_summary` | 47 | 15 | 14 | 43 | 47 |
| `demo_retail.v_product_monthly` | 47 | 18 | 31 | 39 | 45 |
| `demo_retail.v_sales_detail` | 48 | 1 | 11 | 26 | 48 |
| `demo_retail.v_store_monthly_kpi` | 47 | 20 | 35 | 44 | 47 |
| **總計** | **330** | **102** | **160** | **267** | **315** |

## Rerank 後未進候選的正常題

| 案例 | 目標 View | vector 排名 | rerank 排名 |
|---|---|---:|---:|
| `RETAIL-DAILY_SALES-S2-03` | `demo_retail.v_daily_sales` | 7 | 5 |
| `RETAIL-DAILY_SALES-M1-02` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M1-04` | `demo_retail.v_daily_sales` | 1 | 5 |
| `RETAIL-DAILY_SALES-M2-02` | `demo_retail.v_daily_sales` | 7 | 5 |
| `RETAIL-DAILY_SALES-M2-03` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M2-04` | `demo_retail.v_daily_sales` | 3 | 5 |
| `RETAIL-DAILY_SALES-M3-01` | `demo_retail.v_daily_sales` | 4 | 5 |
| `RETAIL-DAILY_SALES-M3-02` | `demo_retail.v_daily_sales` | 5 | 5 |
| `RETAIL-DAILY_SALES-M3-03` | `demo_retail.v_daily_sales` | 3 | 5 |
| `RETAIL-DAILY_SALES-M3-04` | `demo_retail.v_daily_sales` | 3 | 5 |
| `RETAIL-DAILY_SALES-H3-01` | `demo_retail.v_daily_sales` | 4 | 5 |
| `RETAIL-DAILY_SALES-H3-02` | `demo_retail.v_daily_sales` | 5 | 5 |
| `RETAIL-DAILY_SALES-H3-05` | `demo_retail.v_daily_sales` | 4 | 5 |
| `RETAIL-PRODUCT_MONTHLY-S2-04` | `demo_retail.v_product_monthly` | 6 | 5 |
| `RETAIL-PRODUCT_MONTHLY-S2-05` | `demo_retail.v_product_monthly` | 5 | 5 |
