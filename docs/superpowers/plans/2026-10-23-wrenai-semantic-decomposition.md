# WrenAI 獨立需求拆分實作計畫

> **供 agentic workers 使用：**必要子技能為 `superpowers:subagent-driven-development`（獨立工作並行）或 `superpowers:executing-plans`（同 session 逐項執行）。依 checkbox 追蹤。使用者已授權整合審查後開始開發，不再等待計畫批准；禁止 commit／push。

**目標：**新增真實 WrenAI 原生 indexing／intent／retrieval 與 DraftPlanning extension，離線可重播，輸出既有 `DecompositionResponse`，保留逐 transport 證據。

**架構：**CPEA 負責結構 adapter、JSONL client、既有 Draft 解析與 validate／prepare；獨立 Python 3.12 worker 執行 pinned upstream Hamilton／Haystack pipelines。專用 namespace 的原生 Qdrant store、generation manifest、transport recorder 與 node budget 是接入邊界；Oracle 只存在 evaluator。

**技術：**Python 3.12、WrenAI AI service 0.29.3、原 upstream Poetry lock、Poetry 2.1.4、Hamilton、Haystack、LiteLLM、Qdrant、既有 CPEA Pydantic models／pytest。

**規格：**[已整合設計](../specs/2026-10-23-wrenai-semantic-decomposition-design.md)、[F1–F7 審查](../../../evidence-driven-dev/tasks/wrenai-semantic-decomposition/rag-eng-review.md)。

## 全域限制

- upstream SHA 固定 `ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc`；基準 CPEA `ab4c67a45fa7039379bcadd788af0ae83bb3630f`。
- 保留 `workflow.py`、`schema_mapping_workflow.py` 與既有 public models；不得用其 planner fallback。
- 真 upstream 類別必須 import 並執行；不得以本地仿作或 `/tmp/rag-review-wrenai-ce9ed54` 的部分檔案假稱 runtime 證據。
- 本次真模型、業務 DB、SQL generation／execution 呼叫數為 0；可安裝獨立依賴、啟動本機專用 Qdrant，transport 用 fixture。
- 不建立 MDL 業務詞典、synonyms、memory、正式 benchmark；正式題庫由使用者另備。
- 真 retail `SchemaCatalog('projects/retail')` 應有 7 Views／102 欄位；14 schema chunks 只是 upstream batch=50 的先前推算，須以實際產物驗證。
- UTF-8 無 BOM，保留既有換行，Markdown 使用繁體中文；raw artifacts 為 private directory 0700／file 0600。
- 不 commit／push、不改現有待審 Oracle／題庫 fingerprint、不更動 production 資料。

## 審查重點

1. 同名 View／欄位、空或未知 pruning selection：明確拒絕，不能被 renderer 靜默變全欄或遺失（任務 2、3）。
2. 第二 store 寫入失敗、不同 embedding dimension／兩 worker：不發布半成品、不觸碰共用 collection（任務 3）。
3. 部分 embedding batch 成功後失敗／取消：每個已送 attempt 有終態或 unknown，未知成本不填 0（任務 4）。
4. timeout 之後 late event／大量 stderr：不得阻塞、錯貼到下一 run 或自動重送（任務 6）。
5. schema 合法卻多算 measure、移錯 filter／母體／缺值政策：獨立 Oracle mutation 必須 FAIL，expected 不進 prompt（任務 7）。

## 檔案 ownership 與相依順序

| Worker | 唯一寫入範圍 | 責任／相依 |
| --- | --- | --- |
| A：native_worker | `integrations/wrenai/**`，含局部 tests、`.gitignore` 與繁體中文 README | 任務 1、3、4、5、server；先完成環境 spike；不得改 CPEA 或 evaluator |
| B：cpea_boundary | `src/cpea/workflows/task_decomposition/wrenai_{schema,protocol,client,workflow}.py`；`tests/unit/test_wrenai_{schema_adapter,protocol,workflow}.py`；`tests/integration/test_wrenai_worker.py`；`src/cpea/application/services/wrenai_decomposition.py` | 任務 2、6；可與 A 並行，不複製 upstream 或 Draft model |
| C：evaluator | `evaluations/wrenai_{cases,oracles,replay,runner}.py`；`tests/unit/test_wrenai_{node_oracles,replay}.py`；`tests/integration/test_wrenai_evaluation.py` | 任務 7；依 adapter／protocol／artifact 介面開發，禁止修改舊 grader 語意 |
| D：整體 reviewer | EDD 自己的 handoff／Main 指定證據；產品檔只讀 | 任務 8，獨立對照規格／測試／實際來源，不能用 A/B 自述作驗收 |
| integration_planner | 本計畫與上述設計文件 | 整合七項 A，不修改產品或主 ledger |

