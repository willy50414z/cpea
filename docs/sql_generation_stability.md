# SQL 生成穩定性驗證

流程先由檢索與 context budget 選出候選契約，再讓模型比較完整需求，回傳單一 View 的欄位、條件、排序與分組對應。欄位與 View 名稱的 JSON Schema enum 由實際送出的契約產生；不傳入 samples、題庫或預期答案。Python 檢查原文引用、literal 承接與契約政策，再由 compiler 產生唯讀 MSSQL。

`MATCH_PROMPT` 上限為 2,000 字。`default_aggregation` 只提供模型依據，模型明確回傳 null 時不自動補聚合。明確代碼或數值未被承接時拒絕查詢，避免漏掉篩選後擴大查詢；這不是完整的自然語言解析器。

Ollama 的推理模式由 `ASSISTANT_LLM_REASONING` 明確控制，預設 false。啟用時需要足夠的 `ASSISTANT_LLM_NUM_PREDICT`，因為推理也使用輸出額度。LangChain 將推理內容與最終 JSON 分開；產品 SQL／結果不包含推理內容。

`ASSISTANT_LLM_NUM_PREDICT=-1` 或 runner 的 `--max-output-tokens -1` 可取消明確輸出上限。Ollama 傳送 `num_predict=-1`；Azure／GCP 不指定輸出 token 上限，仍受模型與服務本身限制。正在執行的 Gradio／API 服務需重新啟動才會載入 `.env` 變更。

## 測試順序

1. 用 `cpea-eval --project gms2 --runs 1 --concurrency 1` 執行單次正確率評估。
2. 用同一份 `projects/gms2/evaluations/cases.jsonl` 執行 `--runs 3`，觀察正確率與重複生成的一致性；報告依 `category` 分別列出基本與口語案例。
3. 需要分階段排查模型回覆時，才使用下方進階 `mvp`／`workflow` runner；它仍將結果寫入舊版全域 `artifacts/stability/`，不算新的專案 run。

正式專案評估的入口只需 project、runs、concurrency。執行前確認工作目錄乾淨、安裝了對應 provider 套件，並確認 `projects/gms2/.env` 設定的模型服務可用。

```bash
uv run --locked cpea-eval --project gms2 --runs 1 --concurrency 1
uv run --locked cpea-eval --project gms2 --runs 3 --concurrency 1
```

以下進階診斷仍需要明確指定模型、題庫、env 與輸出路徑：

```bash
uv pip install --python .venv/bin/python --no-deps --editable .
CPEA_PROFILE_PATH="$PWD/projects/gms2" .venv/bin/python -m evaluations.stability_runner mvp \
  --env-file projects/gms2/.env --dataset projects/gms2/evaluations/cases.jsonl \
  --provider ollama --model gemma4:26b --reasoning --max-output-tokens 8192 \
  --all-candidates --constrain-names --question '需求原文' --view '核准的完整View名稱' \
  --output artifacts/stability/mvp-unique-run

CPEA_PROFILE_PATH="$PWD/projects/gms2" .venv/bin/python -m evaluations.stability_runner workflow \
  --env-file projects/gms2/.env \
  --provider ollama --model gemma4:26b --reasoning --max-output-tokens 8192 \
  --retrieval-mode lexical --dataset projects/gms2/evaluations/cases.jsonl \
  --output artifacts/stability/workflow-unique-run
```

題庫的預期欄位必須對應選定專案的 profile。進階 runner 可加 `--execute` 使用部署設定的真實唯讀 executor，驗證 SQL 可執行；不提供假結果，也不宣稱已驗證所有業務數值。

## 紀錄與成本

每次執行使用新的輸出目錄，保留 `run.json`、`calls.jsonl`、`results.jsonl`、`summary.json`；資料庫執行另有 `execution.jsonl`。原始紀錄可能含問題、SQL、推理與企業欄位，保存於 Git 忽略的 `artifacts/`。

共用 `artifacts/stability/cloud-calls.jsonl` 呼叫帳本；同平台不同模型合併計數。每次呼叫前先鎖定帳本並預留，失敗也計入。Azure／GCP 各達 500 次後切換到 Ollama，不能換新帳本規避上限。雲端 SDK 隱藏重試停用，provider 錯誤立即記錄並暫停。遇到 quota、auth 或 network 錯誤先分類檢討，不盲目重跑。

指定 `--no-ollama-fallback` 可在達到雲端呼叫上限時停止，避免切回 Ollama。若使用者明確授權增加雲端呼叫，才可用 `--cloud-call-limit` 設定新的絕對累計上限；原帳本與既有計數必須保留，預設仍為每平台 500 次。測試 metadata 會記錄這兩項設定。

實測結果與每輪錯誤檢討保存在 `artifacts/stability/20261015/`；不同 prompt、模型、推理模式或 source fingerprint 的結果分開解讀。
