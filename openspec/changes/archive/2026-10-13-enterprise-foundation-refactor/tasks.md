## 1. 現況盤點與回歸基準

- [x] 1.1 盤點現有 import／啟動入口／依賴／設定，確認可支援的 Python 版本；記錄缺失 `create_graph`、`_parse_model`、原專案 executor 與未移入測試等問題。
- [x] 1.2 建立遷移前的離線行為基準，以 stub LLM、合成契約與注入 fake executor 覆蓋成功／拒絕、欄位／scope／時間政策、compiler、trace、truncation 與 execution error，記錄既有缺陷及預定變更。
- [x] 1.3 盤點既有 catalog、samples、datasets 與歷史結果，列出可分發、私有保存及待確認資產的去向；保留原檔及可回復基準，不以分發不明的客戶資料建立產品 fixture。

## 2. 獨立套件與模組歸屬

- [x] 2.1 建立 `pyproject.toml`、`uv.lock`、`src/cpea` 與 CLI 安裝入口，分清必要／選用／開發依賴並記錄支援 Python 版本；不引入 DB driver 或持久化依賴。
- [x] 2.2 搬移 root、application、infrastructure 與 llm_tools 模組到設計中的責任位置，更新 `assistant.*` import 為 `cpea.*`，移除對原專案模組與 CWD 的依赖。
- [x] 2.3 按 domain／application read models／API DTO／workflow LLM schemas 拆分模型，維持既有欄位與 Pydantic 驗證行為，檢查 application/domain 不反向依賴 API interface。
- [x] 2.4 搬移 graph 為 `workflows/text_to_sql/sql_generation.py`，保留四個 node、SQLGenerationWorkflow 與單一 View 行為，提供可匯入 graph factory，不新增 workflow。
- [x] 2.5 整理既有 answer JSON parsing 為共享且可測的 LLM parsing 邊界，更新 answering／evaluation 呼叫，修復缺失 `_parse_model` 依賴。

## 3. 設定與 Integration 契約

- [x] 3.1 移除 import-time `load_dotenv()`，實作明確 opt-in env file 與 process environment 優先規則；建立 `.env.example`、設定／舊變數對照及非機密診斷，不向上搜尋設定。
- [x] 3.2 定義非機密 integration manifest／部署 binding 設定與型別化契約；保留 profile 內的 physical names／政策，解除核心對 `gms2` 與 `JHD` 的固定假設。
- [x] 3.3 依資產盤點遷移 `ref/db_schema`，將合成示範資源與私有客戶 profile 分開；明確實作套件資源及外部設定路徑解析，保持 catalog、view、sample 引用一致。
- [x] 3.4 定義 CatalogProvider port，拆開 YAML loader、既有確定性契約驗證與 LangChain Document 轉換；維持欄位能力、aggregations、filter、term mapping、scope 和 temporal 規則。
- [x] 3.5 使契約讀取只允許指定 profile 根目錄內的已解析資源，拒絕 path／symlink escape，驗證 API payload 不能控制任意檔案路徑。
- [x] 3.6 使 lexical／vector retrieval 使用 profile 資源並更新 index cache identity，納入 profile、契約 version/fingerprint 與 retrieval／embedding 設定；以兩份合成 profile 驗證切換及更新不混用索引。

## 4. 依賴組裝與既有執行邊界

- [x] 4.1 定義 SQLQueryExecutor port 與既有 callable 注入契約；調整 SQLExecutionAgent 的型別／wiring，移除 `app.core.external_db` fallback；不複製原執行器或新增 DB 實作。
- [x] 4.2 建立 bootstrap 組裝 settings、catalog、retriever、LLM、workflow 與可選 executor／datasource binding；generation 可於 executor 未提供時使用，fake executor 限於 tests。
- [x] 4.3 建立獨立 API `create_app` 並接入 bootstrap，維持 `/api/assistant/sql`、`/api/assistant/query` 的既有 payload；executor／binding 未提供時 query 在 LLM 呼叫前回報穩定的 HTTP 503 diagnostic。
- [x] 4.4 更新已安裝套件的 CLI 與產品根目錄 `langgraph.json`，使 factory／依賴／env 路徑有效；執行模式未設定 executor／binding 時 preflight 非零退出，入口 import 不發送網路請求。
- [x] 4.5 使用 fake executor 回歸既有單次執行、datasource 傳遞、rows bounding、trace 與 answer 合成，確認錯誤不觸發 LLM 修 SQL 或再次執行。

