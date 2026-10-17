# Retail View Matching Benchmark 覆蓋報告

契約指紋：`e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc`。Profile 狀態：`approved`；題目仍須人工審核後才能計入正式成績。

QueryPlan 與 Builder 支援升冪、降冪排序、`COUNT(DISTINCT column)` 及單欄聚合的 HAVING。JOIN 與跨欄位算式目前不在本次功能實作範圍。

| View | S L1/L2/L3 | M L1/L2/L3 | H L1/L2/L3 | 邊界 | 額外案例 | 合計 | 自動驗證 | 待審 | 核准 | 退回 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `demo_retail.v_customer_value` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 2 | 57 | 57/57 | 57 | 0 | 0 |
| `demo_retail.v_daily_sales` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 1 | 56 | 56/56 | 56 | 0 | 0 |
| `demo_retail.v_inventory_status` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 1 | 56 | 56/56 | 56 | 0 | 0 |
| `demo_retail.v_order_summary` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 1 | 56 | 56/56 | 56 | 0 | 0 |
| `demo_retail.v_product_monthly` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 1 | 56 | 56/56 | 56 | 0 | 0 |
| `demo_retail.v_sales_detail` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 2 | 57 | 57/57 | 57 | 0 | 0 |
| `demo_retail.v_store_monthly_kpi` | 5/5/5 | 5/5/5 | 5/5/5 | 10 | 2 | 57 | 57/57 | 57 | 0 | 0 |

## 尚未解決的 Coverage Gap

- 跨會員平均每筆訂單消費額（`RETAIL-CUSTOMER_VALUE-G-01`）與跨門市整體毛利率（`RETAIL-STORE_MONTHLY_KPI-G-01`）需要分別彙總分子、分母再相除；QueryPlan／Builder 尚不支援跨欄位算式，目前各保留一題拒絕案例。支援後需改為可編譯的正常案例並重新審核。
- JOIN 與跨欄位算式目前不在本次功能實作範圍；同欄位雙界限日期篩選仍由產題規則追蹤。

## 已解決並保留驗證的項目

- 九宮格每個 View 的 S/M/H × L1/L2/L3 均為 5 題，沒有缺題。
- 降冪排序已支援；七個 View 各有一題 `ORDER BY DESC` 正常案例。`v_sales_detail` 另有一題 `COUNT(DISTINCT order_id)` 正常案例。
- HAVING 已支援單欄聚合結果與數值門檻比較，七個 View 的 `B-09` 均為正常案例，並驗證未顯示在 SELECT 的指標。
- 固定涵蓋期間、固定庫存快照日期及 `sold_qty_30d` 的固定截止日期已從契約移除，相關舊案例不再產生。
- 審核後的 YAML 宣告 `v_sales_detail` 以 `(order_id, product_id)` 作為複合鍵；`--check` 驗證目前資料沒有重複，舊的『唯一鍵未確認』拒絕案例已移除。

## 人工審核

- 新產題預設 `review_status=pending`；L3、邊界與額外案例優先核對口語語意、拒絕理由及契約假設。
- 題目自動驗證檢查 MATCH_PROMPT 模型形狀與名稱約束、原文片段、欄位／聚合／運算子、九宮格及 SQL 編譯；無法證明自然語言只有唯一合理解讀，也不執行題目 SQL。

## 重跑

在專案根目錄執行 `uv run --locked python -m evaluations.retail_view_benchmark` 重新產生；使用 `uv run --locked --extra postgres-contracts python -m evaluations.retail_view_benchmark --check` 以唯讀資料庫連線檢查目前資料的唯一鍵，並驗證既有檔案與契約仍一致。
