# CPEA A/B 評估與外部引擎研究規格

> **狀態：**使用者後續已指示實作。離線增補工具與隔離 Wren 技術探測進度見 [研究實作紀錄](research-implementation-report.md)；自然比較、獨立核准及 R3 前置仍未完成。本文件本身不是模型或 DB 呼叫授權，原有核准與依賴限制持續適用。

**目標：**在投入更多自建 Query Planner 維護前，用相同業務語意義務比較可替換策略及成熟 Package；保留原 S1～S6 的雙節點、治理、證據與產品驗收。

**架構：**延伸 S1-06／S1-07 的 runner、case loader、grader 及 replay；以評估端能力 adapter 接入研究候選，原生產物與共同比較投影並存。產品程式不得 import `evaluations/`。

**技術：**沿用既有 Python、Pydantic、LangGraph／langchain-core、catalog、compiler／policy。外部 Package 只是候選；R2 另建隔離環境，不新增產品依賴。

**規格來源：**[task.md](task.md)、[subtask-detail.md](subtask-detail.md) 及本次使用者研究需求。決策格式見 [decision-record-spec.md](decision-record-spec.md)。原驗收要求優先，不以研究成績替代。

## 1. 實際基準與可重用邊界

2026-10-22 文件增補前：HEAD `373b66e9b796d6c27c237acd56f6d8e4873c4e45`，branch `feat/progressive-view-retrieval`，`git status --short` 無輸出；主工作目錄 `/home/willy/code/cpea`。`git worktree list` 另列 `/home/willy/code/cpea-reliability-20261015`（`eval/reliability-20261015`）、`/home/willy/code/cpea-semantics-worktree`（`fix/view-result-semantics`）、`/home/willy/code/cpea_terms`（`feat/cross_view`）；本次不修改其他 worktree，也未檢查其 dirty 內容。

| 實際實作 | 已確認能力 | 增補缺口／限制 |
| --- | --- | --- |
| `TaskDecompositionService.plan(request)` | 委派既有 workflow，輸出 `DecompositionResponse`，含 draft／integration／prepared requests／contract fingerprint | 無公開 Coverage／own_gap 介面，不能假造 A0 內部 Coverage 成績 |
| `SQLGenerationService.generate(request, history, clarification_choice, *, mode, owner)` | 既有單 View SQL workflow，輸出 `SQLGenerationResponse`／`QueryPlan`／trace，保留確認守門 | 不是直接接受任意外部 SQL 的服務；研究輸出須獨立靜態核驗 |
| `QueryPipelineService`、`QueryPipelineWorkflow` | 注入 planner／generator；`invoke` 及 `generate_from_plan`；兩個核心 node 不變 | 足以包裝完整規劃／單 View 候選，不需先改正式服務；局部 Coverage 不適用此輸出契約 |
| `TaskSQLInput`、`generate_task_sql`、`validate_task_sql` | 固定 task、原文、catalog 指紋；renderer、batch preflight、QueryPlan 語意、同方言重編譯 SQL／policy | 既有 gate 對受支援子集採重編譯字串一致；不能為研究默默放寬產品 gate |
| `query_pipeline_runner.py` | 三模式、逐節點 settings／prompt／schema／source 指紋、HEAD／dirty、輸入來源、首次 calls／events／generation、隔離 mapping、成本及新 run 目錄 | 缺完整 Experiment／Strategy／Adapter manifest；模型版本目前預設未核實，digest 不可推定存在 |
| `query_pipeline_grading.py`、`query_pipeline_cases.py` | 完整合法替代方案配對、task ID／順序正規化、固定分母、首錯、case／catalog 核准綁定、輸出 hash 的人工審核 | 尚非逐 requirement 的跨格式語意評分器；精確方案匹配不可直接套用所有外部原生格式 |
| `replay_query_pipeline` | 從已錄製 response 離線重評，重驗 SQL gate，保留來源、grader 版本及 drift，新目錄不覆寫 | 這是重評，不等於逐 call 重播全部研究節點 |
| `managed_three_stage_runner.py`、`three_stage_view_selection.py` | 研究契約可注入、逐節點首次 request／call／parsed／normalized／錯誤、模型 digest、完整性 hash；嚴格逐 call replay；scope／grain／population／evidence validation | 研究入口；不能升為產品入口，也不能將 replay PASS 算成自然成功 |
| `own_responsibility_managed_contract.py`、`kind_mapping_managed_contract.py`、`diagnostics/managed_capability_projection.py` | 已有 own_gap、同 View dependency gap 推導、依 kind 的 mapping，以及責任卡無損投影研究 | A2／A3 與這些實作的差異須先盤點；存在原型不表示 Atomic Capability 或自然語意已驗收 |
| `pyproject.toml` | 已依賴 LangGraph、langchain-core、langchain-ollama；Azure extra 有 langchain-openai | 未宣告完整 LangChain SQL toolkit、LlamaIndex、Wren、MetricFlow、Cube、Vanna 或 SQLGlot；不得把既有 LangChain 基礎視為已有 SQL 候選 |

