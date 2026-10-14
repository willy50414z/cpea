## Context

目前 `AssistantRuntime.generate()` 產生受治理的單一 View MSSQL，`execute()` 經 `SQLExecutionAgent.run()` 產生 SQL 後執行，`query()` 再呼叫 LLM 整理文字答案。既有 API 皆為完整 JSON 回應，沒有 Web 首頁；runtime 只有部署方注入 executor 才能查 DB。

私有 GMS2 profile 已有 `gms2.v_inventory`、`gms2.v_sales_forecast`、`gms2.v_sales_returns`。`gms2` 是 schema，實際 database 名稱與登入資訊尚未提供，使用者會補入 `.env`。此設計不需取得密碼即可完成離線實作與驗證。

## Goals / Non-Goals

**目標：**

- 透過部署設定接上 SQL Server，以 GMS2 profile 驗證。
- SQL 通過治理後先傳給前端，再開始 DB 查詢；資料取得後立即回傳。
- 每次請求獨立，只顯示最新問答，統一使用「執行錯誤請再試一次」作為新流程的錯誤訊息。
- 維持既有 API、executor 注入、單次 DB 執行與 generation-only 能力。

**不在本次範圍：**

- 多輪對話、問答保存、會員登入、持久化稽核、多租戶平台與跨 View JOIN。
- 新流程的文字答案生成、逐筆資料串流、結果分頁、自動 SQL 修復與自動重試。
- 修改私有 GMS2 View 契約、建立 ERP schema 或 migration。

## Decisions

### 1. 單一 POST 搭配 SSE 格式串流

新增 `POST /api/assistant/query/stream`，請求只接受 `request`，沿用長度上限並拒絕空白問題；拒絕額外的 `history`、SQL、datasource 與路徑欄位。SQL 與 datasource 均由伺服器決定。此 SSE 端點保留供 API 用戶端使用。使用者已選擇 Gradio，首頁透過 Gradio 的事件傳輸呼叫同一個分段 application service，不另寫 fetch parser。

事件格式：

```text
event: sql
data: {"sql":"SELECT TOP (200) ..."}

event: result
data: {"columns":["倉庫","數量"],"rows":[["A",10]],"rows_truncated":false,"row_limit":200}

```

失敗的終止事件：

```text
event: error
data: {"message":"執行錯誤請再試一次"}

```

合法序列只有 `sql → result`、`sql → error`、`error`；`result` 或 `error` 恰好一個且為終止事件，隨後關閉串流，不再送出其他事件。空資料仍為成功 `result`，保留 columns 並使用空 rows。

StreamingResponse 的迭代器先 yield 完整 `sql` 事件，待 ASGI 發送該 chunk 後才恢復並開始 DB 執行。API 設定 `Cache-Control: no-cache, no-transform` 與 `X-Accel-Buffering: no`；部署文件要求此路由停用代理 buffering 與整包壓縮。這是伺服器送出順序保證；不新增瀏覽器收件 ACK 協定。

替代方案為前端先呼叫 `/sql` 再把 SQL 送回執行端點，會增加 SQL 交接信任邊界與兩次請求協調；既有 JSON `/query` 則無法提前顯示 SQL。採單一伺服器請求能維持相同核准 SQL 的完整生命週期。

### 2. 拆出執行已核准 generation 的共用方法

在 application 層拆出執行已核准 `SQLGenerationResponse` 的方法，沿用 `SQLExecutionResult`、row bounding 與 execution trace。既有 `run()` 仍先 generate 再呼叫此方法，維持舊行為。新增的查詢串流 service 則先 generate、送出 SQL 事件，再把同一份 generation 交給方法執行。

共用方法檢查 supported、非空 SQL 與設定 profile allowlist，重用既有 SQL policy；不得重新呼叫生成 workflow，也不接受使用者送來的 SQL。Workflow 繼續只產生 SQL，DB 操作位於 application service 與 adapter。

SSE framing 留在 API 層，application 層提供具型別的 SQL／結果階段資料。同步 LLM／DB 呼叫透過 threadpool 執行，避免阻塞 ASGI event loop。不同請求各自持有 generation、cursor 與結果，不能共享可變查詢狀態。

### 3. 選配 SQLAlchemy／pymssql adapter 與明確 env 設定

新增 `infrastructure/database/sql_server.py` 的 callable adapter，實作 `(datasource, sql) -> (columns, rows)`；新增選配安裝 extra `sqlserver`。選擇 `SQLAlchemy`／`pymssql` 以對接既有 executor 的簡單同步契約；不引入 ORM 或應用程式自建 pool。使用者指定沿用既有 `mssql+pymssql` 連線方式。SQLAlchemy 僅組裝 Engine／URL，使用 NullPool 停用持續連線池；每次 raw_connection 取得獨立 DBAPI connection，以 cursor 執行未改寫的核准 SQL。支援平台的 pymssql wheel 已包含 FreeTDS，不需要安裝 ODBC；從原始碼建置時仍須 FreeTDS 與編譯工具。

