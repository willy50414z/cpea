# 品質評估

## View Retrieval 漸進評估

使用 `python -m evaluations.retrieval_benchmark --experiment-id <實驗名稱> --exploratory` 比較相同 395 題 Regression 與 50 題待審 Challenge 的 Lexical／純 Vector 排名。工具要求乾淨 worktree，記錄版本、全部分數與實際候選，並分開計算嚴格 Recall@5 與含同分的 Gold Selected Recall。未完成題庫人工審核時，不能省略 `--exploratory`。

目前採納範圍為 View 篩選的同分保留及檢索評估；Semantic Comparison 維持起始版本。本工具不量測完整 SQL 正確率。版本、命令、成本、失敗案例與階段決策見 [漸進改善紀錄](../docs/view_retrieval_improvement.md)。

## 前置需求拆分評估

`cpea-plan-eval` 只評估資料分工規劃，輸出各子任務的 View、必要欄位、條件、粒度、整合計畫及 text-to-sql request，不生成或執行 SQL。Retail 專用題庫為 `projects/retail/evaluations/task_decomposition_cases.jsonl`；與既有 SQL 題庫分開。

```bash
.venv/bin/python -m evaluations.decomposition_runner --project retail --env-file .env --model gpt-6-sol --runs 3 --exploratory
# 安裝套件後也可使用 cpea-plan-eval 搭配相同參數。
```

這個入口從根目錄 `.env` 的 `CPEA_AZURE_LLM_BASE_URL`、`CPEA_AZURE_LLM_API_KEY` 取得 Azure 設定，明確使用指定 deployment，不沿用預設 Ollama 模型，也不依賴 `projects/retail/.env`。資源根 URL 會依 [Azure v1 文件](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle) 補上 `/openai/v1`；已含該 suffix 則保留。模型呼叫不設次數上限，SDK 不重試；遇 provider 錯誤停止後續呼叫並記錄 failed／skipped。rate limit 的原始診斷保存於私有 `provider-error.txt`，依本機帳號額度流程判讀，不直接重跑。

30 題三輪合計 90 次規劃呼叫，第一輪同時為基準，不另外 warmup。新題庫初始皆為 pending，需 `--exploratory`；自動通過不能當作人工核准。輸出位於 `projects/retail/artifacts/task_decomposition/<run-id>/`；包含逐題結果、私有原始呼叫、prompt/schema/契約/題庫/Git 指紋與繁體中文摘要。主要 View 命中與等價任務正確率分開統計；整合及 request 語意仍需人工審查。未完成或略過不提高通過率，一致失敗不算穩定正確。

評分會正規化同一時間軸的月份條件與每日日期範圍，以及日期的含尾／不含尾表示；只用於 filter 的等價日期欄位不要求重複回傳，逐日輸出所需的日期欄位仍必須存在。只有來源契約鍵能證明唯一性時，才接受單列取值與 SUM 等價，或同一分組中的 COUNT 與 COUNT DISTINCT 等價。額外分組維度或遺失必要時間 metadata 仍列為差異，不用題目特例放寬。修正評分器時可使用 `evaluations.decomposition_reports.regrade_run` 離線重評；原始 run 不覆寫，新報告記錄原始結果 SHA-256、模型版本與評分版本，額外模型呼叫數為 0。

## 專案評估

每個私有專案位於 `projects/<project-id>/`，包含 View profile、專屬 `.env`、單一 `evaluations/cases.jsonl` 與執行產物。題庫與答案只用於評分，不傳入模型 context。GMS2 保留原有 reliability 題型；Retail 使用 View Matching 題型，每題記錄 `expected_match`、`expected_sql`、契約與 prompt 指紋，以及獨立的自動驗證和人工審核狀態。Retail manifest 目前為 `approved`；395 題（原有 385 題、3 題仍適用的既有缺口案例及 7 題降冪案例）已通過自動結構驗證，人工審核皆為 `pending`。

```bash
uv run --locked cpea-eval --project gms2 --runs 1 --concurrency 1
uv run --locked cpea-eval --project gms2 --runs 3 --concurrency 1
uv run --locked cpea-eval --project retail --exploratory --runs 3 --concurrency 1 --max-model-calls 500
```

