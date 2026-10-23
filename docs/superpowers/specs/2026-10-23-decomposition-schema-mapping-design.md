# 需求與資料來源證據對照設計

狀態：使用者已核准方案 A（候選證據對照）、獨立入口及前置 View 篩選，保留原流程。核准及追加日期：2026-10-23。

## 目標與現況

先以前置檢索篩選候選 View，再將需求拆解為可追溯的語意單位，逐一與候選 View 的全部欄位契約比對；保留有證據的候選，由第二次全域審核決定來源，最後產生既有 `DecompositionDraft`。整體仍是規劃流程，不生成或執行 SQL。

現有 `task_decomposition/workflow.py` 的流程為載入全部契約、一次 LLM 產生草稿、程式驗證、準備單 View requests。`DecompositionDraft` 與 `prepare_requests` 已能表達多來源、整合粒度及保留母體，因此應重用。`text_to_sql/schemas.py`、`semantics.py` 已有原文區間和契約引文概念，但限定單 View 的 SQL clause；不宜直接套用它們的模型或整段驗證器。

現有使用者修改的 `prompt.py` 與未追蹤 `prompt.md` 必須保留。新階段提示詞另置檔案；草稿階段仍使用既有提示詞並加入經審核的來源限制。

主代理已執行既有四組單元／整合測試，結果為 66 passed；這只代表現行基準。本研究未執行實際模型呼叫。

## 已確認範圍

使用者已指定：「先新增獨立入口，保留原流程」。新增 `SchemaMappingDecompositionWorkflow` 與 `SchemaMappingDecompositionService.plan(request)`；現有 `TaskDecompositionService` 與一次呼叫流程保持原樣，共用末段 `validate_decomposition`／`prepare_requests`。新流程失敗不得靜默回退舊流程。現有 workflow／service／tests／evaluation 全部不改，新入口新增專用測試。

## 兩個可行方案

### A：逐 View 比對、保留稀疏候選，推薦

前置檢索後抽取需求，再對每個候選 View 各呼叫一次 LLM。每次提供全部需求單位、該 View 完整欄位與 View 層契約；每個單位都須回傳有證據的候選，或明確的無匹配／不適用結果。程式檢查所有候選 View 都跑過、每個單位都有結果、候選欄位與引文有效，之後由一次全域審核選定來源，再產生草稿。

若檢索後候選 View 數為 C，正常完成需 C+3 次 LLM 呼叫：需求抽取 1、比對 C、審核 1、草稿 1。前置篩選本身不新增 LLM 呼叫，可以逐 View 分攤 context，保留多來源競爭與二次審核。

限制：這能保證每個候選 View 的所有欄位都被提供給模型、每個需求與候選 View 都有回覆，但不能證明模型實際逐欄思考；不會為所有不匹配欄位逐格輸出拒絕理由。被前置篩選排除的 View 不進行逐詞比對，必須在 trace 清楚列出。

### B：完整需求 × View × 欄位判定矩陣

每個需求單位與每個欄位都回傳 `supported`、`rejected` 或 `uncertain`，附理由；支持時另附原文／契約證據。仍按 View 分批並二次審核，必要時依欄位區塊再分批，且每批帶入完整 View 層約束。

優點是程式能檢查每個組合都有明確判定，適合使用者要求保存「每個欄位為何接受／拒絕」的情境。代價為 O(需求數 × 欄位總數) 的輸出，容易觸及目前 8,000 token 類型的輸出設定；分批又提高呼叫次數、延遲與跨欄位比較困難。正常呼叫為 B+3，其中 B 是比對批次數。

推薦 A：現有需求重點是候選映射的證據與後續審核，可先用完整契約曝光及需求／View 回覆完整性滿足。若「逐欄比對」明確包含每個拒絕組合的可稽核輸出，則應選 B，不能把 A 的完整性宣稱為 B。

## 推薦流程與資料契約

`載入契約 → 前置候選 View 檢索 → 抽需求 → 驗證需求 → 逐候選 View 比對 → 驗證候選 → 全域審核 → 驗證審核 → 產生 DecompositionDraft → 跨階段驗證及既有驗證 → prepare_requests`

