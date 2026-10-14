# 品質評估

分階段的真實模型穩定性驗證使用 `python -m evaluations.stability_runner`。先做模型 MVP，每項修改至少 3 次，再跑完整 workflow；每批累計 3 次失敗立即停止檢討。原始題庫通過後使用 `datasets/query_reliability_colloquial.jsonl`，可加 `--execute` 驗證真實 SQL Server 執行。

此 runner 保留逐筆呼叫、回覆、驗證與執行紀錄，以共用帳本限制 Azure／GCP 各 500 次呼叫並切換 Ollama。完整流程、模型推理設定與輸出規格見 [SQL 生成穩定性驗證](../docs/sql_generation_stability.md)。題庫與答案只用於評分，不傳入模型 context。

`runners/` 保留 query reliability；多模型端到端比較與穩定性測試使用 `governance_runner.py`。`datasets/` 僅含可分發的合成題庫；原專案題庫及歷史結果僅保存在私有的 `artifacts/baseline/original-poc.zip`，由 `original-inventory.json` 記錄逐檔 SHA-256，不納入 wheel／sdist。

執行 no-DB 評估前明確選擇模型服務與 profile：

```powershell
cpea-query-eval --env-file .env --runs 3
```

預設結果位於 `artifacts/evaluations/<run-id>/`；明確指定輸出目錄也不能覆寫已存在檔案。每個 run 帶 run ID、UTC 時間、產品版本／程式摘要、模型／供應商、非機密設定摘要、profile／契約版本及內容摘要、題庫摘要。Optional provider 和 cross-encoder 依賴列在 `requirements/optional.txt`，不屬本次驗證的核心 lock。

評估產物可能包含使用者題目、SQL、trace、prompt、context 或結果列，應當作私有資料保存。設定 metadata 只採允許的非機密欄位；credential 與含認證資訊的 endpoint 不輸出。原歷史結果缺少部分版本資訊，保留其原始內容，但不能和新設定下的延遲／正確率直接比較。

保存、存取與清除由部署方管理。本次沒有提供 durable audit、retention job 或資料庫。不要將 `private/`、`artifacts/` 加入公開版本或通用發行包。

## 模型治理評估

`datasets/governance_cases.json` 是可分發的合成起始題庫；`config/models.json` 是獨立的模型矩陣（目前範例只含一個 Azure 目標；多模型比較須另外配置）。兩者皆為版本 1 JSON。實際企業驗收應使用獲授權的私有題庫；合成案例不代表業務正確率。模型名稱與 deployment 必須依租戶實際可用清單填寫。正式執行前仍須確認目標區域及帳號可用。

```powershell
# 只在完成設定、提交程式使 worktree 乾淨，並注入必要 executor 後，才使用 --live。
uv run --locked cpea-governance-eval compare --cases evaluations/datasets/query_reliability.jsonl --models evaluations/config/models.json --env-file .env --runs 3 --concurrency 1 --max-failures 3 --live
uv run --locked cpea-governance-eval stability --cases evaluations/datasets/query_reliability.jsonl --env-file .env --runs 3 --concurrency 1 --max-failures 3 --live
uv run --locked cpea-governance-eval report artifacts/evaluations/<run-id>
```

不加 `--live` 時，CLI 不會呼叫模型；程式測試可注入 stub model factory 做離線驗證。`stability` 直接使用 `.env` 指定的單一 provider／model，`compare` 逐一套用矩陣。Azure 使用 OpenAI-compatible endpoint，矩陣指定的 endpoint 與 API key 由 `CPEA_AZURE_LLM_BASE_URL`／`CPEA_AZURE_LLM_API_KEY` 注入。GCP 使用 Vertex AI，透過 `CPEA_GCP_PROJECT`、可選的 `CPEA_GCP_LOCATION` 及 ADC 或 `CPEA_GCP_LLM_API_KEY`。雲端套件列於 `requirements/optional.txt`，核心安裝不包含它們。需要驗證回答的題目須由部署方透過 Python 注入唯讀 SQL executor；未注入時會回報 error，不會以假資料代替。

正式模型執行先確認 Git worktree 乾淨、記錄 HEAD SHA，並確認 `artifacts/evaluations/<run-id>/` 被 Git 忽略。輸出包括私有 `calls.jsonl`、`results.jsonl`、`run.json`，以及從它們產生的 `summary.csv`、`model_summary.csv`、`overview.md` 和 `cases/<case_id>.md`。模型彙總列出通過率、錯誤率及端到端延遲 p50／p95；缺少 token usage 的欄位留空。原始 request／response 可能含敏感資料；分享報告僅列檢查種類、結果代碼及 call ID。缺少 provider token usage 或量化資料時保留空值。此變更交付只執行離線 stub 測試，未呼叫任何真實模型，因此沒有實測模型通過率。

`--cases` 接受原治理 JSON 格式，亦可直接讀取 reliability JSONL。JSONL 使用原 `evaluate_cases` 評分規則，包含額外 filter、運算子、投影欄位、精確 group/order 與聚合檢查，不轉寫題庫答案。題庫為 GMS2 View 時，`.env` 須使用對應私有 profile；口語化題庫可替換為 `evaluations/datasets/query_reliability_colloquial.jsonl`。

`compare` 預設 `--runs 1`；多模型穩定性比較必須明確指定 `--runs 3`。`--max-failures 3` 對每模型分別計數且要求 `--concurrency 1`。提早停止的未完成題目不計入通過率，也不代表完整題庫通過。此治理 CLI 不提供雲端共用帳本限制；需要上限與錯誤暫停時，須使用受限模型包裝，或分階段 stability runner。

`model_summary.csv` 包含所有已執行次數的通過率、完成評分通過率、錯誤率、token 總量與用量完整呼叫數、LLM／端到端累計耗時及延遲 p50／p95。完整重複題目另列全部通過、狀態一致與生成結果一致的題數；穩定失敗也可能狀態一致，因此不能用一致性代替正確率。生成一致性比較 supported、selected_views、query_plan 與 SQL，忽略 trace 與 latency。缺少任何呼叫的 provider token 用量時，該模型總量留空；不估算、不將缺漏算成零。
