# View Retrieval 漸進式改善紀錄

本次工作遵循 MVP 0 → MVP 1 → MVP 2 的順序。只有人工審核後的失敗證據支持時，才導入 Column-first、Grain-aware、Hybrid 或 Slot Extraction。維持既有 LangGraph 與逐 View 驗證，不新增生成模型呼叫或依賴。

## 版本與重現

既有未提交修改先保存為 `9ab8778`，包含既有澄清流程、395 題檢索診斷與 API／CLI／UI 的確認功能。既有 395 題及 YAML 預期答案保持原樣；起始測試為 220 passed。

新增工具使用正式 `retrieve_schema` 節點，觀察 selector 截斷前的全部排名、原始與 rerank 分數、候選來源、送驗集合及 context 排除結果。Lexical 沿用既有 reranker；純 Vector 關閉 lexical rerank，以便獨立比較檢索策略。Production 設定不變。

```bash
.venv/bin/python -m evaluations.retrieval_benchmark \
  --experiment-id retrieval-mvp0 --exploratory
```

工具一律要求乾淨 Git worktree，包括探索性實驗。輸出位於被 Git 忽略的 `projects/retail/artifacts/retrieval/<UTC時間>-<SHA>/`，包含 `run.json` 與每個策略的 JSONL，不覆寫既有實驗。每題保存完整排名、分數、實際候選、選擇理由與版本資訊；不查詢資料庫、不保存結果資料列。若初步候選上限不足以觀察全部 Catalog，直接拒絕執行。

`run.json` 記錄 Git SHA、乾淨狀態、兩份題庫各自的 SHA-256、Contract 版本與指紋、實際索引文字指紋、Embedding 模型與 Ollama 權重 digest。Vector 索引在當次執行以同一份 Catalog 重建；索引版本由文字內容與模型身分導出，建立耗時與逐題檢索延遲分開記錄。

Gold Recall@1/3/5 以完整排序計算，Gold Selected Recall 以實際送驗集合計算，兩者不可混用。非拒絕題才有可用 SQL 的意義；既有拒絕題的 `target_view` 只代表題目歸屬。既有題庫沒有完整有效 View 標註，`valid_views` 保留 null，不據此計算 Valid View Recall。

未量測的 SQL Correctness、Clarification Precision／Recall、端到端延遲保留 null（未測）。本工具實際生成模型呼叫數為 0，不代表完整 Pipeline 的平均成本為 0。候選增加量可用於決定後續模型評估範圍，不能充當實測 LLM 成本。

## Challenge Dataset 與人工審核

`evaluations/data/retail_retrieval_challenge.jsonl` 包含 50 題，各類 10 題：Exact Match、Synonym、Colloquial、Ambiguous、Multi-Concept。每題有 Gold／Valid Views、每個可行 View 所需欄位、業務解釋、是否需確認及不支援原因。相同語意的多 View 共用一個 interpretation；不同 Grain、零交易月份或未下單會員造成不同結果集合時，分開標記。

所有新標註均為 Agent 草稿，`review_status=pending`。既有 395 題也尚待人工審核。`--exploratory` 可產生探索數據，但不得視為正式驗收；省略此參數時，未完成審核便會在模型呼叫前拒絕執行。結構及欄位檢查不能取代人工判斷，也不宣稱已窮舉全部有效解法。

人工審核須核對真實 YAML 的欄位、Operator、Aggregation、結果 Grain、資料範圍及各解釋是否等價。完成後填寫 `reviewer`、`reviewed_at`、`reviewed_contract_fingerprint` 與 `reviewed_case_sha256`，最後設定 `review_status=approved`。新題的內容指紋由 `challenge_content_sha256(case)` 計算；既有題沿用 `ViewMatchingCase.content_sha256()`。修改題目、標註或 Contract 後，舊核准失效。不得為取得較好召回數字修改既有預期答案。

本文件後續記錄各階段的實測值與決策；原始逐題數據保存在各次實驗目錄。