由明確選定 `.env` 或 process environment 讀取以下欄位；已先提供空白模板，暫不包含任何憑證：

| 欄位 | 用途／空白時行為 |
|---|---|
| `CPEA_SQLSERVER_CONNECTION_STRING` | 完整 `mssql+pymssql://` SQLAlchemy URL；空白表示未啟用內建 adapter |
| `CPEA_DATASOURCE_ID` | 已有的邏輯 datasource binding；也可由 deployment YAML 提供 |
| `CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS` | 登入逾時，空白採 5 秒 |
| `CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS` | 查詢逾時，空白採 30 秒 |

URL 包含 username、password、host、port 與 database；特殊字元必須 URL encode。設定採 pymssql SQL 登入、UTF-8 與 TDS 7.4；timeout 透過 connect_args 的 login_timeout／timeout 傳入，使用 autocommit 與 read_only 提示。要求 encryption=require，預設套件內 FreeTDS 設定使用 system CA 並驗證 hostname；可透過 process environment 或明確 env file 的 FREETDSCONF／FREETDS 指定自訂設定，不因 driver 切換自動放寬憑證驗證。設定 dataclass 的秘密欄位使用 `repr=False`，不把完整連線字串輸出到 log 或 API。

設定仍遵守 process environment、明確 env file、預設值的順序。不要另外呼叫全域 `load_dotenv()` 或繞過既有設定層。空白連線字串維持 generation-only；有連線字串但缺 binding、沒有選配 driver 或 timeout 無效時，回報不含秘密的設定診斷。建立 app／runtime 可驗證設定但不得連 DB。

明確注入 executor 時優先使用注入物件，不初始化內建 adapter。未注入時，bootstrap 根據非空連線字串與 datasource binding 建立 adapter。Adapter 拒絕與綁定不符的 datasource，不把請求參數當成 database 名稱。

### 4. 有限讀取、唯讀與資料表示

DB 帳號僅授權 profile 核准 View 的 SELECT。Adapter 在執行前沿用 allowlist 與唯讀 SQL 檢查，但不將 driver 的唯讀提示視為資料庫權限替代。每次請求使用獨立 connection／cursor，成功或失敗均透過 `finally` 關閉；不呼叫 commit、不重試、不修改 SQL。

使用有限的 `fetchmany(max_rows + 1)` 保留既有 application 超量裁切判斷，避免 `fetchall()`。Compiler 仍以 `TOP(max_rows)` 限制結果；若剛好達上限而沒有額外一列，不能宣稱一定存在未回傳資料。`rows_truncated` 只表示實際觀察到超量裁切，另以 `row_limit` 告知查詢上限；UI 顯示達上限提示。

新增串流的 JSON 編碼明確處理 NULL、Unicode、日期／時間 ISO 8601、Decimal 精確字串、UUID 字串與 binary 的 `base64:` 字串；其他無法表示的型別視為錯誤。編碼規則放在串流介面，避免改變舊 JSON API。Result 完整編碼成功後才送出事件，避免半個資料事件後接錯誤。此新流程不呼叫 `AnswerSynthesisService`。

### 5. 固定錯誤與終止規則

生成失敗／unsupported、SQL policy 拒絕、缺 DB 設定、driver 例外、逾時、結果編碼錯誤皆使用同一錯誤文字。驗證與 preflight 可在串流開始前回傳適當 HTTP status，body 僅含固定 message；SSE 開始後則回傳 `error` 事件。新端點須覆寫框架預設 validation detail，避免不小心顯示額外技術錯誤。

Gradio 畫面監測 queue 傳輸失敗、非成功 HTTP、資料格式錯誤或未完成就斷線時，也顯示完全相同文字並恢復輸入；不重新提交查詢。若 SQL 已顯示後 DB 失敗，保留本次問題與 SQL，結果區顯示錯誤；生成前失敗則不顯示 SQL。只有使用者再次按送出才重新執行。

內部保留既有 trace 階段與可診斷分類，server log 遮蔽憑證且不記錄完整問題、SQL、rows 或原始 driver 例外。發現客戶端斷線後不開始後續階段；已開始的同步 driver 工作不保證立即取消，仍須在 timeout 或工作結束後釋放資源。

### 6. 同服務單頁與單次畫面狀態

