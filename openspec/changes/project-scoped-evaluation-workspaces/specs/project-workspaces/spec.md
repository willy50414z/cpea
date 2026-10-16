## ADDED Requirements

### Requirement: 明確的私有專案工作目錄
系統 SHALL 以穩定 project ID 選定一個受控的專案根目錄，其中包含可載入的 View profile、專案專屬環境設定與單一評估題庫。project ID MUST 為受限制的識別字，不得作為任意檔案路徑或跨越專案目錄的輸入。專案目錄及其 `.env`、客戶契約、題庫與產物 MUST 排除於通用發行包及公開版本控制。

#### Scenario: 選取專案
- **WHEN** 操作者指定已設定的 project ID
- **THEN** 系統從同一個受控專案目錄解析 profile、`.env`、題庫及產物根目錄

#### Scenario: 無效或跨目錄識別字
- **WHEN** 操作者提供未知 project ID、路徑分隔符或跳出專案根目錄的識別字
- **THEN** 系統在讀取其他專案資料或呼叫模型前拒絕請求

### Requirement: 專案身分與設定一致
專案評估入口 SHALL 明確綁定所選專案的 profile，不得因程序環境或 `.env` 中的另一個 profile／deployment 路徑而改測其他專案。一般模型與資料庫設定 SHALL 使用既有的設定優先順序；衝突的專案身分覆蓋 MUST 產生可操作且不包含機密值的錯誤。

#### Scenario: 設定指向其他 profile
- **WHEN** `--project gms2` 與有效設定中的 profile 路徑指向不同專案
- **THEN** 評估在模型或資料庫呼叫前失敗，並指出身分衝突

#### Scenario: 缺少必要檔案
- **WHEN** 專案缺少 `.env`、manifest、catalog 或正式題庫
- **THEN** 評估在外部呼叫前失敗，指出缺少的檔案類別而不輸出秘密

### Requirement: 專案資料維持可搬遷的檔案來源
本階段 SHALL 以 YAML、JSONL 與私有產物檔案保存契約、題庫及原始評估結果，並提供穩定識別、版本與內容指紋供日後 Web 或資料庫索引使用。此變更 MUST NOT 把客戶契約、評估紀錄或 `.env` 機密搬入 ERP 資料庫，亦 MUST NOT 提供未經專案授權的 Web 讀取介面。

#### Scenario: 未來可索引的 run
- **WHEN** 專案評估完成
- **THEN** run metadata 包含 project ID、契約和題庫的版本或內容指紋，足以在後續系統建立索引而不必推測來源
