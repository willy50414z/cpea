# Retail 前置需求拆分實作計畫

> **供執行者：**核准執行方式後，依選定方式使用 `superpowers:executing-plans` 或 `superpowers:subagent-driven-development`，逐項實作及驗證。尚未取得此計畫的審閱與執行方式選擇前，不開始產品程式實作。

**目標：**新增可獨立呼叫的需求拆分 workflow，並以 Azure `gpt-6-sol` 評估 30 個 Retail 跨 View 需求，驗收到可提交的 text-to-sql requests。

**架構：**Pydantic 定義模型草稿及已驗證計畫；獨立 LangGraph 依序讀取契約、呼叫模型、驗證來源與相依關係、準備 requests。benchmark 直接呼叫該服務，不建立 SQL runtime、retriever 或 DB executor；評分器只在模型回覆之後讀取預期答案。

**技術：**既有 Python 3.12、Pydantic 2、LangGraph、LangChain、Azure/OpenAI 相容模型 factory、pytest；不增加產品依賴。

**規格：**[已核准書面規格](../specs/2026-10-20-retail-task-decomposition-design.md)。

## 全域限制

- 固定使用 `projects/retail` 的 7 個核准 View、30 題跨來源題庫；原 `cases.jsonl` 保持原樣。
- 本次不生成 SQL、不執行 DB、不執行資料合併、不作實際採購決策、不修改既有網頁或 SQL API。
- 使用根目錄 `./.env` 的 `CPEA_AZURE_LLM_BASE_URL`、`CPEA_AZURE_LLM_API_KEY`，模型／deployment 為 `gpt-6-sol`；不改寫 `.env`。
- 不設 Azure 模型呼叫次數上限；SDK retries=0，遇 rate limit 不重跑，依使用者 `quota.py inspect-terminal` 規則判讀後處理。
- 全部契約與完整 response schema 納入 context budget；超限明確失敗，不截斷或自行調高設定。
- 題庫答案、案例 ID 及審核資料不得進入模型訊息；每次規劃只呼叫一次模型。
- Markdown 與使用者訊息使用繁體中文，文字使用 UTF-8 無 BOM，保留既有檔案換行。

## 審查重點

1. 合法替代來源與子任務順序不同：應給等價方案正確分數，不能依索引配對。由任務三測試。
2. 非 ready 或等待綁定的計畫：不得提供看似可立即執行的 payload。由任務一、二測試。
3. 三來源的門市 KPI 沒有商品鍵，月／日／會員子集合可能放大數值：驗證逐邊鍵及保留母體，語意未知處標為人工審核。由任務一、三測試。
4. 根目錄預設仍是 Ollama，且可能含 DB 設定：新 runner 必須確實使用 Azure `gpt-6-sol`，且不載入 DB driver。由任務四測試。
5. provider 中途失敗或缺少 token metadata：產物要能區分成功、失敗、略過與未回報用量，不以部分完成宣稱全通過。由任務四、五測試。

## 任務一：規劃資料契約與 deterministic 驗證

**檔案：**新增 `src/cpea/application/models/decomposition.py`、`src/cpea/workflows/task_decomposition/validation.py`、`src/cpea/workflows/task_decomposition/__init__.py`、`tests/unit/test_task_decomposition_contract.py`。

**介面：**

- `DecompositionDraft`：模型輸出草稿，包含 status、strategy、tasks、integration、clarifications、unsupported_reasons。模型資料 `extra='forbid'`。
- `PlanningTask`：`task_id, view, required_columns, filters, metrics, group_by, output_grain, depends_on, request`；保留待綁定輸入標記。
- `IntegrationEdge`：`left_task, right_task, left_keys, right_keys, mode, cardinality, preparation, preserve_task`；`IntegrationPlan` 另有 anchor、最終粒度與注意事項。三來源使用多條 edge。
- `PreparedSQLRequest`：保留 task_id／view metadata，payload 僅有既有 `request` 與空 `history`。
- `DecompositionResponse`：status、code、draft、prepared_requests、validation_errors、contract_fingerprint、context_tokens、token_counter。非 ready 的 prepared_requests 必須為空。
- `validate_decomposition(draft: DecompositionDraft, catalog: CatalogProvider) -> list[str]`。
- `prepare_requests(draft: DecompositionDraft) -> list[PreparedSQLRequest]`，只能接受已由 service 驗證的 ready 且無待綁定輸入計畫。

