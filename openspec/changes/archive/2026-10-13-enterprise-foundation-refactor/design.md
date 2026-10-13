## Context

現有目錄以原專案的 `assistant` package 為前提。SQLExecutionAgent 預設從 `app.core.external_db` 取得執行器並使用 `JHD`；SchemaCatalog 與向量檢索限定 `gms2`；LangGraph 依賴及 `.env` 指向上層。API 只有 router，缺少獨立 app 組裝；Graph 設定引用不存在的 `create_graph`，模型比較工具引用不存在的 `_parse_model`。

既有能力是單一 View 的 SQL generation graph、外部 executor 呼叫及答案合成。YAML 已治理欄位能力、聚合、詞彙映射、scope rules 和時間語意，這些是遷移基準。domain/models.py 同時承載 API DTO、領域計畫、LLM 回覆與 trace；eval 混放題庫和執行結果。目前未見獨立套件 metadata、lockfile、tests 或 Git repository。

本次使用者授權為產品化重構，企業級能力可納入設計，但不開發資料庫及相關程式。`docs/dev_plan.md` 是另一份功能 PoC 計畫，不作為本 change 的新增功能或時程承諾。利害關係人包括產品開發者、企業整合工程師、後續身分／授權服務與部署維運人員。

## Goals / Non-Goals

**Goals:**

- 提供獨立、可重現、可安裝的產品結構，明確決定依賴與設定來源。
- 核心使用可替換的 catalog 與 executor 邊界，移除特定企業與原專案的固定假設。
- 保留既有 MSSQL 單一 View 生成、拒絕、欄位政策、trace 與注入執行器的行為。
- 明確分開程式、企業整合契約、機密參照、測試、評估與執行產物。
- 在文件中定義未來身分、企業 context、授權、稽核與維運接入流程及驗收條件。

**Non-Goals:**

- 新 workflow、複雜任務編排、需求澄清功能、JOIN、新 SQL dialect 或模型能力升級。
- 新 DB adapter／driver／連線池／交易／SQL 執行引擎、DB provisioning、資料表、ORM、migration 或持久化 repository。
- 真實 ERP API adapter、登入／SSO、RBAC／ABAC 判定、稽核 emitter／sink／查詢服務、secret manager 或共享多租戶 runtime。
- 修改既有契約中尚未確認的財務或聚合語意，或以結構重整宣稱商用安全驗收完成。

## Decisions

### 1. 使用單一 `src/cpea` package 與集中組裝

採用 `pyproject.toml`、`uv.lock` 與 `src/cpea`；實作盤點後鎖定 Windows x64／Python 3.12。測試／打包依賴放 dev dependency group，未驗證的 OpenAI-compatible／cross-encoder 套件明列於 `requirements/optional.txt`，按需另行安裝；核心 lock 不拉入大型模型 runtime。NumPy 是既有 vector retrieval 的實際依賴，明列於核心。CLI 經已安裝套件執行，bootstrap 組裝 settings、catalog、retriever、LLM、workflow 和可選外部 executor。API 提供 `create_app`，Graph 提供設定中可匯入的 factory，入口不在 import 時連線或發送模型請求。

替代方案是維持 root 的 flat modules 與 `assistant` namespace，搬移量較少但仍容易依赖 CWD／原 package 名稱；本次選擇一次明確遷移。核心不引入微服務或通用 plugin framework。

目標結構如下；註記「後續」的部分只寫入設計，不建立空實作或假成功服務。

```text
cpea/
├── pyproject.toml / uv.lock / .env.example / .gitignore
├── langgraph.json
├── src/cpea/
│   ├── bootstrap.py
│   ├── config/
│   ├── interfaces/api/       # app、router、API DTO
│   ├── interfaces/cli/
│   ├── application/ports/   # CatalogProvider、SQLQueryExecutor
│   ├── application/services/
│   ├── application/models/  # response/read models、trace
│   ├── domain/              # QueryFact、SchemaLink、QueryPlan
│   ├── workflows/text_to_sql/
│   │   ├── sql_generation.py
│   │   └── schemas.py       # LLM drafts
│   └── infrastructure/
│       ├── catalog/         # YAML loader、宣告契約驗證
│       ├── llm/             # 既有供應商 factory、context packing
│       ├── retrieval/
│       └── erp/             # 後續實際 DB／API adapter 的責任位置
├── integrations/<profile>/ # manifest、catalog、views；不含機密
├── config/tenants/example.yaml
├── tests/{unit,contracts,integration}/
├── evaluations/{datasets,runners}/
├── artifacts/evaluations/
└── docs/{refactoring_plan,architecture,enterprise_design}.md
```

