# Retail 跨 View 需求測試矩陣

本題庫包含 30 個跨 View 需求：28 題使用兩個來源、2 題使用三個來源，涵蓋全部 7 個現有 View。只驗收到需求拆分、View／欄位選取與 text-to-sql request 準備。未生成或執行 SQL，尚未呼叫 Azure GPT。

契約指紋：`e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc`。所有案例的人工審核狀態為 `pending`，目前不作為人工核准的正式 benchmark 成績。

## 案例與預期來源

| 案例 | 需求 | 預期主要 View | 合併鍵 |
|---|---|---|---|
| cross-view-01 | 依各店各商品目前庫存件數及 2026 年 9 月銷售件數，準備補貨優先評估資料；保留所有庫存商品，暫不計算採購量。 | `v_inventory_status` + `v_product_monthly` | `store_id`, `product_id` |
| cross-view-02 | 以各店各商品目前庫存件數及 2026 年 9 月折扣後銷售額，準備補貨營收影響評估；保留所有庫存商品。 | `v_inventory_status` + `v_product_monthly` | `store_id`, `product_id` |
| cross-view-03 | 比較各店各商品目前庫存成本估值與 2026 年 9 月毛利，準備採購資金配置評估；保留所有庫存商品。 | `v_inventory_status` + `v_product_monthly` | `store_id`, `product_id` |
| cross-view-04 | 用各店各商品目前庫存，搭配 2026 年 8 月與 9 月各自的銷售件數，準備補貨趨勢評估；保留所有庫存商品。 | `v_inventory_status` + `v_product_monthly` | `store_id`, `product_id` |
| cross-view-05 | 比較各店各商品分類目前庫存成本估值與 2026 年 9 月分類淨銷售額，準備分類採購評估；保留庫存中的所有分類。 | `v_inventory_status` + `v_product_monthly` | `store_id`, `category` |
| cross-view-06 | 比較各區域目前庫存成本估值與 2026 年 9 月商品毛利總額，準備區域採購配置評估；保留有庫存資料的區域。 | `v_inventory_status` + `v_product_monthly` | `region` |
| cross-view-07 | 依各店各商品目前庫存與 2026 年 9 月線上通路銷售件數，準備補貨評估；保留所有庫存商品。 | `v_inventory_status` + `v_sales_detail` | `store_id`, `product_id` |
| cross-view-08 | 依各店各商品目前庫存與 2026 年 9 月實體門市通路銷售件數，準備補貨評估；保留所有庫存商品。 | `v_inventory_status` + `v_sales_detail` | `store_id`, `product_id` |
| cross-view-09 | 列出各店各商品目前庫存，並對照 2026-09-01 至 2026-09-14 各有銷售日期的商品銷售件數；保留所有庫存商品。 | `v_inventory_status` + `v_sales_detail` | `store_id`, `product_id` |
| cross-view-10 | 依各店各商品目前庫存及 2026 年 9 月 VIP 會員購買件數，準備 VIP 商品補貨評估；保留所有庫存商品。 | `v_inventory_status` + `v_sales_detail` | `store_id`, `product_id` |
| cross-view-11 | 對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。 | `v_inventory_status` + `v_sales_detail` | `store_id`, `product_id` |
| cross-view-12 | 比較各店目前庫存成本估值總額及 2026 年 9 月營收、月目標，準備門市資金配置資料；保留有庫存資料的門市。 | `v_inventory_status` + `v_store_monthly_kpi` | `store_id` |
| cross-view-13 | 比較各店目前庫存成本估值與 2026 年 9 月營收達標率，準備庫存投入評估；保留有庫存資料的門市。 | `v_inventory_status` + `v_store_monthly_kpi` | `store_id` |
| cross-view-14 | 以目前缺貨商品件數為零的庫存列，按店計算缺貨商品數，對照 2026 年 9 月營收目標；保留有庫存資料的所有門市，缺貨數用條件計數。 | `v_inventory_status` + `v_store_monthly_kpi` | `store_id` |
| cross-view-15 | 比較各店目前庫存成本估值與 2026 年 9 月門市毛利率、客單價，準備營運評估；保留有庫存資料的門市。 | `v_inventory_status` + `v_store_monthly_kpi` | `store_id` |
| cross-view-16 | 依會員註冊城市，對照每位會員累計消費與 2026 年 9 月各通路訂單數及消費金額；包含未下單會員。 | `v_customer_value` + `v_order_summary` | `customer_id` |
| cross-view-17 | 列出 2026 年 8 月註冊會員的註冊日期、註冊城市，搭配其 2026 年 9 月線上訂單數與金額；保留這批會員中沒有線上訂單的人。 | `v_customer_value` + `v_order_summary` | `customer_id` |
| cross-view-18 | 列出每位會員的註冊城市與最近 90 天是否活躍，並對照其 2026 年 9 月實體通路訂單數；包含未下單會員。 | `v_customer_value` + `v_order_summary` | `customer_id` |
| cross-view-19 | 列出每位會員註冊城市、累計消費與 2026 年 9 月各交易門市的訂單金額；包含未下單會員。 | `v_customer_value` + `v_order_summary` | `customer_id` |
| cross-view-20 | 列出每位會員註冊城市、累計消費，以及其 2026 年 9 月各商品購買件數；包含未下單會員。 | `v_customer_value` + `v_sales_detail` | `customer_id` |
| cross-view-21 | 列出每位會員註冊日期與最近 90 天是否活躍，搭配其 2026 年 9 月各商品分類淨銷售額；包含未下單會員。 | `v_customer_value` + `v_sales_detail` | `customer_id` |
| cross-view-22 | 列出註冊城市為台北市的每位會員及累計消費，搭配其 2026 年 9 月線上通路各商品購買件數；保留沒有購買的會員。 | `v_customer_value` + `v_sales_detail` | `customer_id` |
| cross-view-23 | 列出各店 2026 年 9 月營收目標，搭配當月各商品銷量與淨銷售額；保留有當月 KPI 的所有門市。 | `v_store_monthly_kpi` + `v_product_monthly` | `store_id` |
| cross-view-24 | 只看 2026 年 9 月被標記為完整月份的門市，列出門市月目標及各商品分類毛利；保留符合條件的所有門市。 | `v_store_monthly_kpi` + `v_product_monthly` | `store_id` |
| cross-view-25 | 比較各店 2026 年 9 月營收目標及當月各商品分類的折扣金額、淨銷售額；保留有當月 KPI 的所有門市。 | `v_store_monthly_kpi` + `v_product_monthly` | `store_id` |
| cross-view-26 | 比較各店 2026 年 9 月營收目標與當月線上、實體各通路訂單數及訂單金額；保留有當月 KPI 的所有門市。 | `v_store_monthly_kpi` + `v_order_summary` | `store_id` |
| cross-view-27 | 比較各店 2026 年 9 月營收目標及當月 VIP 會員的線上訂單金額；保留有當月 KPI 的所有門市。 | `v_store_monthly_kpi` + `v_order_summary` | `store_id` |
| cross-view-28 | 依各店各商品目前庫存成本估值、2026 年 9 月商品毛利及該店同月營收目標，準備採購資金配置評估；保留所有庫存商品，門市目標作門市背景資料。 | `v_inventory_status` + `v_product_monthly` + `v_store_monthly_kpi` | `store_id`, `product_id` |
| cross-view-29 | 依各店各商品目前庫存、2026 年 9 月線上銷售件數及該店同月營收目標，準備線上補貨評估；保留所有庫存商品，門市目標只作背景。 | `v_inventory_status` + `v_sales_detail` + `v_store_monthly_kpi` | `store_id`, `product_id` |
| cross-view-30 | 比較各店目前庫存成本估值總額，並附上 2026 年 9 月各有銷售日期的門市每日營收；保留有庫存資料的所有門市。 | `v_inventory_status` + `v_daily_sales` | `store_id` |