順序：`1 環境 → 3 store/lifecycle → 4 transport → 5 native graph → 6 真整體 → 8 驗收`；`2 adapter/client contract` 與 `1` 可並行；`7 evaluator` 待共用介面確定即可獨立開發。Main 是主 EDD ledger 唯一 writer。先回報每個子節點結果，再驗父 worker、自然整體與舊流程。

## 固定鄰接介面

### Parent ↔ worker（不 import CPEA 的隔離環境）

JSONL `protocol_version=1`，事件共通 `type/request_id/run_id`。`handshake` 的 IDs 可為 null；每個 plan 的 request_id 與 run_id 必須唯一、不可空。`accepted → running → result | error | cancelled | unknown_outcome`，每 run 恰一 terminal；cancel_requested 為中間狀態。

```text
handshake = {upstream_sha, patch_sha, lock_sha256, python_version,
             import_sources: {module: absolute_path}, capabilities: [str]}
plan = {request: str, catalog_fingerprint: str,
        schema: {mdl: dict, model_to_view: {str: str}, contracts: {view: dict}, adapter_version: str},
        response_schema: dict, case_id: str | null}
result = {draft: dict, context_tokens: int, token_counter: str, artifacts: dict}
error = {code: str, node_id: str | null, message: str, sent_attempts: int, cost_complete: bool}
```

上面各 payload 與共通 envelope 合併成一筆 JSON；不能同時另造不相容的 `payload` 包裝。artifacts 僅為 manifest／private artifact reference 及安全 summary；不得把 raw credential 或 Oracle 放 stdout。worker runtime 來源、版本及必要 capabilities 不符，父端在 plan 前拒絕。

固定上限：line 4 MiB、plan payload 2 MiB、queue 128；run timeout 120 秒、cancel grace 2 秒、terminate grace 2 秒，可由明確設定覆寫且入 manifest。UTF-8 JSON stdout 僅協定，stderr 並行排空；大 stderr 不應累積為無限記憶體 queue。未知或重複 terminal、錯 ID、非 JSON／超限皆為 protocol error，保留原 run 證據後停用該 worker。

### Adapter／workflow

`adapt_catalog(catalog) -> dict` 產上述 `schema`，model-name 用 `m_ + qualified_view.encode('utf-8').hex()`，逆映射只讀 model_to_view。每個 model 為名稱與全欄位；`relationships/views/metrics=[]`，不造 primaryKey。型別精確對應 `number→NUMERIC/string→VARCHAR/date→DATE/boolean→BOOLEAN`；contracts 保留完整 policy。

`WrenAIWorkerClient.plan(*, request: str, run_id=None, case_id=None, **payload) -> dict` 回 result body；client 內部產 request_id 並處理 terminal envelope；`close() -> None` 關閉與 reap。若實作使用 async 內核，由此同步外層負責橋接，不要求 CPEA 切換事件迴圈架構。

`WrenAIDecompositionWorkflow(client, catalog)`；`invoke(request: str, *, run_id=None, case_id=None) -> DecompositionResponse`，另以 `plan` 委派此入口。blank／非字串／>4000 字元在父端 error、worker calls=0；empty catalog 為 unsupported。父端從 `DecompositionDraft.model_json_schema()` 提供 worker schema，返回以既有 model 解析；ready 才執行 `validate_decomposition`／`prepare_requests`，其他狀態無 prepared requests。不新增另一個 Draft class。

### Native transport／artifact ↔ evaluator

每個 call 包含 `run_id/case_id/node_id/call_id/batch_id/attempt=1`、input fingerprint、安全 request、raw response、parsed/error、started/ended/elapsed_ms、provider/model/deployment/SKU、raw usage／normalized usage／usage_source、spend `{currency,amount,pricing_version,pricing_source,status}`。未知值為 null／unknown，run 有 `cost_complete`；embedding／LLM 分別累計。每 attempt 送出前及終態立即 flush；raw response 在 finish-check／extract 之前保存。

