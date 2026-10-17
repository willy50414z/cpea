# Retail View 候選隔離實驗

依目前 YAML 核對的明確及歧義問題；只測候選覆蓋與 context budget，不呼叫生成模型或資料庫。

案例：10；View：7。

| 策略 | top 4 排名涵蓋 | top 5 排名涵蓋 | top 7 排名涵蓋 | top 7 批次 context | top 7 逐 View context |
|---|---:|---:|---:|---:|---:|
| vector_rerank | 9/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| lexical | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| hybrid_rerank | 9/10 | 10/10 | 10/10 | 10/10 | 10/10 |

## 案例

| 案例 | 種類 | 目標 View 排名（vector rerank） |
|---|---|---|
| `RETRIEVAL-DAILY` | clear | `demo_retail.v_daily_sales`：1 |
| `RETRIEVAL-ORDER` | clear | `demo_retail.v_order_summary`：1 |
| `RETRIEVAL-DETAIL` | clear | `demo_retail.v_sales_detail`：2 |
| `RETRIEVAL-INVENTORY` | clear | `demo_retail.v_inventory_status`：1 |
| `RETRIEVAL-STORE-MONTH` | clear | `demo_retail.v_store_monthly_kpi`：1 |
| `RETRIEVAL-PRODUCT-MONTH` | clear | `demo_retail.v_product_monthly`：1 |
| `RETRIEVAL-CUSTOMER` | clear | `demo_retail.v_customer_value`：1 |
| `RETRIEVAL-GRAIN-AMBIGUOUS` | ambiguous | `demo_retail.v_sales_detail`：1、`demo_retail.v_order_summary`：2 |
| `RETRIEVAL-DAY-SYNONYM` | clear | `demo_retail.v_daily_sales`：1 |
| `RETRIEVAL-DAY-COMPLEX` | clear | `demo_retail.v_daily_sales`：5 |