以上是靜態閱讀結果，非本次測試結果。舊 322 passed、4 次 smoke 與其 FAIL 僅引用 [implementation-report.md](implementation-report.md)，不改寫、不重新宣稱。

## 2. S1-02-E1：最小能力介面規格

先利用現有注入邊界，只在 evaluation 層增加候選描述與輸入／輸出封套；若足夠，不新增產品 Protocol 或改動穩定服務。不得將每個 Package 拆成固定 node。

| 能力責任 | 固定輸入 | 可接受原生輸出與比較責任 |
| --- | --- | --- |
| Requirement Parsing | 原文、固定 catalog／契約快照 | 有原文位置的 requirement、scope／grain／population；核驗必要需求是否完整 |
| Capability Resolution | 固定核准 Recall／requirements、單 View 契約 | mappings、可用部分鍵、own responsibility 與依賴證據；候選不提供則標示未觀測 |
| Source Selection／Query Planning | 同一原文／catalog；隔離測試可固定核准上游 | 完整 decomposition 或外部原生 plan；評共同來源、粒度、母體、依賴與整合義務 |
| Single-View SQL Generation | 人工核准 Prepared Task、來源／方言／policy | `SQLGenerationResponse` 或原生 SQL／plan；評映射、條件、靜態 SQL 與 task 一致性 |
| Contract／Semantic Validation | 原文義務、原生產物、契約與來源 lineage | 各層 verdict、引用、未觀測項及首錯；parser 成功不代表語意正確 |
| Cross-View Integration | 核准 integration 與固定結果／fixture | S1／R2 僅靜態計畫；S3／R3 才評實際整合結果 |

評估契約（已於 `evaluations/query_pipeline_experiments.py` 建立離線實作；獨立審查及正式研究驗收未完成）：

- 候選描述 `StrategyDescriptor`：`strategy_id/version`、`adapter_id/version`、`implementation_kind=product_service|research_candidate|external_engine`、能力清單、輸入／輸出種類、套件版本、是否需要模型／DB、支援方言及限制。ID 不等於模型名稱；模型另記版本。
- 固定輸入 `EvaluationInput`：`case_ref/hash`、原文、catalog snapshot／fingerprint、能力範圍、可選核准 upstream／Prepared Task 的安全引用與 hash；`input_origin`、`upstream_injected`、approval 引用必填。此為允許清單，oracle／case ID／預期 SQL／評審結果不傳入自然模型 context。
- 原生結果 `StrategyObservation`：節點 ID、原生 schema ID/version、Raw／Normalized 安全引用與 hash、狀態、呼叫與成本、首錯；解析失敗仍保留 Raw，Normalized 為 null 並記原因。
- 比較結果 `SemanticAssessment`：逐 `requirement_id` 的 obligation／evidence／verdict、層級與評分版本。這是評估投影，不回填模型原輸出、不替模型補規劃。

只有完整候選能透過薄 wrapper 滿足既有 `plan`／`generate` 行為時，才重用 runner factory；現有 factory 注入被標為 stub，增補須明確區分「離線 fake」與「研究候選的真實模型呼叫」，不能以注入即計 natural。局部 Coverage 與外部 plan 以 capability scope 接入同一證據／評分核心，不偽造 `DecompositionResponse`、`ViewCoverage`、own_gap 或 Prepared Requests。候選缺乏同等責任時標為不可直接比較，列缺口且保留總分母。

## 3. 共用 Evaluation Harness

### 3.1 延伸位置與產物