### 前置候選 View 篩選

重用既有 `SchemaRetriever` 的 lexical/vector、rerank 與 `select_with_ties`；不修改原檢索檔。既有 retriever 對明列欄位使用「同一 View 必須具備全部欄位」限制，不適用多來源。因此新 adapter 只在檢索查詢移除已辨識欄位識別碼，完整原文仍交給抽取與後續各階段；再依原文強制補回明列 View 與各明列欄位的所屬 View。多個 View 不拒絕，也不取欄位交集。

限定 `View.column` 只釘其合法所屬 View；未限定欄位若跨 View 同名，保留全部可能所屬來源。單引號資料、比較／LIKE 右值、IN 值區間不作來源指令，避免值剛好含 View 名而擴大候選。

預設 soft cutoff 為 `max(5, settings.rerank_top_k)`，可用新入口 `view_limit` 調整；`retrieval_k` 仍控制既有第一階段。保留精確 cutoff ties，明列來源也可超出上限，不作破壞召回的硬截斷。trace 記錄檢索查詢、候選分數／入選理由、排除 View、soft limit 與延遲；未回傳來源分數未知時不偽造。重用篩選會有 recall 限制，隱含需求來源可能被排除；零分同分或模糊欄位也可能保留大量來源，不能承諾固定候選上限。

service/workflow 支援 `retriever` 注入以離線測試。空候選為 `unsupported/empty_retrieval`，retrieval 例外或未知來源／非有限分數為乾淨 `error/retrieval_error`；保留失敗 trace，不 retry、不呼叫後續模型。預設依設定可能使用外部 embedding/reranker，驗證一律注入 fake 或使用離線 lexical。

### 需求單位

每個單位包含穩定 ID、原文 `start/end/text`、類型、必要性，以及相關需求 ID。區間使用 Python Unicode 字元索引，必須滿足 `request[start:end] == text`。保留完整限定詞，不將「目前庫存件數」縮成「件數」。重複用詞依區間區分。

類型至少分為資料概念、時間／值條件、輸出粒度、母體保留、業務目的、禁止行為。語意單位可以重疊，例如「2026 年 9 月銷售件數」包含期間與指標的關係；不要求空白或字元級斷詞。

範例需求應保留：各店、各商品、目前庫存件數、2026 年 9 月銷售件數，以及「保留所有庫存商品」、「準備補貨優先評估資料」、「暫不計算採購量」。最後三項分別是母體、用途、否定約束，不應強迫映射成 `stock_status`、`reorder_point` 或任意採購欄位。日期值本身也不是欄位，須連到銷售期間需求後再決定日期欄。

抽取結果另列語法／連接詞及標點區間，供程式檢查非空白字元是否都有業務或語法分類；語法區間也須保留原文片段，不能用一個任意 `ignored` 欄位跳過全文。字元覆蓋能偵測未分類空隙，但不能證明語意抽取正確：整句粗略標為一個概念、誤將否定列為語法，都可能覆蓋全文。因此覆蓋只是必要檢查之一，不將無空隙宣稱為所有必要關鍵字完整。

### 單 View 候選

每個需求 ID 對應 `matched`、`unmatched` 或 `constraint_only` 結果。資料候選包含 View、column、用途、理由，以及非空契約引文。證據以結構化路徑定位，如 `columns.stock_qty.description`、`time.rules[0].description`；程式驗證引文確實出現在同一份契約該路徑，不能只驗證任意完整 JSON 中有相同文字。

View 層 `scope`、`time`、`grain`、`usage` 與 `metrics` 都可能提供支持或反證，不能只把欄位描述給 LLM。非欄位約束可引用 View 契約；沒有支援的目的或禁止事項可以保留為約束，不因找不到欄位直接判定需求不支援。

候選 View 的比較順序由 catalog 決定。任何候選 View 的 provider／解析／預算失敗都停止，不把尚未比較當作無匹配。候選未被全域審核選定前不得派送。

### 全域審核

輸入原始需求、已驗證單位、全部候選，以及候選所屬 View 完整契約。審核必須先重新閱讀完整原文，回傳帶 `start/end/text` 的遺漏或錯誤分類需求，不能只聲稱已抽清單皆涵蓋。之後才回傳最終來源與欄位、採納候選 ID、拒絕理由，以及適用的母體／時間／否定約束處理方式。

