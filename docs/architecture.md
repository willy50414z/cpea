# CPEA 架構

目前產品為 `src/cpea` 的單一 Python package，驗證平台為 Windows x64／Python 3.12。核心提供單一 View MSSQL 產生、選配 SQL Server 執行與 Gradio 單題首頁；其他 API 接入與企業級 enforcement 狀態見 [企業級設計](enterprise_design.md)。

```mermaid
flowchart TD
    UI[Gradio Blocks 單題首頁] --> APP
    API[API app factory] --> B[AssistantRuntime／bootstrap]
    CLI[CLI] --> B
    GRAPH[LangGraph factory] --> B
    EVAL[Evaluation runners] --> B
    B --> CONF[Settings／DeploymentSettings]
    B --> CATALOG[YAML profile loader]
    B --> RET[Retriever／Document rendering]
    B --> LLM[既有 LLM factory／ContextPacker]
    B --> APP[Application services]
    APP --> W[Text-to-SQL SQLGenerationWorkflow]
    W --> P[QueryFact／SchemaLink／QueryPlan 與契約政策]
    W --> COMP[MSSQL compiler／SQL policy]
    APP --> EXEC[SQLQueryExecutor port]
    EXEC --> INJECT[部署注入 executor]
    EXEC --> DB[選配 SQLServerExecutor／SQLAlchemy／pymssql]
```

## 目錄與依賴

| 位置 | 責任 |
|---|---|
| `bootstrap.py` | 集中組裝，LLM／retriever／packer 延遲建立，profile 啟動驗證 |
| `config/` | 明確 env 優先順序、部署設定與相對路徑解析 |
| `interfaces/api/`、`interfaces/cli/`、`interfaces/web/` | JSON／SSE／命令列入口、Gradio UI 與錯誤映射 |
| `application/services/` | generation、核准 SQL execution、typed staged query、answering |
| `application/ports/` | CatalogProvider、SQLQueryExecutor；application 不依賴 DB driver |
| `application/models/`、`catalog_contract.py` | Service read models、trace、既有契約政策與 prompt rendering |
| `domain/` | QueryFact、SchemaLink、QueryPlan、ViewDefinition 等核心概念 |
| `workflows/text_to_sql/` | SQL generation graph、LLM draft schema 與 graph factory |
| `infrastructure/database/` | 選配 SQLAlchemy／pymssql adapter（NullPool），綁定 datasource／View、有限讀取、逾時與資源釋放 |
| `infrastructure/catalog/` | 有路徑邊界的 YAML snapshot loader |
| `infrastructure/retrieval/` | LangChain Document 轉換、lexical／vector retrieval、rerank 與 cache |
| `infrastructure/llm/` | 既有模型 factory、共享 JSON parsing、token/context budget |
| `infrastructure/sql_compiler.py`、`sql_policy.py` | 保留既有 MSSQL renderer／唯讀 SQL 檢查 |
| `projects/<project-id>/` | 私有專案 View 契約、`.env`、單一題庫與評估產物；wheel／sdist 排除 |
| `evaluations/` | 共用品質工具與合成 fixture；原始私有 PoC 題庫封存於被忽略的 `artifacts/baseline/` |

Domain 不 import API；application 回應模型由 API 引用。API／CLI／Graph 使用 bootstrap 建立依賴。Provider-specific LLM／retrieval 的現有抽象沿用 LangChain，沒有另外引入通用 plugin 平台。

首頁的 project 下拉選單固定為 `gms2`、`retail`。`ProjectRuntimes` 從 `CPEA_PROJECTS_ROOT` 載入各專案的設定，延遲建立並共用各自的 runtime；HILP 確認綁定送題時選定的 project，不接受透過確認改換來源。HTTP API 使用預設 `gms2` runtime。

## 既有生成與執行

