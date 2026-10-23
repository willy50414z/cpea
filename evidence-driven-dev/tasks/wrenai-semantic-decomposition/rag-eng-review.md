# WrenAI 獨立需求拆分：RAG 與工程計畫審查

日期：2026-10-23。狀態：**DONE_WITH_CONCERNS／issues_open**。這是設計審查，沒有核准或實作任何候選修改。

## 審查依據與執行限制

- 唯一目標：[設計草案](../../../docs/superpowers/specs/2026-10-23-wrenai-semantic-decomposition-design.md)，基準 CPEA `ab4c67a`；不是 branch diff。
- 實際使用使用者指定的 `/home/willy/code/gstack/.agents/skills/gstack-plan-eng-review/SKILL.md`，gstack `VERSION=1.58.5.0`，skill SHA-256 `70401ca36d2d6ebef37de3a037b0ffcdf777538ddfd5aa35a67810f8a05c71a8`。
- 指定 skill 目錄沒有 `sections/review-sections.md`；已另外實讀同安裝根目錄的 `/home/willy/code/gstack/plan-eng-review/sections/review-sections.md`，包含 Architecture、Code Quality、Tests、Performance、Outside Voice 與輸出規範。沒有拿另一個同名 skill 冒充指定版本。
- 已讀 AGENTS、父 Task、DEC-001/002、research、設計，以及下列提及的 CPEA／pinned 官方程式碼。遵守 spawned 模式：不重問已選 review target、不跑 onboarding、upgrade、telemetry、routing injection；建議自動提出，但不視為使用者採納。
- 使用官方 pinned [WrenAI 原始碼](https://github.com/Canner/WrenAI/tree/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service)，下載到 `/tmp/rag-review-wrenai-ce9ed54/` 逐行核對。以下 `upstream/...` 均指該 SHA 的 `wren-ai-service/...`，不是 main。
- 沒有安裝、連 DB、呼叫真模型、讀 secrets、改產品／測試／原設計／既有題庫／TODOS／CLAUDE、commit 或 push。未再次執行父流程已成功的 113 項 baseline。
- 本 agent 就是 Main 委派的 fresh-context outside reviewer；沒有再派 agent，沒有執行額外跨模型 CLI，故**無跨模型共識證據**。略過可能同步／上傳 artifact 的 skill preamble；本地 review metadata 使用隔離的 `~/.gstack/` 子目錄且停用同步。

結論：真實 WrenAI v1＋隔離 worker 是符合已決定範圍的可行方向，無理由改回既有 LangGraph planner。但目前有 **3 個 P1 接入契約缺口、4 個 P2 同階段補齊項目**。P1 應在設計核准時明列處置；不代表已證實真模型品質差，也不代表要重開「以 WrenAI 為主」的決定。

## Step 0：Scope Challenge

### What already exists

| 子問題 | 既有實作與證據 | 建議處置 |
| --- | --- | --- |
| Draft／Response／多 View 整合契約 | `src/cpea/application/models/decomposition.py:24`、`:47`、`:66`、`:81` | 直接重用，保留介面 |
| 欄位、能力、型別、grain、整合驗證與 request 準備 | `src/cpea/workflows/task_decomposition/validation.py:22`、`:206` | 直接重用；不宣稱能證明原需求完整 |
| 全契約 prompt budget | `src/cpea/workflows/task_decomposition/workflow.py:54` 至 `:60` | 重用 budget 原則與 token-counter 邊界，不重用其語意 planner |
| 多來源顯式 identifier 候選保留 | `src/cpea/workflows/task_decomposition/mapping_retrieval.py:19`、`:51` 至 `:65` | 只作測試風險參考；本輪不偷偷併入新 flow |
| 計畫等價評分／case fingerprint／人工核准 | `evaluations/decomposition_grading.py:30`、`evaluations/decomposition_cases.py:13`、`:50` | 可重用基礎，需本輪節點不變量與負向 mutation |
| observer／model req-res 時間 usage | `workflow.py:65` 至 `:77` | 參考 artifact 欄位；不能覆蓋 WrenAI transport 的原始資訊 |
| 真實 indexing／intent／retrieval／provider | pinned upstream 類別 | 原生執行；新 DraftPlanning 是必要輸出 extension |

### 最小正確範圍與複雜度

最小可交付是：一條 `.plan()` 新入口、結構 MDL adapter、真實 upstream schema/index/retrieval、DraftPlanning、既有 validate/prepare，以及能證明呼叫來源與 trace 的離線整體路徑。不需要第二個語意 planner、另一個模型 reviewer 或正式 benchmark。

計畫至少涉及 adapter、worker client／server、DraftPlanning、trace/evaluator 等多個邊界，觸發 skill 的「2+ 新 class/service 或 8+ files」scope gate；此處是設計推估，不冒稱已存在的檔案數。spawned 模式下完成完整審查，將 scope 決策交 Main，而不擅自縮減：**推薦先核准修訂後設計，把第一個驗收切在零模型的真實 upstream＋專用 Qdrant 整合 spike；後續再完成離線 Oracle/replay，正式題庫與真模型維持原本門檻。**保留常駐 worker 作現有提案，不新增服務或改成其他架構。

[Layer 1] 已查官方 Python asyncio subprocess／gather、Qdrant collection aliases 與 Poetry 非 package 模式；已有標準能力足夠，不需要自建排程器／交易服務／package registry。repo 根目錄未找到 `TODOS.md` 或 `CLAUDE.md`，因此沒有可引用的額外 eval pattern 或工時壓縮係數；本報告工時僅為 reviewer 粗估。近期 `ab4c67a`、`2e673d4` 已碰過 decomposition 與 v4 契約，故特別檢查重用契約是否把語意缺漏錯判通過。

### NOT in scope

- 修改兩條既有 flow、引入混合語意 planner：使用者要求保留，混合待原生測量後另議。
- MDL 業務詞典、synonyms、memory、歷史 SQL／問題索引：第一階段排除。
- SQL generation／執行／Engine instance：本輪只輸出 Draft；允許 upstream 必要模組 import。
- 代建正式 benchmark、修改既有 pending Oracle 或其 fingerprint：正式題庫由使用者提供。
- 公開 worker wheel／container 發布、CI release、部署及授權法律判斷：本輪本地研究；但**本機可重現 bootstrap／啟動命令不能省略**。
- 真模型調優、ANN recall 成績、可靠性 SLO 與費用保證：沒有 runtime／使用者資源授權，不能先作結論。

## 1. Architecture Review

### F1 [P1]（confidence: 10/10）專用 collection 尚無可實現的原生 provider 接入邊界

**精確證據：**設計 `:53`：「Qdrant 使用此流程專用 collection」，`:67` 要求 index namespace／manifest；但 [upstream `src/providers/document_store/qdrant.py:386`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/providers/document_store/qdrant.py#L386) 接受後忽略額外 kwargs，`:394` 至 `:400` 會建立六個固定 dataset 的 store，`:411` 的 collection 選擇是 `index=dataset_name or "Document"`。兩條原生 pipeline 直接呼叫 `get_store()` 與 `get_store(dataset_name="table_descriptions")`。

因此，僅在設定塞 `namespace`／`collection` 不會隔離；若連到共用 Qdrant，仍接觸 `Document`、`table_descriptions`、`view_questions`、`sql_pairs`、`instructions`、`project_meta`。**`_reset_document_store` 本身只是建構 store，預設 `recreate_index=False`，不是已證明會清空六個 collection。**實際資料刪除另見 F3；不得因函式名稱誇大破壞性。`SHOULD_FORCE_DEPLOY` 的 bool 環境值又可能啟用 recreate，需顯式固定 false，不能繼承未知 worker 環境。

**影響：**新舊索引可共用固定名稱，或 constructor 先碰到不預期的 collection；違反草案的隔離承諾，單靠 project filter 無法隔離不同 embedding dimension 的 collection。

**1A，推薦 [Layer 1]：**明示一個窄 provider namespace adapter／subclass，所有 logical dataset 都映射至本流程實體 collection，保留原生 Qdrant store/retriever；人約 2–4h／agent 約 30–60m，維護成本是小型 provider 契約測試。

**1B：**使用專用 Qdrant instance，接受固定 dataset 名並封鎖 recreate／共享 endpoint；人約 1–2h／agent 約 20–40m，多維護一個本機資源。

選項差異是架構種類，不以假造完整度分數比較；兩者均保留真 WrenAI。驗證：mock store constructor 盤點全部 names，再以兩個 manifest／兩組 dimension 的本機 Qdrant 證明讀寫互不影響、共用 sentinel 不變；不是只檢查 metadata 字串有 namespace。

### F2 [P1]（confidence: 10/10）欄位裁剪結果會先被靜默改寫，最後的 Draft validator 看不到原始錯誤

**精確證據：**設計 `:89` 啟用 pruning、`:97` 承認 validator 只保結構；[upstream `src/pipelines/retrieval/db_schema_retrieval.py:349`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/retrieval/db_schema_retrieval.py#L349) 只 `orjson.loads`，`:357` 把同 table 名覆寫，`:366` 只處理已知 table；[upstream `src/pipelines/common.py:40`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/common.py#L40) 以 `not columns or ...` 選欄。

已用原始函式 AST extraction 零網路 microprobe 確認：`columns=[]` 輸出**所有欄位**；`columns=[missing_metric_xyz]` 輸出空 `CREATE TABLE`，unknown identifier 不再出現在下游；同來源重複 item 亦不是集合合併。這不同於草案已承認的「模型可能漏必要欄位」：本問題是**模型實際選了什麼會被 adapter 改寫，raw selection 與 rendered schema 的 Oracle／precision 無法等同**。

**影響：**unknown-column fixture 可能未觸發想測的錯誤；下游 Draft 重新選到合法欄位後，final validator 可通過，但 pruning node 已違約。不能把最終合法性倒推成上游合法性。

**2A，推薦 [Layer 1]：**在原生 renderer 前做 deterministic selection contract 檢查，驗 table/column 存在、重複與空集合政策；同時保存 raw selection、rendered DDL、model-name mapping 供 Oracle，比較時把合法 auxiliary keys 分開；人約 2–4h／agent 約 30–60m，Completeness 10/10，維護低。

**2B：**僅保留 raw output 並讓 evaluator 事後 FAIL；人約 1h／agent 約 15m，Completeness 6/10，runtime 仍可能送出被靜默改寫的 context。

推薦 2A 是 explicit boundary validation，不是第二個語意 planner，不強行補齊模型漏掉的來源。不得自動改成舊 planner fallback。測試應直接使用真實 upstream renderer，覆蓋 empty／unknown-only／known+unknown／duplicate table／unknown table，確認錯誤 node 可定位且無 Draft model 呼叫。

### F3 [P2]（confidence: 9/10）兩類索引缺少共同的 ready／failed 發布契約

**精確證據：**設計 `:67` 說不相容就重建、`:87` 說相同 manifest 可重用；[upstream `src/pipelines/indexing/db_schema.py:327`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/db_schema.py#L327) 先 cleaner，再於 `:333` writer；[upstream `src/pipelines/indexing/table_description.py:106`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/table_description.py#L106) 也是獨立 clean/write。[upstream `src/pipelines/indexing/__init__.py:41`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/__init__.py#L41) 在 project_id 為空時用 `filters=None`。

**情境：**DBSchema 寫完但 TableDescription 寫入失敗／worker 退出，下次啟動只見同 manifest，就可能重用一半新、一半舊或空索引。常駐 worker 序列處理可避免單 worker 內並行讀寫，但無法解決 crash recovery 或第二個本機 worker。

**3A，推薦 [Layer 1]：**MVP 使用 generation manifest 的 building→ready／failed，鎖住同 namespace writer，兩類索引 documents/count/content digest 核對成功後才 ready；未 ready 拒讀且允許重建本流程索引；人約 2–3h／agent 約 30–45m，Completeness 10/10，無須新增交易服務。

**3B：**每次啟動重建且禁止重用；人約 1h／agent 約 15m，Completeness 7/10，額外 embedding 成本且仍需拒讀半成品。

如果未來需要不停機切換，Qdrant 已有 [原子 aliases 切換](https://qdrant.tech/documentation/faq/qdrant-fundamentals/)，本地序列 MVP 不必先做藍綠架構。測試：第二類寫入前／中途失敗、兩 worker 同 namespace、空 project_id、manifest digest 偽一致；不得清共用 sentinel。

### RAG 決策：已核對但不另造缺陷

- **Intent 是否必要：**pinned intent 是 SQL intent classifier，不是需求抽取器；其 prompt 要求足夠生成可執行 SQL，可能對前置規劃過早拒絕，這是需測量的 gate 風險，不是假裝已重現誤拒。草案已規定原 request 保留、不採 fallback classification、GENERAL 等回 clarification/unsupported。推薦正式題庫到位後量測 intent 的 false rejection，另作診斷性 observation-only 比較；本輪不擅自停用原生 intent。
- **真實資料傳遞：**兩個 `.run()` 回傳 Hamilton final-node dict，應分別從 `post_process`、`construct_retrieval_results` 解包；不能把整個 dict 當 DraftPlanning schema。原需求傳給 retrieval；重述只作附加 evidence。Intent `wren_ai_docs=[]`、histories/sql_samples/instructions 空、明示 Configuration；不載入 memory。
- **多來源 recall：**本 checkout 7 Views、欄位數 10/9/15/17/14/23/14，在 upstream batch=50 時共 14 schema chunks。原生 retrieval 預設 table top_k=10，intent 為 50，兩者 column chunks 為 100；**此 retail 沒有證據顯示 top_k 必然排掉第 2/3 來源**。但排名仍為 table-description embedding，不是 column inverted index；空候選、未完整成對的 TABLE/TABLE_COLUMNS、同名欄位歧義必須測。
- **名稱／型別：**結構 MDL model 而非 MDL view 的決定正確；以 reversible map 回 CPEA qualified view，禁止直接 `split('.')` 推測來源。型別必須固定數值 target（例如 NUMERIC）並保持原 contract type，不把複合 grain 假充單 PK。未證實必須有 refSql 才能走這些 indexing 路徑，故不以 Engine 級 MDL 要求誤報。
- **完整 context／keys：**下游唯讀 context 必須包含所選 View 的完整 grain/scope/time/usage/column capability 與 integration key 所需欄位，而不只是 pruned DDL；request 裡的 filter-only 欄位與 implicit keys 分開度量。草案 `:66`、`:97` 已允許這些 keys，本輪不把已承認的自然 retrieval 語意限制重報 bug。

## 2. Code Quality Review

### F4 [P1]（confidence: 10/10）在 provider 外層錄製不足以達成每次 transport attempt 的 raw response／usage

**精確證據：**設計 `:103`、`:105` 要每次真正呼叫的原始 req/res、`:109` 第一失敗立即 flush；[upstream `src/providers/llm/litellm.py:157`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/providers/llm/litellm.py#L157) 先 `check_finish_reason(response)`，`:161` 回 `extract_braces_content(message.content)`，所以 provider 外層看到的不是完整 completion，finish error 時更拿不到正常回傳。[upstream `src/providers/embedder/litellm.py:115`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/providers/embedder/litellm.py#L115) 以 `asyncio.gather` 同時送 document batches，`:129` 至 `:135` 才彙總 usage。

已用原始 `_embed_batch` AST extraction＋fake transport 證明：一 batch 失敗、gather 已回 error，另一 batch 仍能完成。Python [官方 gather 契約](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.gather) 也明定 sibling 不會因首個 exception 自動取消。因此「worker 每 request 序列」不等於「每 model transport 序列」，batch 成功成本會在彙總前消失，甚至 run 已標失敗後仍有費用／response。

**4A，推薦 [Layer 1]：**在窄 policy patch 一併明定 LiteLLM completion／embedding 呼叫前後的 local transport recorder；模型原始 response 在 finish-check／JSON extraction 前落盤，每個 batch attempt 有 call_id/batch_id、實際 provider metadata、terminal/unknown 狀態與立即 flush，價格另行從版本化來源估算；人約 4–6h／agent 約 1–2h，Completeness 10/10，維護成本為一個 pinned transport seam。

**4B：**只在 get_generator/run 外面 observer，缺值標 unknown；人約 1–2h／agent 約 20–30m，Completeness 5/10，不能宣稱 A3「每個實際呼叫均有證據」完成。

驗證 transport mock 返回 leading/trailing text、finish_reason=length、usage missing、Azure deployment≠SKU、兩 batch 成功／一成功一失敗／中途取消；以呼叫 ledger 對上每一 attempt，不能只驗最終 totals。retry patch 需連 LiteLLM/SDK/Router fallback 一起固定；沒有 fallback_model_list，禁止結果不明時自動重送。rate limit 保留輸出交 quota.py，不能繼續批次重試。錢／usage 不可為未知值填 0。

### F5 [P2]（confidence: 8/10）worker timeout 與 cancellation 尚未定義「結果不明」及排空規則

**精確證據：**設計 `:53` 列「timeout、取消與正常關閉」，又稱「序列處理 MVP，避免跨 request trace 汙染」；`:109` 要逐 node flush，但尚未交代 cancel 已送出而模型已扣費／response 在路上的處置。這是**待補協定契約，不是已實作 deadlock 的指控**。

**情境：**父程序 timeout 後立刻送下一 run；舊 run 的 completion 或 stdout terminal 晚到。如果只靠「當前 request」關聯，就會把 late response 貼到新 run；若 stderr pipe 沒持續 drain，上游大量 logging 可阻塞 worker。[Python 官方 subprocess 文件](https://docs.python.org/3.12/library/asyncio-subprocess.html) 說明 PIPE 不排空可能 deadlock，不能用 wait 代替輸出處理。

**5A，推薦 [Layer 1]：**明定 accepted/running/terminal、cancel_requested/cancelled/unknown_outcome；terminal exactly-once、late event 按 run/call ID 封存、cancel grace 後 terminate/kill/reap，完成排空／重啟前不接下一 run；stdout/stderr 並行 drain、line/payload/queue 有上限、寫 stdin 要 drain；人約 3–4h／agent 約 45–60m，Completeness 10/10，無需多工排程器。

**5B：**先只支援一 run 結束後退出的診斷 spike，再補常駐生命週期；人約 1–2h／agent 約 20–30m，Completeness 6/10，會延後原設計常駐 worker 驗收，須使用者另選，這裡不採用。

run error 不代表模型未計費；unknown_outcome 要算已發送 attempts，費用完整性為 incomplete。安全 request 的去敏應包括上游 exception/URL/error repr，不只 auth headers；raw private artifact 與公開 summary 邊界沿用原設計。

組織上推薦 adapter、worker protocol、DraftPlanning、recorder、evaluator 各一責任；從既有 validator／case loader 重用，避免複製另一套 Draft model。產品新路徑尚未存在，沒有已寫新 code 的 DRY 問題可宣稱。worker protocol／generation manifest 應在未來實作處附 ASCII state diagram。

## 3. Test Review

### F6 [P2]（confidence: 9/10）離線 test store 門檻不足以驗原生 Qdrant，Oracle 亦需負向 mutation 防止假 PASS

**精確證據：**設計 `:132` 的首階段是「原生 chunker→test store」，`:133` 主要為可控 provider fixture；這能驗 DAG 與 Draft，但無法驗 F1 的真實 namespace／Qdrant filter/scroll／dimension 或 F3 清寫行為。`evaluations/decomposition_grading.py:68` 對 metrics 使用 `all(... for ... expected...)`、`:69` 對 conditional metrics 也是 expected subset，`:71` 對 metadata 亦為 subset；`:139` 只把幾個布林組成 automated_pass。

本輪 microprobe 已確認：多加一個不在 expected 的 SUM metric，`column_precision` 變 2/3，但 `_task_score` 所有 pass checks 仍 true。這不代表既有 grader 寫錯其原用途；代表**直接重用它不能證明新要求的「不憑空增加 measure／條件與母體不變」**。草案已說要額外 invariants，應把這個具體 mutation 列進驗收。

**6A，推薦 [Layer 1]：**零模型階段就加入真 upstream＋專用本機 Qdrant 整體測試（LLM/embedding transport 可 fake），另用 Oracle mutation 明確拒絕 extra measure、錯母體、跨來源 filter 錯置、錯缺值政策；人約 4–6h／agent 約 1–2h，Completeness 10/10，需本機 Qdrant 測試資源。

**6B：**保留 test store 階段但明確把結果標記「尚未完成真實 store integration」並延後完成主張；人約 30m／agent 約 10m，Completeness 5/10，整合風險會留到後面。

這些是必要契約／錯誤 fixture，不是替使用者建立正式 benchmark。retail 真 schema 必須直接來 catalog，不能拿 `tests/decomposition_support.py:15` 的四個 synthetic View 代替七個真 View；synthetic fixtures 可以繼續服務純函式單測。

### ASCII 資料流

```text
                              [planned: new flow]
retail catalog -- adapter --> MDL + reversible name map + manifest
       |                         |
       |                 namespace store provider [F1]
       |                         |
       |          +--------------+----------------+
       |          |                               |
       |      DBSchema                        TableDescription
       |      chunk/embed/clean/write         chunk/embed/clean/write
       |          +--------------+----------------+
       |                  building -> ready [F3]
       |                         |
request(original) --> IntentClassification -- parsed intent / nonready / error
       |                         |     (raw request never overwritten)
       +-----------------> DbSchemaRetrieval
                                 |
                         raw table/column selection
                                 |
                      deterministic boundary check [F2]
                                 |
       +---- selected View full contract + allowed keys
       |                         |
       +-----------------> DraftPlanning -> DecompositionDraft
                                 |
                        existing validate / prepare -> Response

each completion/embedding transport -> recorder [F4] -> private artifacts
worker protocol / cancellation [F5] -----------------> run/call ledger
evaluator-only Oracle -> node scores / regrade / replay; no edge to model
```

### ASCII coverage 圖

`EXISTING` 指既有測試與父 baseline，**不是新 worker coverage**；`GAP/planned` 表示尚未實作，`→E2E` 是零模型真整合，`→EVAL` 需使用者題庫與授權資源。沒有可據以計算的實際新 code branch 分母，因此不填 coverage 百分比。

```text
CODE PATHS                                           USER FLOWS
new plan(request) [GAP/planned]                       新流程提交需求 [GAP/planned]
  + preflight: blank/oversize/no catalog              + 無效輸入 -> error, model_calls=0
  + worker handshake/import source/env [GAP]          + 缺依賴/錯upstream SHA -> 可定位錯誤
  + schema adapter [GAP]                              + 七View/type/name碰撞 -> 拒絕
  + native indexing [GAP, ->E2E]                      + 同manifest重用 / 中途失敗後復原
  |   + two stores / dimension / project isolation    + 兩worker同時啟動 -> 不讀半成品
  + intent [GAP, ->EVAL]                              + 複雜合法需求不誤拒
  |   + valid enum / invalid JSON / parse fallback     + GENERAL/USER_GUIDE/MISLEADING_QUERY
  + retrieval + pruning [GAP, ->E2E, ->EVAL]           + 雙/三來源 + cross-source filters
  |   + empty / unknown / duplicate selection         + 歧義 -> clarification, 不亂猜
  |   + filter-only / implicit keys / legal extras     + 保留母體與背景附加
  + DraftPlanning [GAP, ->EVAL]                       + ready / nonready / malformed Draft
  + validate / prepare [EXISTING boundary]            + nonready不產payload [EXISTING]
  |   + new worker connection [GAP, ->E2E]             + 新worker自然輸出到prepared [GAP]
  + transport recorder [GAP]                          + 部分batch失敗仍保留已完成費用
  + timeout/cancel/crash [GAP, ->E2E]                 + 逾時後下一run不污染
  + Oracle/regrade/replay [GAP]                       + 零網路重播 / 版本drift拒絕
  + old flow compatibility [EXISTING: parent113]      + 舊兩flow介面與行為保留
```

### 具體測試契約與檔案候選

以下名稱只是實作計畫候選，沒有建立測試或變更產品檔案。

| 類型／檔案候選 | 輸入→必驗行為 |
| --- | --- |
| unit `tests/unit/test_wrenai_schema_adapter.py` | 真 retail 七 View／102 欄位完整、可逆名稱與碰撞、4 種型別、無 fake PK；原 policy 保持；空 catalog／unsupported type 拒絕 |
| integration `tests/integration/test_wrenai_native_pipeline.py` | 真 pinned 類別 import source＋DAG、真 Qdrant provider（或選定 namespace adapter）、fake transport；兩個 datasets 與 manifest 成對；相同 request 自然上游輸出流到 Draft，不塞金答案 retrieval |
| unit `tests/unit/test_wrenai_pruning_contract.py` | F2 五種 selection mutation；raw／rendered 差異能檢出；implicit grain/key 與 filter-only 欄位有明確允許集合；同名 city 要澄清 |
| integration `tests/integration/test_wrenai_index_lifecycle.py` | F1/F3 sentinel、project_id 空值、兩代 embeddings dimension、第二store寫入失敗、重啟、重複writer；未ready不查詢 |
| integration `tests/integration/test_wrenai_worker.py` | handshake mismatch、stdout額外文字／過大行、stderr超過pipe buffer、EOF/crash、timeout/cancel/late result、兩run順序、shutdown/reap；unknown outcome不自動重送 |
| unit `tests/unit/test_wrenai_transport_trace.py` | LLM raw completion在finish-check前保存；每embedding batch成功/失敗/取消都有attempt；超額／rate-limit只一次；費率缺失標unknown並留總額完整性 |
| unit `tests/unit/test_wrenai_node_oracles.py` | extra metric／extra conditional metric／漏filter／錯否定／期間邊界／母體／cardinality／缺值政策 mutation都失敗；合法日期改寫與輔助key集合可通過；nonready不用ready的integration條件 |
| integration `tests/integration/test_wrenai_replay.py` | fixture storage只給evaluator；model input sentinel確定無expected答案；regrade零模型；replay包含query/document embedding responses；upstream/patch/lock/Python/model/tokenizer/prompt/schema/input/catalog/index identity mismatch拒絕或明標drift |
| regression 既有5個focused檔案 | 父流程既有113 passed evidence；實作後用明確本checkout PYTHONPATH重跑，不能拿其他editable checkout結果 |

102 欄位來自本次 catalog introspection（10+9+15+17+14+23+14）；14 chunks 是 upstream column_batch_size=50 的推算，不是已執行索引結果。

### Oracle／合法替代與資料洩漏檢查

1. task equivalence 不採自由文字精確比對；替代集合須有人工核准與 fingerprint。extra helper keys、合法 date/month 等價、來源 grain singleton 證明應有獨立可核對理由；不能把所有 extra metrics 都當 precision 低但通過。
2. 不只驗每個來源欄位集合，還要驗 filter 屬於哪個 task、是否從條件計數錯升成全域 WHERE、left anchor 的母體、KPI 背景值沿商品重複加總、NULL 不擅改 0。
3. prompt full contract 是允許的 schema evidence；expected_tasks、acceptable alternatives、oracle notes、review結果不是 model context。用不同 sentinel 檢查 fixture metadata／recorded response resolver 不會把答案送進 request。
4. replay 不是只 mock LLM：本 flow 有索引及兩次 query embedding，需錄製／注入 embedding＋確定的 index snapshot/manifest；不然可能用新 embedding 找舊 index，卻宣稱重播。regrade 只重評舊輸出，不能把新prompt算成重新產生結果。
5. 正式題庫未提供，所以目前只提出契約測試，不宣稱語意成績或把建議六 sample 升格正式題庫。

## 4. Performance Review

### F7 [P2]（confidence: 9/10）三個 LLM node 尚缺完整 input＋output budget，原生 pruning 不會保證 context 裁短

**精確證據：**設計 `:93` 計了呼叫數，但 `:90` DraftPlanning 要原 request、intent、schema、契約，未定每 node context/output reserve；[upstream `src/pipelines/retrieval/db_schema_retrieval.py:283`](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/retrieval/db_schema_retrieval.py#L283) 只計 DDL tokens，超窗／enable pruning 後 `:311` 至 `:322` 仍把全部 retrieved DDL 放進 pruning prompt；不是真正截短器。Intent 沒有該 context budget 檢查。

本次 catalog 完整 context 約 25,150 字元，Draft JSON schema 約 5,208 字元，尚未含 system/request/intent/DDL；**字元數不是 token 數**。所以沒有證據此 retail 必超窗，也不能沿用 upstream 預設 context_window_size=100000 假設任何模型都適用。

**7A，推薦 [Layer 1]：**逐 node 使用實際 rendered system/user/response_schema計數，固定 provider實際context、輸出reserve與safety；超窗在transport前回明確error並保留model_calls=0，禁止靜默截 request/契約；finish_reason／截斷JSON保留raw response後判error；人約 2–3h／agent 約 30–45m，Completeness 10/10，重用既有 budget 原則。

**7B：**先配置足夠大的模型context再以provider error處理；人約 30m／agent 約 10m，Completeness 5/10，仍會產生可避免的費用與失敗。

驗證三node臨界值、輸出reserve、非OpenAI model/tokenizer、prompt包含完整必要scope/time、預算拒絕零transport；輸出max tokens不應只寫metadata。token計數估算與provider usage必分開。

### 其他效能與可安裝性結論

- 正常串行 latency 是兩次 query embedding＋intent/pruning/Draft 三次 LLM，再加 Qdrant；沒有量測不可宣稱加速。只允許同 manifest 重用 schema index；原生 intent 與 retrieval 的 query正規化近似但 cache共用應等實測後再議，現在不加抽象。
- document embedder 原生會同時送 `ceil(documents/32)` batches，規模放大會增加在途請求與記憶體；目前14+7文件量不構成已證實風暴。F4應設transport concurrency／batch上限與失敗drain，不能把將來規模問題描述成本次retail現況。
- 原生 retrieval 的空 embedding 分支走 Qdrant scroll全取，與向量top_k不是同一語意；測試不能拿fake retriever的固定top_k行為冒充。大catalog預算由F7拒絕，本輪不做泛用分散式retrieval。
- Python3.12 `/usr/bin/python3.12`、uv、jq可用；Poetry指令未找到。已比對pinned `pyproject.toml`／`poetry.lock` 的 numpy、tiktoken、Haystack、Qdrant、LiteLLM/OpenAI等主要版本，未發現可據以斷言無解的差異；**未跑resolver／安裝／完整import，不能宣稱依賴可安裝或runtime相容**。
- [Poetry官方](https://python-poetry.org/docs/basic-usage/#operating-modes) 說明package-mode=false僅安裝依賴、不產wheel。後續本機bootstrap須固定upstream SHA、來源/patch/lock hash、Python3.12、只裝必要依賴groups，從upstream root以獨立env明確啟動worker；握手核對import `__file__`，避免繼承本repo PYTHONPATH污染upstream `src` namespace。不要在CPEA `.venv`嘗試解此衝突。
- 不要求本輪公共release pipeline，但可重現本機安裝／啟動／乾淨重建指令是phase1必要驗收；若Poetry缺失可選明確固定工具版本的bootstrap方案，再驗證lock一致性，不能臨時偷偷改lock。

## Failure modes

所有新路徑尚未實作，表中「處理」指草案是否有約定，不代表code已存在。

| 路徑 | 真實失敗情境 | 測試／處理現況 | 使用者看到什麼 |
| --- | --- | --- | --- |
| adapter | 同名View碰撞、unsupported type | 草案有collision檢查；GAP測試 | 應為明確preflight error |
| native store | namespace設定被忽略、碰到共用collection | F1：具體adapter尚未定 | 可能靜默查錯index；critical gap 1 |
| index lifecycle | clean後write失敗、兩store代次不同 | F3：無共同ready定義 | 可能空候選／錯誤誤導成需求問題 |
| intent | 解析fallback、複雜需求誤拒 | 草案已有parse邊界error與nonready；GAP eval | 清楚分類；false rejection待量測 |
| pruning | unknown被消失、空columns變全部 | F2：無raw選欄契約測試 | 原始違約可靜默消失；critical gap 2 |
| DraftPlanning | 合法欄位但漏條件／母體 | 草案已明承runtime無完整coverage；Oracle planned | 不把結構PASS叫語意PASS |
| validate/prepare | 非法grain／keys／request | 既有邊界測試；新接線GAP | error，不派SQL |
| transport trace | batch部分成功、finish error前raw遺失 | F4：provider外層不足；GAP測試 | 已扣費attempt可能無紀錄；critical gap 3 |
| worker | stderr堵塞、取消後late response | F5：名稱有列、狀態語意待補 | 應明確timeout/unknown，不自動重送 |
| Oracle/replay | extra measure假PASS、答案洩漏、版本drift | F6具體mutation與sentinel待補 | 必須FAIL／drift，不能精確重現假主張 |
| budget | prompt超窗／截斷JSON | F7：完整budget待補 | transport前error或保存raw後parse error |

本審查把 F1、F2、F4 的靜默行為且缺具體防線列為 **3 個 critical gaps**；其他為已知研究風險或同分支契約補齊，不把所有planned測試都膨脹成P1。

## Implementation Tasks（候選，未核准）

每個 task 只對應本次finding；工時是粗估，非承諾。路徑為候選，不要求照檔名新增。

- [ ] **T1（P1，人約2–4h／agent約30–60m）** — store — 定義並驗證專用namespace接法；源自F1；候選 `src/cpea/infrastructure/wrenai/`、worker provider patch；驗證 constructor全部dataset names＋真Qdrant雙manifest sentinel隔離。
- [ ] **T2（P1，人約2–4h／agent約30–60m）** — retrieval — 保留及驗證raw pruning selection與rendered schema；源自F2；候選worker retrieval boundary／`test_wrenai_pruning_contract.py`；驗證五種mutation與zero downstream calls。
- [ ] **T3（P2，人約2–3h／agent約30–45m）** — index — 實作building/ready/failed與雙store一致性；源自F3；候選index manifest/lifecycle；驗證第二store故障／重啟／雙writer。
- [ ] **T4（P1，人約4–6h／agent約1–2h）** — trace — 在transport seam錄製原始LLM／embedding batch attempt並固定retry/fallback；源自F4；候選worker transport policy／trace；驗證partial failure、finish_reason、unknown usage/cost、rate limit只一次。
- [ ] **T5（P2，人約3–4h／agent約45–60m）** — worker — 定義並測通排空／取消／unknown outcome／bounded I/O；源自F5；候選worker client/server；驗證late event不跨run、stderr壓力、reap、下一run。
- [ ] **T6（P2，人約4–6h／agent約1–2h）** — evaluation — 加入零模型真Qdrant整體及Oracle/replay mutation／洩漏測試；源自F6；候選`evaluations/`與`tests/integration/test_wrenai_*`；驗證自然上游輸出、extra measure拒絕、embedding replay零網路。
- [ ] **T7（P2，人約2–3h／agent約30–45m）** — budget — 完整逐node input/output budget與truncation政策；源自F7；候選DraftPlanning/provider preflight；驗證臨界context與max-output、preflight拒絕零transport。

未提出額外TODOS：本次finding都應在本流程實作／驗收階段完成，不需把必要正確性延後成泛用優化；沒有修改TODOS.md。

## 階段與平行策略

| 工作流 | 模組 | 依賴 |
| --- | --- | --- |
| S0：確認修訂設計與接線契約 | docs／介面定義 | 使用者決策，未獲批准 |
| S1：乾淨環境／真native/store spike，T1/T3 | worker/bootstrap、worker/providers、index | S0 |
| S2：raw selection／Draft context／budget，T2/T7 | worker/pipelines | S1來源與dataset契約 |
| S3：trace／protocol，T4/T5 | worker/transport、worker/client | S0協定；S1可執行worker |
| S4：Oracle/replay／整體，T6 | evaluations、integration tests | S2＋S3穩定trace與node I/O |

Lane A：S1→S2（worker核心順序）；Lane B：S0後先做Oracle schema／mutation規格及獨立evaluator，再等S2/S3接線；S3與S2同屬worker，**不建議同目錄無協調並行修改**。契約鎖定後可讓evaluator lane與worker lane在各自worktree並行；合併後跑S4與既有113 focused regression。這是未來實作策略，本輪沒有新建worktree或派agent。

## 證據與驗證界線

- 父baseline：`evidence/EV-20261023T074047-2f43a752.json`，指定5檔113 passed；本輪引用既有證據，沒有重跑，不能當成新worker測試。
- 本輪零模型microprobe：`review-evidence/rag-eng-review-microprobes.json`，AST extraction真upstream函式＋fake transport，證明empty/unknown欄位處理與gather sibling繼續；另使用本checkout真正 `_task_score` 證明extra metric不會直接使全部checks失敗。這不是完整upstream import或自然E2E。 結果 SHA-256 `c96bcbf8149f89e2d5a8aa5da4a0e074be3bbc97f410fa80badc398bcfa8de8f`；來源 SHA `ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc`。
- 本輪catalog introspection明確使用 `PYTHONPATH=/home/willy/code/cpea-wrenai/src .venv/bin/python`；實際 `cpea.__file__=/home/willy/code/cpea-wrenai/src/cpea/__init__.py`，fingerprint與草案相同 `f448fd223570b38ab5cd4002a5afc31b60002422cd47549868c64cbf2c87c430`。
- 查核已具體排除：retail預設top_k必然不足、複合PK被草案錯切、既有validator能保證需求完整、reset方法名必然清庫等誤報。
- 未驗證：resolver/install、upstream完整import、Qdrant server/client整合、真模型分類／retrieval/Draft品質、latency與費用；報告沒有把靜態閱讀說成runtime通過。

## 完成摘要與Main優先決策

Step0已完成並觸發複雜度提醒，未由使用者接受／拒絕範圍縮減。Architecture 3項、Code Quality 2項、Tests 1項整合缺口、Performance 1項；共7項，其中3個P1／4個P2。ASCII資料圖、coverage圖、failure modes、既有能力、排除範圍、候選tasks皆已列出。新路徑全部GAP/planned，未製造coverage百分比。outside voice由本fresh-context agent完成，額外cross-model未執行。平行策略2 lanes，worker共享目錄採順序；7個推薦均採完整必要邊界而不新增語意planner。

**給Main的單一優先決策：是否同意先修訂並核准此真WrenAI設計，明列F1/F2/F4三個P1接入邊界，第一階段驗收改為「零模型真upstream＋專用Qdrant整合spike」，通過後再完成離線Oracle/replay？**這保留使用者已定方向；原設計尚未獲核准，本審查不代替使用者作選擇。

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
| --- | --- | --- | --- | --- | --- |
| Eng Review | `/plan-eng-review` | RAG、架構、測試、效能 | 1 | issues_open（PLAN） | 7 issues；3 critical gaps；7候選處置未核准 |
| Outside Voice | Main明確委派fresh-context subagent | 獨立資深RAG／工程審查 | 1 | DONE_WITH_CONCERNS | 本報告；非跨模型共識 |
| 額外跨模型review | skill outside-voice fallback | 未授權外傳／禁止再派agent | 0 | skipped | 未執行，無共識主張 |
| CEO／Design／DX | 本輪未要求 | 不變更既定產品範圍 | 0 | 未執行 | 不作clear主張 |

**VERDICT:** ENG NOT CLEARED／issues_open；eng review required。完成審查不等於可實作或可驗收；三個P1須先明列接入契約，剩餘P2在同階段補齊。

**UNRESOLVED DECISIONS:**
- D0：Main向使用者確認修訂設計與第一階段範圍；不得把spawned自動推薦當同意。
- D1／F1：選定namespace adapter或專用Qdrant instance，以及recreate／共享endpoint的明確界線。
- D2／F2：核准raw pruning selection的strict validation與empty/unknown/duplicate政策。
- D3／F3：核准雙store manifest ready／failed與crash recovery語意。
- D4／F4：核准transport recorder窄patch與每batchattempt／unknown cost保留契約。
- D5／F5：核准worker bounded I/O、cancel／late event／unknown outcome狀態契約。
- D6／F6：核准零模型真store整合＋Oracle/replay mutation與無洩漏驗收範圍。
- D7／F7：核准完整逐node context/output budget與截斷失敗政策。
