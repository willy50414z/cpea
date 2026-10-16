# 任務：根據 View Contract 建立 LLM View Matching 候選測試案例

你是一名資深資料工程師、SQL 專家及 LLM Evaluation Engineer。

請閱讀指定專案的 View Contract YAML、Catalog、全域 SQL Policy、QueryPlan、MATCH_PROMPT、Validator 和 SQL Builder，為每個 View 建立可重複驗證的 LLM View Matching 候選測試案例。題庫、評分規則和固定執行設定經審核後，才共同構成正式 Benchmark。

目標是評估不同 LLM 對自然語言需求的理解能力、SQL 查詢結構推理能力及契約遵循能力。

## 零、輸入、範圍與交付

- 先確認專案 profile、manifest、Catalog、所有 View Contract、目前有效的 MATCH_PROMPT 版本與正式 JSON Schema，以及實際執行路徑的 Validator／SQL Builder。記錄 profile ID、契約指紋、prompt 版本與內容 SHA-256；不可只依提示文字推測系統支援能力。
- 本任務只產生與驗證**測試案例題庫**及 Coverage Report，不執行模型推論，也不建立專案專用 runner。產題不查詢資料庫；`--check` 可用唯讀查詢驗證已宣告的 View 唯一鍵在目前資料中沒有重複。題庫格式應能交由共用 `cpea-eval` 的 View Matching 題型讀取；若共用 runner 尚未支援，明列整合缺口，不另寫一次性執行檔。
- `status: draft` 的 View 契約只可在明確的離線／評估模式載入；不得為了產題移除 draft 標記或放寬正式查詢入口。
- 每題是一個 **test case**；固定且經審核的題庫、評分規則、prompt 與執行設定合起來才稱為 **benchmark**。共用入口讀取專案的 `evaluations/cases.jsonl`，Coverage Report 另存。

## 一、測試規模

每個 View 建立：

- 3 種 SQL 難度 × 3 種語意難度 × 每組 5 題 = 45 題正常案例。
- 額外 10 題契約邊界與拒絕案例。
- 每個 View 的基本題庫目標為 55 題。已知能力或契約缺口可另加具名案例，不佔九宮格或 10 題基本邊界配額；Coverage Report 分開計數。

九種組合均須覆蓋，不可用完全相同的查詢意圖只替換數值來湊數。

## 二、SQL 難度

### S：初級

- 僅使用 SELECT、FROM、WHERE。
- 至少包含一個明確篩選條件。
- 查詢引用的不同欄位不超過 4 個。
- 不使用 GROUP BY、ORDER BY 或聚合函數。

### M：中級

- 必須涉及 SELECT、WHERE、GROUP BY、ORDER BY。
- 引用至少 6 個不同欄位。
- 至少 1 個分組維度。
- 至少 2 種不同聚合函數。
- 聚合方式必須符合欄位業務語意。

### H：高級

- 必須涉及 SELECT、WHERE、GROUP BY、ORDER BY。
- 引用至少 8 個不同欄位。
- 至少 3 個分組維度。
- 至少 2 種不同聚合函數。
- 包含多個明確篩選條件。

欄位數計算 SELECT、WHERE、GROUP BY、ORDER BY 實際引用的不同欄位，不重複計數。

不同聚合函數指 SUM、AVG、COUNT、MIN、MAX 等不同種類，而不是同一函數作用於不同欄位。

所有功能必須由目前實際使用的 QueryPlan、schema linking／Validator 和 SQL Builder **端到端**支援。若其中任何一層會拒絕，即使 QueryPlan 欄位理論上能表示，也不可設為正常案例。目前可表達升冪、降冪排序、`COUNT(DISTINCT column)`，以及有 GROUP BY 的單欄數值聚合 HAVING；HAVING 可引用未顯示在 SELECT 的指標。JOIN 與跨欄位公式目前不在本次功能實作範圍。同欄位上下界的日期區間目前也會被 schema linking 視為衝突。功能變更後須重新檢查，不能永久沿用此清單。

不得為了達到難度而添加無業務意義的欄位、分組、條件或聚合。

## 三、語意難度

### L1：初級

- 優先使用 YAML 中 View / Column Comment 的詞彙。
- 問題簡潔、直接、明確。
- 不加入不必要的背景文字。

### L2：中級

- 部分欄位使用同義詞或自然口語。
- 加入適量背景、連接詞及非查詢性敘述。
- 使用者意圖仍須明確。
- 不得新增超出 YAML 契約的業務含義。

### L3：高級

- 核心指標與維度優先使用間接表達。
- 避免直接複製 Column Comment 的完整描述。
- 可以包含口語、省略式敘述、背景資訊與無關干擾文字。
- 但必須保留所有必要的查詢條件。
- 不得為增加困難度而製造無法合理解讀的需求。

語意難度與 SQL 難度必須獨立控制。

例如 S1 與 S3 應可使用相同的 SQL 結構，但自然語言的表達方式不同。

## 四、契約遵循與拒絕案例

每個 View 另外建立 10 題：