```text
retrieve_schema → match_candidates（逐一驗證候選與 QueryPlan）
                → assess_semantics → [confirm_fields] → compile_query
                → persist_term_mappings → finalize
assess_semantics 若發現來源粒度不符 → 排除當前來源 → match_candidates（剩餘候選）
```

語意檢查優先使用 MATCH 已提供的業務選項；漏給選項時，針對伺服器實際判定的待確認詞彙補一次批次整理，並限制到用途合法的欄位與原有單一來源。補整理不更改查詢子句。只有一個合法候選時自動套用至該詞彙所有子句用途，再驗證完整查詢；這項判定只保留本題依據，不寫入人工確認詞彙檔，也不覆蓋不同的既有人工選擇。其餘歧義才詢問使用者。來源粒度不符時繼續其他候選，來源排除與失敗原因保留於 trace。模型無法產生合法選項屬系統錯誤；只有確實沒有相關選項或口徑仍太多時，才向使用者指出需補充的詞彙。

Graph 只產生 QueryPlan／SQL／QueryTaskTrace；SQLExecutionAgent 顯式取得 executor 與 datasource 後執行一次，保留最大筆數、truncation 和 execution trace；AnswerSynthesisService 根據結果產生附來源的回答。首頁未設定 executor／binding 時，以生成模式完成 SQL 與 HILP，明確標示未執行查詢；方式固定於送題時。執行型 JSON／SSE API 仍在 generation／LLM 呼叫前回報 unavailable。TOP 和 SQL policy 不取代真實資料庫權限與負載限制。

第一階段檢索文字只含 View 摘要與欄位描述，不列欄位名稱或型別。檢索與 context budget 篩選後，依排名逐一將單一候選 View 的完整核准契約交給模型，回傳欄位草稿並驗證。每個候選最多一次驗證後修正，失敗才試下一個候選。預設 v10 在通過 QueryPlan 硬性驗證後檢查語意疑慮，需要時先 HILP 確認，再產生 SQL；確認不再次呼叫 MATCH。歷史 v1–v9 保留逐一驗證並編譯的比較流程。每次呼叫的 JSON Schema 只允許當前 View 及其欄位。候選契約包含欄位名稱、描述、能力、可用聚合、詞彙對應、範圍與 operator 政策；不把 samples、測試題庫或預期答案放入模型 context。格式解析錯誤另有一次重試。雲端 SDK 的隱藏重試停用，API 錯誤交由呼叫端處理。

Python 將 fields／criteria／having／group 轉為 QueryFact、SchemaLink 與 QueryPlan，再由既有 compiler 產生 MSSQL。MATCH v10 的欄位與 View 名稱由當次單一候選契約限制，輸出格式由 Pydantic JSON Schema 約束，並增加完整詞彙證據與原文字元區間；上游 v1–v9 prompt 與 schema 保留原版本。v3 View 契約不使用預設聚合，聚合函數需由需求與契約能力決定。驗證失敗時，將原契約、前次映射與錯誤傳給同一 View 修正一次；仍失敗才試下一個 View。條件值必須來自需求原文或契約明確的 term mapping。檢查原文引用、欄位能力、operator／aggregation、catalog scope、QueryPlan 與唯讀 SQL policy；明確代碼、數值等 literal 若未承接，則拒絕查詢，避免漏掉篩選後擴大查詢。此檢查不等同完整自然語言解析。

Python 不依特定品號、客戶或題目補寫查詢，也不透過案例或答案修正模型。查詢只使用一個核准 View；來源參照保留實際選中的契約，候選與失敗嘗試留在 trace。

Catalog snapshot 保留各 View YAML 的 physical name、欄位能力、聚合、詞彙、範圍與時間語意。Manifest 指定 profile_id、contract_version、source_kind 和 catalog；loader 不限定 `gms2`。所有 resource 必須解析到該 profile 根目錄內；讀取 symlink 也以最終路徑檢查。契約內容 fingerprint 約束 cache，更新契約後需重新建立 runtime 取得新 snapshot。

