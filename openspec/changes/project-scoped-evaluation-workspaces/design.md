## Context

目前執行時的合成 profile 位於 `src/cpea/resources/demo/`，私有 View 契約位於 `integrations/private/{gms2,retail}/`，兩份 GMS2 reliability 題庫與治理範例位於 `evaluations/datasets/`，runner 與報表程式位於 `evaluations/`，產物位於全域 `artifacts/`。`SchemaCatalog()` 未收到路徑時會載入 demo；治理 runner 的輸出前置檢查只接受全域 `artifacts/evaluations/`。現有私有資料被 Git 忽略，但部分測試及文件直接引用舊路徑。

本變更須保留檔案為資料來源，維持既有單一 View 政策及評分規則。未來 Web 顯示屬於後續工作；目前身分、授權與跨企業隔離仍只有設計，不能將私有題目或原始 trace 直接公開。

## Goals / Non-Goals

**Goals:**

- 一個專案 ID 唯一選定私有 profile、`.env`、單一分類題庫與產物根目錄。
- 提供 `cpea-eval --project <id> --runs <n> --concurrency <n>` 真實模型入口，記錄可比對且不覆寫的結果。
- 將目前目錄、檔案與歷史資料納入明確搬遷表，完成後驗證內容與引用。

**Non-Goals:**

- 本次不建立評估資料庫、Web 編輯器、登入／授權、機密管理服務或 ERP 業務資料表。
- 不自動把過去不同條件下的歷史結果合併成新基準；不以假模型結果代表真實模型品質。

## Decisions

### 專案目錄與身分

採 `projects/<project-id>/`，其中 project ID 為穩定、無路徑分隔符的 slug，由可信 CLI 參數選取，不接受相對路徑或絕對路徑作為 ID。每個目錄包含 `manifest.yaml`、`catalog.yaml`、`views/`、可選 `samples/`、`.env`、`evaluations/cases.jsonl` 及被忽略的 `artifacts/evaluations/`。`profile_id` 是契約識別，`deployment_id` 是部署識別，兩者不必等於 project ID。`database/` 不適合作為上層名稱，因目錄還包含模型、題庫與報告。

`projects/` 預設為私有並排除 Git 與通用 wheel／sdist；可分發的合成範例另放 `examples/` 或測試 fixture。實作須容許從受保護的外部位置提供專案根目錄，不能假定所有客戶資料都會進入 checkout。

### 專案設定解析

CLI 根據 project ID 選取 `<project>/.env` 並明確綁定同一目錄作為 profile root；`.env` 不重複指定 `CPEA_PROFILE_PATH`。模型、embedding 與選配 DB 連線由該 `.env` 與既有設定解析器讀取。既有一般設定仍依 process environment 優先；但 `CPEA_PROFILE_PATH`、`CPEA_DEPLOYMENT_FILE` 等可能改變專案身分的衝突覆蓋在專案評估入口必須被拒絕，避免測到其他客戶。缺少 `.env`、profile 或題庫時，在模型呼叫前失敗。密碼/API key 不寫入 run metadata 或報告。

### 單一題庫與 CLI

每專案使用一份有穩定 `case_id`、`category`、問題與預期檢查的 `cases.jsonl`；分類只供篩選與報告，不把答案送進模型 context。`runs=1` 是單次正確率觀察，`runs>=2` 才計算重複執行穩定性；報告明確標示完成題數與未完成題數。CLI 對使用者只暴露 project、runs、concurrency 三個必要變數；執行模式固定為真實模型。保留內部 stub 注入以做離線程式測試，但其輸出不能混入正式專案報告。

新題庫須由現有兩份 GMS2 reliability JSONL 經逐題校對後合併，不能無條件串接：原 core 首題問題寫 `GN2300`、預期 filter 卻是 `ZX100`。既有治理 JSON 範例與 demo 題庫可留作合成 fixture；使用者重新設計題目後再確立正式 GMS2 題庫。Retail 目前沒有題庫，遷移時不得捏造驗收案例；在提供題庫前 project 評估前置檢查須清楚失敗。

### 執行紀錄與報告

輸出固定為 `projects/<id>/artifacts/evaluations/<run-id>/`。run ID 使用 UTC 微秒時間與 Git `HEAD` 短 SHA，例如 `20261015T103015123456Z-a1b2c3d`；已存在則拒絕覆寫。Git SHA 只識別受版本控制的程式，私有契約與題庫另存內容指紋。`run.json` 保存 project ID、profile／contract 身分與指紋、題庫指紋、程式 SHA、實際 provider／model／deployment、非機密有效設定、runs 與 concurrency。逐次紀錄保存狀態、失敗代碼、耗時及 provider 回報 token；未回報用量以空值表示，不估算為零。

