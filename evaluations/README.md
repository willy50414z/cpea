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

## 查詢 Pipeline：SQL 階段

獨立入口 `python -m evaluations.query_pipeline_runner`（安裝新版套件後亦可用 `cpea-pipeline-eval`）提供 `planning`、`sql`、`integrated` 三種模式，依序對應原始需求的切割、核准任務的單 View SQL 生成，以及自然串接。既有 CLI、API、網頁與單題服務不改道。

目前兩段預設皆為 Ollama `qwen3.8:27b`，僅先作連通 smoke；正式面板與三輪驗收留待人工核准及分階段調校。可明確指定各節點 provider／model；`--ollama-base-url` 設定 Ollama 端點。以下命令會呼叫真實模型，須明確使用 `--live`；待審案例必須加 `--exploratory`，不計為正式驗收：

```bash
.venv/bin/python -m evaluations.query_pipeline_runner \
  --mode integrated --profile projects/retail \
  --cases projects/retail/evaluations/query_pipeline_cases.jsonl \
  --env-file .env --ollama-base-url http://127.0.0.1:7401 \
  --planner-provider ollama --planner-model qwen3.8:27b \
  --sql-provider ollama --sql-model qwen3.8:27b \
  --runs 1 --exploratory --live
```

連通 smoke 應先把單一正向案例複製到另外的 casefile，保留原案例與內容指紋，再透過 `--cases` 指向該檔；不要將 smoke 混入完整面板三輪分母。程式注入的 `planner_factory`／`generator_factory` 屬離線 stub，永遠不計為自然成功。每個 trial 使用全新的 mapping repository 與 registry；不沿用產品詞彙、不建立 executor 或 DB runtime，不改寫 `.env`。

`sql_ready` 要求所有核准 task 通過整批 preflight、task-to-QueryPlan 語意核對、compiler 重編譯及 SQL policy；它只表示 SQL 階段就緒。NULL／boolean filter、conditional metric、metadata 集合、相依輸入與不支援的 operator／value 均整批拒絕。第一個 pending／錯誤會停止後續任務；先前 SQL 僅保存在私有證據。外層目前沒有確認恢復或 DB／整合／回答能力。

每次建立新目錄，包含 `run.json`、`events.jsonl`、`planning.json`、`result.json`、`grading.json` 與繁體中文 `overview.md`。公開摘要僅含固定狀態、問題碼、計數與私有引用；`private/trials/<安全編號>/` 保存原文、planning、實際交接、generation、被 gate 拒絕的原始計畫與 model calls。模型 task_id 不用作路徑。原始 provider 診斷保存於 `private/provider-error.txt`；provider 錯誤停止剩餘 trial，不補跑，rate limit 依根目錄 `AGENTS.md` 處理。

輸入核准與輸出審核分開。案例 `approved_plans` 中的替代必須是完整方案，不能混拼各方案片段。`automated_pass` 僅代表確定性檢查；自然成功還要求對該 `response_sha256` 的人工 `output_reviews` 核准。事後人工審查可使用獨立 UTF-8 JSON：最外層為 case_id，下一層為 response_sha256，再填 `decision=approved`、`reviewer`、`reviewed_at`；透過 replay 的 `--reviews <審查檔>` 載入，會記錄審查檔指紋，不改寫題庫或原 run。未審核輸出、stub、replay、skipped 與未完成 trial 都不會提高新增自然成功率。模型版本無法確認時保留 `model_version_verified=false`；缺少 provider 用量保留 null。

離線重評不呼叫模型或 DB，寫入新目錄並保留原 mode／input_origin；case／catalog 漂移會拒絕，source／prompt／schema 漂移另標記。`sql_ready` 的錄製 SQL 仍會重新執行 gate：

```bash
.venv/bin/python -m evaluations.query_pipeline_runner \
  --mode integrated --profile projects/retail \
  --cases projects/retail/evaluations/query_pipeline_cases.jsonl \
  --replay projects/retail/artifacts/query_pipeline/<原始run目錄>
```

能力矩陣與待審面板見 [S1 能力矩陣](../docs/superpowers/plans/2026-10-22-query-agent-integration/capability-matrix.md)。本階段尚未完成正式自然品質驗收。

## 共用與歷史工具

`evaluations/` 保留共用評分、治理 runner、模型矩陣範例與合成 fixture。舊版兩份 reliability JSONL 保存在 `examples/legacy-evaluation-cases/` 作來源對照；既有 `artifacts/evaluations/`、`artifacts/stability/` 和原 PoC 封存保留原位，不改寫為新的專案 run。

`cpea-governance-eval compare` 可用於額外的多模型研究，必須明確指定 `--cases`、`--models` 與 `--env-file`。舊 `cpea-query-eval` 與 `python -m evaluations.stability_runner` 是進階診斷入口，現在也必須明確傳入 `--dataset`；它們不會自動選取專案。.env 中的 API key、DB 密碼與帶認證資訊的 endpoint 不寫入 metadata 或摘要。

## 欄位確認評估

預設 MATCH v10；`cpea-eval --prompt-version v10 --runs 3` 對每個已核准案例重複三次。統一 JSONL 可包含 `case_kind=hilp`，以明確腳本確認、取消或檢查詞彙沿用。每次使用隔離的詞彙 JSON；多階段狀態保存於 `hilp_phases`，另產出 `hilp_summary.json` 統計語意誤放行、過度確認與三次穩定性。pending／過期審核不算正式通過。舊 Retail 題庫產生器固定 v6；不要因預設版本改變就覆寫已核准 ground truth。詳細協定與限制見 [欄位確認文件](../docs/hilp_confirmation.md)。
