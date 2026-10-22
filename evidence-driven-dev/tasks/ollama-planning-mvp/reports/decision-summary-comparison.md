# GPT 與 DeepSeek 可見決策摘要比較

已新增獨立診斷型別 `ExplainedDecompositionDraft` 與 `ExplainedDecompositionResponse`，必填 `decision_summary`。六欄各限 1–600 字元，要求一至兩句可核對的決策及契約依據；原 v3 schema、預設流程與舊結果不變。

此欄位是模型自述的高層決策理由，不是私有思維鏈，亦不能證明模型內部先後順序。說明可能錯誤或不完整，驗證與 request 組裝只使用 typed 計畫，摘要不成為執行指令。

| 模型 | 呼叫 | 摘要完整 | Request ready | 原自動分 |
|---|---:|---:|---:|---:|
| gpt-6-sol | 3 | 3/3 | 3/3 | 3/3 |
| DeepSeek-V4.1-Flash | 3 | 3/3 | 1/3 | 0/3 |

三題11、14、26使用相同Chat Completions輸入；temperature=1、top_p=1、seed=42、context=16384、輸出上限4096、SDK retries=0，每題每模型一次，順序交替。六次共約64秒。這是新增摘要後的新版本觀測，不能將與歷史差異歸因為只多一欄。

GPT三題由主agent依既有獨立oracle核對為安全ready；DeepSeek只有14為ready，但有未核准額外計數及摘要缺漏，沒有將ready直接當嚴格語意全對。原sidecar的自由文字缺值政策與COUNT等價存在已知保守誤判，原分與診斷結果皆保留，未回寫追分。

## cross-view-11

對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。

**第一個可見差異**：source_selection：GPT排除無通路欄位的商品月表；DeepSeek仍選該表。

**GPT 判定**：安全ready；來源、九月online條件、兩金額、店商品鍵與庫存母體完整。

**DeepSeek 判定**：error；選v_product_monthly卻引用其不存在的sales_channel，欄位亦未列required_columns。

**摘要與計畫一致性**：DeepSeek摘要與typed filters都要求online，但所選來源沒有該能力；是契約依據錯誤，不能把摘要承諾當已完成條件。

| 摘要欄位 | GPT 原文 | DeepSeek 原文 |
|---|---|---|
| 來源選擇 | 庫存件數與盤點日期取自庫存 View；商品銷售明細 View 同時提供通路、折扣金額及淨銷售額。商品月度 View 沒有通路欄位，因此不足以單獨處理線上銷售。 | 目前庫存需用 v_inventory_status 保留所有庫存商品並取得 snapshot_date；線上通路折扣與淨銷售需用 v_sales_detail 或 v_product_monthly，因 v_daily_sales 無通路與商品欄位、v_order_summary 無商品欄位，選 v_product_monthly 可同時提供門市×月×商品的 discount_amount 與 net_sales。 |
| 欄位角色 | 庫存件數及盤點日期是每筆庫存的單值屬性；折扣金額與淨銷售額按門市商品加總。盤點日期保留為來源時間，不作銷售月份分組。 | 庫存任務以 store_id、product_id 為識別鍵，帶入 stock_qty、reorder_point、stock_status、snapshot_date 與商品屬性；銷售任務以 store_id、product_id、sales_month 為分組，sum(discount_amount) 與 sum(net_sales) 為度量，並收集 sales_month 作為來源月份 metadata。 |
| 條件與期間 | 僅銷售明細限定訂單月份為 2026 年 9 月、通路為線上；庫存來源不加篩選。 | 庫存任務不加期間篩選以保留所有目前庫存商品；銷售任務限 sales_month = 2026-09-01 且 sales_channel = 'online'，通路條件只套用於銷售來源。 |
| 根／子粒度 | 庫存契約以門市與商品識別碼組合唯一決定一列；銷售明細彙總至同一門市商品粒度後對照。 | 庫存依 v_inventory_status 契約為門市×商品，故 output_grain 為 store_id、product_id；銷售依 v_product_monthly 契約為門市×月份×商品，先限縮 2026-09 後同為門市×商品粒度。 |
| 保留母體 | 以所有庫存商品為母體；沒有匹配的期間及通路銷售資料時保留庫存列，銷售金額不自行填零。 | 以庫存門市×商品為母體並保留所有庫存商品，線上銷售未匹配者以缺值呈現，不補零；不將庫存快照日期跨日加總，並以 metadata 揭露日期。 |
| 整合方式 | 以 store_id、product_id 將已彙總的銷售結果左接庫存，兩側在整合時均為門市商品粒度；庫存盤點日期與歷史銷售期間分別呈現。 | 以庫存任務為 anchor，透過 store_id、product_id 左接銷售任務，使每個庫存商品保留其對應線上折扣與淨銷售；邊為庫存對銷售之多對一，銷售端已先按門市×商品彙總。 |