generation identity 包含 catalog／adapter／upstream／patch／lock（內部欄位 `lock_hash`，握手欄位 `lock_sha256`，相同 digest）／embedding provider/model/dimension；namespace 為 `cpea_wrenai_<sha256前24碼>_<dataset>`，非空 project_id 為完整 hash。manifest 保留完整 identity 防截斷碰撞、building／ready／failed、兩 store documents count/content digest。run manifest 另存 Python／tokenizer／prompts／response schema／input／index identity；replay 必須比對這些欄位。

## 任務 1：可重現獨立環境與來源 spike（A，先決門檻）

**檔案：**建立 `integrations/wrenai/{bootstrap.py,README.md,.gitignore}`、`integrations/wrenai/native_worker/{__init__.py,__main__.py,runtime.py}`、`integrations/wrenai/tests/test_runtime.py`。runtime 預設 `integrations/wrenai/.runtime/{upstream,env}`，不進 Git。

**介面：**`python3 integrations/wrenai/bootstrap.py --runtime-root integrations/wrenai/.runtime` 建立完整 pinned checkout／獨立 env 與 runtime manifest；`runtime.py` 暴露來源握手資料給 server。固定 Poetry 2.1.4，以 upstream 原 lock `install --only main --no-root`；工具可透過 uv 隔離安裝，不更新 CPEA lock。

- [ ] 寫 `test_runtime.py`：錯 SHA／部分 checkout／來源落到本 repo 的 `src` 必拒絕；handshake 所列 module.__file__ 必在 pinned checkout。先執行，確認缺實作為 RED。
- [ ] 實作 bootstrap／runtime：完整 checkout、驗 SHA、鎖前後 hash；清除繼承 PYTHONPATH，cwd 指向 upstream `wren-ai-service`，僅加 worker package 路徑；保存 Python／lock／patch／tool fingerprint、AGPL source/license。
- [ ] 真的執行 resolver／安裝／import `DBSchema/DDLChunker/TableDescription/IntentClassification/DbSchemaRetrieval/LitellmLLMProvider/LitellmEmbedderProvider/QdrantProvider/BasicPipeline`，證據不能只是 find_spec。
- [ ] 用 `integrations/wrenai/.runtime/env/bin/python -m pytest integrations/wrenai/tests/test_runtime.py -q` 驗綠；保存安裝／完整 import 原始輸出與 hash。無法安裝時回研究者重判，不自行換 SHA／移除原生類別。
- [ ] 回父節點：能從明確命令啟動 worker 並握手；尚不宣稱 indexing 或品質通過。完成本 task 不 commit。

## 任務 2：真 retail schema adapter 與 protocol 契約（B，可與 1 並行）

**檔案：**建立 `wrenai_schema.py`、`wrenai_protocol.py` 及兩個同名 unit tests，路徑依 ownership 表。

**介面：**輸出固定 `adapt_catalog`／JSONL v1 payload；供任務 3、5、6 使用。protocol 模組只使用 parent 環境／標準型別，不 import upstream。

- [ ] 寫 `test_retail_schema_is_complete_and_reversible`：真 catalog 的 7 model、102 columns、四種型別、完整 policy、不造 PK；每個 model_to_view 可逆。另測同 basename 不同 qualified view、未知型別、非法 MDL 識別與空 catalog。
- [ ] 執行 `env PYTHONPATH="$PWD/src" .venv/bin/python -m pytest tests/unit/test_wrenai_schema_adapter.py tests/unit/test_wrenai_protocol.py -q` 確認 RED。
- [ ] 實作 adapter 與 envelope encode／decode／validation；拒絕缺／錯 protocol、IDs、未知事件、超限、重複 terminal；Oracle keys 不在 plan allowlist。
- [ ] 同命令驗綠；`test_oracle_sentinel_rejected_from_plan_payload` 確認 expected_tasks／oracle_notes 不會進 worker。
- [ ] 將可用 schema payload 交 A，由 native chunker 消費；純函式 PASS 不能替代原生 indexing。完成本 task 不 commit。

## 任務 3：namespace provider、generation lifecycle 與 pruning boundary（A，F1/F2/F3）

**檔案：**建立 worker `providers.py`、`index.py`、`selection.py`；建立 `integrations/wrenai/tests/test_{namespace,index_lifecycle,selection}.py`。

