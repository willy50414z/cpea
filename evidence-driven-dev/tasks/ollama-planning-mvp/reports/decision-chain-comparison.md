# 模型自填 decision_chain 比較

已新增診斷型別 `DecisionChainDecompositionDraft` 與 `DecisionChainDecompositionResponse`，必填 `decision_chain`，由模型自行填寫。原有四個 schema 與預設流程不變。

六個節點各涵蓋來源、欄位角色、條件、粒度、母體及整合一次。每節點包含 `step_id`、`stage`、`decision`、`evidence`、`task_ids`、`depends_on`；程式驗證步號連續、引用真實 task、依賴只指向前置節點。依據是否正確仍須核對需求與契約。

這是有序的公開決策紀錄，不是私有思維鏈，也不證明模型內部思考順序。決策文字及摘要只保存在診斷 response，不參與驗證判斷或下游 request 組裝。

## 測試背景與目的

對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。

使用第 11 題確認 GPT 與 DeepSeek 是否能各填寫一次有效紀錄，並核對自述、typed 計畫及下游 payload 的一致性；不是完整語意 Gate。

兩模型各一次，相同 messages／schema／七個 View 契約；Chat Completions、temperature=1、top_p=1、seed=42、context=16384、輸出上限4096、SDK retries=0。輸入估計10711 tokens，連同輸出與安全預留15831，符合16K。兩次合計約31秒。

## 測試結果

| 模型 | 六節點結構 | Runtime | 原自動分 | 主 agent 語意核對 |
|---|---|---|---|---|
| gpt-6-sol | 完整有效 | ready | PASS | SAFE |
| DeepSeek-V4.1-Flash | 完整有效 | ready | FAIL | UNSAFE |

source_selection：GPT 選 v_sales_detail；DeepSeek 選缺少通路欄位的 v_product_monthly。

安全 ready：來源具通路欄位，九月與 online 條件完整，折扣與淨銷售額按店商品加總，以庫存母體 left join；保留盤點日期、不跨日加總、不填零。

不安全 ready：conditions 節點明說所選 View 無通路欄位，typed filters 也只有月份；卻仍生成 ready 與兩筆 prepared requests。

子任務 request 與整合 notes 仍宣稱線上通路，但實際送往下游的 typed payload 缺 sales_channel 條件，所選來源亦無該欄位。

DeepSeek 在第 3 節點寫道：「線上通路條件因 View 契約無通路欄位而無法以 filters 表達。」此紀錄與實際 filters 都揭露需求未滿足，卻與 ready 狀態及 request 的線上通路承諾矛盾。

GPT 原 sidecar 因自由文字 missing_data_policy 仍標記需獨立審核；主 agent 核對完整缺值文字及契約後判安全。原 sidecar 和自動分完整保留，沒有回寫。

## 完整模型紀錄

### gpt-6-sol

| 步號／類別 | 模型決策原文 | 模型依據原文 | Task 引用 | 前置節點 |
|---|---|---|---|---|
| 1 / source_selection | 選用庫存狀態與銷售明細兩個 View。 | 「各店各商品目前庫存件數」<br>v_sales_detail 含 sales_channel、discount_amount、net_sales | inventory, online_sales | [] |
| 2 / field_roles | 逐筆呈現庫存件數及盤點日期，並加總銷售折扣金額與淨銷售額。 | v_inventory_status.stock_qty、snapshot_date<br>v_sales_detail.discount_amount、net_sales | inventory, online_sales | [1] |
| 3 / conditions | 只對銷售明細套用 2026 年 9 月及線上通路條件。 | 「2026 年 9 月線上通路」<br>v_sales_detail.order_month、sales_channel | online_sales | [1] |
| 4 / grain | 庫存維持逐店逐商品，銷售彙總至相同粒度。 | v_inventory_status 唯一鍵為 store_id、product_id<br>「各店各商品」 | inventory, online_sales | [1, 2] |
| 5 / population | 完整保留庫存商品，不將未匹配銷售資料視為零。 | 「保留所有庫存商品」<br>v_sales_detail 僅含已完成訂單的商品明細 | inventory, online_sales | [3, 4] |
| 6 / integration | 以門市及商品識別碼左接銷售彙總至庫存列。 | 兩個 View 均有 store_id、product_id<br>「對照」且「保留所有庫存商品」 | inventory, online_sales | [4, 5] |

