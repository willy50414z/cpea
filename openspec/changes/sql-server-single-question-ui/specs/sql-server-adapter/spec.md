## ADDED Requirements

### Requirement: 明確設定與選配安裝

系統 SHALL 提供選配的 SQL Server adapter，使用 `CPEA_DATABASE_URL` 與明確 datasource binding 設定連線。系統 MUST 遵守既有 process environment、明確 env file、預設值的設定優先順序，且 MUST 提供空白 env 欄位而不包含憑證。連線字串空白時 SHALL 維持未啟用狀態。登入與查詢 timeout SHALL 分別由 `CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS`、`CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS` 設定；空白時分別採 5 秒與 30 秒，非正數或非法值 MUST 拒絕。

#### Scenario: 使用者尚未提供 DB 設定

- **WHEN** 連線字串空白且沒有注入 executor
- **THEN** 系統可以使用生成模式，執行模式依既有 unavailable 契約拒絕，且不使用 fake executor 作為預設

#### Scenario: 明確設定優先順序

- **WHEN** process environment 與指定 env file 都提供同一 DB 設定
- **THEN** 系統使用 process environment 的值，且不自動讀取上層 `.env`

#### Scenario: 部分設定或 driver 不可用

- **WHEN** 連線字串非空但沒有 datasource binding、timeout 無效，或未安裝所需選配 driver
- **THEN** 系統回報不包含秘密的設定診斷，不嘗試任何 LLM 或 DB 呼叫

### Requirement: Port 與唯讀單次執行

Adapter SHALL 實作既有 `(datasource, sql) -> (columns, rows)` 的 `SQLQueryExecutor` 契約，MUST 驗證 datasource 與部署 binding 相符，且 MUST 拒絕未通過既有 SELECT／profile allowlist 政策的 SQL。每次成功執行請求 SHALL 只送出核准 SQL 一次，MUST NOT 自動修復、重新產生 SQL 或重試。部署帳號 SHALL 僅有核准 View 的 SELECT 權限。

#### Scenario: 核准查詢

- **WHEN** adapter 收到符合 binding 與 profile 政策的 SQL
- **THEN** adapter 僅執行該 SQL 一次，依 cursor 欄位順序回傳 columns 與對應 rows

#### Scenario: 錯誤 datasource 或不安全 SQL

- **WHEN** datasource 不符、SQL 為異動指令，或引用非核准 View
- **THEN** adapter 在 DB 執行前拒絕，且不發送 SQL

### Requirement: 有限讀取與資源釋放

Adapter SHALL 使用設定的登入與查詢 timeout，並 SHALL 每次請求取得獨立的 connection／cursor。Adapter MUST 有限讀取至多 `max_rows + 1` 列，交由既有 application row bounding 處理；MUST NOT 使用無界 `fetchall()`。成功、driver 失敗、逾時與已開始工作後的客戶端斷線均 MUST 最終釋放 cursor／connection，且 MUST NOT 呼叫 commit。

#### Scenario: 回傳資料超量

- **WHEN** 注入的 DB driver 回傳超過 max_rows 的資料
- **THEN** adapter 至多取得 max_rows + 1 列，application 僅回傳 max_rows 列並設定 rows_truncated

#### Scenario: 執行失敗與逾時

- **WHEN** connect、execute 或 fetch 發生錯誤或 timeout
- **THEN** 已開啟的 connection／cursor 均被關閉，且不重新執行查詢

#### Scenario: 同時有多個獨立請求

- **WHEN** 兩個使用者同時查詢不同問題
- **THEN** 各請求使用自己的 cursor 與結果，不混用 SQL 或資料列

### Requirement: GMS2 案例接線

系統 SHALL 透過 `CPEA_PROFILE_PATH` 或 deployment 設定載入既有私有 GMS2 profile，並 MUST 由 DB 連線設定取得實際 database 名稱，MUST NOT 把 schema 名稱 `gms2` 當作 database 預設值。Adapter MUST 可由設定切換到其他合法 profile，不要求更改共用程式碼。

#### Scenario: GMS2 與替代 profile

- **WHEN** 部署選定 GMS2 或合成的替代 profile，並提供相符 binding
- **THEN** adapter 依該 profile 核准 View 政策執行，共用程式碼不依賴固定 GMS2 schema

#### Scenario: 分發套件

- **WHEN** 建置 wheel 或 sdist
- **THEN** 套件不包含私有 GMS2 契約、`.env` 或實際連線憑證

### Requirement: SQLAlchemy pymssql 連線與 TLS

內建 adapter SHALL 使用 mssql+pymssql URL 與 NullPool，建立 runtime 時 MUST NOT 連線。套件 SHALL 包含 FreeTDS 預設 TLS 設定，要求加密、system CA 與 hostname 驗證。既有 dotenv 優先順序 SHALL 套用於 FREETDSCONF／FREETDS，自訂相對路徑 SHALL 相對明確 env file 解析。系統 SHALL 說明 pymssql timeout 與 FreeTDS TLS config 的程序共用限制。

#### Scenario: 特殊字元與單次核准 SQL

- **WHEN** 帳密包含特殊字元、URL 指定非預設 port，且 SQL 含 LIKE 百分比字元
- **THEN** adapter 保留解碼後的帳密、port 與原始核准 SQL，不改寫、不重試，且使用 deployment 設定的 timeout

#### Scenario: 安全設定預設

- **WHEN** 部署未另外選定 FreeTDS 設定
- **THEN** adapter 使用套件內要求加密與憑證驗證的設定，不因更換 driver 而停用驗證
