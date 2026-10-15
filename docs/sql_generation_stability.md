# SQL 生成穩定性驗證

流程先由檢索與 context budget 選出候選契約，再讓模型比較完整需求，回傳單一 View 的欄位、條件、排序與分組對應。欄位與 View 名稱的 JSON Schema enum 由實際送出的契約產生；不傳入 samples、題庫或預期答案。Python 檢查原文引用、literal 承接與契約政策，再由 compiler 產生唯讀 MSSQL。

`MATCH_PROMPT` 上限為 2,000 字。`default_aggregation` 只提供模型依據，模型明確回傳 null 時不自動補聚合。明確代碼或數值未被承接時拒絕查詢，避免漏掉篩選後擴大查詢；這不是完整的自然語言解析器。

Ollama 的推理模式由 `ASSISTANT_LLM_REASONING` 明確控制，預設 false。啟用時需要足夠的 `ASSISTANT_LLM_NUM_PREDICT`，因為推理也使用輸出額度。LangChain 將推理內容與最終 JSON 分開；產品 SQL／結果不包含推理內容。

`ASSISTANT_LLM_NUM_PREDICT=-1` 或 runner 的 `--max-output-tokens -1` 可取消明確輸出上限。Ollama 傳送 `num_predict=-1`；Azure／GCP 不指定輸出 token 上限，仍受模型與服務本身限制。正在執行的 Gradio／API 服務需重新啟動才會載入 `.env` 變更。

## 測試順序

1. 先用 `mvp` 直接測試模型與回覆驗證，不執行完整 workflow 或資料庫。
2. 每項模型修改至少測試 3 次，確認語意、原文引用與契約一致。
3. 再用 `workflow` 跑原始題庫，每題至少 3 次。
4. 原始題庫穩定通過後，測試口語化題庫，並選擇是否實際執行 SQL。
5. 同一批完整 workflow 累計 3 次失敗立即停止，檢討原始 request／response 與 trace 後，回到 MVP。

確認目前環境載入工作目錄的 `src/cpea`，避免測到舊 wheel。雲端使用時另安裝對應的選配 provider 套件。

```bash
uv pip install --python .venv/bin/python --no-deps --editable .
.venv/bin/python -m evaluations.stability_runner mvp \
  --provider ollama --model gemma4:26b --reasoning --max-output-tokens 8192 \
  --all-candidates --constrain-names --question '需求原文' --view '核准的完整View名稱' \
  --output artifacts/stability/mvp-unique-run

.venv/bin/python -m evaluations.stability_runner workflow \
  --provider ollama --model gemma4:26b --reasoning --max-output-tokens 8192 \
  --retrieval-mode lexical --dataset evaluations/datasets/query_reliability.jsonl \
  --output artifacts/stability/workflow-unique-run

.venv/bin/python -m evaluations.stability_runner workflow \
  --provider ollama --model gemma4:26b --reasoning --max-output-tokens 8192 \
  --retrieval-mode lexical --dataset evaluations/datasets/query_reliability_colloquial.jsonl \
  --execute --output artifacts/stability/colloquial-unique-run
```

題庫的預期欄位必須對應 `.env` 選定的 profile。口語化題庫保留原始合成需求的預期語意，不因模型失敗而改答案。`--execute` 使用部署設定的真實唯讀 executor，驗證 SQL 可執行；不提供假結果，也不宣稱已驗證所有業務數值。

## 紀錄與成本

每次執行使用新的輸出目錄，保留 `run.json`、`calls.jsonl`、`results.jsonl`、`summary.json`；資料庫執行另有 `execution.jsonl`。原始紀錄可能含問題、SQL、推理與企業欄位，保存於 Git 忽略的 `artifacts/`。

共用 `artifacts/stability/cloud-calls.jsonl` 呼叫帳本；同平台不同模型合併計數。每次呼叫前先鎖定帳本並預留，失敗也計入。Azure／GCP 各達 500 次後切換到 Ollama，不能換新帳本規避上限。雲端 SDK 隱藏重試停用，provider 錯誤立即記錄並暫停。遇到 quota、auth 或 network 錯誤先分類檢討，不盲目重跑。

指定 `--no-ollama-fallback` 可在達到雲端呼叫上限時停止，避免切回 Ollama。若使用者明確授權增加雲端呼叫，才可用 `--cloud-call-limit` 設定新的絕對累計上限；原帳本與既有計數必須保留，預設仍為每平台 500 次。測試 metadata 會記錄這兩項設定。

實測結果與每輪錯誤檢討保存在 `artifacts/stability/20261015/`；不同 prompt、模型、推理模式或 source fingerprint 的結果分開解讀。
