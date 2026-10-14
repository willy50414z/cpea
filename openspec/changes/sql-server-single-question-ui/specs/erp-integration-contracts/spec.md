## MODIFIED Requirements

### Requirement: External SQL executor boundary

Application services SHALL 使用 catalog port 與 SQL executor 契約，不依賴原專案的具體資料庫模組。 系統 SHALL 保留部署方注入 executor 的能力，並 SHALL 允許 bootstrap 以明確部署設定組裝選配 SQL Server adapter。Application services MUST NOT 直接依賴 DB driver。執行契約 SHALL 保留 datasource、核准 SQL、columns、rows、單次執行、row bounding 與 trace 語意；串流流程 SHALL 可以執行同一份已核准 generation，而不重新生成 SQL。本次 MUST NOT 新增 ERP schema、migration、應用程式自建 connection pool 或通用 transaction layer。

#### Scenario: Injected executor behavior preservation

- **WHEN** 離線測試注入 fake executor 與明確 datasource binding
- **THEN** executor 僅接收 binding 與核准 SQL 一次，回傳資料保留既有裁切與 trace 行為

#### Scenario: Executor failure

- **WHEN** 注入 fake executor 執行失敗
- **THEN** application 保留既有 execution failure trace，且不要求 LLM 修復或重跑 SQL

#### Scenario: Configured SQL Server adapter

- **WHEN** 未注入 executor 且部署提供完整 SQL Server 設定與 datasource binding
- **THEN** bootstrap 透過相同 port 組裝 adapter，application 使用既有受治理的執行語意

#### Scenario: Streamed approved SQL

- **WHEN** 串流 service 已生成並送出核准 SQL
- **THEN** 共用執行方法只執行該份 generation 的 SQL，保留 attempts、row bounding 與 trace，不再次生成