- 3 題：缺少必要欄位。
- 2 題：字面相似但業務語意不符。
- 2 題：需要其他 View 或 JOIN 才能滿足。
- 3 題：違反黑名單限制、不支援操作或 Prompt Injection。

僅在現有契約確實無法滿足時，才能將預期結果設為 `table=null`。

測試案例不可預設所有未知詞彙都應拒絕，也不可將合法需求刻意判定為不支援。

### Coverage Gap 的額外案例

- 已知缺口除記載於報告，也應有至少一題可追蹤的具體需求與 `unsupported_evidence`；使用穩定 ID，與基本 55 題分開統計。每次重跑須保留人工審核紀錄的指紋規則。
- 目前 Retail Coverage Gap：跨會員平均每筆訂單消費額與跨門市整體毛利率需要跨欄位算式，目前各保留一題 `unsupported` 案例；JOIN 與跨欄位算式不在本次功能實作範圍。同欄位雙界限日期篩選仍由邊界案例或產題規則追蹤。
- HAVING 已納入正常案例：每個 View 的 `B-09` 以明確分組維度、聚合函數、比較運算子與門檻值驗證彙總後篩選，並容許該指標不出現在 SELECT。Ground Truth 必須區分 WHERE 與 HAVING；例如「依門市分組，只保留營收合計大於 100 的門市」需要 `HAVING SUM(revenue) > 100`，不能改成 `WHERE revenue > 100`。有 GROUP BY 時，一般欄位門檻仍是 WHERE。MATCH v6 的 `expected_match.having` 與 `expected_sql.having` 必須一致；未使用 HAVING 的 v6 題目使用空陣列。
- 已處理項目：七個 View 各有降冪排序正常案例；`v_sales_detail` 有 `COUNT(DISTINCT order_id)` 正常案例；固定涵蓋期間、固定庫存快照日期及 `sold_qty_30d` 的固定截止日期已從契約移除，對應舊案例不再產生。`v_sales_detail` 的 `(order_id, product_id)` 已由審核後的 YAML 宣告為複合唯一鍵，`--check` 驗證目前資料沒有重複；不得再以「明細唯一鍵未確認」產生拒絕案例。複合鍵不等於單一欄位識別碼，題目須明確要求兩欄。
- `COUNT(*)` 或直接 `AVG` 比率欄位不得充當上述跨粒度需求的 Ground Truth；也不得將使用者要求的降冪改成升冪。若新的計算公式或日期保證尚未確立，採 `unsupported` 或 `ambiguous` 並寫明實際證據，不得產生虛構的 `expected_sql`。
- 草稿契約的未確認敘述只能測試系統是否謹慎處理，不應當作經確認的業務真值。待契約或 Builder 改版後，重新判定拒絕是否仍成立，補上可編譯的正常案例，再更新 Coverage Report；不得讓過期的拒絕案例繼續計入正式成績。

## 五、生成 Ground Truth

每個案例須產生：

1. 唯一 Test Case ID。
2. 目標 View。
3. SQL Difficulty：九宮格正常案例為 S / M / H；額外能力案例與拒絕案例若不適用則為 null。
4. Semantic Difficulty：九宮格正常案例為 L1 / L2 / L3；額外能力案例與拒絕案例若不適用則為 null。
5. Category：normal / unsupported / ambiguous / security。
6. 自然語言需求 `request`。
7. 預期 MATCH_PROMPT JSON 結果 `expected_match`。
8. 預期 QueryPlan／SQL 結構 `expected_sql`：至少包含 `select_columns`、具欄位／運算子／原文型別值的 `filters`、獨立的 `having`、`aggregations`、`group_by`、`order_by`；拒絕案例為 null。
9. 測試設計理由。
10. 自動驗證狀態 `validation_status`：validated / needs_review。
11. 獨立的人工審核狀態 `review_status`：pending / approved / rejected。新產題一律為 pending；核准時另記審核者、時間、題目內容指紋及契約指紋；產生器不得自行標為 approved。
12. 題型版本、profile ID、候選 View 範圍、契約指紋，以及拒絕案例的具體不支援證據。

`expected_match` 必須符合目前 MATCH_PROMPT 的正式 JSON Schema。

`expected_match` 是 LLM 對應結果的 Ground Truth；`expected_sql` 是後續 QueryPlan／SQL 的 Ground Truth。兩者應分別驗證，不能因最終安全拒絕就把正常題的錯誤 mapping 算成通過。`table=null` 的拒絕案例仍須提供符合正式 schema 的完整 JSON 結構與理由。

所有 `text` 必須是 request 中連續且完全一致的原文片段。

欄位名稱與 View 名稱必須與 YAML 完全一致，不可翻譯或修改。

Criteria 的值不可憑空推測代碼或業務映射。

未要求顯示的條件欄位不得自動放入 fields。

所有分組維度必須同時列入 fields 與 group；fields 還須包含明確要求顯示的指標。不同指標可同時使用不同的合法聚合，例如 SUM(revenue) 與 MAX(order_count)。