### DeepSeek-V4.1-Flash

| 步號／類別 | 模型決策原文 | 模型依據原文 | Task 引用 | 前置節點 |
|---|---|---|---|---|
| 1 / source_selection | 選擇 v_inventory_status 取得門市×商品庫存件數，v_product_monthly 取得 2026 年 9 月各店各商品折扣金額與淨銷售額。 | 對照各店各商品目前庫存件數<br>v_inventory_status 粒度：門市×商品<br>v_product_monthly 欄位含 discount_amount、net_sales、sales_month、store_id、product_id | t_inventory, t_online_promo | [] |
| 2 / field_roles | 庫存以 store_id、product_id 分組並保留 stock_qty 為屬性、snapshot_date 為時間 metadata；促銷以 discount_amount 與 net_sales 做 sum 聚合，sales_month 僅作篩選欄位。 | 目前庫存件數<br>stock_qty 為 measure<br>discount_amount 為 measure<br>net_sales 為 measure | t_inventory, t_online_promo | [1] |
| 3 / conditions | 僅對促銷任務設定 sales_month = 2026-09-01；庫存任務不加篩選，且線上通路條件因 View 契約無通路欄位而無法以 filters 表達。 | 2026 年 9 月<br>v_product_monthly 欄位 sales_month<br>v_product_monthly 契約無 sales_channel 欄位 | t_inventory, t_online_promo | [1] |
| 4 / grain | 兩任務輸出粒度皆為 store_id、product_id；促銷任務先聚合至門市×商品月彙總，庫存任務維持門市×商品唯一鍵。 | 各店各商品<br>v_inventory_status 鍵：store_id、product_id<br>v_product_monthly 鍵：store_id、sales_month、product_id | t_inventory, t_online_promo | [2] |
| 5 / population | 以庫存任務為母體保留所有庫存商品；促銷未匹配資料標記缺值，契約未保證時不填零。 | 保留所有庫存商品<br>v_inventory_status 包含門市×商品庫存列<br>missing_data_policy：保留未匹配資料並標記缺值 | t_inventory, t_online_promo | [1, 4] |
| 6 / integration | 以 t_inventory 為 anchor，對 t_online_promo 以 store_id、product_id 做 left join 且 preserve_task 為 t_inventory，不將促銷彙總再依商品加總。 | 各店各商品<br>v_inventory_status 與 v_product_monthly 皆含 store_id、product_id<br>left join 的 preserve_task 必須是 left_task | t_inventory, t_online_promo | [4, 5] |

## 驗證與限制

兩筆原始輸出在 fresh subprocess 重播：artifact hash、凍結來源／契約／題文／messages、六節點、response、payload、自動分與 sidecar 均一致；四個既有 schema SHA256 不變。相關回歸 96 passed，涵蓋缺節點、無效依賴／引用、空白依據，以及說明不得改變 payload 或放行不合法計畫。

驗證由同一主 agent 依既有獨立 oracle 與契約核對，未新增跨 agent 審查。模型自述可能不完整或錯誤，結構通過不代表語意正確；本輪每模型只有一題，不能推論整體成功率。

完整 typed 計畫、原分、診斷與紀錄見[機器比較資料](decision-chain-comparison.json)。原始 request／call／result 保存在本 Task 的 `.local/decision-chain-20261020T153804Z-eea260/`，未更動原始輸出。

離線驗證沒有新增模型呼叫；本輪共兩次首次呼叫、零重試，沒有 SQL／DB／Ollama 呼叫。DeepSeek 完整 Gate 仍未通過。