若審核發現必要詞遺漏，本次不得產生 ready 草稿；第一版以明確內部錯誤及遺漏片段結束，避免增加未設上限的模型迴圈。不能把新補詞直接加入來源審核繞過逐 View 比對。未來若要自動修補，必須讓補詞重新通過全部 View 比對與審核，另訂最大輪數及呼叫成本。抽取與審核仍可能共同漏判，這是語意驗證限制，須由反例和實際模型驗收補足。

審核只能採納已有證據的候選；需要 join key 或盤點日期等輔助欄位時，也必須引用契約證據，明列支援的整合／時間需求，不能在草稿階段自行擴充。必要資料概念無候選為 `unsupported`；有候選但語意衝突、條件未明為 `needs_clarification`；格式、引文或階段引用無效則是錯誤，不混作業務不支援。

同一必要指標允許多個等價來源候選，審核選定其中一套。不能為增加候選命中率而把不相容時間、粒度或母體的欄位一起放入最終來源。

### 草稿及跨階段限制

產生草稿時帶入原需求、全部約束、核准來源／欄位及其完整契約。保留 `DecompositionDraft` 現有格式。新入口使用專用回應模型，保留既有 status/draft/prepared_requests 契約並增加 trace：需求 span、候選證據、審核決定／遺漏及各階段狀態；既有公開模型不改。observer 保存原始模型呼叫，回應 trace 不含憑證或原始 provider 錯誤。

草稿每個 `required_columns`、filter、metric、grain、metadata 與整合 key 都必須在審核 allowlist，所有必要資料需求都須連到實際任務欄位。僅驗證候選後仍讓草稿任選 catalog 欄位，會失去這次流程的意義。

母體保留等結構化決定須與 integration 對照：例如審核選定庫存母體，anchor 必須是庫存任務，邊須保留該母體；期間決定須能追溯到對應 filter。禁止計算採購量須保留為目的限制，且不得生成該項任務／指標。任意自然語言業務限制仍無法全部由 allowlist 證明，不能把這些檢查宣稱為完整語意驗證。

## 範例的實際契約風險

- `v_inventory_status.sold_qty_30d` 固定為 2026-09-15 至 2026-10-14，不能回答 2026 年 9 月銷售件數；即使字面相近也須拒絕此用途。
- `v_product_monthly.units_sold` 配合 `sales_month`，或 `v_sales_detail.quantity` 配合 `order_date`／`order_month`，都可能支援九月銷量；後者須聚合至門市商品，不能因來源較細就判為錯誤。
- 庫存 `snapshot_date` 未保證全部資料同日或最新，不可把「目前」變成未獲契約支持的全表最新日，也不能跨不同快照加總庫存。
- 保留所有庫存商品意味著以庫存為母體附接銷售；不能 inner join 排除無銷量商品，也不能自行將銷售缺值當成零。
- 門市／商品名稱可作顯示維度；join 應使用有契約支持的識別碼。既有驗證只允許同名且同型別的跨來源 key，本次沿用，不新增跨名映射能力。

## 完整性驗證的界線

程式可確定：來源是否存在、所有檢索候選 View 是否比較、每個需求是否回覆、區間是否精確、契約引文是否原文、候選與審核是否閉合、草稿是否使用核准欄位，以及已結構化粒度／母體／時間決定是否一致。不能對被前置排除的來源宣稱已完成逐詞比對或所有必要來源皆召回。

程式不能單憑引文存在確定其支持語意；真實引文也可能是否定句或描述其他期間。不能證明 LLM 未漏抽概念、正確分類否定約束、真的比較每個欄位，或第二次審核獨立於第一次錯誤。方案 B 只提高判定紀錄的完整性，仍不能證明判定正確。必須以正反案例與實際模型證據補足。

## 檔案接點與相容性

