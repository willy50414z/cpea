## Why

目前客戶 View 契約、評估題庫、模型設定與執行結果分散在不同目錄，執行者必須手動配對路徑，容易用錯契約或題庫。以專案為單位整理資料與評估入口，可以讓每次真實模型測試有明確的來源、設定與可追溯結果，也為日後 Web 呈現建立穩定資料邊界。

## What Changes

- 新增 `projects/<project-id>/` 私有專案工作目錄，集中該專案的 View profile、單一分類題庫、專屬 `.env` 與評估產物；將現有私有 integration 資料遷入，保留原始資料與 provenance。
- 新增以 `--project`、`--runs`、`--concurrency` 為主要使用介面的真實模型評估指令。專案 ID 決定 profile、設定、題庫與輸出位置；指令不要求手動指定 env、題庫、模型或輸出目錄，也不產生假模型的正式結果。
- 每次執行在專案內建立獨立且不可覆寫的報告目錄，以 UTC 時間和 Git 短 SHA 組成 run ID；保留程式版本、View 契約與題庫內容指紋、實際模型設定、逐次結果、耗時及 provider 回報的 token 用量。報告依題目分類呈現正確率與重複執行穩定性。
- **BREAKING**：移除未指定 profile 時自動載入 bundled demo 的正式執行路徑；未選定有效專案或 profile 時提供清楚的設定錯誤。合成範例改作獨立測試／教學資產。
- 保留檔案作為本階段的契約、題庫與原始評估紀錄來源。未來 Web 可讀取受控報告；資料庫、Web 編輯、身分與授權不在此變更實作範圍。

## Capabilities

### New Capabilities

- `project-workspaces`: 定義私有專案識別、資料布局、專案設定解析及來源邊界。

### Modified Capabilities

- `quality-tooling`: 將專案題庫、真實模型評估入口、run ID、專案內報告與可追溯 metadata 納入品質工具契約。
- `standalone-runtime`: 移除正式執行時未指定 profile 的隱含 demo fallback，要求明確 profile 選擇。

## Impact

- 影響 profile loader 的預設行為、評估 CLI／runner／報表、設定載入、測試資產、私有資料遷移、`.gitignore`、wheel／sdist 排除規則及使用文件。
- 現有使用預設 demo 或舊評估指令預設路徑的腳本需要改用明確專案／profile；既有歷史結果保留原樣，不重新標示為新格式的實測基準。
- 不新增資料庫 schema、機密儲存服務或 Web API；不將客戶資料、`.env` 或原始評估紀錄放入通用發行包。