不得為了使 SQL 合法而擅自增加使用者沒有要求的分組維度。

若預期查詢需要目前端到端流程不支援的功能，應列入 Coverage Gap，不得偽裝成正常案例。正式 Benchmark 不以整份 JSON 的字元逐字相等作唯一評分：欄位、運算子、值、分組、排序、View、額外要求與 text grounding 應檢查；合法原文片段不要求與標準答案截取完全相同，SELECT 欄位順序不同但結構等價時不判錯。`unsupported_reason` 等自由文字理由留給類型檢查與人工審核。

## 六、案例多樣性

每個難度組合的 5 題應盡量使用不同的業務意圖、欄位搭配或篩選方式。

優先涵蓋：

- 單一條件及多條件。
- 日期範圍或單側日期界限；真正的雙界限區間僅在端到端流程支援時納入正常案例。
- 字串與數值條件。
- 不同維度的分組。
- 不同合理聚合函數。
- 升冪與降冪排序；降冪正常案例須確認 MATCH 對應、QueryPlan 方向與編譯 SQL 一致。
- 明細查詢與彙總查詢。
- 容易混淆的業務指標。
- 正確拒絕不支援需求。

以上僅在契約及系統能力支援時才納入，不得為了覆蓋率而違反限制。

## 七、自動驗證

生成後，使用程式執行以下檢查：

1. 測試案例 ID 不重複。
2. 9 個難度組合的數量符合規劃。
3. 引用的 View / Column 全部存在於指定候選契約；profile、契約與 prompt 指紋相符。
4. 聚合與運算子符合全域政策及黑名單。
5. SQL 難度符合實際預期查詢結構。
6. 所有 text 都是 request 的連續原文。
7. 正常案例可由指定的單一 View 滿足。
8. 拒絕案例在**實際提供的候選 View 集合**下確實無法滿足；須記錄缺少欄位、業務語意衝突、JOIN 需求、政策限制或不支援操作的證據。不能只因目標 View 缺欄位，就忽略其他候選 View 已能完整滿足需求。
9. 不產生 View 無法提供的業務資訊。
10. 不產生沒有合理業務目的的 SQL 複雜度。
11. 每組 5 題的查詢意圖有實質差異，不能只替換條件值；L1/L2/L3 的語意變體可共用同一 SQL 意圖。
12. 題目是否含尚未審核的業務假設，及 `review_status` 是否如實保留。

對於正常案例，將預期 QueryPlan 透過現有 SQL Builder 編譯，並檢查產生的 SQL 結構與全域唯讀政策。若 workflow 其他階段會拒絕該 QueryPlan，也不得標示為端到端可用。

不需要記錄 SQL 執行後的實際資料結果。

若無法通過驗證，先嘗試重新生成；不得把失敗案例標示為 `validated`，也不得算入正式題數。

`validation_status=validated` 只表示自動檢查通過，**不代表人工核准**。所有新題保持 `review_status=pending`；優先逐題審核 L3、拒絕案例及契約存在業務不確定性的題目，其他題也須在正式採計前核准。審核通過才設 `review_status=approved`；有誤的題目先修正、重跑自動驗證，再重新審核。題目或契約指紋變更後，原核准須失效。

## 八、無法達成指定難度時

若某個 View 的欄位數量、Grain、業務語意或限制不足以產生指定難度，不得捏造欄位或無意義分組。

應在 Coverage Report 中說明：

- 無法滿足哪個難度組合。
- 缺少哪些必要條件。
- 實際成功生成幾題。
- 建議如何調整 View 契約或測試條件。

寧可少於目標題數，也不可犧牲 Ground Truth 的正確性。

## 九、交付與後續評估

- 交付固定 ID 的 JSONL 題庫、Coverage Report、可重跑的產生／驗證程式及人工審核清單。產生器重跑不得默默覆寫人工審核紀錄；審核資料須以題目內容與契約指紋連結。
- Coverage Report 應列出每個 View 的正常／基本邊界／額外缺口題數、九宮格分布、自動驗證通過率、`pending`／`approved`／`rejected` 數量，以及缺口的原因、實際成功題數和調整建議。自動通過率與人工核准率須分開呈現。
- 正式 workflow 穩定性測試由共用 `cpea-eval` 執行，分別評分 `expected_match` 與 `expected_sql`，保留原始 LLM request／response trace，但不把原始內容放進分享型報告。正式通過率只納入當前契約下已核准的題目；待審題若需先測，須明確標為探索性結果。
- 每次 benchmark run 固定題庫、契約、prompt 版本與模型設定，記錄各自指紋。額度或 provider 錯誤導致未執行的題目應標示 skipped，不當作通過；不可用另一模型自動接續原模型的正式成績。
- 版本化 MATCH_PROMPT 資源位於 `src/cpea/workflows/text_to_sql/prompts/match/`；每次執行記錄 system、human 模板與 response schema 指紋。解析後的各次 mapping 留在私有 workflow trace；原始模型 request／response 留在私有 `calls.jsonl`。
