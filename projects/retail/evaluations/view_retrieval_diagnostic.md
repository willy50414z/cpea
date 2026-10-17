# Retail View 檢索診斷

只評估正常題的正確 View 排名；不呼叫模型、不驗證最終 SQL。

正常題：330；契約指紋與目前 YAML 不一致：330。
指紋差異不影響此處的排名計算，但題庫正式評分前仍需重新審核。

| View | 題數 | 原本 top-1 | 目前 top-1 | 原本 top-4 | 目前 top-4 |
|---|---:|---:|---:|---:|---:|
| `demo_retail.v_customer_value` | 47 | 15 | 29 | 45 | 47 |
| `demo_retail.v_daily_sales` | 47 | 2 | 3 | 11 | 38 |
| `demo_retail.v_inventory_status` | 47 | 37 | 43 | 47 | 47 |
| `demo_retail.v_order_summary` | 47 | 13 | 10 | 46 | 45 |
| `demo_retail.v_product_monthly` | 47 | 9 | 36 | 45 | 46 |
| `demo_retail.v_sales_detail` | 48 | 27 | 25 | 48 | 48 |
| `demo_retail.v_store_monthly_kpi` | 47 | 40 | 34 | 46 | 47 |
| **總計** | **330** | **143** | **180** | **288** | **318** |

## 目前未進 top-4 的正常題

| 案例 | 目標 View | 原本排名 | 目前排名 |
|---|---|---:|---:|
| `RETAIL-DAILY_SALES-M1-04` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M2-02` | `demo_retail.v_daily_sales` | 5 | 5 |
| `RETAIL-DAILY_SALES-M2-03` | `demo_retail.v_daily_sales` | 5 | 5 |
| `RETAIL-DAILY_SALES-M2-04` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M3-02` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M3-03` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-M3-04` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-H3-02` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-DAILY_SALES-H3-04` | `demo_retail.v_daily_sales` | 6 | 5 |
| `RETAIL-ORDER_SUMMARY-S3-03` | `demo_retail.v_order_summary` | 3 | 6 |
| `RETAIL-ORDER_SUMMARY-M1-05` | `demo_retail.v_order_summary` | 2 | 5 |
| `RETAIL-PRODUCT_MONTHLY-S2-04` | `demo_retail.v_product_monthly` | 5 | 5 |

## 未進 top-4 的原因診斷

以下是根據需求文字、目前 YAML 契約及字面檢索分數的判斷；排名低的原因是推測，替代 View 可編譯則已用目前 compiler 驗證。

| 題目 | 觀察與可能原因 |
|---|---|
| `DAILY_SALES-M1-04`、`M2-02`～`M2-04`、`M3-02`～`M3-04`（7 題） | 需求沒有指定日期或每日粒度。月 KPI View 也具備所需欄位；將預期 QueryPlan 的來源改為 `v_store_monthly_kpi`，7 題都能通過契約與 SQL 編譯。`MAX` 等聚合以「日列」或「月列」計算會得到不同結果，因此目標 View 並非由需求唯一決定。月 KPI 在這 7 題均排在目標 View 前面。 |
| `DAILY_SALES-H3-02`、`H3-04`（2 題） | 需求明示「有成交的那一天」，月 KPI 不含 `sales_date`，替代編譯失敗；這兩題有足夠的日粒度線索。`v_daily_sales` 契約使用「銷售日期／有銷售的日期」，字面檢索沒有將其與「有成交的那一天」視為同義，兩題都排第 5。 |
| `ORDER_SUMMARY-S3-03` | 需求「逐筆的從哪個管道成交、賺到的毛利，會員叫什麼 LIKE 王%」未說明每筆是訂單或商品明細。`v_order_summary` 與排名第 1 的 `v_sales_detail` 都有對應欄位，將相同 QueryPlan 分別套入兩個 View 都能編譯；結果粒度及毛利意義不同。目標 View 排第 6，屬需求粒度歧義。 |
| `ORDER_SUMMARY-M1-05` | 需求含精確欄位名 `cost_amount`，但檢索文件刻意移除欄位名稱，連描述中的同名文字也會替換成「欄位」，因此失去強烈的識別訊號。其餘「折扣後總金額、商品總件數、日期」在多個 View 描述中重疊，目標排第 5。 |
| `PRODUCT_MONTHLY-S2-04` | 需求用「折讓金額」，契約描述用「折扣金額」；目前字面檢索缺少這組同義詞。需求也未指定商品或月份粒度，其他 View 的城市、折扣、銷量描述因而競爭，目標排第 5。 |

因此，12 題中有 8 題可由不只一個 View 合理承接或缺少粒度判定資訊；另外 4 題較像詞彙或技術識別碼的召回缺口。單純提高 top-k 可讓更多目標 View 進候選，但無法替使用者決定「日或月」、「訂單或明細」的口徑。

## 流程執行結果分類

依指定的既有執行紀錄分類；與上述離線排名分開統計。

| 分類 | 次數 |
|---|---:|
| `pass` | 39 |
| `retrieval_miss` | 3 |