維持私有 `calls.jsonl`、`results.jsonl`，生成 `summary.csv`、`model_summary.csv`、`overview.md`、`cases/<case-id>.md`。概覽增加分類別統計、已完成／預定次數與重複執行的一致性；只輸出允許的摘要欄位，不將原始 request／response 或資料列嵌入可分享報告。既有乾淨 worktree 前置檢查與不覆寫原則沿用，但產物路徑檢查改為所選專案下的受控目錄。

### 檔案來源與未來 Web

本階段 YAML、題庫及 JSONL 是來源；Web 日後可透過受權限控制的後端讀取摘要。需要多人查詢、線上編輯、審核與發布時，再決定獨立的評估資料庫：專案／題庫版本／run 索引與摘要可入庫，大型原始 trace 留在受控檔案或物件儲存。ERP 資料庫不能兼作此控制資料庫，`.env` 機密也不搬入一般資料表。

## 現有資料搬遷對照

| 現在 | 後續實作的去向／處理 |
|---|---|
| `integrations/private/gms2/{manifest.yaml,catalog.yaml,views/,samples/,README.md}` | 原樣保留內容遷至 `projects/gms2/`；檢查 YAML 相對引用與樣本來源。 |
| `integrations/private/retail/{manifest.yaml,catalog.yaml,views/,contract_review.md}` | 原樣保留內容遷至 `projects/retail/`；無正式題庫時不執行評估。 |
| 根目錄 `.env` 或部署者自行保管的設定 | 由部署者建立每專案 `projects/<id>/.env`；不能自動複製或輸出秘密。 |
| 本機 GMS2 `.env`、`config/freetds.local.conf` | 經確認原 `.env` 綁定 GMS2 後，私下複製到 `projects/gms2/.env` 與 `projects/gms2/freetds.conf`，移除重複的 profile 路徑並修正 FreeTDS 相對路徑；舊檔保留作回復。 |
| `evaluations/datasets/query_reliability.jsonl`、`query_reliability_colloquial.jsonl` | 核對與重新設計後整合為 `projects/gms2/evaluations/cases.jsonl`，保留來源與舊版摘要；修正錯誤預期值後才作正式基準。 |
| `evaluations/datasets/governance_cases.json`、`evaluations/config/models.json` | 作為可分發的合成 fixture／範例設定保留，不能冒充任何客戶的正式題庫或實際專案模型設定。 |
| `evaluations/` 內的 Python runner、評分、metadata、報表程式 | 留在共用品質工具套件，改由專案入口調用；避免複製到各專案。 |
| `src/cpea/resources/demo/` | 移至合成範例／測試 fixture，正式執行不再隱含載入；同步調整包裝、測試與文件。 |
| `artifacts/evaluations/`、`artifacts/stability/` 的既有結果 | 保留原位作歷史紀錄，不改寫 metadata 或重新命名為新 run；新 run 才寫入專案目錄。 |
| `artifacts/baseline/original-poc.zip` 及 provenance manifest | 保留原封存位置與內容；不當成新題庫或新 run 搬遷。 |

## Risks / Trade-offs

- [既有文件、測試或部署設定仍引用舊路徑] → 盤點引用並更新可執行路徑，舊版歷史文件保留時間脈絡。
- [私有目錄被 Git 或建置工具收錄] → 先更新 ignore／package 規則，再搬檔並檢查 wheel、sdist 與 Git 狀態。
- [Git SHA 無法代表被忽略的客戶資料] → 同時記錄契約、題庫與非機密設定指紋。
- [合併題庫造成錯誤答案或重複題目] → 要求穩定 ID、唯一性與逐題校對；保留舊題庫作遷移核對，不直接宣稱等價。
- [Web 顯示私有紀錄導致跨專案洩漏] → 本次不提供 Web 路由；後續先完成身分與專案授權再提供讀取介面。

## Migration Plan

1. 盤點並記錄私有檔案、本機部署設定與歷史結果的檔名、大小、SHA-256；確認目標目錄的 Git 忽略與發行包排除規則。
2. 建立新目錄與專案解析器；先以複製方式遷入 GMS2／Retail profile，逐檔比對雜湊並驗證 catalog 仍可載入，再移除舊工作副本。
3. 針對 GMS2 題庫做來源對照、題目校對、分類與固定 ID；建立單一題庫。Retail 維持無題庫狀態，直到專案方提供題目。
4. 加入專案評估指令、受控輸出與報表；更新 demo fallback、測試、包裝規則及 README／評估文件／架構文件中的現行路徑。
5. 以離線測試驗證解析、隔離、評分及報表；真實模型執行由具備有效專案憑證的部署環境另行進行，不能以 stub 結果取代。
6. 發布時先保留已封存的歷史產物與可回復的舊版程式／設定。若新入口失敗，回復上一版程式及其舊 profile 路徑；不得用重寫歷史報告的方式修復。

## Open Questions

- 正式 `cases.jsonl` 的業務題目與預期答案由專案方重新設計；此變更僅定資料結構、遷移流程與校驗門檻。
- 未來 Web 採單企業獨立部署或共享服務，會影響授權與保存策略；本次不預先選定資料庫產品。