完整typed計畫、payload、原始說明與分數見本Task的 `.local/decision-summary-20261020T152551Z-3f8ec7/`，或[機器比較資料](decision-summary-comparison.json)。

## cross-view-14

以目前缺貨商品件數為零的庫存列，按店計算缺貨商品數，對照 2026 年 9 月營收目標；保留有庫存資料的所有門市，缺貨數用條件計數。

**第一個可見差異**：field_roles／grain：DeepSeek多輸出未要求的COUNT(stock_qty)，摘要未交代；另將來源鍵描述為店×商品×日期。

**GPT 判定**：安全ready；缺貨條件留在conditional_metrics，沒有全域filter刪母體；固定月份目標取原值。

**DeepSeek 判定**：ready；核心條件計數、店母體與日期metadata合理；多出未要求的一般COUNT(stock_qty)，未有用途核准，不宣稱整題嚴格語意全對。

**摘要與計畫一致性**：摘要未覆蓋額外一般計數，且來源契約鍵實為store_id/product_id，與其grain文字不同。stock_status=缺貨與stock_qty=0、COUNT與DISTINCT在真店商品唯一鍵下有既有等價依據。

| 摘要欄位 | GPT 原文 | DeepSeek 原文 |
|---|---|---|
| 來源選擇 | 庫存 View 提供商品庫存件數與盤點日期；門市月 KPI View 提供 2026 年 9 月營收目標。單一 View 不含兩者，因此使用兩個來源。 | 缺貨商品數需要 v_inventory_status 的 store_id、product_id、stock_status 與 snapshot_date；2026 年 9 月營收目標需要 v_store_monthly_kpi 的 sales_month、store_id、target_amount。其他 View 無目前庫存狀態或門市月目標欄位，因此不選用。 |
| 欄位角色 | 以 product_id 對 stock_qty＝0 的庫存列作條件計數；snapshot_date 收集為各店來源日期集合。月目標 target_amount 是固定月份的單值屬性，不作加總。 | 庫存任務以 store_id 為分組，條件計數 stock_status = 缺貨 的商品列，並以 snapshot_date 作 metadata_collections 揭露來源時間；目標任務以 sales_month 篩選 2026-09-01 後取 target_amount。目標金額是單一值，不作加總以外的聚合。 |
| 條件與期間 | 缺貨條件只用於庫存列的條件計數，不篩掉其他庫存列；sales_month＝2026-09-01 只套用於月 KPI 來源。 | 庫存條件為 stock_status = 缺貨，套用於 v_inventory_status；期間條件為 sales_month = 2026-09-01，套用於 v_store_monthly_kpi。庫存任務不先過濾掉非缺貨列，以保留門市母體並讓條件計數可表達零缺貨。 |
| 根／子粒度 | 庫存列依 store_id 彙總為每店一列；月 KPI 的 store_id、sales_month 唯一鍵在月份固定後也對應每店一列。 | 庫存任務原始 grain 為 store_id × product_id × snapshot_date，輸出前依 store_id 分組為每門市一列；目標任務來源 grain 為 store_id × sales_month，篩選 2026-09 後輸出為每門市一列。整合後輸出 grain 為 store_id。 |
| 保留母體 | 以有庫存資料的所有門市為母體，包含缺貨數為零的門市；沒有匹配月目標時保留門市並標記目標缺值。 | 以 v_inventory_status 有庫存資料的所有門市為保留母體，左接 2026 年 9 月門市月目標；未匹配目標的門市仍保留，target_amount 記為缺值，契約未保證不得填零。 |
| 整合方式 | 兩項結果以 store_id 一對一左連接，保留庫存門市；庫存已先按店彙總，不會因商品明細重複月目標。 | 以 store_id 作唯一對齊鍵，anchor_task 為庫存任務，透過 left join 將 2026 年 9 月目標附到每門市缺貨商品數；兩側輸出 grain 均為 store_id，因此為一對一，無需額外 nest、pivot 或 aggregate。 |