- [ ] 先寫失敗測試 `test_ready_plan_requires_admitted_views_and_all_used_columns`，斷言未知 View／filter／metric／group／edge 欄位被拒絕；不合法聚合不得變成 ready。
- [ ] 加入 `test_dependencies_are_known_acyclic_and_not_self_referencing`、`test_non_ready_and_unbound_plans_expose_no_dispatch_payload`、`test_three_source_edges_use_store_key_for_kpi`；斷言重複 task_id、循環、錯誤鍵、鍵型別不符、非連通 integration 被拒絕。
- [ ] 執行 `.venv/bin/python -m pytest tests/unit/test_task_decomposition_contract.py -q`，確認因尚未實作而失敗。
- [ ] 實作上述 Pydantic 契約及 validation；沿用 `catalog.field_contract` 的型別、能力及聚合限制。驗證 request 非空且長度符合既有 4000 字上限；prepared payload 從通過驗證的結構重建，包含來源、全部必要欄位、條件與粒度，不信任草稿文字能完整表達結構。
- [ ] 準備動作只描述資料對齊，不能把目前尚未執行的彙總宣稱已完成；以 typed preparation 描述 `aggregate`、`nest`、`pivot` 或背景附加，未知語意保存為待審注意事項。
- [ ] 執行該測試檔到通過，提交這個可獨立審查的資料契約。

## 任務二：獨立 LangGraph 規劃服務

**檔案：**新增 `src/cpea/workflows/task_decomposition/workflow.py`、`src/cpea/workflows/task_decomposition/prompt.py`、`src/cpea/application/services/task_decomposition.py`、`tests/unit/test_task_decomposition_workflow.py`。

**介面：**

- 消費任務一的 `DecompositionDraft`、`DecompositionResponse`、`validate_decomposition` 與 `prepare_requests`。
- `TaskDecompositionWorkflow(llm, catalog: CatalogProvider, *, settings: AssistantSettings, token_counter=None)`；`invoke(request: str) -> DecompositionResponse`。
- `TaskDecompositionService(llm, catalog, *, settings, token_counter=None)`；`plan(request: str) -> DecompositionResponse`。
- `DECOMPOSITION_PROMPT_VERSION` 與固定 prompt 文字供 runner 計算指紋；prompt 只依契約及一般規劃原則，不包含題庫特例。

- [ ] 寫 `test_inventory_plus_custom_period_sales_prepares_two_requests`，fake LLM 回傳合法雙 View 草稿，斷言只呼叫一次、每個 request 僅一個來源、必要條件都進 payload；對 SQL compiler／executor 設置失敗 sentinel。
- [ ] 加入 `test_inventory_30d_sales_can_stay_single_view`、`test_missing_policy_and_unavailable_fields_do_not_dispatch`，斷言單來源控制不被過度拆分、澄清及不支援不出 payload。
- [ ] 加入 `test_full_prompt_budget_rejects_before_model_call`、`test_parse_and_validation_errors_are_not_retried`、`test_prompt_contains_all_contracts_and_no_case_or_oracle`，斷言 context 不足時模型呼叫數為 0，且錯誤無 key／endpoint。
- [ ] 執行 `.venv/bin/python -m pytest tests/unit/test_task_decomposition_workflow.py -q`，確認 RED。
- [ ] 以 `load_contracts → plan_tasks → validate_plan → prepare_requests` 節點實作獨立 graph；用現有 parsing 和 factory 注入模型，不建立 `AssistantRuntime`。使用 `build_token_counter(settings)` 計算實際完整 messages 與 schema 的輸入 token，保留 output reserve 與 safety tokens。
- [ ] 記錄原始 model response、usage_metadata 與耗時的可選 observer；observer 由 runner 注入，application 回覆不公開原始 prompt。回報解析、契約及 provider 固定錯誤碼，保存私有診斷，不自動修復重試。
- [ ] 執行任務一、二測試至通過，提交規劃服務。

## 任務三：題庫驗證、評分與報告

**檔案：**新增 `evaluations/decomposition_cases.py`、`evaluations/decomposition_grading.py`、`evaluations/decomposition_reports.py`、`tests/unit/test_decomposition_evaluation.py`。