| 接點 | 建議變更 |
|---|---|
| 新增 `src/cpea/workflows/task_decomposition/schema_mapping_workflow.py` | 獨立 workflow、新階段與早停；沿用 schema binding、provider 設定及 observer |
| 新增 `src/cpea/application/services/schema_mapping_decomposition.py` | 獨立 service；現有 service／workflow 不變 |
| 同目錄新增 `mapping_models.py`、`mapping.py`、`mapping_prompts.py` | 中間模型、原文／引文／完整性／跨階段檢查、新提示詞；實際拆檔以最小實作為準 |
| 同目錄新增 `mapping_retrieval.py` | 重用排名、多來源識別碼補回、ties／排除 trace；原 retriever 不改 |
| 同目錄既有 `validation.py` | 原樣重用；新 mapping 模組先執行跨階段驗證 |
| 新增 `src/cpea/application/models/schema_mapping_decomposition.py` | 新入口專用回應及 trace；既有 decomposition 模型不變 |
| 新增專用測試 support | 依階段回覆的 fake，重用現有 catalog fixture；既有固定 draft fake 不改 |
| 新增 `tests/unit/test_schema_mapping_decomposition.py` | 測試各階段及 C+3 calls；現有一次呼叫測試完整保留 |
| 新增 `tests/unit/test_schema_mapping_retrieval.py` | cutoff ties、跨來源明列欄位、複數 View、literal 排除、錯誤與召回限制 |
| 既有 `evaluations/decomposition_runner.py`／`decomposition_reports.py` | 保持不動；既有一次呼叫 metadata 與 regrade 不代表已驗新 mapping 流程 |

`observer` 目前每筆 event 都被既有 runner 計為一次 LLM 呼叫；本次不將新入口接入該 runner。新入口每次 provider invoke 都帶 `stage`，比對階段另帶 View／批次識別，保留 usage/error 欄位；非模型檢查放在專用回應 trace。未來若另行整合 benchmark，須先處理事件計數，並記錄所有階段 prompt/schema 雜湊，不能只沿用舊單一 prompt metadata。

每次呼叫前各自算 context，超出不截斷契約。公開 `context_tokens` 若保持單一數值，建議定義為單次 context 峰值；總 token 用量保留在 observer／評估彙總，避免誤把累計輸入與單次 context 上限相比。單 View 契約或全域審核仍可能超窗，第一版可明確錯誤，不能宣稱逐 View 已解決所有規模問題。

正常 C+3 次並不表示每個需求都一定跑滿：檢索／抽取失敗、預算不足或業務不可支援可提前結束。provider rate limit 不 retry、不繼續後續 View；保留既有私人錯誤紀錄與帳號額度規則。這次設計不授權額外雲端呼叫或提高既有額度。

## 分階段驗收

1. **需求／證據節點**：固定輸入測試精確區間、重複文字、完整限定詞、日期與指標關聯；目的／否定／母體不被強制欄位化。測試漏 View、漏需求、假欄位、跨 View 引文、空引文、錯 path、真實但期間相反的引文；測試審核能回報抽取階段遺漏的詞與 span，且不能直接 ready。覆蓋全文但錯把否定當語法須有反例。語意正確性不能只靠字串檢查宣稱可判斷。
2. **審核到草稿整合**：固定分階段 fake 驗證選用 monthly 或 detail 的等價方案皆可；拒絕無核准來源／輔助欄位、遺漏必要需求、庫存母體被改成銷售、期間被丟失、否定目的新增採購任務。所有失敗皆不暴露 prepared requests。
3. **完整流程回歸**：跑現有四組 66 項基準及新增 focused tests；確認每階段 budget、provider 錯誤、parse 錯誤都早停且零 retry；驗證實際 invoke 次數、trace 與 prepared requests 的來源一致，秘密資訊未外洩。現有 runner 30／90 calls 和 regrade 零呼叫斷言保持原樣。
4. **驗證限制**：本次未授權雲端 benchmark，實際模型語意與成本未驗證。後續若另獲授權，建議先測庫存＋九月銷量及固定窗口反例，檢查需求到草稿完整鏈。實作可完成結構／流程驗證，但不得將 fake 通過宣稱為真實模型語意已通過。

獨立入口與方案 A 均已確認，依此產生實作計畫並執行。方案 B 僅保留為已比較替代方案。既有私有 prompt 修改不得覆寫。
