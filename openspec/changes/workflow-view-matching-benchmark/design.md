## Context

`cpea-eval` 已依專案讀取單一題庫、重複執行完整 SQL generation workflow，並由 `TracedModel` 將實際 LLM request／response 寫入私有 `calls.jsonl`。目前 `ProjectCase` 只接受 reliability 欄位，評分主要看最終 `SQLGenerationResponse`／QueryPlan；解析後的 `SQLClauseMapping` 未以可直接評分的形式留在 trace。Retail 題庫含 `expected_match`、`expected_sql`、SQL 與語意難度及 `validation_status`，但位於被 Git 忽略的 draft 專案目錄。正式 prompt 仍是 `sql_generation.py` 內的常數；舊 `stability_runner --prompt-file` 會改寫模組全域變數。

## Goals / Non-Goals

**Goals:**

- 使用同一 `cpea-eval --project ... --runs ...` 路徑執行既有 GMS2 reliability 題與 Retail View Matching 題，保留單一私有題庫與原有 run trace。
- 將模型對應與 QueryPlan／SQL 結構分層評分；正常、拒絕、無法解析與模型呼叫錯誤有不同結果。
- 讓 prompt 版本、題庫、契約及審核狀態可追溯，並在額度上限或 provider 致命錯誤後停止後續呼叫。

**Non-Goals:**

- 不新增 Retail 專用 runner、Web 審核介面或資料庫；不執行 Retail SQL，也不驗證實際資料列。
- 不因評估需求修改 View 契約、QueryPlan 能力或 SQL Builder；降冪、JOIN、`COUNT(DISTINCT)` 等仍維持 Coverage Gap。
- 不以 JSON 整體逐字相等當作唯一評分規則；不自動核准人工待審題。

## Decisions

### 1. 共用 runner 支援兩種題型

在專案題庫模型加入明確的題型版本／識別欄位。既有 reliability 行維持原解析與評分；View Matching 行保留 `expected_match`、`expected_sql`、九宮格標籤、候選 View 範圍及審核欄位。載入時先驗證 profile ID、View／Column、ID 唯一、契約指紋、原文片段與案例狀態，再轉成共用執行項目。Retail 的生成器可產出或轉換成此題型，但評估 runner 不依賴 Retail 專用模組。

### 2. 擷取解析後 mapping，再評兩層

workflow 在每次解析模型輸出後，於私有 trace 保留 `SQLClauseMapping`、嘗試次序與該次是否被接受；成功時標示實際用於 QueryPlan 的 mapping，拒絕時保留最後可解析的 mapping 或明確的 `mapping_unavailable`。`calls.jsonl` 繼續保留原始 prompt／response，作為調查來源。

View Matching 評分以欄位與聚合、條件欄位／運算子／原文字面值、分組與排序、選中 View、text 原文連續片段及不應多出的查詢要求為準；`unsupported_reason` 的自由文字不逐字比較，但拒絕原因類型須與缺欄位／語意／安全等預期一致或交人工審查。最終層比較 QueryPlan 的 SELECT、filter、aggregate、GROUP BY、ORDER BY 及單一 View，並驗證已編譯 SQL 的基本結構。正常題任一層失敗即整體失敗；拒絕題要求沒有可執行 SQL，且 `table=null` 或明確無可用 mapping 的狀態與原因可辨。兩層都需能報 `error`／`pending`，不能以最終拒絕掩蓋 mapping 錯誤。

### 3. Prompt 以版本化資源注入 workflow

將系統 `MATCH_PROMPT` 移至共用套件內的 UTF-8 版本化資源，保留 human 訊息模板與 response schema 的版本識別。prompt loader 於 runtime 建立時讀取並固定內容，再傳入 workflow 實例；所有 context budget 計算與模型呼叫使用同一內容，不改寫模組全域變數。`cpea-eval` 預設使用正式版本，可選已登錄版本做實驗；run metadata 記錄版本、SHA-256 與有效 prompt 設定。仍以 `calls.jsonl` 查實際送出的完整訊息。舊 `MATCH_PROMPT` 匯入若被測試依賴，設相容別名並逐步遷移。

### 4. 額度預留與錯誤即停

共用模型呼叫邊界在發出每次實際 LLM 呼叫前，對目標模型做原子額度預留；限額計算包含 warmup 與 workflow 重試。可選的私有 ledger 保留跨 run 用量，不能由已生成的結果數倒推。達上限時不發出該次呼叫。provider rate limit 或認證錯誤不重跑；停止該模型尚未開始的題目，標記 `skipped` 與原因。並行執行時已在途的呼叫可完成，但觀察到停止條件後不得再開始新呼叫。其他暫時性錯誤依既有 workflow 規則分類，不以切換 Ollama 代替原模型結果。

### 5. 審核與 draft 邊界

`validation_status` 只表示機器驗證，新產題的 `review_status` 一律為 `pending`；後續可為 `pending`、`approved`、`rejected`。核准須有審核者、時間、題目內容與契約指紋。修正題目或契約指紋變更後，先前核准失效。正式分母僅含目前契約下已核准題；待審題可在明確 exploratory 模式執行，但結果標為待審且另列，不計正式正確率。`--allow-draft-profile` 僅傳入評估建立的 catalog；正式查詢入口仍拒絕 draft。run metadata 記錄 profile status 與是否明確允許 draft。

### 6. 保留原報表並新增分層統計

現有 `run.json`、`calls.jsonl`、`results.jsonl` 及 CSV／Markdown 繼續使用；新增對應層與 SQL 層的狀態、每 View 九宮格、拒絕類別、待審及 `skipped` 統計。穩定性同時呈現「每次通過」與「同題各次結果一致」，避免把一致失敗誤報為穩定正確。既有 GMS2 報告欄位維持可讀。

## Risks / Trade-offs

- [跨候選重試可能產生多個 mapping] → 在 trace 標示嘗試次序及最終採用 mapping；評分使用 workflow 最終決策，保留各次原始 trace 供診斷。
- [自由文字拒絕原因可能有多種等價表述] → 不逐字比較 `unsupported_reason`；對契約缺口做結構驗證，語意邊界維持人工審核。
- [原始 prompt／response 含私有資料] → 只存私有 Git-ignored JSONL；分享型報告僅保留統計、ID 與錯誤碼。
- [額度停止使 run 不完整] → 顯示 planned、completed、skipped；未執行題不計通過率，並保留停止原因。
- [draft 契約與核准題可能過期] → 以契約指紋綁定審核，變更後要求重新驗證與審核。

## Migration Plan

1. 加入版本化 prompt loader，維持預設 prompt 內容不變並驗證封裝結果。
2. 擴充 trace 與雙層評分，再讓共用題型接受 Retail 資料；先以離線 stub 比對 GMS2 舊結果。
3. 導入 Retail 審核 metadata 與評估專用 draft 選項；待審題僅產生 exploratory 結果。
4. 加入額度與 provider 錯誤即停、分層報告與文件；用離線故障注入驗證中止及未執行題數。
5. 若需回退，選用既有 reliability 題型與既有 prompt 版本；新報表欄位不影響舊 run 原始資料。

## Open Questions

- Retail 的 175 題人工待審案例由哪位業務／資料契約負責人核准，審核紀錄如何在被忽略的私有專案目錄中保存與備份？
- 若使用跨 run 額度 ledger，部署環境的共享儲存位置與帳號識別範圍須在執行真實模型前確認。