**介面：**

- `load_decomposition_cases(path: Path, catalog: CatalogProvider) -> list[dict]`：驗證 schema、唯一 ID、案例及契約指紋、expected tasks 與 acceptable_alternatives。
- `grade_decomposition(case: dict, response: DecompositionResponse, catalog: CatalogProvider) -> dict`：回傳 canonical／等價 View 結果、欄位 precision/recall、filters／metrics／grain、整合鍵結構與 payload_ready，另列 `semantic_review_required`，不假裝完成語意審核。
- `write_reports(output: Path, cases: list[dict], results: list[dict], metadata: dict) -> None`：產生 `summary.json` 與繁體中文 `overview.md`。

- [ ] 先寫 `test_case_loader_rejects_stale_fingerprint_and_invalid_alternative`、`test_grading_is_invariant_to_task_order_and_ids`，斷言換 task_id／排序不改成績，遺失必要欄位會失敗，額外合法欄位不掩蓋缺漏。
- [ ] 寫 `test_equivalent_sales_detail_plan_passes_without_canonical_hit`、`test_wrong_city_channel_or_period_is_not_accepted`、`test_three_source_kpi_edge_and_anchor_preservation`；逐 task 接受 canonical 或完整 alternative，不能混用一半欄位而湊過答案。
- [ ] 寫 `test_partial_run_and_consistent_failure_do_not_count_as_stable_pass`，報告分母使用規劃題次數，逐題區分三次全通過、狀態一致失敗及未完成；缺少 token 保留 null。
- [ ] 執行 `.venv/bin/python -m pytest tests/unit/test_decomposition_evaluation.py -q` 確認 RED，再實作 loader、全域一對一 task matching 與報告；小型任務集合可枚舉配對，不依題目 ID 分支。
- [ ] 日期等價表示只能做語意有據的正規化；自動評分未支持的條件計數或自然語言整合要求列入人工審核，不用字串完全相同當作語意 oracle。
- [ ] loader 重用既有 30 題答案，不為提高成績靜默改動 oracle；發現題庫錯誤必須保存獨立更正原因及新指紋。
- [ ] 跑通評分測試並重新執行 `reports/validate_matrix.py`，提交評分與報告。

## 任務四：Azure runner 與獨立 CLI

**檔案：**新增 `evaluations/decomposition_runner.py`、`tests/integration/test_decomposition_runner.py`；修改 `pyproject.toml` 的 scripts／sdist include 與 `evaluations/README.md`。

**介面：**

- `azure_planning_settings(env_file: Path, model: str) -> AssistantSettings`：根目錄設定載入後，以 Azure 專用欄位明確覆蓋 provider／endpoint／key／model；清空 `sqlserver` 與其他 project 綁定，不實例化 DB。
- `evaluate_decomposition(*, profile: Path, env_file: Path, model: str, cases_path: Path, runs: int = 1, exploratory: bool = False, llm_factory=None) -> dict`：一次只跑一個指定模型，不設 max-model-calls。
- `main(argv=None) -> int` 與新入口 `cpea-plan-eval`；CLI 提供 `--project retail --env-file .env --model gpt-6-sol --runs 3 --exploratory`，不依賴不存在的 `projects/retail/.env`。