### 2. 設定在啟動時明確載入

移除 import 時的 `load_dotenv()`。預設只使用 process environment；開發者明確指定 env file 時才載入該檔案，process environment 優先於檔案，缺省值最後套用，不向上搜尋 `.env`。既有 `ASSISTANT_*` 與現有 fallback 變數列入對照，第一輪保持明確的優先順序，新增 product 路徑／profile 設定不再靠 CWD。LangGraph 指向產品自己的設定位置。

獨立設定定義 integration profile、契約根目錄與 datasource binding；缺少執行設定不使用 `JHD`。分離一般設定與機密參照；範例使用 placeholder。對 caller 明確給定的相對路徑，依載入的設定檔位置解析；對套件預設資源使用 `importlib.resources` 等可驗證方式；不要以 `__file__` 推算外部部署目錄。

替代方案是自動載入根目錄 `.env`，操作較短但設定來源難以追溯；本次採明確 opt-in。正式 secret manager 只保留文件中的接入規則。

### 3. Integration 契約與執行實作分開

`integrations/<profile>/manifest.yaml` 記錄 profile ID、契約版本、來源種類與 catalog 位置。`catalog.yaml` 維持允許資源清單；View YAML 維持現有 physical name、欄位能力與業務規則，`gms2` 可存在於該 profile 的資料，但不得寫死於共用程式。設定將企業部署實例綁到 profile 與 datasource ID，不建立企業管理服務。

YAML loader 回傳型別化、與 LLM framework 無關的契約模型。將目前 SchemaCatalog 的檔案讀取、契約規則與 LangChain Document 轉換拆開：loader 放 infrastructure/catalog，既有確定性規則放 domain/application 的驗證元件，Document 建立放 infrastructure/retrieval。Compiler 可以維持 infrastructure 的 MSSQL renderer，但只接收已核准計畫與契約介面；workflow 經注入組裝，application port 不依賴具體 YAML loader 或資料庫 driver。

CatalogProvider 只涵蓋現有資源讀取與欄位契約需要的能力，不提早設計一套涵蓋所有 ERP 的查詢語言。讀檔只允許指定 profile 根目錄內的資源，包含正規化後的 path／symlink 邊界檢查；API caller 不得指定任意檔案路徑。Retriever 使用 profile 所宣告的 schema 資源，lexical／vector 規則一致。索引 cache key 至少包括 profile identity、契約內容版本／fingerprint 與 embedding／retrieval 設定；本次僅驗證部署 profile 間不混用，不實作每位使用者權限過濾。

契約資源是否內嵌 wheel 必須明確：只內嵌經確認可分發的合成示範 profile；既有客戶契約由外部部署檔案或私有交付載入。客戶樣本不隨 wheel 發行，原檔移轉前先盤點，保留有授權的私有版本及必要 baseline 來源記錄。

替代方案是把所有 YAML 放入 infrastructure/erp，會混合客戶設定與可重用實作；另一方案是完全改為 API-first，會擴大本次功能範圍。本次保留既有 YAML 與單一 View MSSQL。

### 4. 解除 executor 耦合，不新增 DB 程式

SQLQueryExecutor 定義目前 `datasource + sql → columns + rows` 的執行契約，保留注入既有 callable 的方式，只調整 service 的型別與 bootstrap wiring。原 `app.core.external_db` 的 implicit fallback 移除；本專案不複製該模組，也不安裝／開發 DB driver、連線池或新的查詢實作。

純 SQL generation 可獨立使用。DB query 模式需要部署端以 programmatic bootstrap 明確注入既有 executor 及 datasource binding；初始化不因 executor 未設定而影響 generation。執行入口在呼叫 LLM／executor 前確認設定，未提供時以可辨識的 dependency-unavailable 錯誤結束：HTTP 503、CLI 非零退出、評估 preflight 清楚說明，不能使用 fake 作為 production fallback。Fake executor 僅存在 tests。