沿用 `evaluations/query_pipeline_{runner,cases,grading}.py` 及既有 private artifact 結構。研究執行／記錄由 evaluation 層 adapter 包裝，與正式 Application Service 隔離；managed runner 的嚴格 Raw replay 能力以唯讀引用／匯入索引銜接，保留其原始格式及 fingerprint，不修改封存資料。實作前先核對共用函式是否可抽用，不建第二套 case registry、grader 或報表標準。

`planning|sql|integrated` 原義不變；另用 `experiment_scope=internal_coverage|complete_planning|single_view_sql|external_semantic_plan|full_architecture` 表達研究責任。外部原生計畫沒有 S1 型別時，使用 evaluation observation 分支及同一評分核心，不傳入只接受 S1 型別的舊 grader。R3 只追加 fixture／結果評估資料，不改寫 S1 的 mode／SQL-stage 定義。

新增產物放 `projects/retail/artifacts/query_pipeline/<全新run-id>/`；實驗索引連到既有 run／managed 證據，禁止覆寫。預定追加 `experiment.json`、`strategy.json`、`assessments.json`、`replay-report.json`、`comparison.md`；敏感原生產物放 `private/`。這些路徑本次不建立。每項 registry 的證據欄日後填 run／artifact hash、HEAD、命令、退出碼、審核引用；不能只填 PASS。

| 必記資料 | 欄位／規則 |
| --- | --- |
| 實驗與候選 | Experiment ID、run／trial／case ID、strategy／adapter ID 及版本、scope、mode、案例分組、預先登錄比較矩陣 |
| 程式版本 | Git SHA、branch、worktree 路徑與狀態、dirty paths／diff 指紋、未追蹤程式指紋、套件 lock／image digest、runner／grader 版本 |
| 模型 | 各節點 Model Name／Digest／Provider、實際 immutable revision、核實時間／來源、temperature／seed／context／輸出設定；無法取得 digest 為 null＋原因，不能以名稱代替 |
| 輸入與知識 | 原文來源及 hash、catalog／schema／prompt fingerprint、upstream_injected、上游／Prepared Task 核准引用、額外語意模型／範例／檢索知識與人工工時 |
| 節點證據 | 各節點首次 Raw、Parsed（若有）、Normalized、原生計畫、SQL／QueryPlan、安全 lineage／hash、parse／contract 錯誤、planned／completed／failed／skipped／unfinished |
| 語意與首錯 | 逐 requirement 覆蓋／mapping／gap／scope／grain／population、首次失敗 stage＋category、附帶錯誤及傳播；保留原生首錯與共通分類對照 |
| 用量 | Model Calls、Input／Output Tokens、token 計量方式、模型／節點／總 Latency、預處理與轉換成本；未知為 null，不當作 0；重試數必為 0 |
| 重現與核准 | 來源完整性驗證、Raw replay 或 response regrade 類型、版本相容性／結果、Independent Semantic Approval 狀態／reviewer／時間／輸入輸出與評分 hash |

完整性分開記錄：證據是否齊全、trial 是否完成、查詢結果 `complete|truncated|unknown`。S1／R1／R2 沒有 DB 結果，結果完整性為未測，不能填 complete。

### 3.2 輸入與資料分組

支援固定自然語言需求、固定 Catalog、固定 Recall／Planning、人工核准 Prepared Task、完整合法替代方案，以及 unsupported／clarification 案例。每筆有原文、需求義務、版本、核准、來源及適用 scope；合法替代不得混拼不同方案片段。

| 分組 | 用途與控制 |
| --- | --- |
| Regression | 歷史 38 題及所有已使用案例，記原題庫／案例 lineage；原件保留，不重新標 Holdout |
| Diagnostic | 已知 planning anchor、legacy transport coverage、部分鍵、own_gap 等首錯定位；不算未見泛化 |
| Metamorphic | 受控 schema rename、ID 改名、日期／閏日邊界、scope／母體變更；有變形規則、預期不變／應變語意及獨立核准 |
| Holdout | 測試前由獨立審核者核准且未參與開發的新案例，先封存 hash／預期義務，執行者不看答案；洩漏或用於調校後移出未見組，仍保留實驗分母與紀錄 |

S1 原 12 題、六正六負面板不變，與研究集分開報告。Pilot 預定 4 題（部分鍵正例、無關 identifier、日期／scope、unsupported 各一），擴大研究面板預定 20 題、涵蓋下節風險；兩者均為待建／待核准規格，不是新 Holdout 或已存在題庫。Pilot 一旦用於調校就屬已見案例。正式研究分組題數、每格試次與 Holdout 保管人需於 R1-00 確認；不得用這 20 題取代原 12 題驗收。