**介面：**`NamespaceQdrantProvider(namespace: str, **native_kwargs)` 繼承原生 provider，覆寫 get_store；`ensure_index(schema: dict, identity: dict) -> dict` 在兩原生 indexing 成功才回 ready manifest；`validate_selection(raw: dict, schemas: list[dict]) -> dict` 原封回傳合法 raw，違約拋可定位錯誤。renderer 本體仍用 upstream。

- [ ] 先測全部六 logical datasets 都被映射、recreate false；空 project_id／identity mismatch 拒絕。真專用本機 Qdrant 上放共用 sentinel，以兩 namespaces／不同 dimensions 分別寫讀並驗 sentinel 未變。
- [ ] 先測第二 store 寫入前／中失敗、重啟 building、競爭 writer、counts 相同但內容 digest 不同；狀態必 failed／拒讀，ready 只在兩store內容核對後發布。
- [ ] 先測 empty results／empty columns／unknown-only／known+unknown／duplicate table或column／unknown table；真 upstream renderer 只能接合法 selection，錯誤不觸發 Draft transport。
- [ ] 執行 `integrations/wrenai/.runtime/env/bin/python -m pytest integrations/wrenai/tests/test_namespace.py integrations/wrenai/tests/test_index_lifecycle.py integrations/wrenai/tests/test_selection.py -q` 確認 RED。
- [ ] 實作窄 subclass、排他檔鎖與原子 manifest、renderer 前 hook；collection 初始化／重建只限該 generation，保留 native filtering／scroll 語意。
- [ ] 同命令驗綠；加真 retail indexing 的 TABLE／TABLE_COLUMNS／table description 成對與全部欄位檢查。回父節點從 worker API 再讀，不能只驗 metadata。完成本 task 不 commit。

## 任務 4：transport recorder、retry policy 與三 node budget（A，F4/F7）

**檔案：**建立 worker `transport.py`、`budget.py`、`artifacts.py`；`integrations/wrenai/patches/` 僅保存 pinned 窄 patch／版本 manifest；建立 `integrations/wrenai/tests/test_{transport,budget}.py`。

**介面：**transport seam 包住實際 `acompletion/aembedding`，接收 node/run context 後回原始 provider response；`check_budget(node_id, rendered_request, model_limits, token_counter)` 在送出前拒絕。Native provider 的 finish-check／JSON extraction 保持原有位置與行為。

- [ ] 寫 raw completion leading/trailing text、finish=length、invalid JSON／usage missing、Azure deployment≠SKU 測試：raw artifact 必存在且 usage／費用未知不填零。
- [ ] 寫 document embedding 兩batch成功／一成功一失敗／取消：已開始 call ledger 筆數等於 transport attempt，末態 complete/error/unknown；batch32、在途上限1，失敗後 drain；rate limit 只送一次。
- [ ] 寫三 node budget 臨界值：含 system/user/response schema，加 output reserve/safety；超窗該 node transport=0；output max_tokens 真正送 provider。測非 OpenAI tokenizer，禁止截原 request／必要 contract。
- [ ] 執行 `integrations/wrenai/.runtime/env/bin/python -m pytest integrations/wrenai/tests/test_transport.py integrations/wrenai/tests/test_budget.py -q` 確認 RED。
- [ ] 實作 recorder／pricing provenance 與窄 patch；外 backoff max_tries、LiteLLM、SDK／Router retries及fallback全固定一次，不能只記 metadata。禁止有任何自動未知重送。
- [ ] 同命令驗綠；以真 native provider＋fake transport 證明 provider 外層無法看到的 raw 仍已落盤。回父節點統計 call ledger，而非只驗 totals。完成本 task 不 commit。

## 任務 5：原生 DAG 與 DraftPlanning extension（A）

**檔案：**建立 worker `native.py`、`draft_planning.py`、`server.py`、`prompts/draft_planning.txt`；建立 `integrations/wrenai/tests/test_native_pipeline.py`。

**介面：**`NativeWrenAIPlanner.plan(payload: dict, *, run_id: str, request_id: str) -> dict` 接固定 payload、回 result body；`DraftPlanning(BasicPipeline).run(request, intent, retrieval_results, contracts, response_schema)` 回 Draft dict。handler 透過 server 輸出 accepted/running/terminal，server 與 client 共享上述 JSON 契約、不共享 runtime imports。

