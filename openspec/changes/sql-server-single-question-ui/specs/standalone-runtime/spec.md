## MODIFIED Requirements

### Requirement: Composition of existing services

系統 SHALL 提供 bootstrap 邊界，注入 settings、catalog、retrieval、LLM 與選配外部 SQL executor。未注入 executor 且明確部署設定啟用 SQL Server 時，bootstrap SHALL 組裝內建選配 adapter 與 datasource binding；明確注入 executor MUST 優先於內建 adapter。API 與 CLI MUST 使用此邊界，不得在核心固定企業 datasource。沒有 executor 設定時 SQL 產生 SHALL 仍可使用。建立 runtime、import 或 app factory MUST NOT 因新增 adapter 而建立 DB 連線。

#### Scenario: Explicit injected dependencies

- **WHEN** bootstrap 接收合成 profile、stub LLM 與 fake executor
- **THEN** API 與 CLI 使用注入依賴，不 import `app.core.external_db`，不預設為 `JHD`，且不初始化內建 DB adapter

#### Scenario: Configured built-in adapter

- **WHEN** 未注入 executor 且明確 env／deployment 設定提供 DB 連線字串與 binding
- **THEN** bootstrap 建立選配 adapter，DB 連線延後至執行請求才建立

#### Scenario: Generation-only runtime

- **WHEN** DB 連線字串空白且未注入 executor
- **THEN** bootstrap 維持 generation-only，不要求 DB driver、不連 DB，執行入口仍依 unavailable 契約拒絕
