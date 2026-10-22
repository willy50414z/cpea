# Markdown 高優先規則與第二 DeepSeek 證據審查

已依要求新增兩份實際 Markdown system prompt。規劃器第一區塊是「最高優先規則：完整涵蓋需求」，其後才是角色、契約政策與決策紀錄；模型輸出仍為 JSON。審查器第一區塊則要求決策必須有完整證據。

- 規劃 prompt：`evaluations/prompts/coverage_first_planner.md`
- 審查 prompt：`evaluations/prompts/evidence_reviewer.md`
- 實驗版本：`v3-md-priority-review-1`

## 本輪流程

第 11 題：對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。

第一個 DeepSeek 以 Markdown system 生成原始計畫。既有程式照原規則驗證及準備 request，不因自述或審查而放行。第二個 DeepSeek 使用新 client、全新兩則訊息的對話，收到同一需求、完整七個 View 契約、第一份原始計畫與可用的 prepared requests，逐項檢查缺少證據的決策；不提供 GPT 答案、oracle、自動分或 validation_errors，不自動重寫計畫。

兩次均為 DeepSeek-V4.1-Flash，temperature=1、top_p=1、seed=42、context16384、輸出4096、安全預留1024、timeout300秒、SDK retries=0。規劃輸入估計11150、審查10505 tokens，均符合16K；兩次合計約33秒。沒有第三次自動修正呼叫。

## 規劃結果：仍失敗

規劃器仍選 `v_product_monthly`。與前次漏掉通路條件不同，本輪在 required_columns、filters 及 group_by 中加入該來源不存在的 `sales_channel`；decision_chain 第1與第3項也將它寫成契約證據。

第1項 evidence 原文包含：

> v_product_monthly columns: discount_amount, net_sales, sales_channel

這項契約引用不成立。原始草稿為 ready，既有驗證器回傳 `error`／`invalid required columns`，沒有產生任何下游 prepared request。Markdown 及優先規則沒有令本題通過，原始分數完整保留。

## 第二 DeepSeek：reject，抓到核心缺證據決策

審查回傳7項 checks、3項 findings（2 blocking、1 advisory），整體判定 `reject`。第一項 blocking 對應來源與條件決策（step 1、3）：

> 任務在 v_product_monthly 過濾 sales_channel=online，但該契約 View 沒有任何 sales_channel 欄位

它要求具備可支援指定通路的契約來源及實際條件，並指出 `v_sales_detail` 是可核對的替代能力依據。這項拒絕由原始契約、typed 計畫及先前核准 oracle 支持，不是只接受審查器自述。

審查器也有品質限制，不能把全部 findings 當作成立：

- 第二項 blocking 額外懷疑門市識別碼語意，沒有提出獨立契約證據，不採為新增阻擋理由；核心線上條件問題已由第一項涵蓋。
- 盤點日期未保證全球最新，應揭露資料時間；但來源已以門市×商品組合唯一，不可推成同店商品有多筆日期資料，也不應自動加日期篩選刪母體。
- 部分路徑使用 task_id 索引簡寫，`planner_output.notes` 並非實際頂層路徑，另有 step_id 與陣列索引混用。引用檢查只保證 task_id、step_id 存在，尚不保證文字路徑完全精確。

因此分開記錄：**規劃 FAIL；審查抓到核心問題，PASS_WITH_WARNINGS**。沒有將 reject 計為生成正確或首次通過。

## 驗證與限制

新增3項測試：審查不得在已有缺漏時 approve，以及不得引用不存在的 task／決策節點；相關回歸99 passed。兩筆 raw、解析、response、自動分／sidecar、審查、prompt/schema/source hash 與輸入重建均由 fresh subprocess 核對一致。原v3預設與四個舊schema不變。

同一主 agent 依既有獨立 oracle 與完整契約驗證，未新增跨 agent 驗收。這是同一模型的不同對話，不是獨立真值來源；一題一次也不能評估審查誤拒率或證明改為 Markdown 的因果效果。主 DeepSeek Gate 仍未過，不擴題或轉 Ollama。

完整原始計畫、所有審查 checks／findings 見[機器資料](markdown-evidence-review.json)，raw 位於本 Task 的 `.local/markdown-review-20261020T161155Z-4d197a/`。本輪只有兩次新 DeepSeek 呼叫，沒有 SQL／DB／Ollama 或重試。