- [ ] 寫真完整 upstream＋Qdrant、fake completion／embedding transport 的自然整體測試：由任務 2 真 schema 索引，自然 intent/retrieval 結果進 Draft，禁止注入金答案 retrieval。
- [ ] 寫 intent valid enum、fallback JSON error、GENERAL/USER_GUIDE→unsupported、MISLEADING_QUERY→needs_clarification；native final-node dict 應分別解包 `post_process`／`construct_retrieval_results`。
- [ ] 寫完整所選 View contract／integration keys、原 request 保留、不把 rewrite 蓋原條件；fixture expected sentinel 不得在模型 request。遇無候選／budget／pruning error 不得再送 Draft。
- [ ] 執行 `integrations/wrenai/.runtime/env/bin/python -m pytest integrations/wrenai/tests/test_native_pipeline.py -q` 確認 RED。
- [ ] 實作 native pipelines 組裝；intent docs/histories/sql_samples/instructions 為空且 Configuration 明示；Draft 用 upstream provider＋Haystack PromptBuilder＋Hamilton AsyncDriver，不載入舊 planner、不建 Engine instance。
- [ ] 同命令驗綠；保存 import source、Hamilton graph、index manifest、原生自然上游結果、逐 call artifact。只以 fake transport 證明接線正確，不宣稱真模型品質。完成本 task 不 commit。

## 任務 6：常駐 client 生命週期與既有 Draft 邊界（B，F5）

**檔案：**建立 `wrenai_client.py`、`wrenai_workflow.py`、`src/cpea/application/services/wrenai_decomposition.py`、unit workflow／integration worker tests；既有兩個 workflow 只讀。service 接設定與client，僅組裝新流程。

**介面：**前述 `WrenAIWorkerClient.plan/close`、`WrenAIDecompositionWorkflow.invoke/plan`；response 的 context_tokens/token_counter 來自 worker，catalog fingerprint 由 parent 自己核對。

- [ ] 寫 fake subprocess 測試：握手 mismatch、非 JSON／超大行、超過 pipe buffer 的 stderr、EOF／crash、timeout／cancel／late result、連續兩 run、shutdown／reap；證明錯 run 的晚到訊息不會被下一 run 接收。
- [ ] 寫 parent contract 測試：invalid input worker calls=0；native terminal raw draft 由既有 model 解析；ready 必 validate/prepare；nonready 無 payload；invalid columns／grain 變 invalid_plan，不觸發 SQL。
- [ ] 執行 `env PYTHONPATH="$PWD/src" .venv/bin/python -m pytest tests/unit/test_wrenai_protocol.py tests/unit/test_wrenai_workflow.py tests/integration/test_wrenai_worker.py -q` 確認 RED。
- [ ] 實作並行 stdout/stderr drain、有限 queue、stdin drain、cancel state machine、terminate/kill/reap；request timeout 結果未知就封存 unknown_outcome、下一 run 先重啟，不自動重送。
- [ ] 同命令驗綠；再透過 client 啟動**真 worker**執行任務 5 的 fake-transport 自然端到端案例，Draft 通過既有 validator 並產 prepared requests。
- [ ] 回父節點：父 .plan 到原生 DAG 再回 Response 完整驗證；只 fake child 測試通過不得聲稱真 worker 完成。完成本 task 不 commit。

## 任務 7：使用者題庫載入、node Oracle、regrade／replay（C，F6）

**檔案：**依 evaluator ownership 表；本次不新增正式 datasets。

**介面：**`load_wrenai_cases(path: Path, catalog) -> list[dict]`；`grade_wrenai_run(case: dict, run: dict, catalog) -> dict`；`regrade(run_dir: Path, case: dict, catalog) -> dict`；`replay(run_dir: Path, *, runtime_identity: dict, allow_drift: bool=False) -> dict`。`python -m evaluations.wrenai_runner --help` 提供 regrade/replay 與未授權 live mode 的明確說明；不得預設 live。