- [ ] 先寫 `test_runner_overrides_ollama_uses_root_azure_and_never_loads_sql_driver`、`test_no_model_call_cap_and_no_hidden_calls`，用 fake factory 檢查 model/provider，30×3 題必須正好 90 次呼叫；不新增限額參數，不改寫既有全專案 call budget 行為。
- [ ] 加入 `test_pending_cases_require_exploratory`、`test_run_output_is_immutable_and_contains_fingerprints`、`test_endpoint_normalization_is_idempotent`，斷言新目錄不覆寫，metadata 不含 key、認證 URL 或原始 `.env`。
- [ ] 加入 `test_provider_error_records_trigger_and_skips_remaining_without_retry`，rate limit／auth／network 記錄觸發失敗，後續標 skipped，無 fallback。原始 stderr 存私有檔案，供依使用者規則交 `quota.py` 判讀；錯誤訊息不進公開摘要。
- [ ] 執行 `.venv/bin/python -m pytest tests/integration/test_decomposition_runner.py -q` 確認 RED。
- [ ] 實作 runner 並使用既有 Azure factory；先以已安裝 SDK 原始碼／官方 SDK 文件確認 Azure OpenAI 相容路由與 GPT 參數。root endpoint 依現有 `/openai/v1` 路由規則正規化，已含 suffix 不重複添加；若實際 endpoint 非此介面則明確錯誤，不對多個 URL 猜測重試。
- [ ] run 保存開始／完成時間、Git SHA 及 dirty diff 指紋、完整 prompt/schema/contract/casefile SHA-256、實際模型及 request 次數、planned/completed/failed/skipped。`calls.jsonl` 保存真實 request／response，不以預期答案偽造輸出。
- [ ] 新入口與 sdist include 加入 runner／loader／grading／reports；README 記錄根目錄設定、無呼叫上限、pending 題庫為探索性及不執行 SQL 的界線。
- [ ] 測試通過後提交 runner、入口與文件。

## 任務五：整體驗證、Azure benchmark 與 EDD 收尾

**檔案：**新增 `openspec/changes/retail-task-decomposition/` 的 change 登記文件，規格與工作項目引用上述兩份文件，不複製第二套規格；更新 EDD ledger、checkpoint 與最終驗收報告。

**介面：**消費任務二服務及任務四 CLI；主要驗收產物是 30 題三輪的逐題結果、View／欄位選擇與 prepared requests，不是 SQL。

- [ ] 實作前先登記 OpenSpec change，並在 EDD plan 保存 S/M/L、MVP、可否證假設及實驗條件。第一個 fake LLM focused 實驗確認只準備 requests，才進入正式程式整合；重要進展用 CLI `checkpoint/update` 記錄。
- [ ] 執行 `.venv/bin/python -m pytest tests/unit/test_task_decomposition_contract.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py -q`，全部通過才進 live。
- [ ] 執行既有完整測試 `.venv/bin/python -m pytest -q`，並用現有 build backend 建置 wheel/sdist，確認安裝後 CLI 與新增 modules 存在、私有 Projects／env 不進套件。
- [ ] 執行獨立 review，特別查完整題文／case_id hardcode、模型 context 洩漏 oracle、過度接受替代來源、metadata 假用量與重複呼叫。若選 native，由主 agent 實作後交 fresh reviewer 審查整體變更。
- [ ] 於固定 revision 執行 `.venv/bin/python -m evaluations.decomposition_runner --project retail --env-file .env --model gpt-6-sol --runs 3 --exploratory`。90 次是此矩陣的工作量，不是程式設定的呼叫上限；不另外執行 warmup 或先跑一整輪。
- [ ] 查看第一輪及三輪 View／欄位／結構結果，保留全部失敗案例；若需要修正 planner，以通用錯誤為依據，先補回歸再改 prompt／validator，不為單題加特例。每版使用新 run 目錄與指紋。
- [ ] 如遇 rate limit，停止 provider 呼叫；將私有 terminal output 交 `python3 ~/.claude/skills/account-switch/bin/quota.py inspect-terminal -t codex --file <private-output>` 判讀，不因 Azure 錯誤自動更換 Codex 帳號；未知／認證／網路錯誤依結構化狀態處理，保存剩餘 skipped。
- [ ] 完成 fresh subprocess 驗證與 EDD 獨立驗收；只有證據足以支持各 acceptance 才標記完成。報告同時列模型實測成績、未通過需求與人工語意審核限制，不把 30 題 pending 擅自升為人工核准。

## 自我審查與執行交接

規格要求對應任務一至五：契約／相依／dispatch 邊界在一，完整 context／一次模型呼叫在二，公平 oracle 與三輪統計在三，根目錄 Azure／無次數上限／產物在四，回歸與真實驗收在五。五項審查重點均有明確測試，不依賴 SQL 或真實資料庫。

建議採 **native**：由主 agent 在目前 `feat/cross_view` 分支依序實作，完成後交獨立 reviewer。模組介面相依明確，直接執行較省重複 context；若選逐任務 subagent，則依該 skill 進行各任務的獨立實作與審查。目前執行方法尚未由使用者選定，不能預設已授權 spawn。
