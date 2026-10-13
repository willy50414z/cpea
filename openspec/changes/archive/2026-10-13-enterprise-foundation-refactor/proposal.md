## Why

CPEA 從原專案的 PoC 分離後，仍依賴原專案的 import、環境設定、資料庫執行器與特定企業 schema，無法形成可獨立交付的產品。需要先建立可安裝、可設定、可替換整合與可回歸驗證的架構，為後續企業級能力提供明確接入位置。

## What Changes

- 建立獨立 Python 套件、依賴鎖定、API／CLI／LangGraph 啟動入口與明確的設定載入機制。
- **BREAKING**：正式 import namespace 改為 `cpea`，原 `assistant.*` import、腳本位置與隱式上層 `.env` 載入方式依遷移文件更新；HTTP 路徑與既有成功回應欄位維持相容。
- 將 `ref/db_schema` 遷移為具版本與驗證規則的 integration 契約；核心解除 `gms2`、`JHD` 與原專案路徑的固定假設。
- 定義 catalog／SQL 執行的 ports 與 bootstrap 注入方式。SQL 執行保留既有可注入 callable 的行為；未注入執行器時明確回報未設定，移除原專案的隱式 fallback。
- **BREAKING**：SQL 查詢執行需要由部署端明確注入既有執行器；本次不提供新的資料庫 adapter，預設 standalone 安裝不宣稱具備真實 DB 查詢能力。
- 將 graph 明確歸屬 `workflows/text_to_sql/sql_generation.py`；分開 API DTO、領域模型、LLM 結構化回覆與執行 trace。
- 分開確定性測試、模型評估題庫與執行結果，修復缺失的 graph factory 與評估解析入口。
- 交付企業身分／context、授權、稽核、機密、資源限制與隔離的設計文件及未來接入契約；不實作登入、政策判定、稽核保存或資料庫相關功能。
- 另建 `docs/refactoring_plan.md`，保留 `docs/dev_plan.md` 作為原功能開發計畫；重構計畫以交付門檻安排，不沿用一個月 PoC 時程作為企業級承諾。
- 範圍排除：新業務 workflow、複雜任務拆解、跨 View JOIN、實際 ERP API 串接、DB driver／連線池／交易、新資料庫或資料表、ORM／migration、權限／稽核持久化與正式多租戶服務實作。

## Capabilities

### New Capabilities

- `standalone-runtime`: 獨立安裝、設定載入、組裝依賴與可驗證的 API／CLI／Graph 入口。
- `erp-integration-contracts`: 可替換的整合契約與 catalog／執行器邊界，維持既有單一 View MSSQL 查詢語意。
- `workflow-boundaries`: 明確的 workflow 責任、模型歸屬與現有 HTTP 行為相容性。
- `quality-tooling`: 可重複的功能基準、確定性回歸、模型評估與產物管理。
- `enterprise-extension-design`: 企業級 context、授權、稽核與維運的設計交付，以及設計與實作狀態的揭露。

### Modified Capabilities

無。專案尚無既有 OpenSpec 主規格；以上規格包含本次首次正式記錄的既有能力約束。

## Impact

- 影響根目錄模組、`application/`、`domain/`、`graph/`、`infrastructure/`、`llm_tools/`、`ref/` 與 `eval/` 的位置及依賴；增添套件、設定範例、測試、評估與文件結構。
- 既有模型供應商、檢索方式、單一 View compiler、欄位政策、拒絕流程與 trace 為遷移基準，不增加 SQL dialect 或查詢能力。
- 原專案沒有一併移入的測試須整理為新專案的回歸資產；原客戶 samples／評估結果須盤點後決定私有保存、去識別或合成 fixture，避免直接成為產品發行資料。
- 本次交付建立企業級擴充基礎；權限與稽核僅設計，真實 DB／API adapter 未提供，不構成正式商用或共享多租戶安全驗收。