`--project` 自動選取專案 `.env`、View 契約、題庫及報告位置；`--runs 1` 是單次正確率觀察，重複執行才有穩定性統計。指令只跑設定中的真實模型，不提供假模型模式或手動輸出目錄。Draft 契約必須明確加 `--allow-draft-profile`；這只影響評估入口，一般查詢仍拒絕 draft。Retail 尚未有人工核准題，需加 `--exploratory` 才能測待審題，結果不列入正式通過率。正式執行只選當前契約下已核准的案例。專案身分與 `.env` 指向其他 profile 時會在模型呼叫前拒絕。

`--max-model-calls` 是每模型的實際 LLM 呼叫上限，包含 warmup、解析重試與答案生成；可用 `--call-ledger <私有路徑>` 跨 run 共用原子計數。達上限或遇 provider rate limit／認證錯誤後，該模型的其餘題目標為 `skipped`，不自動重跑或改用其他模型。`--max-failures` 是獨立的失敗次數限制。若專案不在 checkout 內，可由部署環境設定 `CPEA_PROJECTS_ROOT` 指向受保護的專案根目錄。

每次輸出到 `projects/<project-id>/artifacts/evaluations/<UTC時間>-<Git短SHA>/`，既有目錄不覆寫。`run.json` 記錄 project、Git SHA、非機密有效設定、模型／供應商、profile／契約、題庫與 MATCH_PROMPT system／human／response schema 指紋，以及預定、完成、略過次數。`calls.jsonl` 保留原始 LLM request／response；`results.jsonl` 保留解析後 mapping、QueryPlan／SQL 與分層評分。`overview.md`、`summary.csv`、`model_summary.csv`、`category_summary.csv`、`view_grid_summary.csv` 與 `cases/<case-id>.md` 是不含原始 prompt／response 的分享型摘要。`all_pass_cases` 計算完整重複且每次通過的題目，`status_consistent_cases` 只代表結果一致，一致失敗不算穩定正確；待審和 skipped 不提高正式通過率。缺少 provider token 用量時保留空值。報告可用 `cpea-governance-eval report <run目錄>` 重建。

Retail 題庫可用 `uv run --locked --extra postgres-contracts python -m evaluations.retail_view_benchmark --check` 驗證；這會以唯讀資料庫連線檢查各 View 的 `grain.keys` 在目前資料中沒有重複值，再核對題庫與覆蓋報告。重建時省略 `--check`，不會查詢資料庫。產生器會保留內容與契約指紋相同題目的審核 metadata；題目或契約變更後需重新自動驗證及人工審核。人工核准需填 `review_status=approved`、`reviewer`、`reviewed_at`、`reviewed_case_sha256` 與 `reviewed_contract_fingerprint`；其中案例 SHA-256 是不含審核 metadata 的案例內容指紋。`validation_status=validated` 只代表程式檢查通過。產題準則見 `docs/prompt/benchmark_prompt.md`。

正式模型評估要求乾淨的 Git 工作目錄。客戶問題、SQL、trace、prompt、response 與資料列可能是私有內容；原始產物不可當作公開報告。`projects/` 與 `artifacts/` 被 Git 忽略，通用 wheel／sdist 也排除私有專案資料。本次沒有 durable audit、retention job 或資料庫；保存與存取由部署方管理。

## 共用與歷史工具

`evaluations/` 保留共用評分、治理 runner、模型矩陣範例與合成 fixture。舊版兩份 reliability JSONL 保存在 `examples/legacy-evaluation-cases/` 作來源對照；既有 `artifacts/evaluations/`、`artifacts/stability/` 和原 PoC 封存保留原位，不改寫為新的專案 run。

`cpea-governance-eval compare` 可用於額外的多模型研究，必須明確指定 `--cases`、`--models` 與 `--env-file`。舊 `cpea-query-eval` 與 `python -m evaluations.stability_runner` 是進階診斷入口，現在也必須明確傳入 `--dataset`；它們不會自動選取專案。.env 中的 API key、DB 密碼與帶認證資訊的 endpoint 不寫入 metadata 或摘要。

## 欄位確認評估

預設 MATCH v10；`cpea-eval --prompt-version v10 --runs 3` 對每個已核准案例重複三次。統一 JSONL 可包含 `case_kind=hilp`，以明確腳本確認、取消或檢查詞彙沿用。每次使用隔離的詞彙 JSON；多階段狀態保存於 `hilp_phases`，另產出 `hilp_summary.json` 統計語意誤放行、過度確認與三次穩定性。pending／過期審核不算正式通過。舊 Retail 題庫產生器固定 v6；不要因預設版本改變就覆寫已核准 ground truth。詳細協定與限制見 [欄位確認文件](../docs/hilp_confirmation.md)。