## 5. 評估工具與產物管理

- [x] 5.1 將 evaluation.py、eval_main.py、query_reliability_eval.py 整理至 `evaluations/runners`，固定 datasets 與 retained baseline 分開，更新所有命令與預設路徑。
- [x] 5.2 為評估產物加入 run ID／時間／程式版本或摘要／模型與供應商／非機密設定摘要／契約及題庫 fingerprint，使用 run-specific output 避免覆寫 baseline。
- [x] 5.3 讓 DB-dependent 比較 runner 接受 bootstrap 的外部 executor 並在缺少依賴時 preflight；用 stub／fake 驗證原有比較流程，不新增 DB 連線程式或以 fake 成績宣稱真實模型品質。
- [x] 5.4 建立 ignore／distribution 規則與私有產物保存說明，排除 `.env`、環境目錄、bytecode、generated outputs、客戶 samples、raw prompt／rows 與私有資料；保留有價值 baseline 的來源記錄。

## 6. 企業級擴充設計交付（僅文件）

- [x] 6.1 撰寫 `docs/enterprise_design.md` 的 trusted RequestContext、企業／ERP／profile／schema 區分與傳遞流程，及 catalog 暴露／檢索前和執行前的 PolicyEnforcer 檢查／缺失即拒絕規則；不寫 runtime 身分或授權實作。
- [x] 6.2 定義 AuditEvent／AuditSink 的欄位、correlation、delivery／去重、保存／清除、存取與失敗策略，區分 diagnostic trace 與 durable audit；不開發 emitter、sink、稽核表或持久化程式。
- [x] 6.3 定義 secret reference、敏感診斷遮罩、timeout／cancellation／row／concurrency／retry 責任、tenant/policy 對 cache／connection／history／state／checkpoint／artifact 的未來隔離規則，標示僅設計的邊界。
- [x] 6.4 定義未來 ERPReadOperationExecutor、operation allowlist、輸入驗證、paging 與結果／provenance mapping，並列出真實 DB／API、身分／授權／稽核與共享多租戶的後續 change；不建立 runtime API operation registry 或真實 adapter。
- [x] 6.5 寫明獨立企業部署的暫定假設、dependency readiness、升級／回復流程及正式商用安全／維運驗收，逐項標示 implemented／design-only／deferred，避免宣稱已具備完整企業安全。

## 7. 文件、驗證與交付

- [x] 7.1 建立 `docs/refactoring_plan.md` 與 `docs/architecture.md`，整理本次範圍、分期依賴、驗收、舊新 import／命令／路徑對照及設定方式；連結 enterprise design，保留 `docs/dev_plan.md` 的原功能 PoC 範圍。
- [x] 7.2 執行核心離線回歸與有變更風險的契約測試，驗證 HTTP 成功／拒絕 payload、未設定 execution diagnostic、設定優先順序、profile/cache 切換與資源路徑邊界，保存結果。
- [x] 7.3 建立 wheel 並在 clean environment／checkout 外的工作目錄驗證安裝、API app／CLI／Graph factory、套件資源與依賴；檢查分發內容沒有客戶或機密資料。
- [x] 7.4 若已配置模型服務，執行 opt-in no-DB query reliability 評估並記錄版本及結果；否則在交付報告標示未執行原因，且不宣稱真實 DB／模型品質验收。
- [x] 7.5 核對 specs 與 tasks 完成情況、維持 DB／API／auth／audit 的排除範圍，交付已知限制及版本化 package／設定／契約回復指引；未注入 executor 的真實 DB 查詢不可用須清楚揭露。
