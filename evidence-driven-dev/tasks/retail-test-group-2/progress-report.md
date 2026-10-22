# Test group 2 階段結果（尚未完成）

既有14題已記錄為test group 1；排除後抽取30題為test group 2，計畫各3次共90次。固定名單見projects/retail/evaluations/test_groups/。

目前完成23/90：9次符合原預期、14次未符合，其中2次為模型服務ReadTimeout（每次300秒）。另一次獨立8-token health診斷在45秒逾時，不混入90次結果。剩餘67個tuple尚未執行，不能宣稱完成穩定性測試。

查到同一Ollama另有來自/home/willy/code/cpea_terms的run_ollama_decomposition.py正在推論，開始時間與逾時區段重疊；尚未單獨確證根因。保留原兩個segments，不重試已執行tuple，等待後端可完成推論後接續。

| 案例 | 已測 | 符合原預期 | 生成狀態 | 失敗原因 |
|---|---:|---:|---|---|
| `RETAIL-SALES_DETAIL-S1-01` | 3/3 | 3 | ready, ready, ready | {} |
| `RETAIL-ORDER_SUMMARY-S1-01` | 3/3 | 0 | needs_clarification, needs_clarification, needs_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-STORE_MONTHLY_KPI-S1-01` | 3/3 | 3 | ready, ready, ready | {} |
| `RETAIL-INVENTORY_STATUS-S2-04` | 3/3 | 3 | ready, ready, ready | {} |
| `RETAIL-CUSTOMER_VALUE-S2-02` | 3/3 | 0 | ready, ready, ready | {"mapping_view": 3, "mapping_fields": 3, "mapping_criteria": 3, "mapping_group": 3, "sql_view": 3, "sql_select": 3, "sql_filters": 3, "sql_aggregations": 3, "sql_group": 3, "sql_policy": 3} |
| `RETAIL-PRODUCT_MONTHLY-S2-05` | 3/3 | 0 | needs_clarification, needs_clarification, needs_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-DAILY_SALES-S3-03` | 3/3 | 0 | needs_clarification, needs_clarification, needs_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-CUSTOMER_VALUE-S3-03` | 2/3 | 0 | error, error | {"ReadTimeout: timed out": 2} |

原始紀錄見本Task .local/segment_registry.json、各segment的results.jsonl/calls.jsonl及partial-summary.json；來源、原Oracle與固定群組未變。沒有執行DB，正式案例審核仍pending。
