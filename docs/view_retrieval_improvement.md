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

## MVP 0：對照結果

執行版本：`56f2228a27eb31ace44e5614feb255591ea7104a`；完整數據：`projects/retail/artifacts/retrieval/20261019T054801104387Z-56f2228a/`。兩種策略皆在乾淨 worktree 執行相同 445 題，未修改題庫或 Contract。

| 資料集／策略 | Recall@1 | Recall@3 | Recall@5 | Gold Selected | Valid View Recall | 完整歧義覆蓋 | 平均候選 | 檢索 P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 395／Lexical | 245/395 | 356/395 | 394/395 | 394/395 | 未標註 | 未標註 | 5 | 5.87 ms |
| 395／Vector | 117/395 | 253/395 | 348/395 | 348/395 | 未標註 | 未標註 | 5 | 16.07 ms |
| 50／Lexical | 32/44 | 40/44 | 43/44 | 43/44 | 68/72 | 5/6 | 5 | 5.28 ms |
| 50／Vector | 16/44 | 37/44 | 41/44 | 41/44 | 62/72 | 4/6 | 5 | 13.11 ms |

Challenge 有 6 題不支援需求，沒有 Gold View，因此 Gold 分母為 44；6 題仍保留於候選數與延遲統計。所有數字是待審題的探索結果。SQL 正確率、確認 Precision／Recall、端到端耗時與完整 Pipeline 的 LLM 成本均未測；檢索工具本身為 0 次生成呼叫。

Vector 使用 `nomic-embed-text`，權重 digest 為 `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`；索引建立為 5510.65 ms。Vector 只補到原始同分案例及其 Challenge 複本；另有 50 題 Gold 只有 Lexical 選到，兩者共同漏 Gold 為 0。完整差異清單見 `run.json.comparison`。

失敗案例 `RETAIL-ORDER_SUMMARY-S3-03`（Challenge 複本 `RETRIEVAL-AMBIGUOUS-04`）：需求為逐筆成交管道、毛利及會員名稱 LIKE 王%；Gold 為 `v_order_summary`，有效解釋另有 `v_sales_detail`。Lexical 全部排名與分數如下：

| 排名 | View | retrieval／rerank 分數 | 來源 |
|---|---|---:|---|
| 1 | v_sales_detail | 0.11199999999999999 | lexical |
| 2 | v_customer_value | 0.09266666666666666 | lexical |
| 3 | v_store_monthly_kpi | 0.06933333333333333 | lexical |
| 4 | v_product_monthly | 0.066 | lexical |
| 5 | v_daily_sales | 0.06333333333333334 | lexical |
| 6 | v_order_summary | 0.06333333333333334 | lexical |
| 7 | v_inventory_status | 0.03266666666666667 | lexical |

根因為最後一道嚴格前五名截斷；Contract 或 Validator 並未參與此失敗。首選解法是同分保留，不需新檢索策略。其餘有效 View 的召回缺口以逐題 `valid_views` 對 `selected_views` 可重建；標註與原因仍須人工審查，不據此立即導入 Column-first。

決策：`ACCEPT_AND_CONTINUE_TESTING`。已重現原始 394/395 及同分第六名；維持 Production Lexical，進入 MVP 1。MVP 0 的人工標註驗收尚未完成。

## MVP 1：實作規則

`select_with_ties()` 保留原本前 K 個候選，再保留與門檻分數完全相同者。比較採同次運算的 IEEE-754 精確值，不使用浮點容許誤差；差一個可表示浮點值也不算同分。非有限分數與非正整數上限不允許進入選擇。

初步 lexical／vector 候選與 rerank 後選擇都套用相同規則，避免更早的截斷隱藏同分候選。Vector 的記憶體索引原本就會掃描 Catalog，現在觀察全部結果後再依門檻選取。相同分數依有版本的 Catalog 順序排序，維持原有第五、六名次序，並避免後端輸入順序改變結果。日誌及逐題紀錄保留超過 K 的數量。

沒有新增依賴、設定或生成模型呼叫；逐 View Mapping、SQL Validator 與確認流程沿用現況。候選增加可能使後續 Mapping 呼叫增加，其實際成本需另行量測。


## MVP 1：實測結果與決策

