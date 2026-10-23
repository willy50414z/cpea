# 獨立需求與來源證據對照入口

既有 `TaskDecompositionService` 保持一次 LLM 規劃。新入口須明確建立：

```python
from cpea.application.services.schema_mapping_decomposition import SchemaMappingDecompositionService

planner = SchemaMappingDecompositionService(
    llm, catalog, settings=settings, observer=private_events.append, view_limit=5,
)
result = planner.plan('依各店各商品目前庫存件數及2026年9月銷售件數，準備補貨評估資料；保留所有庫存商品，暫不計算採購量。')
if result.status == 'ready':
    requests = result.prepared_requests
```

`llm`、`catalog`、`settings` 與原入口相同；`private_events` 為呼叫者管理的清單。不會生成 SQL 或存取 DB，也不會自動接到既有 CLI／API 或 benchmark。新回應繼承 `DecompositionResponse`，保留 `draft`／`prepared_requests`，增加 `trace`：前置檢索候選／排除與分數理由、原文 spans、逐候選 View 的引文、審核、task bindings、階段狀態。失敗亦保留已完成部分，不回退原流程。

最前面重用 `SchemaRetriever` 的 lexical/vector 與 rerank 篩選候選。新 adapter 在檢索查詢移除明列欄位識別碼，避免單一 View 必須具有所有欄位的交集限制；完整原文保留給後續階段，並強制保留明列 View／欄位的所屬來源。值字串與 IN 內容不當作來源指令。限定 `View.column` 釘其來源；未限定同名欄位可保留多個來源。

`view_limit` 預設 `max(5, settings.rerank_top_k)`，是 soft cutoff：同分與明列來源可能超過上限。原 `retrieval_k` 第一階段限制仍適用，隱含來源可能未召回，請查 `result.trace.retrieval` 的排除理由。可注入 `retriever`（提供 `retrieve(query)` 回傳既有 RetrievalResult）作離線測試；預設依設定可能呼叫 embedding／reranker。空候選回 `unsupported/empty_retrieval`，檢索失敗回 `error/retrieval_error`，不繼續 LLM。

正常完成為候選 View 數量 C+3 次 LLM 呼叫：抽取、每個候選 View 一次、審核、草稿。每次先檢查 context budget，不截斷契約；provider／解析／驗證錯誤不 retry。Token 計數服務失敗時回 `token_count_error`，保留失敗 stage 與先前 trace，不呼叫該階段模型。`context_tokens` 為單次 context 峰值，含被預算攔截的訊息。observer 每個實際呼叫帶 `stage`、`view`、usage、耗時與原始輸入輸出；可能含敏感需求及 provider 錯誤，僅存於呼叫者控制的私人紀錄，勿直接對外展示。

候選必須引用同 View、同欄位契約的真實非空原文。所有必要詞須逐 View 回覆，審核重新讀完整需求並可回報漏詞；發現漏詞立即停止。審核核准欄位與用途是草稿 allowlist，task bindings 連回原詞；期間條件限制所有關聯 task／指標，必要 grain 須保留到最終輸出，母體 anchor 及明列禁止用途須一致。禁止採購計算透過允許的來源操作約束，無任意衍生算式介面。

這是方案 A：每個候選 View 的全部欄位都提供模型比對，但只保存候選及逐詞無匹配理由，不保存每個不匹配欄位的拒絕矩陣；被檢索排除的 View 未逐詞比對。字元覆蓋、真實引文和結構檢查不能證明模型理解正確，也不能保證審核發現所有語意遺漏。實際模型品質與成本尚未驗證；本次驗證使用離線 staged fake／lexical，未進行真實模型／資料庫呼叫。既有 benchmark/regrade 紀錄只涵蓋原流程，不能視為新入口驗收。
