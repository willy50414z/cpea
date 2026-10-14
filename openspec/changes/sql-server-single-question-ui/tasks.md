## 1. 設定與選配依賴

- [x] 1.1 在現有 `.env` 與 `.env.example` 補上空白 SQL Server 連線、datasource、登入與查詢 timeout 欄位，保留原內容與換行格式
- [x] 1.2 新增 DB 設定模型及既有 env 層整合，驗證空白預設、process environment 優先順序、正數 timeout 與秘密欄位隱藏
- [x] 1.3 新增 `sqlserver` 選配 extra 與 `SQLAlchemy`／`pymssql`，更新 lockfile，保留未安裝 driver 的 generation-only 模式

## 2. SQL Server adapter 與 bootstrap

- [x] 2.1 實作 SQLQueryExecutor adapter，綁定 datasource 與 profile allowlist，執行前驗證唯讀 SQL
- [x] 2.2 加入登入／查詢 timeout、有限 fetchmany、cursor／connection 的 finally 釋放與遮蔽 driver 錯誤，不 commit 或自動重試
- [x] 2.3 在 bootstrap 依完整設定組裝 adapter，注入 executor 優先，建立 runtime／app 不連 DB
- [x] 2.4 以 fake driver 驗證單次執行、錯誤 binding／View 拒絕、超量讀取、timeout、各失敗階段清理與並行請求隔離
- [x] 2.5 驗證 GMS2 profile 與合成替代 profile 的設定切換，不改動私有 View 契約或假設 database 名稱

## 3. 分段查詢 application service

- [x] 3.1 從 SQLExecutionAgent 拆出執行已核准 generation 的共用方法，保留舊 run 行為、attempts、row bounding 與 trace
- [x] 3.2 新增具型別的 SQL／結果階段流程，以空 history 生成一次、提供 SQL 階段後才執行同一份 SQL；不呼叫 AnswerSynthesisService
- [x] 3.3 驗證 unsupported／policy 拒絕不呼叫 DB、成功 SQL 一致與單次執行、零列結果，以及 execution trace

## 4. POST 串流 API

- [x] 4.1 新增 request-only DTO 與 `/api/assistant/query/stream`，拒絕空白及額外欄位，保留舊 API 契約
- [x] 4.2 實作 sql／result／error 的 SSE framing 與唯一終止事件，加入快取／buffering header 並將同步操作移至 threadpool
- [x] 4.3 統一新端點 validation、preflight、generation、DB 與編碼失敗的固定 message，不洩漏技術例外或憑證
- [x] 4.4 實作 NULL、Unicode、日期、Decimal、UUID、binary 的明確 JSON 編碼與 row_limit；完整編碼後才送出結果
- [x] 4.5 加入斷線偵測與階段停止，驗證已開始 driver 工作最終釋放資源，無自動重試
- [x] 4.6 以受控 ASGI send 與暫停中的 executor 驗證 sql body 已先送出才進入 DB；再以實際 HTTP 串流確認 DB 未完成時可讀到 SQL
- [x] 4.7 驗證 sql→result、sql→error、error 的事件序列，包含 malformed payload、缺依賴、unsupported、timeout、序列化失敗及 secrets 不出現在回應

## 5. 單頁 UI 與靜態資源

- [x] 5.1 提供套件內 Gradio Blocks 首頁，由既有 FastAPI 掛載，實作中央最新問答與底部輸入框
- [x] 5.2 以 Gradio generator 分段更新 SQL，再顯示結果表格／查無資料／上限提示；驗證中文傳輸
- [x] 5.3 實作最新問題取代、暫存工作階段狀態、固定錯誤文字、送出停用與同工作階段重複請求隔離；傳輸失敗不顯示技術例外
- [x] 5.4 使用 Gradio 輸入元件驗證 Enter／Shift+Enter、中文 composition、手機版捲動與狀態可存取性；問題、SQL 與資料皆安全呈現
- [x] 5.5 以瀏覽器驗證慢速 DB 先看到 SQL、成功／零列／各階段錯誤、第二題取代、重新整理清空、重複提交與 HTML 字串安全呈現

## 6. 相容性、打包與文件

- [x] 6.1 執行既有及新增相關 pytest，確認舊 JSON API、CLI、graph factory、executor 注入及 generation-only 未回歸
- [x] 6.2 建置 wheel／sdist，在 checkout 外驗證 Gradio 首頁與框架靜態資源；確認不含私有 profile、`.env` 或憑證
- [x] 6.3 更新繁體中文 README／架構文件，說明選配 driver、Linux／Windows pymssql wheel／FreeTDS 前置需求、env SQLAlchemy URL 填法、明確 env 啟動與代理串流設定

## 7. 使用者設定完成後的 GMS2 驗證

- [x] 7.1 使用者填入連線字串與 datasource binding 後，確認實際 profile、資料庫、驗證方式與核准 View 的唯讀權限；不把連線資訊複製到文件
- [x] 7.2 在實際 GMS2 執行唯讀 smoke test，確認先收到 SQL 再收到資料、結果欄位／數值正確及固定錯誤行為，記錄不含敏感資料的驗證結果