`ERPReadOperationExecutor`、operation allowlist／參數 schema／paging／一致結果封套先寫入企業整合設計；本次不建立可呼叫 ERP API 的程式。未來 SQLQueryResult 可透過 mapping 轉為共用 OperationResult，這次不改變既有 HTTP 成功回應。

替代方案是先完整實作 MSSQL adapter，可完成真實查詢但違反本次 DB 排除範圍；保留原 import 則仍無法独立交付。選擇顯式注入並揭露預設 DB execution 不可用。

### 5. Workflow 與模型按責任遷移

將 graph/workflow.py 搬到 workflows/text_to_sql/sql_generation.py，保留 SQLGenerationWorkflow 與既有四個 node 的名稱和單一 View 範圍；新增可匯入 factory 修復 Graph 設定。Application service 負責生成、外部執行器呼叫與答案合成，目前不新增端到端 graph。

Domain 保留 QueryFact、SchemaLink、QueryPlan 等核心概念，Pydantic 可繼續使用。SQLGenerationRequest 與 HTTP payload 定義放 interfaces/api；SQLGenerationResponse、AssistantQueryResponse 與 QueryTaskTrace 為 application read models，由 API 引用，不讓 application 反向 import interfaces。LLM drafts 放 workflow schemas，ConversationTurn、SourceReference 依使用範圍放 application models。將現有 answering 的 JSON parsing 整理到共享的 LLM parsing 元件，讓評估與 answering 使用同一份已驗證行為，取代評估對不存在的 Graph 私有 parser 的引用。

HTTP 路徑 `/api/assistant/sql`、`/api/assistant/query` 及既有成功 payload 保留；診斷／拒絕階段保持可比較。Namespace、檔案與命令遷移以文件明確揭露；不保留會回頭匯入原專案的相容層。

替代方案是僅改檔名，無法解決 API 模型與業務模型混用；完全改寫 domain 為純 dataclass 會增加不必要遷移風險。本次以責任拆分為限。

### 6. 建立回歸與評估資產，控制新增測試範圍

tests 用 deterministic stub LLM、合成 profile、fake executor 驗證核心行為與整合邊界，不連 DB 或真實 ERP API。必要案例覆蓋成功／拒絕、欄位／scope／時間政策、參數值、trace、筆數截斷與外部 executor 失敗，以及 clean install、設定來源、profile 切換及路徑邊界。採用 deterministic cases 作為重構 gate，避免模型波動阻斷純結構遷移。

現有 query_reliability 與 model comparison runners 搬到 evaluations；固定題庫與有價值 baseline 分開。產物記錄程式版本（無 Git 時使用 package 版本／內容摘要）、模型／供應商、非機密設定摘要、契約版本／fingerprint、題庫摘要、run ID 與時間。原結果含 final_context、final_prompt 或 rows；必須按私有產物管理並在文件定義敏感內容的保存方式，不自動上傳或發行。

真實模型評估為 opt-in；需要 DB 的比較 runner 在未注入 executor 時先回報 unavailable。離線測試可用 fake 驗證 runner orchestration，但不得將 fake 成績當真實模型 baseline。正式 DB／安全／負載測試留到對應後續 change。

### 7. 企業級能力交付為設計文件

建立 docs/enterprise_design.md，明確標示所有以下項目為 design-only，描述責任位置、概念契約、失敗路徑與後續验收，不新增 runtime auth／audit／DB 實作。

