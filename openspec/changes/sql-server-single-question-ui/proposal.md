## Why

CPEA 已具備受治理的 MSSQL 產生能力，但尚無可直接設定使用的 SQL Server adapter 與問答頁面。本次以既有 GMS2 profile 接上真實資料庫，讓使用者送出獨立問題後先看到 SQL，再看到查詢結果，且不保存問答紀錄。

## What Changes

- 新增可透過明確選定的 `.env` 設定 SQL Server 連線的 adapter，實作既有 `SQLQueryExecutor` 介面，保留外部 executor 注入能力。
- 以 `integrations/private/gms2/` 的既有 View 契約作為接線案例；實際 database、帳號與 datasource binding 由部署設定提供。
- 新增 POST 串流問答 API：SQL 通過既有治理與驗證後先回傳 `sql` 事件，接著只執行這份 SQL 一次，取得資料後回傳 `result` 事件。
- 新增以 Gradio Blocks 實作、使用體驗類似 ChatGPT 的單頁介面；每次問題獨立，僅保留最新問題、SQL 與查詢結果，不使用問答資料庫、localStorage、sessionStorage 或 workflow checkpoint。
- 新流程任何失敗均在前端顯示固定文字「執行錯誤請再試一次」，不提供技術例外、不自動重試。已收到的本次 SQL 可以保留。
- 第一版答案為查詢結果表格，不額外呼叫 LLM 產生文字摘要，確保 DB 資料取得後立即回傳。
- 先提供空白 DB 連線環境變數供使用者補入；既有 `/api/assistant/sql` 與 `/api/assistant/query` 的回應契約維持相容。

## Capabilities

### New Capabilities

- `sql-server-adapter`：SQL Server 連線設定、唯讀執行、逾時、資源釋放、結果格式與 GMS2 案例接線。
- `streamed-query`：單次問答的 SQL／資料分段串流、單次執行、終止事件與固定錯誤訊息。
- `single-question-web-ui`：單頁輸入、最新問答取代、SQL 即時呈現、表格與錯誤狀態。

### Modified Capabilities

- `erp-integration-contracts`：調整 executor 邊界要求，允許產品提供選配 SQL Server adapter，同時保留 port、注入、單次執行與治理限制。
- `standalone-runtime`：擴充 bootstrap，依明確 DB 設定組裝選配 adapter，保留無 DB 設定時的 generation-only 模式。

## Impact

- 涉及 `config/`、`bootstrap.py`、`application/services/sql_execution.py`、新增查詢串流 application service、`interfaces/api/` 與套件內的 Web 靜態資源。
- 新增 `/api/assistant/query/stream` 與首頁 `/`；串流與既有 JSON API 並存，text-to-sql graph 繼續只負責 SQL 產生。
- 新增 Gradio 與選配 `SQLAlchemy`／`pymssql` dependency，支援平台使用內含 FreeTDS 的 pymssql wheel，不需 ODBC；更新 lockfile、安裝／啟動說明與 wheel 靜態資源驗證。
- 使用既有私有 GMS2 profile；不將客戶契約或連線資訊加入可分發套件，不新增 ERP schema、migration 或跨 View JOIN。
- 使用者補齊 `.env` 後才能做真實 DB 驗證；離線測試使用合成 profile 與注入 executor，不宣稱已連上 GMS2。
