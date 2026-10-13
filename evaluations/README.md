# 品質評估

`runners/` 保留 query reliability；多模型端到端比較與穩定性測試使用 `governance_runner.py`。`datasets/` 僅含可分發的合成題庫；原專案題庫及歷史結果僅保存在私有的 `artifacts/baseline/original-poc.zip`，由 `original-inventory.json` 記錄逐檔 SHA-256，不納入 wheel／sdist。

執行 no-DB 評估前明確選擇模型服務與 profile：

```powershell
cpea-query-eval --env-file .env --runs 3
```

預設結果位於 `artifacts/evaluations/<run-id>/`；明確指定輸出目錄也不能覆寫已存在檔案。每個 run 帶 run ID、UTC 時間、產品版本／程式摘要、模型／供應商、非機密設定摘要、profile／契約版本及內容摘要、題庫摘要。Optional provider 和 cross-encoder 依賴列在 `requirements/optional.txt`，不屬本次驗證的核心 lock。

評估產物可能包含使用者題目、SQL、trace、prompt、context 或結果列，應當作私有資料保存。設定 metadata 只採允許的非機密欄位；credential 與含認證資訊的 endpoint 不輸出。原歷史結果缺少部分版本資訊，保留其原始內容，但不能和新設定下的延遲／正確率直接比較。

保存、存取與清除由部署方管理。本次沒有提供 durable audit、retention job 或資料庫。不要將 `private/`、`artifacts/` 加入公開版本或通用發行包。

## 模型治理評估

`datasets/governance_cases.json` 是可分發的合成起始題庫；`config/models.json` 是獨立的六模型矩陣。兩者皆為版本 1 JSON。實際企業驗收應使用獲授權的私有題庫；合成案例不代表業務正確率。矩陣將 Azure 目標對應到 [Microsoft Foundry 型錄](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models) ID `FW-DeepSeek-V4.1-Flash`，Google 目標對應到 [Gemini 模型文件](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) ID `gemini-3.8-flash`；若租戶使用不同部署名稱，需修改 `deployment`。正式執行前仍須確認目標區域及帳號可用。

```powershell
# 只在完成設定、提交程式使 worktree 乾淨，並注入必要 executor 後，才使用 --live。
cpea-governance-eval compare --cases evaluations/datasets/governance_cases.json --models evaluations/config/models.json --env-file .env --live
cpea-governance-eval stability --cases evaluations/datasets/governance_cases.json --env-file .env --runs 3 --live
cpea-governance-eval report artifacts/evaluations/<run-id>
```

不加 `--live` 時，CLI 不會呼叫模型；程式測試可注入 stub model factory 做離線驗證。`stability` 直接使用 `.env` 指定的單一 provider／model，`compare` 逐一套用矩陣。Azure 使用 OpenAI-compatible endpoint，矩陣指定的 endpoint 與 API key 由 `CPEA_AZURE_LLM_BASE_URL`／`CPEA_AZURE_LLM_API_KEY` 注入。GCP 使用 Vertex AI，透過 `CPEA_GCP_PROJECT`、可選的 `CPEA_GCP_LOCATION` 及 ADC 或 `CPEA_GCP_LLM_API_KEY`。雲端套件列於 `requirements/optional.txt`，核心安裝不包含它們。需要驗證回答的題目須由部署方透過 Python 注入唯讀 SQL executor；未注入時會回報 error，不會以假資料代替。

正式模型執行先確認 Git worktree 乾淨、記錄 HEAD SHA，並確認 `artifacts/evaluations/<run-id>/` 被 Git 忽略。輸出包括私有 `calls.jsonl`、`results.jsonl`、`run.json`，以及從它們產生的 `summary.csv`、`model_summary.csv`、`overview.md` 和 `cases/<case_id>.md`。模型彙總列出通過率、錯誤率及端到端延遲 p50／p95；缺少 token usage 的欄位留空。原始 request／response 可能含敏感資料；分享報告僅列檢查種類、結果代碼及 call ID。缺少 provider token usage 或量化資料時保留空值。此變更交付只執行離線 stub 測試，未呼叫任何真實模型，因此沒有實測模型通過率。