不支援跨 View JOIN、SQL dialect 切換或新業務 workflow。未來 API operation 是獨立能力介面，設計列於 enterprise_design，不會強迫以 SQL 呼叫 API。

## 單題串流與 Gradio 首頁

`StagedQueryService` 以空 history 產生 `SQLStage`，檢查 supported、profile allowlist 與 query plan，再由 `SQLExecutionAgent.execute_generation()` 執行相同 SQL，回傳 `ResultStage`。驗證會以既有 compiler 重新編譯 plan 並比較 SQL，不再次呼叫 LLM。舊 `run()`／JSON query 行為及 execution trace、attempts、row bounding 保留；新流程不呼叫 AnswerSynthesisService。

SSE 端點在 ASGI send 完整 SQL frame 後才恢復迭代並開始 DB 工作，所有同步生成與 DB 工作都移至 threadpool。結果完成 JSON 編碼後才送出唯一 result／error 終止事件。介面明確轉換日期、Decimal、UUID、binary，且拒絕無法表示的型別與非有限數字；錯誤只對外提供固定訊息。內部新流程僅記錄失敗階段，不記錄原始例外、問題、SQL 或 rows。

Gradio Blocks 在 FastAPI `/` 掛載，使用 generator 提供完整畫面快照：最新問答、業務語意選項、聊天內完整詞彙摘要、SQL 程式碼區塊、結果表格與輸入／送出狀態。進度使用固定文字，選項僅含業務描述及隨機 ID，摘要與結果欄位使用安全的業務標題；SQL 區塊以外不傳送內部資料庫識別碼或原始流程內容。已產生的 SQL 在執行期間或執行失敗時仍保留。工作階段各自使用暫存 lock 防止重複提交，不向模型傳送前一題內容。問題在傳給 Chatbot 前先 HTML escape，即使停用 Markdown 仍不依賴框架 sanitizer 作為純文字保證。少量 JavaScript 提供 Enter／Shift+Enter、中文 composition 防誤送出、空白攔截、live region 與 queue 傳輸失敗的固定錯誤提示。選「都不符合」會回到原題編輯；傳輸失敗不重新提交查詢。重新整理取得新工作階段，沒有問答持久化或 browser storage；Gradio analytics 與 run history 均停用。

`AssistantSettings.sqlserver` 隱藏連線字串的 repr；設定沿用 process environment 與明確 env file 層。從 project 目錄載入 env file 時，以同目錄的 manifest／catalog 辨識 project，自動將目錄名稱用於 datasource binding 與詞彙檔 scope；此識別碼不受舊的環境變數或 deployment YAML 覆蓋。一般獨立部署與程式注入仍保留原有明確 binding 介面。Bootstrap 只在沒有注入 executor 且連線字串非空時載入選配 driver，建立 adapter 時不連接資料庫。每次呼叫驗證 datasource 與單一核准 View 的 SELECT，套用登入／查詢 timeout，讀取至多 max_rows + 1 列，最後關閉 cursor 與 connection；不呼叫 commit、修復或重試。SQLAlchemy 使用 NullPool 取得獨立 raw_connection，pymssql 套用 login_timeout／timeout、UTF-8、TDS 7.4 與 read_only intent；底層可執行連線初始化／metadata 查詢，核准業務 SQL 仍只執行一次。TLS 預設要求加密、system CA 與 hostname 驗證，FREETDSCONF／FREETDS 可由既有 env 層提供並解析相對路徑。pymssql timeout 與 TLS 設定有程序共用效果，不同部署設定使用不同程序。資料庫 SELECT 權限仍由部署環境提供，schema 名稱不作為 database 預設值。

安裝與代理串流設定見 [README](../README.md)。離線測試與真實 GMS2 驗證分開記錄，缺少 driver、網路連線或權限時不能宣稱已連線驗證。
