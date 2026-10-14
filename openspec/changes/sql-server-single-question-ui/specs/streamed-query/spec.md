## ADDED Requirements

### Requirement: 單次獨立請求與相容 API

系統 SHALL 新增 `POST /api/assistant/query/stream`，只接受非空白、長度 1 至 4000 的 `request`，MUST 拒絕額外 history、SQL、datasource 或檔案路徑欄位。請求 MUST 以空 history 執行且不建立問答保存或 checkpoint。既有 `/api/assistant/sql` 與 `/api/assistant/query` 的 request 與成功回應契約 MUST 保留。

#### Scenario: 獨立連續問題

- **WHEN** 同一使用者先後送出兩個有效問題
- **THEN** 第二次 generation 不包含第一次問題、SQL 或結果

#### Scenario: 禁止客戶端控制 SQL

- **WHEN** 請求包含 SQL、history 或 datasource 欄位
- **THEN** 新端點拒絕請求，使用固定錯誤訊息，且不呼叫 LLM 或 executor

#### Scenario: 舊 API 呼叫

- **WHEN** 既有有效 payload 傳送到原本的 JSON API
- **THEN** 回應格式、注入 executor 行為與成功序列化維持相容

### Requirement: SQL 先於 DB 執行送出

新端點 SHALL 使用 `text/event-stream` 回應。單次 generation 產出的 SQL 通過既有 supported、query plan、SQL policy 與 profile allowlist 驗證後，系統 MUST 先將完整 `sql` 事件送入 ASGI response body，才開始 DB 執行。系統 MUST 執行同一份已送出的 SQL 一次，不得重新生成。`sql` payload SHALL 包含 `sql` 字串。

#### Scenario: 可觀察的先送 SQL 順序

- **WHEN** 核准 SQL 已生成且注入 executor 在執行時暫停
- **THEN** ASGI body 已送出完整 sql 事件，executor 尚未完成，而客戶端可以先讀取並顯示 SQL

#### Scenario: generation 不支持問題

- **WHEN** generation 回傳 unsupported 或 SQL 不通過驗證
- **THEN** 系統不送出 sql 事件、不呼叫 DB，回傳固定 error 並結束

### Requirement: 結果與終止事件

DB 取得資料後系統 SHALL 回傳完整 `result` 事件，包含 `columns`、`rows`、`rows_truncated` 與 `row_limit`，不額外呼叫 LLM 整理文字答案。系統 MUST 在資料完成 JSON 編碼後才送出 result。成功串流 SHALL 僅包含 `sql → result`；失敗串流 SHALL 僅包含 `error` 或 `sql → error`。`result` 或 `error` MUST 為唯一終止事件，送出後 MUST 關閉串流。

#### Scenario: 成功取得資料

- **WHEN** 同一份核准 SQL 執行成功
- **THEN** 系統在 sql 事件之後回傳欄位、資料列與限制資訊，且不呼叫 AnswerSynthesisService

#### Scenario: 零列資料

- **WHEN** SQL 成功但查無資料
- **THEN** 系統送出含 columns 與空 rows 的 result，正常關閉且不送出 error

#### Scenario: 資料表示

- **WHEN** 結果包含 NULL、Unicode、日期／時間、Decimal、UUID 或 binary
- **THEN** 串流使用 null、UTF-8 文字、ISO 8601、精確十進位字串、UUID 字串及 base64: 字串，維持欄位與資料列對應

#### Scenario: 達到查詢上限

- **WHEN** SQL TOP 限制返回恰好 max_rows 列且未觀察到額外資料
- **THEN** 系統回傳 row_limit 但不僅因列數等於上限而宣稱 rows_truncated 為真

### Requirement: 新流程固定錯誤契約

新端點在 request validation、preflight、生成、治理、DB 執行、timeout 或序列化失敗時，對外 message MUST 精確為「執行錯誤請再試一次」。串流開始前 SHALL 使用適當的失敗 HTTP status 與固定 message body；開始後 SHALL 使用唯一 `error` 終止事件。系統 MUST NOT 對前端輸出原始例外、連線字串、traceback 或框架 validation detail，MUST NOT 自動重試。內部階段診斷 SHALL 遮蔽憑證，且不記錄完整問題、SQL 或結果資料。

#### Scenario: 串流前驗證或依賴失敗

- **WHEN** payload 無效或 execution preflight 發現缺少 executor／binding
- **THEN** 新端點回傳失敗 status 與固定 message，且不呼叫 LLM 或 DB

#### Scenario: SQL 已送出後 DB 失敗

- **WHEN** 已送出 sql 事件後 DB 執行或結果序列化失敗
- **THEN** 串流只再送出固定 error 事件並結束，不重新生成或執行

### Requirement: 串流傳輸與斷線生命週期

新路由 SHALL 提供停用快取與代理 buffering 的回應設定，部署說明 MUST 明示關閉此路由的 buffering／整包壓縮。同步模型與 DB 呼叫 MUST 不阻塞 ASGI event loop。系統在偵測客戶端斷線後 MUST 不開始下一個階段；已啟動的 driver 工作 SHALL 受 query timeout 約束並最終釋放資源，不承諾即時強制取消。

#### Scenario: SQL 等待期間斷線

- **WHEN** 系統已偵測客戶端斷線且 DB 執行尚未開始
- **THEN** 系統不開始 DB 查詢，不自動重試

#### Scenario: DB 執行期間斷線

- **WHEN** DB 查詢已啟動時偵測斷線
- **THEN** 系統不開始後續階段，DB 工作在完成或 timeout 後釋放資源
