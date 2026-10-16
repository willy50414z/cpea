## Why

Retail 已有依 7 個 draft View 產生的 385 題 View Matching 題庫，但共用 `cpea-eval` 只能讀取既有 reliability 題型，無法評分 `expected_match`，也無法在評估模式載入 draft profile。要比較模型的 workflow 穩定性，需要沿用同一套專案 runner，分辨 LLM 對應錯誤與最終 QueryPlan／SQL 錯誤，並固定 prompt、契約與題庫版本。

## What Changes

- 擴充共用專案題型與評分流程，讀取每題的 `expected_match`、`expected_sql`、View、SQL／語意難度、驗證與人工審核狀態；既有 GMS2 reliability 題庫保持相容。正常與拒絕案例分開評分，報告分別呈現 View Matching、QueryPlan／SQL 及整體結果。
- 在 workflow trace 保留可評分的解析後 `SQLClauseMapping` 與對應的模型呼叫／嘗試資訊；沿用現有私有 `calls.jsonl` 的原始 request／response 記錄，不另建 Retail runner。
- 將正式 `MATCH_PROMPT` 移至納入版本控制的資源檔，由共用 loader 載入。一次 run 固定一個 prompt 版本，記錄版本、內容 SHA 與有效設定；不以修改模組全域變數切換 prompt。
- 將 `stability_runner` 的額度與錯誤保護納入共用評估：可設定每模型呼叫上限，達上限或遇到 provider rate limit／認證錯誤時停止該模型後續呼叫，明列未執行題數；不自動重試或切換模型。
- 提供僅限評估的明確 draft profile 選項；不移除 Retail 的 `status: draft`，也不放寬正式查詢流程的載入規則。增加測試案例人工審核狀態與審核紀錄，未核准題目不得混入正式通過率。
- 擴充報告，依 View、九宮格、拒絕類別及模型呈現正確率、重複執行一致性、錯誤與待審數。實作驗收使用離線 stub；不在本變更中呼叫真實模型或執行資料庫查詢。

## Capabilities

### New Capabilities

- `workflow-view-matching-benchmark`: 定義雙層 ground truth、prompt 版本、案例審核、draft 評估及 workflow 穩定性判讀。

### Modified Capabilities

- `quality-tooling`: 擴充共用專案 runner 的題型、額度／錯誤停止規則、run metadata 與分層報告，同時維持既有題庫相容性及私有產物邊界。

## Impact

- 影響 `evaluations/` 的專案題型、runner、評分、trace、報表及離線測試；影響 `src/cpea/workflows/text_to_sql/` 的 prompt 載入與 mapping trace，以及 prompt 資源的封裝。
- Retail 私有題庫與審核結果保留在 `projects/retail/`；共用發行包不包含客戶題目或原始模型紀錄。既有 GMS2 題庫與 `cpea-eval --project gms2` 的行為須維持。
- 不建立專案專用執行檔、Web 審核介面、資料庫 schema，亦不以自動切換模型填補額度中止的 run。