### 3.3 分層 verdict 與指標

各層分別填 `PASS|FAIL|NOT_OBSERVED|NOT_APPLICABLE`、證據與原因；N/A 僅限事前宣告的責任邊界，不因候選失敗事後改列。NOT_OBSERVED 不算通過，不減總計畫分母。原生 verdict 與共同 verdict 同時保存。

1. 結構合法：原生 schema／解析；不是要求全部輸出相同 JSON。
2. 契約引用合法：來源／欄位／能力／JSON pointer／quote／指紋成立；引用存在不表示引用能證明該語意。
3. Requirement 語意正確：映射、條件、own responsibility、依賴及時間／來源範圍均符合核准義務。
4. 整合計畫安全：grain、join key／cardinality、母體與缺值政策有證據；S1 只評靜態，不宣稱數值正確。
5. SQL 靜態通過：單 View subset 的 QueryPlan／compiler／policy、方言、額外操作與來源漂移；外部 join SQL 另依相同安全義務核驗，不能假稱通過產品單 View gate。
6. 完整自然流程通過：無注入核准上游、固定版本、首次輸出、全部必要任務及獨立語意審查。S1 僅原文至 SQL；資料取得／跨來源結果／回答需 S2～S6 證據。任何隔離／Replay 結果不得算本層成功。

| 指標 | 計分責任 |
| --- | --- |
| Requirement Coverage | 每義務 satisfied／partial／missing／unsupported／clarification／unknown 與證據；必要義務全滿足才算正向成功 |
| Mapping Recall／Precision | 核准可用映射命中／應有映射；正確映射／所有輸出映射；無關 ID 映射列 false positive，禁止只獎勵多列欄位 |
| Own Gap Accuracy／Dependency Accuracy | 對照獨立標記的自身缺口與同 View scope／grain 依賴；保留有用 partial mapping，不以缺 scope 推論完全無能力 |
| Source Selection／Grain Correctness／Population Preservation | 核准來源或完整合法替代、輸出粒度、保留母體及來源時間一致；靜態與結果層分開 |
| SQL Contract Consistency／Join Safety | 每項欄位／filter／聚合／限制與契約一致；aggregation 前後、fanout／重複計算與 join 安全分列 |
| Unsupported／Clarification Accuracy | 預期正確停下與誤拒合法需求、錯誤放行分開計數；不能以所有問題一律拒絕提高安全成績 |
| Oracle False Reject／False Accept | 獨立審查合法替代及注入已知錯誤，列出自動評分誤拒／誤收分子分母；有爭議先記 disputed，不現場改 oracle 換 PASS |
| Model Calls／Tokens／Latency | 逐節點與整體、額外 calls／知識建模工時、總量與分布；模型設定不可比時分層呈現，不宣稱單一策略因果優勢 |

沒有原生 own_gap 的引擎，若可從有引用的業務義務投影評分，明記 `derived_by_evaluator` 與獨立審核；不可把投影冒充模型輸出。無法觀測者呈現缺口，不造 JSON 或硬給 own_gap 分數。

### 3.4 公平比較、Replay 與獨立審核

- 實驗前凍結 case／catalog／生成設定／候選版本、每格試次、比較順序與成本預算；相同模型可用時做同模型組，不可用時另做系統整體組，明列差異。套件必要額外知識全部列帳，不含測試答案。
- 固定上游隔離組所有適用候選使用同一核准輸入；自然完整組各自從同一原文開始，不能把隔離 Coverage 的 PASS 與完整規劃直接比較。R1-A 與 R1-B 分開固定變因，整體品質另回原 integrated 評估。
- 首次 Raw 先保存再解析。模型、SDK、agent 修復、fallback、DB introspection／sample rows 等隱含呼叫須可關閉並驗證；不能關閉者在 R1／R2 判為不適用，留下受阻證據，不能偷偷呼叫。
- 先離線偽回應確認證據、成本、分母與禁止 DB 的 sentinel，再 Pilot，最後擴大。Pilot FAIL 不刪題；改候選／prompt／schema／等價規則即新實驗版本，不覆寫最初結果或抽成功答案。
- 對每個配對單位（案例、輪次、catalog、模型組、scope）呈現逐層差異；failed／skipped／unfinished 全留。因 provider 停止的其他題標未觀測，不解釋成語意 FAIL，也不排除總分母；不自動補跑。
- 證據完整性先核驗。嚴格 Raw replay 重跑相同 parser／normalizer／validators；response regrade 只重評既有 response，兩者分開記錄。新版本不相容為 `source_drift|incompatible_replay`，不能改歷史 hash 配合新程式。
- 所有語意等價變更先由非提案者獨立審核，綁定原文／catalog／產物／規則 hash；舊分數保留，另存新版重評。需求與輸入核准、輸出語意核准、產品業務契約核准三者分開。審核者可為人員或另行授權的獨立審查流程，本次未執行任何審查模型。

