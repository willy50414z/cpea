# SQL 生成穩定性驗證

流程先由檢索與 context budget 選出候選契約，再依排名逐一將單一 View 契約與完整需求交給模型，回傳欄位、條件、排序與分組對應。當次 JSON Schema enum 只包含該 View 及其欄位；不傳入 samples、題庫或預期答案。Python 檢查原文引用、literal 承接與契約政策，由 compiler 產生唯讀 MSSQL；失敗時試下一個候選，成功就停止。

字面檢索以 View 摘要及最相關的三個欄位描述評分，避免欄位較多的 View 因全文命中較多而佔優勢；需求明示完整 View 名稱時優先保留該 View。模型若選中 View 卻同時宣稱不支援，或將必要的聚合、分組、排序、篩選語意放進 `ignored`，會被退回修正。可用 `uv run --locked python -m evaluations.retail_view_retrieval --report projects/retail/evaluations/view_retrieval_diagnostic.md` 離線比較原本與目前的正確 View 排名；此檢查不呼叫模型，也不代表最終 SQL 正確。

`MATCH_PROMPT` 上限為 2,000 字。MATCH v9 使用 Markdown 標題與條列，先要求模型填寫顯示指標及分組維度，再處理篩選與排序；單一候選的 JSON Schema 限制輸出形狀及名稱。驗證失敗後，修正呼叫會收到同一 View 契約、前次映射與具體錯誤；不會把其他 View 的欄位放進同一呼叫。HAVING 條件須有明確聚合或分組後門檻語意；普通資料列門檻不得自行改為 HAVING，錯誤映射會退回修正。候選契約只提供已設定的欄位屬性；v3 View 契約不使用 `default_aggregation`。明確代碼或數值未被承接時拒絕查詢，避免漏掉篩選後擴大查詢；這不是完整的自然語言解析器。

Ollama 的推理模式由 `ASSISTANT_LLM_REASONING` 明確控制，預設 false。啟用時需要足夠的 `ASSISTANT_LLM_NUM_PREDICT`，因為推理也使用輸出額度。LangChain 將推理內容與最終 JSON 分開；產品 SQL／結果不包含推理內容。

目前預設使用 HILP 的獨立 MATCH v10；上游 v1–v9 prompt 與 schema 保留供歷史比較。v10 延用逐一候選與同一 View 修正流程，在 QueryPlan 硬性驗證後檢查完整詞彙證據，需要時先請使用者確認，再產生 SQL；確認後不重跑 MATCH。詳見[欄位確認流程](hilp_confirmation.md)。

`ASSISTANT_LLM_NUM_PREDICT=-1` 或 runner 的 `--max-output-tokens -1` 可取消明確輸出上限。Ollama 傳送 `num_predict=-1`；Azure／GCP 不指定輸出 token 上限，仍受模型與服務本身限制。正在執行的 Gradio／API 服務需重新啟動才會載入 `.env` 變更。

## 網頁與評估結果不一致時

- 核對 project、prompt 版本、檢索方式、context 與輸出額度。舊版 prompt 的通過紀錄不能直接視為 v10 的穩定性成績。
- `execution_preflight / sql_executor_unavailable` 表示尚未進入 SQL 生成。首頁在 project 缺少 executor／datasource 時改用純生成模式，仍可完成 HILP，結果明確標示未執行查詢。
- 「整理報表時照城市別分組……」實際是 `RETAIL-STORE_MONTHLY_KPI-M3-03`，目標為 `demo_retail.v_store_monthly_kpi`。完成訂單筆數、毛利及完整月份旗標的門檻都是 WHERE，不能因另外按城市分組就改成 HAVING。

2026-10-17 的本地診斷使用 `qwen3.8:27b`、lexical、context 16000、輸出上限 8192。v10 在同一 View 修正一次後進入 HILP；以隔離暫存詞彙檔和明確測試選項確認後，產出 `SUM(units_sold)`、`MAX(revenue)` 與上述三項 WHERE。診斷僅保留自然排名第一的候選，未呼叫資料庫，未寫入正式詞彙檔；這是單次流程驗證，不是三次重複穩定性成績。另已補上「單列最大值／最小值」語法及詞彙邊界的離線回歸測試，避免正確草稿被未承接的「值」拒絕，或把比較、排序語法存成業務詞。

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