完整typed計畫、payload、原始說明與分數見本Task的 `.local/decision-summary-20261020T152551Z-3f8ec7/`，或[機器比較資料](decision-summary-comparison.json)。

## cross-view-26

比較各店 2026 年 9 月營收目標與當月線上、實體各通路訂單數及訂單金額；保留有當月 KPI 的所有門市。

**第一個可見差異**：conditions：GPT明列online/in_store；DeepSeek摘要明說不限制通路集合，typed filters亦無IN。

**GPT 判定**：安全ready；訂單級COUNT合法，明示兩通路集合，按店pivot後保KPI母體與缺值。

**DeepSeek 判定**：error；漏使用者指定雙通路限制；pivot準備使用子查詢沒有的sales_month鍵，且兩側月份欄位無已核准mapping。

**摘要與計畫一致性**：摘要與typed計畫一致地漏通路限制，均違反需求；摘要稱按月份完成pivot，實際準備鍵不合法。

| 摘要欄位 | GPT 原文 | DeepSeek 原文 |
|---|---|---|
| 來源選擇 | 月營收目標取自門市月 KPI View；通路訂單數與金額取自每筆已完成訂單一列的訂單摘要 View，單一 View 無法同時提供所需資料。 | v_store_monthly_kpi 提供每門市每月營收目標，v_order_summary 提供每筆已完成訂單的門市、月份、通路、訂單數與訂單金額，兩者足以比較目標與線上／實體通路表現。 |
| 欄位角色 | KPI 的 target_amount 為單值屬性；訂單以 order_id 計數、order_amount 加總，並以 sales_channel 區分通路。 | store_id 與 sales_month 為分組及輸出識別鍵；target_amount、order_id、order_amount 為度量；sales_channel 用於 pivot 成通路欄位，不作為長期資料時間而保留。 |
| 條件與期間 | 兩個來源各自篩選 2026 年 9 月；訂單來源另限使用者指定的 online 與 in_store 通路。 | 兩個來源皆篩選 2026-09 月份：KPI 用 sales_month = 2026-09-01，訂單用 order_month = 2026-09-01；不額外限制通路集合，保留線上與實體之原始通路值。 |
| 根／子粒度 | KPI 契約在門市與月份組合上唯一，固定月份後為每門市一筆；訂單先彙總至門市與通路，再整理為每門市一筆。 | kpi_target 為每門市每月一列，channel_orders 為每門市每月每通路一列；最終輸出粒度為每門市每月一列，對齊契約鍵 store_id 與月份。 |
| 保留母體 | 以有 2026 年 9 月 KPI 的所有門市為母體。沒有匹配訂單或特定通路資料時保留缺值，不推定為零。 | 以有 2026 年 9 月 KPI 的門市為母體，left join 後保留所有此類門市；未匹配到通路訂單時標記缺值，不自行補零。 |
| 整合方式 | 先依 store_id 將通路結果橫向整理，再左接至 KPI 門市；避免通路列重複門市月目標。 | 以 store_id 與月份將 channel_orders 左接至 kpi_target，先將通路訂單依 store_id、月份、sales_channel 彙總，再 pivot 為線上、實體欄位，避免原始訂單列與 KPI 一對多膨脹。 |

完整typed計畫、payload、原始說明與分數見本Task的 `.local/decision-summary-20261020T152551Z-3f8ec7/`，或[機器比較資料](decision-summary-comparison.json)。

## 驗證紀錄

六筆raw→診斷draft→response→payload／原分／sidecar均在fresh subprocess重播一致，同題messages完全相同，原兩個v3 schema SHA256未變。新增五項測試涵蓋摘要必填、原schema相容、摘要不改payload、不合法計畫不因說明而放行、context無oracle；相關回歸86 passed。

未增加模型重試、未查DB、未產生或執行SQL、未呼叫Ollama。DeepSeek完整Gate仍未通過。
