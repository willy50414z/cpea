# Retail 395 題 View 篩選測試

使用正式流程的 `retrieve_schema` 節點與目前專案設定，並模擬後續單一 View 的完整契約打包；不呼叫 SQL 生成模型或資料庫。
`target_view` 對拒絕類題目只代表題目所屬 View，不代表應產生 SQL。

檢索：`lexical`；reranker：`lexical`；候選上限：5；契約指紋：`e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc`。

完整契約可容納：1975/1975 次候選打包。

| 題目類別 | 題數 | top 1 | top 4 | top 5 | 檢索摘要可容納 | 完整契約可容納 |
|---|---:|---:|---:|---:|---:|---:|
| all | 395 | 245 | 383 | 394 | 394 | 394 |
| ambiguous | 14 | 14 | 14 | 14 | 14 | 14 |
| normal | 330 | 180 | 318 | 329 | 329 | 329 |
| security | 11 | 11 | 11 | 11 | 11 | 11 |
| unsupported | 40 | 40 | 40 | 40 | 40 | 40 |

## 未進入候選的題目

### RETAIL-ORDER_SUMMARY-S3-03

- 類別：`normal`
- 目標 View：`demo_retail.v_order_summary`
- 問題：我想看逐筆的從哪個管道成交、賺到的毛利，條件是會員叫什麼 LIKE 王%。
- 前五名：`demo_retail.v_sales_detail`、`demo_retail.v_customer_value`、`demo_retail.v_store_monthly_kpi`、`demo_retail.v_product_monthly`、`demo_retail.v_daily_sales`


此結果只量測候選召回與 context 容量；不表示模型最後會選對 View、拒絕不支援需求或產生正確 SQL。