## 4. R1：節點級 A/B Test

### 啟動契約與 baseline

R1 需既有 S1-07、增補 S1-07-E1 及 S1-08-BL。BL 是原 S1-08 的第一輪里程碑：S1-01 面板人工核准後，固定兩段設定與所有指紋，對原 12 題依序規劃三模式各一輪；報告列全體計畫分母、真實首次 calls／Raw、自然 integrated 的首錯及停止後 skipped。`sql` 模式本來就是核准輸入，照原標記，不與 integrated 自然成績混合。

BL 不要求正向全 PASS，也不要求 S1-08 三輪完成。若 provider 中斷，保留第一輪不完整報告，由獨立審核確認是否已有足夠 planning／integrated 首次輸出定位研究問題；完全沒有可判讀自然輸出時，BL 尚未取得，R1 不能啟動。不得以重試補成功或把 pending 未核准面板當正式 BL。既有單題連通 smoke 不符合 BL，不能回填成新里程碑。

取得 BL 後，R1-A 可研究 planning 根因，R1-B 可使用人工核准 Prepared Task 隔離研究 SQL；即使自然 integrated FAIL 仍合法。S1-08 維持未完成；R1 不修改其分母、三輪門檻或產品 `sql_ready` 判定。

### R1-A：Planning／Coverage

| 候選 | 比較範圍與控制 |
| --- | --- |
| A0 | 正式 `TaskDecompositionService` 的首次規劃行為，產品 baseline；只評其可觀測完整規劃責任，不假設已有 Coverage |
| A1 | 既有研究三階段及 Responsibility Cards；先凍結實際模組組合，避免混合不同歷史版本的最佳結果 |
| A2 | Atomic Capability Evidence＋分離 Own Responsibility；先對照現有 own／kind mapping／capability projection 找出真正差異，再定義最小候選，不重建已有能力 |
| A3 | 證據可驗證下的 deterministic dependency／status 推導；從同一固定 atomic／own 上游決策推導，不用題庫答案補 evidence 或推定依賴成立 |

分兩層：內部 Coverage 組固定 Recall、責任卡及 catalog，測 A1～A3 的相同能力；完整 planning 組才以原文比較 A0 與能提供完整責任的研究組。A2／A3 若只有 Coverage，完整組標不可比；如未來補組完整流程，所有增加的 Selection／LLM／轉換成本均計入。A1→A2→A3 分別列 ablation，避免同時改上游與 status 規則卻歸因於單一變數。

至少涵蓋：有用部分鍵、無關 identifier 負例、own_gap 與 scope／grain 依賴缺口、View Scope、Grain、Population、Schema Rename、日期邊界、不支援需求、契約 Evidence。包含「只有對齊鍵但無指標」、「同名欄位屬不同業務物件」、「缺本 View 期間不能向別 View 借條件」及缺證據時保守停下。

**完成條件：**責任對齊與 Pilot／擴大矩陣已獨立核准；各候選適用格均有首次輸出或明確受阻原因、逐義務與分層成績、首錯與成本、Replay／完整性結果及獨立審核。交付 `r1-a-comparison.md` 與證據索引；保留 FAIL，可結論為不可比／證據不足，不要求任一研究組勝出。

### R1-B：單 View SQL Generation

固定人工核准 Prepared Task（task／integration／來源與原文／指紋），比較現有 `SQLGenerationService` 與可行的 LangChain／LlamaIndex 生成候選。Prepared Task 透過各自必要序列化提供相同語意，不把標準 SQL 作 prompt；只在評分端持有 oracle。

