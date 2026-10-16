## ADDED Requirements

### Requirement: 共用專案 runner 的模型呼叫額度與停止規則

共用專案 runner SHALL 支援明確設定每個模型的 LLM 呼叫上限，並在每次實際呼叫前原子預留額度；warmup、重試及 workflow 內所有模型呼叫 MUST 計入。達上限或收到 provider rate limit／認證錯誤時，runner MUST 停止對該模型開始新的呼叫，不得自動重試或切換模型。已完成與在途結果 SHALL 保留；尚未執行的題目 SHALL 記錄為 skipped 並附原因，不得計為通過。可選的跨 run 私有 ledger MUST 不含機密值。

#### Scenario: 額度在下一次呼叫前耗盡
- **WHEN** 模型已達設定呼叫上限而 workflow 尚有題目待跑
- **THEN** runner 不發出超額呼叫，保留已完成結果，並將其餘題目標記 skipped／quota_cap_reached

#### Scenario: Provider rate limit
- **WHEN** 模型呼叫回報可辨識的 rate limit 或認證錯誤
- **THEN** runner 記錄該次錯誤並停止該模型後續呼叫，不以另一模型的輸出填補原模型成績

#### Scenario: 並行在途呼叫
- **WHEN** 並行執行中偵測到停止條件
- **THEN** 已開始的呼叫可完成，但偵測後不得開始新的模型呼叫，報告區分在途與 skipped 數量

### Requirement: 分層正確率與穩定性報告

共用報告 SHALL 保留現有模型／案例／分類摘要，並對 View Matching 題增加按 View、SQL／語意九宮格、拒絕類別與模型的 mapping、SQL、整體狀態統計。報告 MUST 區分 planned、completed、skipped、error、pending、pass 與 fail，且未執行或待審題不得提高正式通過率。重複執行 SHALL 分別呈現全次通過與輸出／狀態一致性；一致失敗不得稱為正確。分享型報告 MUST 不包含原始 prompt、response 或客戶資料列。

#### Scenario: 三次重複且有一次失敗
- **WHEN** 同一已核准題重複執行三次，其中兩次通過、一次失敗
- **THEN** 報告顯示逐次結果與該題未全次通過，且不將它計入穩定正確題數

#### Scenario: 額度中止的報告
- **WHEN** runner 在計畫題數完成前因額度上限中止
- **THEN** 報告列出計畫、完成與 skipped 次數及停止原因，正式通過率分母規則可由報告直接看出
