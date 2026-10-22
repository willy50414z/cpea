# Retail test group 2 穩定性測試

已固定既有14題為test group 1；另外排除原14題後以seed20261020分層抽出30題為test group 2。30題各3次，合計90次。測試期間凍結產品、prompt、契約、群組與原Oracle，不因結果修改產品或重抽樣本。曾因provider逾時中斷；逾時算失敗，核對版本後只接續尚未執行項目，沒有重試已做tuple。

原預期映射及SQL結構完整通過 **48/90**；三次全通過 **16/30題**，三次全失敗 14 題、通過/失敗混合 0 題。生成狀態三次一致 29/30題；一致失敗仍算失敗。

正常查詢通過 36/72；不支援/歧義/安全案例符合原預期 12/18。

有產生 SQL 的 13 題，三次完整 SQL 文字皆相同；其中 12 題符合預期，另 1 題三次都選錯 View，因此不能將 SQL 相同解讀為正確。其餘 17 題無完整三次 SQL 可比較。正確／失敗結果三次一致為 30/30 題，包含 14 題一致失敗。

正常查詢的 12 題失敗中，6 題停在 View 澄清、1 題產生 SQL 但映射至錯誤 View、5 題回覆不支援或服務錯誤（其中 1 題包含兩次逾時）。另外 2 題邊界案例雖皆回覆不支援、未輸出 SQL，但映射未符合原 Oracle，仍保留為失敗；本輪未調整預期或評分。

HILP：18 次為 View 澄清，72 次未發起確認，沒有自動代選。正式評審狀態為 88 次 pending、2 次逾時無生成結果；本輪沒有正式核准任何案例。

## 每題三次結果

SQL一致性比較完整SQL文字；無SQL記為「—」，不把三次沒有SQL算成SQL穩定。正確率沿用原題庫預期；HILP/澄清另列且不代選。

| 案例 | 類型 | 通過 | 三次生成狀態 | 狀態一致 | SQL一致 | 待確認狀態 | 失敗原因 |
|---|---|---:|---|---|---|---|---|
| `RETAIL-SALES_DETAIL-S1-01` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-ORDER_SUMMARY-S1-01` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-STORE_MONTHLY_KPI-S1-01` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-INVENTORY_STATUS-S2-04` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-CUSTOMER_VALUE-S2-02` | normal | 0/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {"mapping_view": 3, "mapping_fields": 3, "mapping_criteria": 3, "mapping_group": 3, "sql_view": 3, "sql_select": 3, "sql_filters": 3, "sql_aggregations": 3, "sql_group": 3, "sql_policy": 3} |
| `RETAIL-PRODUCT_MONTHLY-S2-05` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-DAILY_SALES-S3-03` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-CUSTOMER_VALUE-S3-03` | normal | 0/3 | error, error, unsupported | 否 | — | not_requested, not_requested, not_requested | {"ReadTimeout: timed out": 2, "mapping_unavailable": 1, "query_plan_unavailable": 1} |
| `RETAIL-DAILY_SALES-M1-05` | normal | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-STORE_MONTHLY_KPI-G-02` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-INVENTORY_STATUS-M2-05` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-SALES_DETAIL-M2-02` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-ORDER_SUMMARY-M2-03` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-PRODUCT_MONTHLY-M3-04` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-ORDER_SUMMARY-M3-01` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-DAILY_SALES-M3-05` | normal | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-PRODUCT_MONTHLY-H1-04` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-CUSTOMER_VALUE-H1-02` | normal | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-INVENTORY_STATUS-H1-01` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-STORE_MONTHLY_KPI-H2-04` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-SALES_DETAIL-H2-03` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-ORDER_SUMMARY-H3-03` | normal | 3/3 | ready, ready, ready | 是 | 是 | not_requested, not_requested, not_requested | {} |
| `RETAIL-STORE_MONTHLY_KPI-H3-01` | normal | 0/3 | needs_clarification, needs_clarification, needs_clarification | 是 | — | view_clarification, view_clarification, view_clarification | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-INVENTORY_STATUS-H3-05` | normal | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_unavailable": 3, "query_plan_unavailable": 3} |
| `RETAIL-SALES_DETAIL-B-03` | unsupported | 3/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {} |
| `RETAIL-CUSTOMER_VALUE-B-02` | unsupported | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_view": 3, "mapping_fields": 3} |
| `RETAIL-DAILY_SALES-B-06` | unsupported | 3/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {} |
| `RETAIL-PRODUCT_MONTHLY-B-04` | ambiguous | 3/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {} |
| `RETAIL-INVENTORY_STATUS-B-05` | ambiguous | 0/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {"mapping_view": 3, "mapping_fields": 3} |
| `RETAIL-STORE_MONTHLY_KPI-B-10` | security | 3/3 | unsupported, unsupported, unsupported | 是 | — | not_requested, not_requested, not_requested | {} |

## 設定與成本

Ollama `qwen3.8:27b`、`Q4_K_M`，模型digest `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`；MATCH v10、PostgreSQL、temperature 0、seed 42、context 16000、max output 8192、lexical retrieval；每次空白隔離詞彙檔。

共 575 次模型呼叫、案例執行累計 368.5 分鐘（不含排隊）；從開始到合併共 547.5 分鐘（含等候）；輸入 2,421,557 tokens、輸出 215,005 tokens。

## 產物與可追溯性

- 群組：[group1](../../../projects/retail/evaluations/test_groups/test_group_1.json)、[group2](../../../projects/retail/evaluations/test_groups/test_group_2.json)。
- 本Task `.local/live-group2-20261020/` 保存run.json、results.jsonl、calls.jsonl；`.local/verification.json`保存90筆重評與完整性摘要，原始大型I/O不提交Git。中斷及續跑segments與合併檔由.local/segment_registry.json、merged-seals.json、combined-group2-20261020/追溯，未覆寫原始資料。
- HEAD `014cee1aff3abcfb51bbe5af6db0abd2ef060225`；EDD工作樹指紋 `1c843050fcd699b19aff6641c0045e9b6fd8a92d1ea2329be9d68acb4d490f7c`；產品source fingerprint `14a65caf5324ecc612bfa726effa95f47cc7f933c9883e6396db91e5152acafb`。

## 限制

另有 2 次獨立health診斷，不混入90次與casetest呼叫數。provider錯誤 2 次，執行segments 3 個；全部原樣保留並納入90次結果。

- 案例pending且為draft契約，屬探索性評估。
- 未執行DB或驗證實際數值。
- 30題來自已知395題，非從未見過的盲測。
- 本輪只測group2，沒有新增group1修復版執行。
- 曾遇provider逾時，中斷後只接續未做項目；逾時保留失敗且未重試。
- Main依原Oracle於fresh subprocess重評，未另啟Reviewer Agent。

measurement_integrity=PASS只代表測量紀錄完整且版本一致，不能解讀為產品全部通過。
