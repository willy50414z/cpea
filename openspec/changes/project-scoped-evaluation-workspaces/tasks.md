## 1. 盤點與保護現有資料

- [x] 1.1 盤點 `integrations/private/gms2`、`integrations/private/retail`、三份 `evaluations/datasets` 題庫、`src/cpea/resources/demo` 與既有 `artifacts`；記錄應保存檔案的路徑、大小及 SHA-256，區分私有資產、合成 fixture 與歷史產物。
- [x] 1.2 更新 `.gitignore` 與 wheel／sdist 包裝規則，確認 `projects/` 內的 `.env`、契約、題庫、樣本與評估產物不會進入公開版控或通用發行包。

## 2. 專案資料與設定搬遷

- [x] 2.1 建立受控 `projects/<project-id>/` 解析器，限制 ID 格式與路徑邊界，並在缺少專案或必要檔案時於外部呼叫前報錯。
- [x] 2.2 將 GMS2 的 manifest、catalog、views、samples、README 與本機 FreeTDS 設定，及 Retail 的 manifest、catalog、views 與 contract review 複製到對應專案目錄；逐檔比對雜湊並驗證兩個 catalog 載入與相對引用後，才移除舊工作副本。
- [x] 2.3 讓專案入口選取 `<project>/.env` 並明確綁定同目錄 profile；拒絕程序環境或 env 檔中會改變專案身分的衝突路徑，保留一般設定既有優先順序與不輸出機密的錯誤訊息。
- [x] 2.4 移除正式 runtime 的隱含 demo fallback，將合成 demo 移為明確選用的範例／測試資產，更新受影響的安裝與執行測試。

## 3. 單一題庫與真實模型入口

- [x] 3.1 定義含固定 `case_id`、`category`、問題與完整預期檢查的單一 `cases.jsonl` 契約，加入唯一性、欄位、預期檢查與 profile 對應驗證。
- [x] 3.2 對照現有 GMS2 core 與 colloquial 題庫，標出重複、衝突及錯誤預期值（含 `GN2300`／`ZX100`）；取得核對後的正式題目，整合至 `projects/gms2/evaluations/cases.jsonl`，保留來源紀錄。Retail 題庫缺席時明確拒絕評估。
- [x] 3.3 實作 `cpea-eval --project <id> --runs <n> --concurrency <n>`，自動選用專案 `.env`、profile、題庫與模型，固定為真實模型模式，且不要求使用者指定輸出路徑。
- [x] 3.4 產生 UTC 微秒時間加 Git 短 SHA 的 run ID，建立不可覆寫的 `projects/<id>/artifacts/evaluations/<run-id>/`，保留乾淨 worktree 與受控私有輸出前置檢查。

## 4. 執行資料與報告

- [x] 4.1 在 run metadata 記錄 project、程式 SHA、非機密有效設定、模型／deployment、契約與題庫指紋、預定與完成次數；保證 `.env` 機密不落入輸出。
- [x] 4.2 保留逐次呼叫與結果紀錄，補上分類別正確率、錯誤率、耗時、重複執行一致性與 provider token 完整度；缺失用量維持空值。
- [x] 4.3 由私有紀錄生成 `overview.md`、逐題 Markdown、CSV 彙總；確認可分享摘要不嵌入原始 request、response、SQL literals 或結果列，且提早停止時不把未執行題目當通過。

## 5. 相容性、文件與驗證

- [x] 5.1 更新目前會執行的路徑引用，包括 `README.md`、`.env.example`、`evaluations/README.md`、`docs/architecture.md`、`docs/sql_generation_stability.md`、相關測試及入口設定；歷史 OpenSpec 與封存資料保留原始時間脈絡。
- [x] 5.2 驗證專案隔離、錯誤 profile 覆蓋、缺少題庫、run ID 撞名、報告重建、敏感欄位排除及顯式合成 fixture；測試中可注入 stub，但不得產生正式專案實測基準。
- [x] 5.3 比對搬遷前後私有 profile 檔案與 catalog 行為，檢查 Git 狀態及 wheel／sdist 內容；確認舊 `artifacts/evaluations/`、`artifacts/stability/` 與原 PoC 封存未被改寫。
- [ ] 5.4 記錄新舊指令與資料路徑的遷移方式、已知不相容點及回復步驟；由具備專案有效憑證的環境另行執行真實模型驗收並保存輸出。