執行版本：`eb04d5b7`；完整數據：`projects/retail/artifacts/retrieval/20261019T055113528938Z-eb04d5b7/`。題庫及 Contract 指紋與 MVP 0 相同。全套離線測試為 235 passed。

| 指標 | 修改前 | 修改後 |
|---|---:|---:|
| 395 題 Gold Selected Recall | 394/395 | 395/395 |
| 395 題嚴格 Gold Recall@5 | 394/395 | 394/395 |
| 395 題 Recall@1／3 | 245／356 | 245／356 |
| 395 題平均候選 | 5 | 5.05823 |
| 395 題檢索 P95 | 5.87 ms | 5.85 ms |
| Challenge Gold Selected Recall | 43/44 | 44/44 |
| Challenge Valid View Recall | 68/72 | 69/72 |
| Challenge 完整歧義覆蓋 | 5/6 | 6/6 |
| Challenge 平均候選 | 5 | 5.08 |
| SQL Correctness | 未測 | 未測 |
| 完整 Pipeline 平均 LLM 呼叫／端到端延遲 | 未測 | 未測 |

395 題原有前五名全部保留，總計增加 23 個候選；Challenge 增加 4 個，合計 27／2225，候選送驗量增加 1.21%。這是候選成本，尚不是實際 LLM 呼叫增幅。Vector 結果維持 348/395 與 41/44，沒有新增互補的 Gold 收益。

以下三個 Challenge 的等價替代 View 分數低於門檻；Gold 及其業務解釋的其他代表仍在候選中。不是同分問題，不透過任意改排名掩蓋，完整排名／分數／來源見 `lexical-failures.jsonl`。

| 題目 | 未召回的有效替代 View | 排名／分數 | 根因與處置 |
|---|---|---|---|
| EXACT_MATCH-07：交易日門市訂單數 | v_order_summary | 7／0.13333333333333333 | 全文分數低於 0.19242424242424241；daily 與 detail 已覆蓋相同解釋，先人工審核 |
| AMBIGUOUS-07：已完成訂單毛利總和 | v_product_monthly | 6／0.1987654320987654 | 分數低於 0.2962962962962963；其他四個等價來源已保留，先驗證下游等價判斷 |
| AMBIGUOUS-09：各門市各月毛利 | v_order_summary | 6／0.11449275362318839 | 分數低於 0.17101449275362315；含零交易／僅有交易兩種解釋皆保留，先人工審核 |

決策：`ACCEPT_AND_CONTINUE_TESTING`。同分根因已修復，原本成功的 394 題無召回退步。停止擴充檢索演算法，進入 MVP 2 下游測試；不能宣稱整體 SQL 回歸或人工驗收已通過。

## MVP 2：測試入口

`evaluations.retrieval_grain_probe` 重用既有 CallRecorder／TracedModel，單執行緒呼叫目前設定的真實模型，保存 Provider、Model、Quantization、模型 digest、Temperature、Top-P、Num-Ctx、Max-Tokens、每次 prompt／response、token 用量、SQL 驗證 trace 與延遲；不執行 SQL 或保存資料列。

```bash
.venv/bin/python -m evaluations.retrieval_grain_probe \
  --experiment-id retrieval-mvp2 --exploratory --max-model-calls 100
```

探測包含使用者指定的 Q1／Q2／Q3、可安全加總的全體毛利、缺少必要欄位、不支援 LIKE、禁止加總毛利率；Q3 出現訂單／明細選項時，分別選取並重新驗證。這是小樣本探索，不能代替 395 題完整 SQL 正確率回歸或人工審核後的確認 Precision／Recall。


## MVP 2：已重現的比較失敗與最小修正

修改前真實模型探測版本為 `095e075`，產物為 `projects/retail/artifacts/grain-probes/20261019T055323418326Z/`。Q1「查詢每張訂單的毛利」得到 `needs_clarification`，不符合明確需求；Q2「查詢每個商品明細的毛利」得到正確的 `ready`。取得 Q1 根因後結束該輪，剩餘問題不列為完成；Q3 中斷中的呼叫不作為成功或失敗的 SQL 樣本。

