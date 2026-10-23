# RAG 映射流程測試計畫

由 plan-eng-review 於 2026-10-23 產生；所有新流程測試與真實服務執行均待使用者採納。
分支：feat/complex_req_test。專案：cpea_terms。

## 受影響入口

- SchemaMappingDecompositionService.plan(request)：獨立規劃入口，無瀏覽器頁面或SQL執行。
- 舊 TaskDecompositionService：維持原一次呼叫與既有66項focused回歸。

## 關鍵互動

- 用庫存與2026年9月銷售準備評估資料，保留全庫存商品且不計採購量。
- 允許交易彙總或月度等價來源；不接受固定跨九十月窗口代替九月。
- raw原句召回與子需求召回應保留完整來源組合。
- retrieval gap、預算不足、失敗候選與catalog不支援須有可區分結果。

## 邊界與失敗

- 無候選、100零分ties、同名欄位多owner、query去重、補查無進展與預算耗盡。
- 刪漏禁止詞、把否定標syntax、真實但否定的引文、目前快照語意不足。
- 新來源整合鍵不相容、漏輸出grain、inner丟母體、期間未限制所有相關指標。
- fingerprint／profile／模型／tokenizer變動的cache失效；provider/parse/tokenize失敗不得partial-ready。
- 並行只在後續採納後驗workers界限、回應次序與錯誤；未量服務延遲不訂虛構門檻。

## 重要路徑與驗收

- 抽取→多查詢→融合→逐View mapping→有限gap loop→review→MappedDraft→deterministic驗證→requests，使用fakes離線整合。
- 舊focused與新schema mapping測試已實跑173 passed in 10.33s；此結果不代表未實作流程已有測試。
- G1–G10詳細輸入／斷言與人工oracle計畫見同目錄2026-10-23-rag-mapping-eng-review.md。
- 真實LLM eval需人工審定gold完整來源集合、hard negatives與held-out；記錄false-ready/unsupported、成本與延遲，這次未執行。
