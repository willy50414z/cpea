# 銷售來源選擇理由：模型追加回覆

原需求：對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。

依使用者要求，GPT 與 DeepSeek 各追加一次詢問，提供原需求、完整七個 View 契約與各自上一份原始回覆；沒有提供另一模型輸出或評分回饋。兩模型使用相同問題與契約，但各自看到的上一份回覆不同。

這是事後的簡短決策說明，不是首次生成時的內部思維紀錄。原計畫、ready 狀態與原分數沒有更新；DeepSeek 承認問題不計為首次成功。

## 共同追加問題

> 請針對上一份規劃中你選擇的銷售來源，提供簡短、可核對的選擇理由：哪些需求與View契約支持此選擇？v_sales_detail與v_product_monthly的適用差異為何？所選來源能否滿足指定線上通路條件？如有不足請明說。僅說明原選擇，不重做規劃或修改原輸出；不要求私有逐步思維鏈。

## 模型原文

### gpt-6-sol

**原選擇**：`demo_retail.v_sales_detail`

**選擇理由**：原規劃選用此 View，因需求須按門市、商品對照 2026 年 9 月線上通路的折扣金額與淨銷售額；它同時提供對應識別碼、月份、通路及兩項金額欄位。

**契約依據**：

- 需求指定「各店各商品」及「2026 年 9 月線上通路」。
- v_sales_detail 具有 store_id、product_id、order_month 與 sales_channel；sales_channel 的 online 代表線上。
- v_sales_detail 的 discount_amount 為明細折扣金額，net_sales 為折扣後銷售金額，且僅含已完成訂單。
- v_inventory_status 以 store_id、product_id 為列鍵，提供 stock_qty 與 snapshot_date，可作為保留所有庫存商品的對照母體。

**另一來源比較**：v_product_monthly 已是門市×月份×商品粒度，也有 discount_amount、net_sales，適合不區分通路的月度商品統計；但契約沒有 sales_channel，無法單獨限定線上。v_sales_detail 是訂單商品明細，雖須彙總至門市×商品，卻能先依月份及 online 篩選。

**能否滿足線上通路條件**：能

**限制**：所選來源只涵蓋已完成訂單明細；沒有匹配銷售列時，不能僅憑此 View 證實銷售金額為零。庫存的 snapshot_date 是盤點日期，目前庫存不可解讀為 2026 年 9 月的歷史庫存。

### DeepSeek-V4.1-Flash

**原選擇**：`demo_retail.v_product_monthly`

**選擇理由**：原規劃的促銷任務 t_online_promo 指定用於 2026 年 9 月、以門市×商品粒度彙總折扣金額與淨銷售額，而 v_product_monthly 的粒度正是門市×月份×商品，且具備 sales_month、store_id、product_id、discount_amount、net_sales 等欄位，能直接以月份篩選後聚合至門市×商品，因此原選擇此 View 取得折扣金額與淨銷售額。

**契約依據**：

- v_product_monthly 粒度：門市×月份×商品，鍵為 store_id、sales_month、product_id
- v_product_monthly 含 discount_amount（折扣金額合計）與 net_sales（折扣後銷售額）兩個 measure
- v_product_monthly 含 sales_month 欄位（當月第一天），可用於篩選 2026 年 9 月
- v_product_monthly 的 net_sales 契約明示適合跨門市彙總商品營收
- v_product_monthly 不含 sales_channel 欄位，契約未提供通路維度

**另一來源比較**：v_sales_detail 粒度為每筆已完成訂單的每個商品明細，具備 sales_channel、quantity、discount_amount、net_sales，可精確表達線上通路並自行彙總至門市×商品×月份；但它是明細層，需求只要月度門市×商品的折扣金額與淨銷售額，v_product_monthly 已是對應粒度且已內建 discount_amount 與 net_sales，無須再自行聚合明細，故原規劃選擇 v_product_monthly 較直接。

**能否滿足線上通路條件**：不能

**限制**：原規劃的促銷任務僅以 sales_month = 2026-09-01 篩選，未能表達線上通路條件：v_product_monthly 契約未提供 sales_channel 欄位，故無法在 filters 中限定 online，該需求的線上通路條件未被滿足；此點已於原輸出的 decision_summary.conditions 與 decision_chain 第 3 步承認。若要真正滿足通路條件，契約上有 sales_channel 的 v_sales_detail 才是可行來源，但這不改變原選擇的事實。

## 核對結果

GPT 自述優先確保月份、通路、金額等需求均能表達；DeepSeek 自述月表粒度貼近需求且較直接，但承認缺通路欄位而未滿足需求。事後理由不能證明首次內部思考或因果。

契約確認 `v_sales_detail` 有 `order_month`、`sales_channel`、`discount_amount`、`net_sales`；`v_product_monthly` 有月份及兩項金額，但沒有 `sales_channel`。原 DeepSeek typed filters 只有月份，仍不符合指定通路。

兩次追加呼叫均取得有效 JSON；fresh subprocess 核對 request、raw、schema 解析、前次輸出與 artifact hash 一致。temperature=1、top_p=1、seed=42、輸出上限1536、context=16384、SDK retries=0；合計約12秒。沒有重做規劃、SQL／DB／Ollama 呼叫。

本輪只新增診斷詢問腳本與報告，未修改產品模型或規則。完整模型文字見[機器資料](source-selection-reasons.json)，原始 request／call／result 位於本 Task 的 `.local/source-reasons-20261020T155003Z-1cfda9/`。