先查候選是否能禁用執行與修復；LangChain SQL agent 的 DB 工具不能照範例直接啟用。R1-B 僅生成，catalog 由固定檔案提供，不建立 DB 連線。SQLGlot 僅作 AST／解析／正規化／靜態檢查候選，不是 NL planner 的競爭組。

比較欄位映射、條件完整性、SQL Policy、Compiler 合法性、Source Drift、額外排序／HAVING／limit／JOIN 等操作、Unsupported／Pending、Tokens／Latency。能無損轉成既有 QueryPlan 者沿用產品 gate；只有原生 SQL 者另評 AST 與相同語意義務，產品 gate 結果標未適配。AST 等價不能取代產品精確重編譯 gate，也不能自行核准語意等價。

**完成條件：**至少現有服務與一個可行候選完成 Pilot／核准研究矩陣；若均不可行，提供所需執行能力、API／版本及實證受阻報告。交付 `r1-b-comparison.md`、逐題六層成績／成本與離線重現、獨立審核；零 DB 並有禁用執行的證據。不得把外部生成 SQL 直接送到產品服務。

## 5. R2：外部 Semantic Query Engine PoC

先功能與適配性研究，再優先 Wren 最小 PoC；不要求全部實作。MetricFlow 次之，Cube 按治理需求決定；LangChain／LlamaIndex／Vanna 為基本 Text-to-SQL／MVP 對照。研究比較的是核准的業務語意義務，不要求引擎輸出 `ViewCoverage`／own_gap／Prepared Requests。

使用 `projects/retail/catalog.yaml` 的七 View：`v_customer_value`、`v_daily_sales`、`v_inventory_status`、`v_order_summary`、`v_product_monthly`、`v_sales_detail`、`v_store_monthly_kpi`。固定 YAML 快照及技術測試許可，不更改來源檔。`contract_review.md` 仍稱 draft，但目前 manifest 為 `status: approved`，profile／version 仍帶 draft；需先核對核准來源與效力，不推定已完成正式業務審核。PoC 副本明示技術用途，不改正式 loader 的守門。

R2-01 產出版本化能力矩陣：每項填官方證據、預計適配方式、實測／未測、額外人工語意、不能支援項。R2-02 在獨立 venv／容器／checkout 固定 release／commit、lock／image hash，使用無 DB credentials 的封閉執行面；編譯、驗證或服務啟動若必須連 DB／取 schema／sample rows，就記錄受阻並縮為離線語意模型／編譯研究，不越過 S1 限制。隔離安裝與模型呼叫都須未來另行授權。

最小 PoC：七 View 的模型定義與轉換盤點，Pilot 選單 View、跨來源母體、粒度／cardinality、unsupported 各一情境；只在核准案例子集生成原生 plan／SQL 並做靜態核驗。自然模型組與固定 semantic request 的編譯組分開，後者不是 NL 成功。S1 尚無真正整合器，因此外部完整 Join 能力僅記靜態義務與限制，不與 S1 多份單 View SQL 宣稱端到端勝負。

| 評估項 | 必留證據／成本 |
| --- | --- |
| 新 ERP View 導入 | 每 View 初次人工工時、所需資料、轉換比例、需要業務回答的問題；七 View 試作不能冒充已證明新客戶成本，另列估算假設 |
| Schema／Semantic Model | YAML→MDL／其他模型逐欄對照、遺失政策、人工新增 entities／relationships／metric 定義、來源及核准；沒有可證唯一鍵時不得編造 |
| Join／Cardinality | one-to-one／many-to-one、未知鍵／many-to-many 拒絕或限制、fanout、聚合順序、join 可追溯性 |
| 指標／粒度／母體／缺值 | 非可加指標、庫存 snapshot、KPI 背景重複、left 母體、NULL／零／無列政策、日期 scope；不靠引擎預設偷偷補商業規則 |
| 方言／靜態能力 | PostgreSQL／SQL Server 分列實際支援、離線 compile／explain 是否會查 DB、來源白名單與 SQL policy 可適配程度 |
| 權限／部署／商業限制 | 本地／服務／雲端、權限注入／隔離、telemetry、所需授權來源、確切版本 LICENSE／NOTICE、商業化與託管限制待審項；不以產品名稱推論可用 |
| 未支援 CPEA 要求 | 澄清／pending、own responsibility 可觀測性、metadata 集合、conditional metric、跨來源／相依任務、證據 lineage 與 S1 gate 的適配缺口 |