## View 覆蓋

| View | 作為主要來源的題數 |
|---|---:|
| `demo_retail.v_customer_value` | 7 |
| `demo_retail.v_daily_sales` | 1 |
| `demo_retail.v_inventory_status` | 18 |
| `demo_retail.v_order_summary` | 6 |
| `demo_retail.v_product_monthly` | 10 |
| `demo_retail.v_sales_detail` | 9 |
| `demo_retail.v_store_monthly_kpi` | 11 |

## 預期答案與評分界線

- 每題 JSONL 均包含預期子任務、主要 View、必要欄位、filters、彙總方法、輸出粒度、合併方式、缺值處理與整合注意事項。
- `required_columns` 是必要欄位集合，不要求回覆只含這些欄位；額外欄位需合法且有用途，不能忽略必要欄位。
- `acceptable_alternatives` 明列可接受的等價來源與欄位映射，例如商品月表可用銷售明細在相同條件下彙總替代；canonical 命中率與等價方案正確率分開報告。
- 子任務順序不影響評分。拆成多個 request 仍須保留業務條件、期間、分組粒度和整合鍵。
- 三來源題的 `expected_integration.keys` 是商品事實合併鍵；`required_steps` 另明列門市 KPI 只依 `store_id` 附加，不能以不存在的商品欄位合併。
- 庫存快照是目前資料，不能當作九月歷史庫存，也不能跨日期或商品列重複加總門市背景數值。
- 第 14 題要求在所有庫存門市上條件計數缺貨商品；只先篩選缺貨列再分組會漏掉零缺貨門市。
- 彙總題 05、06、12、13、14、15、30 將盤點日期明列 `metadata_collections`，表示每組完整 DISTINCT 日期集合；不能任取單一日期、誤加為業務分組或把混合日期宣稱為同日庫存。欄位的跨日禁止加總仍適用。
- 第 26 題 canonical 與銷售明細替代方案明列 `sales_channel IN [online,in_store]`，契約沒有保證通路域只含這兩個值；條件 pivot 的零值／缺值差異尚未無條件納為等價。
- 替代來源僅列已知等價方案；未列的合法新方案需要獨立審核，不能只因不符合 canonical 就斷言模型錯誤。
- 現階段自動檢查只證明案例數量、欄位／聚合合法與契約覆蓋，不能證明模型拆分能力或資料數值正確。