Q1 中已通過驗證的兩個方案分別為：明細 View 的 `SUM(gross_profit) GROUP BY order_id`，以及訂單 View 直接取 `gross_profit`。模型比較原本已選訂單 View，回傳原文證據「每張訂單」與契約證據「粒度：每筆已完成訂單一列」。程式要求使用者片段同時逐字出現在契約且只出現在一個契約；這個門檻否決了模型選擇，轉成不必要的確認。比較輸入也缺少已驗證的 QueryPlan，無法清楚區分結果 Grain 與原生 Grain。

修正範圍為既有 Semantic Comparison：加入已驗證 QueryPlan，並新增同一次比較呼叫可回傳的 `equivalent` 結果。模型須涵蓋全部有效候選、說明原因，且每個 View 提供至少兩段可核對的契約原文，其中包含相關指標定義。程式另檢查結果鍵、WHERE 與 HAVING 一致；明細按訂單分組可與訂單原生鍵相容，純 scalar aggregation 可彼此相容。這只是必要條件，指標與母體是否等價仍由既有比較模型核對。沒有已知鍵、缺少證據、原生訂單與原生明細不同鍵、篩選不一致時，不接受等價宣稱。

原本針對共享模糊詞的選擇限制維持；沒有新增檢索策略、Node、依賴或模型呼叫。`select` 仍需原有證據，`equivalent` 是獨立且有條件的比較結果。結果鍵使用 Contract／QueryPlan 的實際欄位，不主動推測跨欄位別名。

新增測試在修改前為 2 failed、3 passed；修正後包含原有澄清與探測測試為 12 passed。隔離 worktree 全套為 241 passed、1 skipped（未複製的私有部署 fixture）；合併回原工作目錄後再驗證該 fixture。原本第六名 regression test 亦已確認在 `56f2228` 舊碼失敗。

目前決策：`REVISE_CURRENT_MVP`，先用真實模型驗證修正，再決定採納；不能以 scripted model 的測試宣稱實際比較模型已通過。


第一輪修正 `bcff446` 的真實探測為 `projects/retail/artifacts/grain-probes/20261019T060215419595Z/`。Q1 仍未通過：模型回傳 equivalent，但省略 reason，並引用 QueryPlan 的制式 explanation，未提供指標定義。程式正確拒絕這份不完整證據，因此該輪仍是 `REVISE_CURRENT_MVP`；取得原因後停止其餘探測。

第二輪將 QueryPlan 的 supported／explanation 排除於比較輸入，等價證據改為具名的 `grain_or_scope`、`metric_definition`，分別核對對應契約內容；Structured Output 要求 reason、equivalent_views、equivalence_evidence 完整回傳。新增制式說明不能當作指標證據的 regression test。先以原始真實模型已產生且重新編譯驗證的 Q1 mapping 重測比較模型，另行標記 comparison-only，避免混入完整 Pipeline 成本。


## MVP 2：最終小樣本結果

執行版本：`29551146370c3be9d19047d69cf864e3fe1d51a3`。全套離線測試為 **243 passed**，包含缺少契約證據、制式說明冒充指標證據、不同結果鍵與不同篩選不得視為等價，以及原有 API／CLI／UI 確認流程。

Q1 的聚焦真實比較產物：`projects/retail/artifacts/grain-probes/20261019T060837998334Z-comparison-only/`。來源為最初真實 Mapping；兩個方案重新經過現有 Compiler 與 SQL Validator，結果保存在 `revalidated-sql.jsonl`。只重跑比較模型一次，得到等價並選擇按訂單彙總的明細方案；這是 comparison-only，不能當作完整 Pipeline 的延遲或呼叫數。

其餘真實流程產物：`projects/retail/artifacts/grain-probes/20261019T061009438521Z/`。重現命令：

```bash
.venv/bin/python -m evaluations.retrieval_grain_probe \
  --experiment-id retrieval-mvp2-final --exploratory \
  --max-model-calls 100 --case-id GRAIN-Q3 --case-id GRAIN-EQUIVALENT
```

模型為 Ollama `qwen3.8:27b`、Q4_K_M；digest 為 `aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`。Temperature=0、Top-P=1、Num-Ctx=16000、Max-Tokens=8192，完整 request／response 與用量已保存。