FastAPI 在 `/` 掛載 Gradio Blocks，不增加獨立前端建置流程；以 Gradio 元件提供問答、SQL 與表格，外觀採框架預設。中央區域顯示本次問題、SQL 與表格，底部輸入框支援 Enter 送出、Shift+Enter 換行；中文輸入法 composition 中不得誤送出。

```text
待輸入 → 產生 SQL 中 → 顯示 SQL／查詢中 → 顯示結果
                     ↘ 錯誤             ↘ 錯誤
```

提交新問題時立即清空上一題的 SQL、結果與錯誤，保留新問題；處理中停用送出避免同頁重複請求。前端阻擋處理中的重複提交，各 Gradio 暫存工作階段也使用獨立 lock，避免舊查詢覆蓋較新狀態。空白問題在瀏覽器拒絕送出。

畫面以 Gradio generator 分段更新 SQL 與結果，UTF-8 與傳輸 chunk 由框架處理。問題元件停用 Markdown，且文字先 HTML escape，SQL 使用 Code 元件，資料表使用純文字欄位，避免 HTML 注入。零列顯示「查無資料」；表格可水平捲動，手機可正常輸入與閱讀。狀態文字提供可存取的 live region。

狀態僅在頁面與 Gradio 暫存工作階段的記憶體，重新整理清空；請求不帶 history，不寫問答 DB、瀏覽器 storage 或 checkpoint。套件打包必須包含 Gradio UI 模組；在 checkout 外安裝 wheel 與依賴後也可提供首頁。

## Risks / Trade-offs

- 代理 buffering 延後 SQL 顯示 → 明確回應 header、部署設定與實際 HTTP 分段順序驗證；完整 TestClient 回應不足以證明 SQL 已先送出。
- 憑證尚未提供 → 先完成注入 fake driver／executor 的離線驗證；GMS2 實測列為設定完成後的工作，不使用猜測連線資訊。
- 固定錯誤文字降低使用者診斷資訊 → 維持伺服器內部已遮蔽的階段診斷，畫面只顯示指定文字。
- 同步 DB 操作在斷線後仍可能完成 → 使用查詢 timeout 與確實資源回收，不承諾 driver 無法保證的強制取消。
- Query TOP 上限無法證明完整筆數 → 明示 row_limit，僅對實際觀察到的裁切設定 rows_truncated。
- 新 SQL Server 依賴增加安裝需求 → 選配 extra 與延遲 import，保留沒有 driver 的生成模式。

## Migration Plan

1. 先提供空白 `.env`／`.env.example` 欄位，保留目前 LLM 與 profile 設定。
2. 實作選配 adapter、設定組裝及共用已核准 SQL 執行方法，驗證舊 API 相容。
3. 加入新串流端點與單頁，完成離線協定、DB 資源與瀏覽器驗證。
4. 使用者填入實際連線字串與 binding，依明確選定 `.env` 啟動，在核准 View 上做 GMS2 唯讀 smoke test。
5. 回退時移除內建 adapter 的連線設定並使用舊入口；無資料庫結構或問答資料需要 migration。

## Open Questions

- GMS2 實際 SQL Server／database、驗證方式與憑證狀態由使用者補入 `.env`；不阻擋離線實作，但是真實連線驗證的前置條件。
- 實際部署使用 Linux 或 Windows，以及是否經過反向代理，會影響 pymssql wheel／FreeTDS、TLS 與串流設定；文件提供兩平台前置需求，於 live smoke test 確認實際環境。

### 使用者實作選擇：Gradio

使用者指定使用 Gradio，不需客製外觀，使用體驗類似 ChatGPT 即可。首頁採 Blocks／Chatbot／Code／Dataframe 與 generator；SSE API 保留既有規劃的嚴格順序與固定錯誤契約。鍵盤／composition、立即清除舊畫面與固定傳輸錯誤使用少量套件內 JavaScript 補足框架行為，不建置獨立前端。

### 使用者實作選擇：mssql+pymssql

使用者指定改用既有 SQLAlchemy 的 mssql+pymssql，取代本變更初版的 pyodbc。保留相同 env 欄位與 executor port，連線值改為 SQLAlchemy URL；本地已填入的 ODBC 值以程式轉換，未輸出或複製至文件。原 ODBC sudo 安裝腳本移除。

pymssql／FreeTDS 的 login_timeout 與 timeout 有程序共用效果，FREETDSCONF 也屬程序設定；單一服務使用相同設定，不承諾同程序中不同部署各有獨立 timeout／TLS policy。不同設定應使用不同程序。每次查詢仍使用獨立 connection／cursor，並行 SQL 與 rows 不共享。SQLAlchemy／pymssql 可進行連線初始化與 metadata 查詢，核准的業務 SQL 仍只執行一次、不自動重試。