- [ ] 寫載入測試：重用既有 case_sha256／approved_for，catalog／review fingerprint drift、重複 ID、未核准 Oracle、nonready fixtures 合法處理。ready case 走既有 loader；nonready 分支只驗其相關欄位，不要求 ready tasks/integration。
- [ ] 寫 Oracle mutation：extra metric、extra conditional metric、漏 filter、錯否定／期間邊界、跨來源 filter 錯置、錯 anchor／preserve／cardinality／missing policy、背景 measure 重複加總，逐一從 PASS 變 FAIL。合法 helper keys／核准日期等價仍 PASS；不要自由文字精確比對。
- [ ] 寫 sentinel 測試：expected_tasks／alternatives／notes 只由 evaluator 讀；request resolver／model input 不含答案。raw selection 與 rendered DDL 分別評分。
- [ ] 寫 regrade 零模型、replay completion＋document/query embedding＋匹配 index snapshot；以禁止網路 spy 驗證。任一 upstream/patch/lock/Python/model/tokenizer/prompt/schema/input/catalog/index identity mismatch 預設拒絕；allow_drift 必明標，不能稱精確重現。
- [ ] 執行 `env PYTHONPATH="$PWD/src" .venv/bin/python -m pytest tests/unit/test_wrenai_node_oracles.py tests/unit/test_wrenai_replay.py tests/integration/test_wrenai_evaluation.py -q` 確認 RED。
- [ ] 實作最小 loader／附加 invariants 與 artifact resolver；重用既有 grader 基礎但不把 subset 通過當沒有 extra measures；unknown cost 保留 incomplete。replay 若需 native graph，委由已存在 worker replay seam，不另建 planner。
- [ ] 同命令驗綠，將一個真 worker 錄製的離線自然整體 run 重評／重播，回父節點確認重新產生 Draft 與原輸出一致。完成本 task 不 commit。

## 任務 8：獨立完整驗收與回歸（D／Main）

**檔案：**產品只讀；驗證 log／版本與髒工作樹指紋由 Main EDD run 保存。已有 focused baseline 113 passed，不能冒稱為新變更後證據。

- [ ] 逐一確認任務 1–7 真正執行的 commands、exit code／raw log／來源與 fixture；跳過的真 Qdrant／真 worker 項目直接列 GAP，不能 counted PASS。
- [ ] 執行全部 `integrations/wrenai/tests`（獨立 env，專用本機 Qdrant，fake transport）；證明六 dataset namespace、兩store lifecycle、raw selection、attempt ledger、budget、自然 Native→Draft。
- [ ] 執行 parent 新增 unit／integration tests；再於本 checkout 明確 `PYTHONPATH="$PWD/src"` 重跑：`tests/unit/test_task_decomposition_workflow.py tests/unit/test_task_decomposition_contract.py tests/unit/test_schema_mapping_decomposition.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py`。預期舊 focused cases 全通過；任何失敗不削弱 assertions。
- [ ] 以 source inspection＋Engine instantiation spy 確認沒有 SQL generation／execution／DB connection，無舊 planner fallback；核對 upstream／CPEA import path，避免 editable checkout 誤載。
- [ ] 獨立 reviewer 逐項對照 A1–A5／F1–F7、負向 mutation 與自然端到端證據，無待修問題才讓 Main 宣稱離線交付完成。
- [ ] 最終說明明列真模型品質、正式 benchmark、實際費用／latency 尚未驗證；正式題庫與 provider/model/embedding/Qdrant/預算到位後才進 live smoke，不自行呼叫。

## 完成／失敗判準及復原

**離線 MVP 完成：**真完整 pinned 環境能重建，來源／patch／lock handshake 正確；真 Qdrant＋fake transport 的自然 worker 到既有 Draft/prepare 成功；七 findings 的正／負契約測試、trace/regrade/replay、舊 focused regression 及獨立審查均有證據。這個完成範圍不包含真模型語意品質。

**失敗且須重判：**依賴無法由原 lock 安裝、原生輸出不符假設、namespace／generation 汙染、renderer boundary 無法攔截、attempt 無法對帳、Oracle mutation 假 PASS、自然 end-to-end 依靠金答案 retrieval；保留第一失敗，回研究者做有辨識力修正，不私換 SHA／假 store／舊 planner 或補正式題庫。

**復原：**新入口為獨立新增檔，不切既有預設流程；失敗時停止 worker、取消／排空／reap，保留 private artifacts 與 failed manifest；只重建本流程 namespace。Git 檔案保留待審，不用 reset／clean 清使用者變更，不刪共用 Qdrant、不 commit／push。

規劃時已取得的局部證據：Main 核對 `EV-20261023T081205-fe5d82d9` 為完整環境／來源 import，`EV-20261023T081344-3111051d` 為原生四 pipelines spike（7 models／102 fields→14／7 documents→intent／retrieval）。上述是先決可行性證據，尚不代表 Draft extension、JSONL lifecycle 或完整離線驗收完成；checkbox 由各 owner 依自己的實際證據更新。