| 探測 | 修改前 | 修改後／本次觀察 | 實際生成呼叫 | 耗時 |
|---|---|---|---:|---:|
| Q1：每張訂單毛利 | 錯誤要求確認 | 原始 Mapping 重新驗證後，比較模型接受等價 | 1（僅比較） | 32.46 秒（僅比較） |
| Q2：每個商品明細毛利 | ready，SQL 使用明細 View | 原路徑不需修改；最終版本未重跑此完整題 | 前測 5 | 前測 205.68 秒 |
| Q3：逐筆管道與毛利 | 未完成前測 | needs_clarification，選項恰為訂單／明細 | 6 | 136.09 秒 |
| Q3：選擇訂單 | 未完成前測 | 重新驗證後 ready，訂單原生粒度 | 6 | 103.28 秒 |
| Q3：選擇明細 | 未完成前測 | 重新驗證後 ready，明細原生粒度 | 6 | 146.23 秒 |
| 全體已完成訂單毛利加總 | 未測 | 多個 scalar SUM 方案等價，ready、不確認 | 6 | 366.53 秒 |

最後一輪共 4 個流程斷言通過、24 次模型呼叫；Q1 聚焦驗證另為 1 次。Q3 三次各消耗 input 19033／output 1038 tokens；全體毛利為 input 19017／output 1180 tokens。這些數字包含逐 View Mapping 與既有語意比較，並非新增 Retrieval 的模型呼叫。

Q1 比較呼叫的 input tokens 由 554 增為 833，output tokens 由 55 增為 342；耗時由 6.79 秒增為 32.46 秒。呼叫數仍為一次，但證據較完整會增加輸出成本。這是單題探索，暖機／執行環境也未控制；尚不能據此宣稱全部題目的平均 LLM 成本、端到端 P95 或成本驗收通過。

另執行完整契約容量檢查：`projects/retail/artifacts/retrieval/contract-admission-20261019T061810512058Z.json`。原 395 題共 **1998/1998** 個候選能容納完整契約，Gold **395/395** 能送驗；嚴格 Recall@5 仍是 **394/395**。新增同分候選沒有在完整契約打包時再次漏掉。

本輪未執行三個 CONTRACT-COLUMN／OPERATOR／AGGREGATION 的真實模型探測；未執行全部 395 題端到端 SQL 評估，也未完成其餘 Challenge 的下游確認評估。相關整體 SQL Correctness、Clarification Precision／Recall 與完整 Pipeline P50／P95 皆為「未測」，不能以檢索結果、單元測試或上述小樣本替代。

決策：`ACCEPT_AND_CONTINUE_TESTING`。保留同分修正及已通過小樣本的 Semantic Comparison 修正，繼續待審題庫的人工標註、完整 SQL 回歸與成本驗收。不新增 Retrieval Node、生成模型或依賴；不啟用 Column-first、Grain Diversity、Hybrid、Dynamic Router 或 Slot Extraction。這不是正式環境上線決定，也不是最終驗收完成。

## 交付檔案與後續驗收

| 階段 | 主要檔案 | 狀態 |
|---|---|---|
| 現況保存 | 起始工作目錄的原有修改，提交 9ab8778 | 已保存，未丟棄既有工作 |
| MVP 0 | evaluations/retrieval_benchmark.py、evaluations/data/retail_retrieval_challenge.jsonl、tests/unit/test_retrieval_benchmark.py | 445 題探索對照完成，人工審核未完成 |
| MVP 1 | src/cpea/infrastructure/retrieval/schema.py、tests/unit/test_retrieval_ties.py | 395/395 Gold Selected，原本 394 題召回不退步 |
| MVP 2 | src/cpea/workflows/text_to_sql/sql_generation.py、evaluations/retrieval_grain_probe.py、tests/unit/test_semantic_equivalence.py、tests/unit/test_retrieval_grain_probe.py | 特定真實模型流程通過；完整回歸與成本仍待驗收 |
| 報告 | 本文件、evaluations/README.md、既有診斷報告文字 | 分開呈現候選基準 K、嚴格排名與實際候選 |

50 題人工閱讀清單位於 `projects/retail/artifacts/retrieval/challenge-review-v1.md`。必須由人工核對並核准標註，再將相同版本題庫用於正式檢索與完整 SQL／確認流程評估；既有 395 題也仍是 pending。原題庫預期答案與 YAML 完全未修改。所有原始數據保持在私有 artifacts，沒有資料庫查詢回傳資料。
