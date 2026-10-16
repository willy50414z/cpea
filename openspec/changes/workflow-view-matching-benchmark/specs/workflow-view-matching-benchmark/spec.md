## ADDED Requirements

### Requirement: 契約綁定的 View Matching 題庫

共用專案評估器 SHALL 支援含穩定 ID、目標 View、SQL 難度、語意難度、類別、原始 request、`expected_match`、`expected_sql`、設計理由、驗證狀態與審核狀態的 View Matching 題型。載入時 MUST 驗證 View／Column 名稱、MATCH_PROMPT JSON 形狀、所有 `text` 的連續原文片段、ID 唯一及契約指紋；無效題目 MUST 在模型呼叫前拒絕。既有 reliability 題型 MUST 保持可用。

#### Scenario: 有效 Retail 題庫
- **WHEN** 共用 runner 載入與目前 Retail 契約指紋一致的 View Matching 題庫
- **THEN** 每題保留九宮格、預期 mapping、預期 SQL 結構與審核資訊，並可由同一專案執行入口排程

#### Scenario: 不合法 Ground Truth
- **WHEN** 題目引用不存在欄位、`text` 不在 request 中或與目前契約指紋不符
- **THEN** runner 在任何模型呼叫前拒絕該題庫，且不建立看似有效的成績

#### Scenario: 舊題型相容
- **WHEN** 共用 runner 載入既有 GMS2 reliability 題庫
- **THEN** 題目仍按原本預期欄位與完整 workflow 結果評分

### Requirement: 解析後 mapping 與雙層評分

workflow SHALL 在私有 trace 中保留每次可解析的 `SQLClauseMapping`、嘗試次序、是否被採用及最終 mapping 狀態。評估器 SHALL 分開評分 LLM View Matching 與最終 QueryPlan／SQL 結構，並保留整體結果。Mapping 評分 MUST 檢查選中 View、顯示欄位與聚合、條件欄位／運算子／值、分組與排序、原文片段及多餘要求；`unsupported_reason` MUST NOT 以全文逐字相等評分。SQL 層 MUST 檢查單一 View、預期 QueryPlan 結構及正常案例的編譯結果。無法解析、模型錯誤與合法拒絕 MUST 可區分。

#### Scenario: Mapping 錯但 SQL 未產出
- **WHEN** 模型對正常題回傳錯誤欄位或無法解析的 mapping，workflow 因驗證失敗而不產 SQL
- **THEN** mapping 層記錄對應失敗或錯誤，SQL 層記錄未產出，整體不得因安全拒絕而判為通過

#### Scenario: Mapping 對但最終結構錯
- **WHEN** mapping 符合 Ground Truth，但最終 QueryPlan 遺漏條件、聚合、分組或排序
- **THEN** mapping 層通過，SQL 層失敗，報告指出失敗所在層

#### Scenario: 合法拒絕
- **WHEN** 題目確實要求契約不能提供的資訊或不支援操作，且 workflow 回傳無可執行 SQL 的拒絕結果
- **THEN** 評估器檢查 `table=null` 或明確 mapping 不可得的原因與最終拒絕，不要求自由文字理由逐字相同

### Requirement: 固定且可追溯的 prompt 版本

正式 MATCH_PROMPT SHALL 由納入版本控制的 UTF-8 資源載入。一次評估 run MUST 固定一個已登錄版本，並記錄版本識別、內容 SHA-256、human 模板及 response schema 版本／指紋。workflow 的 context budget 與模型訊息 MUST 使用同一實例所載入的 prompt；執行中 MUST NOT 透過修改模組全域變數切換 prompt。現有私有 `calls.jsonl` SHALL 保留實際送出的完整 request／response。

#### Scenario: 重複執行同一版本
- **WHEN** 兩次 run 選用相同 prompt 版本與相同資源內容
- **THEN** metadata 中的 prompt 指紋相同，且每次 run 的所有 workflow 呼叫使用該版本

#### Scenario: 資源被改動
- **WHEN** 已登錄 prompt 版本的檔案內容改變或指定版本不存在
- **THEN** run 在模型呼叫前拒絕或以不同指紋明確標示，不能默默沿用原版本身分

### Requirement: 分離機器驗證與人工審核

題庫 MUST 將 `validation_status` 與 `review_status` 分開記錄。新產題的 `review_status` MUST 為 `pending`；其後 SHALL 為 `pending`、`approved` 或 `rejected`。核准 MUST 有審核者、時間、題目內容指紋及當時契約指紋。題目內容或契約指紋改變後，舊核准 MUST 失效。正式成績只納入當前契約下已核准的案例；明確 exploratory 模式 MAY 執行待審題，但 SHALL 將其標記為待審且排除正式通過率。

#### Scenario: 待審 L3 題
- **WHEN** Retail 的 L3 題通過自動驗證但 `review_status=pending`
- **THEN** 該題不能被計入正式成績，探索執行時仍可保留逐次輸出與待審標記

#### Scenario: 契約變更
- **WHEN** View 契約指紋與題目核准時記錄的指紋不同
- **THEN** runner 要求重新驗證與審核，不能沿用舊 `approved` 結果

### Requirement: 評估專用 draft 契約入口

共用專案評估命令 SHALL 提供明確選項允許載入 `status: draft` 的 profile，並在 run metadata 記錄此選項及 profile 狀態。該選項 MUST 只作用於評估 runtime，不得改變一般查詢入口對 draft profile 的拒絕行為。

#### Scenario: 明確評估 draft
- **WHEN** 使用者指定 Retail 專案與評估專用 draft 選項
- **THEN** 共用 runner 可載入 Retail 契約進行無資料庫的 workflow 評估，run metadata 標示 draft

#### Scenario: 未授權載入 draft
- **WHEN** 一般查詢入口或未指定 draft 選項的評估入口載入 Retail draft profile
- **THEN** 載入被拒絕，且不發出模型呼叫