**完成條件：**R2-01 能力矩陣、R2-02 版本固定的最小 PoC 成功／失敗原件及靜態核驗、R2-03 成本／缺口報告與獨立語意審核均可追溯；至少嘗試驗證 Wren 的無 DB 路徑可行性。無法安全啟動時提交受阻實證，不宣稱 PoC 通過，ADG 可據此判證據不足。

官方研究入口（2026-10-22 閱讀；屬可變來源，執行前須固定版本）：[Wren AI／MDL](https://github.com/Canner/WrenAI)、[原 wren-engine](https://github.com/Canner/wren-engine)、[MetricFlow](https://github.com/dbt-labs/metricflow)、[Cube](https://github.com/cube-js/cube)、[LangChain SQL agent](https://docs.langchain.com/oss/python/langchain/sql-agent)、[LlamaIndex](https://github.com/run-llama/llama_index)、[Vanna](https://github.com/vanna-ai/vanna)、[SQLGlot](https://github.com/tobymao/sqlglot)。原 wren-engine 官方已指向 WrenAI 的 `core/`，PoC 不預設沿用舊部署架構；MetricFlow 官方說明依賴 dbt project／adapter，且授權有版本歷史，均須納入選版與隔離研究。這些官方功能描述不是 CPEA 適配性或商業授權審核結論。

## 6. Architecture Decision Gate 與 R3

ADG-01 於 R1／R2 報告可審核後執行，建議先於 S1 最終驗收決策，最晚 S2 前。結論為 `KEEP|ADAPT|REPLACE|INSUFFICIENT_EVIDENCE`，必須附實測、成功／失敗、語意風險、工程維護／新客戶導入成本、後續驗證與業務核准前提，格式見決策規格。研究報告完成可以包含受阻結論，不等於能力通過；未進行的實測不能填成 PASS。

R3 在 S3 完成後比較 CPEA Planner＋Deterministic Integrator、Wren／可行外部引擎適配結果，必要時加入純 LangChain SQL Agent 基準。先確認雙方承擔同等來源與語意責任；沒有可行候選時保留缺口與不足結論，不能因缺對手推定 CPEA 勝出。

相同核准需求、資料來源可見範圍、方言、固定資料庫 fixture／snapshot 與 oracle；CPEA 可多查詢後整合、外部可完整 Join，依結果語意比較，並將 round trips、模型與執行成本計入，不要求相同 SQL／JSON。跨 DB 與同 DB 是不同組；不能讓外部讀到底層表或額外資料而不揭露。

先靜態評查詢語意、Join Cardinality、母體保留、Aggregation Safety，再在 S2／S3 已核准受控 fixture 評 NULL／零／無列、結果完整性、重複計算、unsupported／模糊需求；包括重複鍵、100 庫存商品／60 有銷售、日期不一致、未知完整性及背景 KPI。DB 查詢不提前進 S1；正式資料不得用於研究測試。無執行許可時結果層維持未測，不能宣稱 R3 完整結果比較已完成。

**完成條件：**R3-01 凍結相同 fixture／oracle 與環境授權；R3-02 交付靜態及實際結果的分層比較、故障／限制、成本與獨立審核；R3-03 依同一決策格式記錄架構結論，逐項更新 S4 的 binding／DAG、S5 的錯誤／恢復、S6 的 requirement／claim evidence 驗收規格。研究有負面或證據不足結論也須列下一步；結果層未測則 R3-02 不勾完成，S4 前補驗或另行核准修訂研究範圍，不能默認略過。

## 7. 仍需自建與可研究重用

| 預計重用／候選 | CPEA 仍承擔的責任 |
| --- | --- |
| 既有 LangGraph、LangChain model factory、catalog／compiler／SQL policy、runner／grader／replay | 薄雙節點、受治理交接、證據保存與獨立語意驗收；優先沿用現有實作 |
| SQLGlot（候選） | AST／方言解析／正規化可研究重用；業務等價、來源許可與產品 compiler gate 仍由 CPEA 確認 |
| LangChain／LlamaIndex／Vanna（候選） | 生成工具可研究重用；Prepared Task、確認狀態、來源約束及禁止額外操作不能直接委託預設 agent |
| Wren／MetricFlow／Cube（候選） | 語意模型／指標／join 規劃可評估適配；ERP 業務知識、母體／缺值政策、核准與跨引擎 evidence 必須有人治理 |
| 確定性 Integrator、Binding、恢復、回答 evidence | 沿 S3～S6 建立；若 R3 證明外部能力可替代，另提遷移方案，不能預先認定全部自建或全部外包 |

## 8. Open Questions 與執行順序

| ID | 尚未確認資訊 | 由哪個任務解決／影響 |
| --- | --- | --- |
| OQ-01 | Retail manifest approved 的核准來源／效力與舊 draft 審查落差；未知鍵、sold_qty_30d 日期與比率口徑 | R2-01；未有業務證據前只作技術測試 |
| OQ-02 | A2 Atomic 定義與現有 kind／own／capability projection 的實際差異、A3 status 推導的證據充足條件 | S1-02-E1、R1-00；不推定已有完整候選 |
| OQ-03 | 逐 requirement 安全閾值、正式研究組數／試次、Holdout 保管與審核者、可接受成本 | R1-00，執行前預先登錄；未核准不開始擴大測試 |
| OQ-04 | Wren 選版、無 DB compile 介面、模型供應者可替換性；MetricFlow dbt／adapter 能否完全離線 | R2-01／02；無安全路徑記受阻 |
| OQ-05 | 外部原生 SQL 如何無損映射 QueryPlan；哪些只能由評估 AST 證明，哪些尚無語意 oracle | S1-07-E1、R1-B／R2；不得放寬產品 gate |
| OQ-06 | 七 View 以外的新 ERP 導入代表樣本、人工工時估算及部署／授權限制 | R2-03；未實測的新客戶成本僅能估算 |
| OQ-07 | R3 DB 方言、fixture／snapshot、執行預算、來源等權與服務權限 | R3-01；未核准不執行 DB |

建議順序：使用者確認本計畫 → S1-02-E1 → S1-06-E1 → S1-07-E1；同步先做 R2-01 文件研究及 S1-01 面板核准 → 原 S1-08 第一輪 BL → R1-00 Pilot 規格 → R1-A／R1-B、R2-02／03 → ADG-01 → 依決策另行核准必要修正，再完成原 S1-08 三輪與 S1 全部驗收 → S2 → S3 → R3-01／02／03 → S4 → S5 → S6。互不相依工作可分別排程，但本計畫不授權委派或自動執行。

## 附錄：本次實際閱讀範圍

以下為完整檔或相關方法／段落的靜態閱讀清單；不是執行證據：

- 規則／計畫：根目錄 `AGENTS.md`；同目錄 `task.md`、`subtask-detail.md`、`implementation-report.md`；`docs/architecture.md` 的 pipeline／catalog／planning 段落；`evaluations/README.md` 的 pipeline／replay 段落。
- 服務／Model：`src/cpea/application/services/{task_decomposition,sql_generation,query_pipeline}.py`；`src/cpea/application/models/{decomposition,query,query_pipeline}.py`；`src/cpea/domain/models.py`；`src/cpea/workflows/query_pipeline/{workflow,task_sql,validation}.py` 相關方法。
- 評估：`evaluations/{query_pipeline_runner,query_pipeline_cases,query_pipeline_grading,managed_three_stage_runner,three_stage_view_selection,metadata}.py`；`evaluations/{own_responsibility_managed_contract,evidence_bound_managed_contract}.py`；`evaluations/kind_mapping_managed_contract.py` 定義定位、`evaluations/diagnostics/managed_capability_projection.py` 定義與責任投影段落。
- 測試設計／契約：`tests/unit/test_query_pipeline_grading.py`、`tests/integration/test_query_pipeline_runner.py` 的 oracle／replay／sentinel 段落；`pyproject.toml`；`projects/retail/{manifest.yaml,catalog.yaml,contract_review.md}`；`projects/retail/evaluations/task_decomposition_matrix.md`。
- 歷史補充：`docs/task-decomposition-evidence-review.md` 的搜尋命中片段；未將歷史研究或既有診斷案例當成新 Holdout，未修改歷史 Task／結果。
- 使用技能：`superpowers:using-superpowers`（含 Codex 工具參考）、`superpowers:brainstorming`、`superpowers:writing-plans`；本次依使用者指定範圍僅編修計畫，不進入實作或提交流程。