| 項目 | 設計必須涵蓋 |
|---|---|
| 身分與 context | RequestContext 包含 request ID、trusted tenant／principal、授權 scope、integration binding；來源為未來驗證身分或可信部署設定，不接受 LLM 自行選擇企業 |
| 授權 | PolicyEnforcer 在 catalog 暴露／檢索前限制資源，在執行前再次驗證來源、欄位、operation 與條件；缺失 context／policy 以 deny 處理；Python 型別不是安全機制 |
| 稽核 | AuditEvent 含 event ID、UTC time、request／workflow ID、tenant／principal、operation、來源 ID、政策／契約版本、結果／拒絕階段、duration；避免預設保存 raw prompt、SQL literals、rows 或 secrets |
| 稽核生命週期 | AuditSink 由後續實作，定義 delivery、去重、存取、保存／清除與失敗處理；高要求環境無法滿足稽核時拒絕執行，其他模式只能明確設定與揭露，不能靜默成功 |
| 機密與診斷 | Secret reference、錯誤遮罩、日誌 redaction；現有 exception 字串截短不等同脫敏，未來真實 adapter 必須滿足錯誤邊界 |
| 資源與隔離 | 逾時、取消、最大筆數、concurrency／retry 責任；tenant／profile／契約／policy scope 必須約束 cache、連線、history、state、checkpoint 與 artifact namespace |
| 部署與維運 | 先以每企業獨立部署作為文檔假設，未承諾共享 SaaS；紀錄 upgrade／rollback、健康與 readiness、依賴不可用行為、正式商用前的安全與維運 gate |

替代方案是此次直接實作 auth／audit service，會引入身份來源與持久化決策，超過範圍；完全延後設計則容易讓未来 context 改動傳遍所有 service。此次先交付完整設計，後續以獨立 change 實作。

## Risks / Trade-offs

- [未提供真實 DB executor，預設 query 功能不可用] → 明確 503／CLI error、保留注入契約、用 fake 回歸驗證舊行為；新增 DB adapter 需另案授權。
- [Namespace／入口變更會影響原呼叫端] → 提供舊新對照、保留 HTTP 成功契約、整包部署；不靠 CWD 或舊專案維持偶然相容。
- [契約／樣本包含客戶資訊] → 先盤點，私有資料外置，wheel／公開 fixture 使用合成示例，baseline 保存來源與機密排除規則。
- [資料 grain、成本單位等語意未確認] → 不在重構中自動更改聚合；列入後續客戶資料治理 gate。
- [測試未從原專案移入，模型有非確定性] → 以本地可重現離線案例建立行為基準，原有評估只作已知樣本參考；不宣稱準確率提升。
- [產品架構完成被誤解為商用安全完成] → 文件逐項標示 implemented／design-only／deferred，禁止 auth／audit placeholder 回傳允許或成功。
- [uv／Python 版本未定] → 先盤點 dependency compatibility 並選擇一組可 clean-install 的版本，寫入 metadata 與 lockfile，不以現有 pyc 推定支援版本。

## Migration Plan

1. 建立現有行為／資產清單與離線基準，明列缺失入口、無可用 DB fallback 與資料治理缺口。
2. 建立 package、lockfile 與新 namespace，更新所有 import、腳本及 Graph 入口；以已安裝 wheel 驗證 package／資源完整性。
3. 引入明確 settings 與 bootstrap，移轉 integration 契約及 catalog loader；測試 profile 切換、cache versioning 與檔案邊界。
4. 改為显式注入 executor，驗證缺少依賴在 preflight 失敗；用 fake 回歸 execution／answering，不開發 DB adapter。
5. 搬移 workflow、模型與評估工具，修復 factory／parsing 缺失；完成 deterministic gates。
6. 完成 refactoring_plan／architecture／enterprise_design 與入口遷移文件，交付設計限定與待實作清單。若模型服務可用，再進行 opt-in no-DB 評估並記錄結果，否則揭露未執行原因。

部署單位是應用套件、非機密設定與匹配版本的 integration 契約；回復時三者一起恢復，記錄 baseline 和契約摘要。本次不修改任何資料庫，沒有 schema migration 或 DB rollback 步驟。即使未初始化 Git，也須以版本化交付檔保存可回復基準。

## Open Questions

- 第一批企業的部署模式尚未確認；本次使用獨立部署假設，真正共享多租戶方案留到另一份 change。
- 原專案是否能提供既有 executor／測試的獨立可注入交付？若無，該依賴以 unavailable 狀態交付，不能以此擴增 DB 開發範圍。
- 現有客戶 schema 契約、samples 與 baseline 的分發權限？未確認的資產不加入通用 wheel，以私有資料處理。
- 實作已驗證 Windows x64／Python 3.12；沒有明確配置的模型服務，真實模型評估未執行。其他平台與 optional provider 仍待後續驗證。
