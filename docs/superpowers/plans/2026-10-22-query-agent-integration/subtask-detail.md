# CPEA 查詢 Agent 子任務實作細節

> **執行方式：**使用者依序實作；agent 若受託執行，使用 `superpowers:executing-plans` 並遵守當次授權，不自行委派、commit 或 push。所有未勾選步驟均為待辦，測試命令的預期結果不是已執行結果。

**目標：**先完成可獨立驗證的雙節點 SQL 整合，再逐階段建立可靠取數及附證據回答。

**架構：**既有 `TaskDecompositionService` 與 `SQLGenerationService` 保持獨立；新增 typed pipeline、確定性交接 gate 及外層 LangGraph。第一階段保留相容 request 介面，所有下游輸出都須回頭核對核准任務。

**技術：**Python 3.12、Pydantic 2、LangGraph、pytest 與既有 catalog／compiler／policy。不新增產品依賴。

**規格：**[task.md](task.md)，包含全域限制、範圍、共同驗證方式與完成定義。

**研究增補：**[ab-evaluation-plan.md](ab-evaluation-plan.md) 定義共同業務語意義務、候選責任、實驗控制與限制；[decision-record-spec.md](decision-record-spec.md) 定義實驗及架構裁定。2026-10-22 首次增補只編修文件；後續依使用者指示的實作進度見 [研究實作紀錄](research-implementation-report.md)。下列後綴／R 任務不繼承原 S1-02～S1-07 的完成狀態，亦不改寫其證據。

## 全域限制與審查重點

完整繼承 `task.md` 的全域限制。特別注意：第一階段零 DB 執行、保留確認守門、不以 stub／gold 輸入冒充自然成功、不重試 rate limit、不修改歷史證據、不自動 commit。

每個子任務先寫能揭露目標失敗的測試，確認失敗原因後才實作最小變更，最後執行該項及受影響的回歸。文件／基準整理不需要新增實作鏡像測試。每項完成後填寫「實作證據」；提交動作由使用者決定。

## 檔案責任配置

以下為預定新增路徑；實作前若已有同名功能，優先重用並同步修改本計畫，不建立平行重複系統。

| 檔案 | 責任 |
| --- | --- |
| `src/cpea/application/models/query_pipeline.py` | 外層輸入、結果、問題、狀態與逐任務紀錄 |
| `src/cpea/workflows/query_pipeline/validation.py` | 整批能力檢查與 task／QueryPlan／SQL 一致性 |
| `src/cpea/workflows/query_pipeline/task_sql.py` | 接受 typed task，包裝既有 SQL service，處理清理 |
| `src/cpea/workflows/query_pipeline/workflow.py` | 兩個核心 node、路由及逐任務狀態 |
| `src/cpea/workflows/query_pipeline/__init__.py` | workflow package，不增加 import side effects |
| `src/cpea/application/services/query_pipeline.py` | 獨立 application 入口與依賴注入 |
| `evaluations/query_pipeline_cases.py` | 案例、核准輸入與測試資料驗證 |
| `evaluations/query_pipeline_grading.py` | 三種模式評分及首錯歸因 |
| `evaluations/query_pipeline_runner.py` | 模式選擇、顯式模型設定、產物及 replay |
| `tests/fixtures/query_pipeline/cases.json` | 不含私有 Retail 資料的 synthetic 控制案例 |
| `projects/retail/evaluations/query_pipeline_cases.jsonl` | 新增 Retail 面板；保留既有兩套題庫不變 |
| `tests/unit/test_query_pipeline_*.py` | 契約、gate、adapter、graph、grader 測試 |
| `tests/integration/test_query_pipeline_runner.py` | runner、證據、零 DB 及錯誤傳播 |

原有實作參考：`application/models/decomposition.py`、`application/models/query.py`、`domain/models.py`、`workflows/task_decomposition/validation.py`、`infrastructure/sql_compiler.py`、`infrastructure/sql_policy.py`。產品程式不得 import `evaluations/*`。

## S1-01：建立新基準、能力矩陣與驗收面板

**依賴：**無。**檔案：**新增上述兩份案例資料；後續程式責任檔見 S1-06。基準與審核產物放 `projects/retail/artifacts/query_pipeline/<run-id>/`，不提交私有產物。

**輸入：**實際 HEAD、現有兩段服務、catalog、既有 Retail 題庫與已知失敗。

**輸出：**`baseline.json`、案例核准紀錄、能力矩陣；每個面板案例含 `case_id`、`request`、`review_state`、需求檢核清單、`expected_stage_status`、核准任務與合法替代、預期 QueryPlan 的結構約束及 `required_capabilities`。

- [x] 記錄 HEAD、dirty paths、Python／套件版本與測試命令。只記錄設定名稱及非敏感值，不保存 `.env` 全文。
- [x] 先執行既有兩段的聚焦基準：

  ```bash
  .venv/bin/python -m pytest tests/unit/test_task_decomposition_contract.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py tests/unit/test_mapping_preflight.py tests/unit/test_request_operation_boundaries.py tests/unit/test_business_clarification.py tests/unit/test_having.py -q
  ```

- [x] 建立 12 題固定面板：6 題正向（原始列、聚合、AND 日期／業務條件、兩個獨立 View、同一 View 的獨立任務、可證明等價條件各一題）；6 題負向／pending（歧義、缺來源能力、conditional metric、metadata 集合、相依輸入、不可忠實表示的 filter 各一題）。
- [ ] 逐題列出原文中的必要需求與預期狀態，人工確認任務及合法替代；以需求與欄位意義配對，不要求固定 task_id 或順序。
- [x] 正向面板只使用 S1 可完整表達的能力；不把既有 30 題中能力不足的案例改成較簡單題目來提高成功率。
- [x] synthetic 案例可公開；Retail 面板沿用私有資料管理。人工未核准者保留 pending，只能 exploratory 執行。
- [x] 將歷史研究指紋／私有產物問題、產品回歸及模型語意失敗分別列出；不得為了基準通過修改守門。

**驗收：**每題有明確可判定的預期結果；至少一份人工核准輸入能通過既有規劃 validator。基準測試真實結果及失敗分類已保存。

**實作證據：**實際 HEAD `11d55a54a4e58591c67c11c32a4ad05ff8a098ca`；新基準 170 passed（exit 0）。12 題 synthetic／Retail、矩陣與基準已建立；六題正向通過 validator。人工核准 pending，尚未完成本項。證據見 [實作紀錄](implementation-report.md)。

## S1-02：定義外層契約並共用任務序列化

**依賴：**S1-01。**新增：**`application/models/query_pipeline.py`、`tests/unit/test_query_pipeline_contract.py`。**修改：**`workflows/task_decomposition/validation.py` 及其既有契約測試。

**新增待辦連結：**可替換策略的能力盤點與 evaluation 封套另列 S1-02-E1；原型及契約已完成的紀錄保持原義，不為抽象化重寫現有 `plan()`／`generate()`。

**介面：**

- `PipelineIssue`：`stage`（`planning|handoff|sql_generation|sql_validation|evaluation`）、`code`、可選 `task_id`、安全公開 `message`。
- `TaskSQLInput`：`original_request: str`、`task: PlanningTask`、`contract_fingerprint: str`；不接受可任意取代 task 的外部 request 字串。
- `TaskSQLResult`：`task_id`、`status`（既有 SQL response 狀態）、可選 `generation: SQLGenerationResponse`、`issues`。未 ready 不暴露可執行 SQL。
- `QueryPipelineResponse`：`run_id`、`status`（`sql_ready|needs_clarification|needs_confirmation|unsupported|error`）、`planning`、`task_results`、`skipped_task_ids`、`issues`、`contract_fingerprint`、`semantic_review_required: bool`。
- `render_task_request(task: PlanningTask) -> str`：從現有 `prepare_requests()` 抽出既有文字與 JSON 序列化，維持舊輸出格式及 4000 字元上限。

`TaskSQLResult.status=ready` 可表示該 task 曾成功生成；整體非 `sql_ready` 的公開摘要將其 `generation` 設為 null。整體 `sql_ready` 則要求全部核准 task 各有一份 ready generation、通過 gate、沒有 skipped 或 issues，不能只檢查 status 字串。

- [x] 寫 `test_sql_ready_requires_every_task_ready_and_no_skipped_or_issues`、`test_non_ready_response_has_no_dispatchable_sql`、`test_duplicate_or_unknown_task_results_are_rejected`。
- [x] 寫 `test_render_task_request_preserves_legacy_payload`、`test_render_task_request_rejects_over_4000_characters`；4000 字元可接受，4001 拒絕，不截斷內容。
- [x] 執行以下命令，確認新行為尚未實作而失敗，再實作契約及共用 renderer：

  ```bash
  .venv/bin/python -m pytest tests/unit/test_query_pipeline_contract.py tests/unit/test_task_decomposition_contract.py tests/unit/test_task_decomposition_workflow.py -q
  ```

- [x] `prepare_requests()` 改用共用 renderer；不變更原有 draft schema、狀態及既有 payload key。
- [x] 整體非 `sql_ready` 時，先前已生成 SQL 只保存於私有診斷；公開結果只保留狀態、issues 及合法 pending 資料。
- [x] 執行相同命令至通過。

**驗收：**既有 planning API／schema 相容；所有新狀態不變量有測試；`sql_ready` 僅表示 SQL 階段結構就緒，`semantic_review_required` 在未人工驗收的自然輸出為 true。

**實作證據：**新增 typed 契約與共用 renderer；4000／4001 邊界、全任務就緒及公開 SQL 清理均已測試。初次契約與既有 planning 回歸 44 passed；最終選定驗證共 322 passed。未提交，基準 HEAD 同 S1-01。

## S1-03：整批能力檢查與下游一致性 gate

**依賴：**S1-02。**新增：**`workflows/query_pipeline/validation.py`、`tests/unit/test_query_pipeline_validation.py`。

**介面：**

- `preflight_tasks(planning: DecompositionResponse, *, catalog: CatalogProvider) -> list[PipelineIssue]`。
- `validate_task_sql(task_input: TaskSQLInput, generation: SQLGenerationResponse, *, catalog: CatalogProvider, settings: AssistantSettings) -> list[PipelineIssue]`。

固定問題碼至少包含 `unsupported_task_capability`、`stale_contract`、`invalid_handoff`、`handoff_too_long`、`semantic_drift`、`sql_mismatch`、`sql_policy_violation`、`provider_error`、`invalid_model_response`。能力不足映射為整體 unsupported；指紋、交接、模型或 SQL 驗證失敗映射為 error；既有兩種 pending 狀態原樣傳遞。更多問題碼只能追加，不在不同 run 中更換同一錯誤的意義。

- [x] 寫 `test_batch_preflight_rejects_unsupported_capability_before_any_sql_call`：任一 task 有 conditional metric、metadata 集合、dependency、unbound input、NULL／boolean 或其他不可忠實表示的 value，全批停下，SQL service 呼叫數為 0。
- [x] 寫 `test_stale_catalog_and_nonready_planning_do_not_dispatch`：非 ready、catalog 指紋不符、重複 task_id、draft／prepared metadata 不一致均不得 dispatch；再次沿用 `validate_decomposition()` 驗證。
- [x] 寫參數化 `test_gate_rejects_semantic_drift`：改 View、少 filter、多 filter、改 operator／value、改 aggregation、改 group、漏必要輸出、多未核准輸出、擅加 HAVING／order／limit，均失敗。
- [x] 寫 `test_gate_accepts_condition_order_and_in_value_order_equivalence`；只允許已定義且可證明的正規化。不得把「同名金額」或粒度相近直接當等價。
- [x] 寫 `test_gate_rejects_sql_that_differs_from_recompiled_plan` 及 `test_gate_rejects_wrong_dialect_and_unapproved_source`。
- [x] 執行 `.venv/bin/python -m pytest tests/unit/test_query_pipeline_validation.py -q` 確認 RED，再實作 gate。
- [x] 支援子集中的預期輸出欄位為 `attributes ∪ output_grain ∪ metrics.keys()`；filter-only 欄位不必 SELECT。group 與 metrics 須保留；跨粒度等價須有 catalog 唯一鍵等證明及專門測試。
- [x] 呼叫既有 `validate_single_view_plan()`、`compile_single_view()`、`validate_generated_sql()`；使用實際 dialect 與相同 `max_rows`，核對重編譯 SQL。不得為此建立 `SQLExecutionAgent` 或 executor。
- [x] 區分 compiler 的保護性上限與 task 未要求的業務 limit；task 未表示排序、Top N 或 HAVING 時，下游不得自行加入。原文是否被上游完整理解由獨立語意評分負責。
- [x] 執行新測試及 S1-01 聚焦回歸至通過。

**驗收：**結構合法的錯誤 SQL plan 仍會被擋下；不支援能力不被默默省略；檢查結果帶穩定 stage／code。

**實作證據：**整批 preflight、能力矩陣 `s1-capabilities-v1`、source／filter／metric／group／output／HAVING／order／limit mutation 與雙 dialect 重編譯已驗證；初次 gate 29 passed。最終驗證見 [實作紀錄](implementation-report.md)。

## S1-04：建立可獨立測試的 SQL node adapter

**依賴：**S1-03。**新增：**`workflows/query_pipeline/task_sql.py`、`tests/unit/test_query_pipeline_task_sql.py`。

**介面：**`generate_task_sql(task_input: TaskSQLInput, *, generator: SQLGenerationService, catalog: CatalogProvider, settings: AssistantSettings) -> TaskSQLResult`。

- [x] 寫 `test_adapter_renders_approved_task_and_uses_empty_history`：以共用 renderer 建立 request，呼叫既有 `generate(..., history=[], mode="sql")`；不把整個多來源需求重新當成單題輸入。
- [x] 寫 `test_adapter_preserves_pending_confirmation_and_clarification`：沿用既有 HILP／語意確認，pending 絕不自動確認或寫入測試外的 mapping。
- [x] 寫 `test_adapter_runs_gate_before_exposing_ready`、`test_adapter_does_not_retry_provider_failure`。
- [x] 寫 `test_inner_registry_is_finished_after_success_pending_and_error`：成功、pending、gate 拒絕及例外均清理此次 inner run；保存安全的 pending 問題供報告，S1 不提供外層恢復 API。
- [x] 執行 `.venv/bin/python -m pytest tests/unit/test_query_pipeline_task_sql.py -q` 確認 RED，再包裝既有 service；不重寫 retrieval、欄位 mapping 或確認流程。
- [x] offline／live 評估皆使用隔離的 mapping repository，保留產品真實確認行為；不得用人工預填答案抬高自然成績，也不得污染使用者現有 mapping。
- [x] 無法取得 inner run_id 的例外依既有 lifecycle 規則清理；以 stub 及真實 registry 測試確認沒有 pending 資源殘留。
- [x] 執行新測試及 `tests/unit/test_confirmation_lifecycle.py`、`tests/unit/test_business_clarification.py`、`tests/unit/test_mapping_preflight.py`。

**驗收：**核准 task 可獨立進入第二段；既有守門未被繞過；所有退出路徑有清理證據。

**實作證據：**adapter 沿用 renderer、空 history、sql mode；以 owner 清理此次 registry，真實 HILP checkpoint 測試通過；未自動確認。初次 adapter 與 lifecycle／business／mapping 回歸 71 passed。已保存私有 gate 拒絕候選與 parse 錯誤分類。自然 legacy coverage 問題另列 S1-08。

## S1-05：組成雙節點 LangGraph

**依賴：**S1-04。**新增：**`workflows/query_pipeline/workflow.py`、`workflows/query_pipeline/__init__.py`、`application/services/query_pipeline.py`、`tests/unit/test_query_pipeline_workflow.py`。

**介面：**`QueryPipelineService(planner: TaskDecompositionService, generator: SQLGenerationService, *, catalog: CatalogProvider, settings: AssistantSettings, observer=None)`；`invoke(request: str, *, run_id: str | None = None) -> QueryPipelineResponse`。workflow 使用同名公開 invoke，service 只包裝 workflow。

另提供 `generate_from_plan(request: str, planning: DecompositionResponse, *, run_id: str | None = None) -> QueryPipelineResponse`，供 SQL 獨立模式使用。它與第二個 node 共用整批 preflight／生成／gate 邏輯，不呼叫 planner，不另造規則；`settings` 指 SQL 節點設定，planner 設定由注入的 planner 自己持有。

- [x] 寫 `test_single_view_pipeline_reuses_existing_services`、`test_two_views_generate_two_independent_sql_results`，以注入的 service 驗證呼叫順序及 task_id 配對。
- [x] 寫 `test_generate_from_plan_skips_planner_and_uses_same_batch_gates`，確認獨立 SQL 模式與自然串接使用同一份能力及一致性規則。
- [x] 寫 `test_planning_pending_unsupported_and_error_skip_sql_node`、`test_any_preflight_failure_skips_every_sql_task`。
- [x] 寫 `test_second_task_failure_preserves_first_diagnostic_but_not_sql_ready`：第二個失敗時第三個列 skipped；先前 SQL 只留私有證據。
- [x] 寫 `test_no_db_executor_or_execution_runtime_is_constructed`：對 executor／execution_agent／staged_query_service 安裝失敗 sentinel，任何路徑均不得觸發。
- [x] 寫 `test_request_and_catalog_state_do_not_leak_between_runs`，以及空白／超過 4000 字元輸入在任何模型呼叫前失敗。
- [x] 執行 `.venv/bin/python -m pytest tests/unit/test_query_pipeline_workflow.py -q` 確認 RED，再組 graph：`START → decompose_request → generate_task_sql → END`，planning 非 ready 時直接結束。
- [x] `generate_task_sql` node 先整批 preflight，再依序呼叫 S1-04；第一個非 ready 即停止，保存 completed／failed／skipped。保留 integration，但不執行。
- [x] 使用注入的兩段服務；不在 graph 內讀 `.env`、建立 DB runtime 或切換全域模型設定。第一階段不加入新的持久化 checkpointer。
- [x] observer 至少記錄 `run_started`、`planning_finished`、`preflight_finished`、`task_finished`、`run_finished`，不公開完整 prompt 或內部私密推理。
- [x] 執行 S1-02～S1-05 新測試及既有兩段聚焦測試。

**驗收：**外層確實有兩個核心 node；切割與 SQL 可分開注入，完整串接零 DB，所有狀態能定位首錯。

**實作證據：**兩個核心 LangGraph node 與 generate_from_plan 共用整批 gate；部分失敗、skipped、公開 SQL 清理及 DB sentinel 通過。初次 S1-02～05 共 51 passed；最終選定驗證 322 passed。

## S1-06：三模式評估 runner 與證據產物

**依賴：**S1-05。**新增：**`evaluations/query_pipeline_cases.py`、`evaluations/query_pipeline_runner.py`、`tests/integration/test_query_pipeline_runner.py`。

**新增待辦連結：**Experiment／Strategy／Adapter、模型 digest、逐節點原件及實驗索引另列 S1-06-E1，重用本項 runner 與既有產物，不建立第二套系統。

**介面：**`evaluate_query_pipeline(*, mode: str, profile: Path, cases_path: Path, env_file: Path, planner_settings: AssistantSettings, sql_settings: AssistantSettings, runs: int = 1, exploratory: bool = False, output_root: Path | None = None, planner_factory=None, generator_factory=None) -> dict`。mode 僅允許 `planning|sql|integrated`。

- [x] 寫 `test_modes_use_expected_input_origins_and_model_factories`：planning 只呼叫 planner；sql 只使用核准任務呼叫第二段；integrated 由自然 planning 結果交接。
- [x] 三模式分別呼叫 `planner.plan()`、`pipeline.generate_from_plan()`、`pipeline.invoke()`；planning 結果維持 `DecompositionResponse`，不得包裝成尚未產生 SQL 的 `sql_ready`。
- [x] 寫 `test_gold_oracle_never_enters_natural_prompts`、`test_stub_and_replay_are_not_counted_as_natural_success`。
- [x] 寫 `test_run_metadata_records_both_node_versions_and_settings`、`test_case_and_contract_drift_fail_preflight`、`test_pending_cases_require_exploratory`。
- [x] 寫 `test_provider_error_preserves_first_failure_and_marks_remaining_skipped`，rate limit 不重跑；原始診斷私有保存，公開報告無 secret。
- [x] 寫 `test_model_task_id_cannot_escape_artifact_directory`：不能直接以模型 task_id 拼 filesystem path，使用安全產物 ID 並保留對照。
- [x] 執行 `.venv/bin/python -m pytest tests/integration/test_query_pipeline_runner.py -q` 確認 RED，再實作 runner。
- [x] 模型／provider 為逐節點顯式設定。重用現有 factory，不修改 `.env` 或全域環境；禁止 planner／SQL 節點不小心沿用另一段預設。
- [x] CLI 最少提供 `--mode`、`--profile`、`--cases`、`--env-file`、`--planner-provider`、`--planner-model`、`--sql-provider`、`--sql-model`、`--runs`、`--exploratory`、`--output-root`。真實模型呼叫須顯式 `--live`；offline 自動測試使用 factory 注入，不連外。
- [x] 每次產生新目錄，不覆寫：`run.json`、`events.jsonl`、`planning.json`、`tasks/<safe-id>/input.json`、`tasks/<safe-id>/generation.json`、`result.json`、`grading.json`、繁體中文 `overview.md`。原始 prompt／response、inner trace 及 provider error 放私有區；公開輸出只留安全引用。
- [x] `run.json` 保存 HEAD／dirty diff 指紋、逐節點 prompt／schema／source 指紋、catalog／casefile 指紋、模型與生成參數、dialect、mapping 初始狀態指紋、輸入來源、token counter 及時間。原始資料與公開報告分離，不 hash credential 來冒充安全公開值。
- [x] 計畫或 schema 版本不符視為評估輸入錯誤；現有預期替代方案只能從評估端載入，不流入模型端。
- [x] 執行 runner 及 graph 測試至通過；本步不啟動真實模型。

**驗收：**三種模式能用 stub 完整跑完，各模式的呼叫數、輸入來源與成績不可混用；輸出可獨立追溯。

**實作證據：**三模式 factory、固定設定 metadata、隔離 mapping、公開／私有產物、安全 task ID、provider 停止與 evaluation error 分類均已測試。三模式 stub 各 12 次、零真實模型／DB 呼叫；正式輸入與自然品質尚未核准。產物見 [實作紀錄](implementation-report.md)。

## S1-07：語意評分、錯誤歸因與離線 replay

**依賴：**S1-06。**新增：**`evaluations/query_pipeline_grading.py`、`tests/unit/test_query_pipeline_grading.py`。**修改：**新 runner 及其測試，必要時重用原有評分器。

**新增待辦連結：**逐 requirement、跨原生格式評分、Oracle 誤判與兩種 Replay 責任另列 S1-07-E1；不得改寫本項歷史分數或封存指紋。

**介面：**`grade_pipeline_case(case: dict, response: DecompositionResponse | QueryPipelineResponse, *, mode: str, catalog: CatalogProvider) -> dict`；`replay_query_pipeline(run_dir: Path, *, profile: Path, cases_path: Path, output_root: Path | None = None) -> dict`。planning 模式只接受前者，sql／integrated 只接受後者；型別與 mode 不符時為評估錯誤，不計為模型語意失敗。

- [x] 寫 `test_task_order_and_ids_do_not_change_semantic_score`、`test_alternative_plan_must_be_complete_not_mixed_fragments`。
- [x] 寫 `test_valid_schema_with_wrong_period_channel_metric_or_grain_fails_semantics`；首錯可以是 planning，即使下游忠實產生了錯誤規劃的 SQL。
- [x] 寫 `test_correct_planning_with_sql_drift_is_attributed_downstream`；handoff 指序列化／能力承接失敗，sql_generation 指模型失敗，sql_validation 指生成結果違反 task 或 compiler。
- [x] 寫 `test_consistent_failure_is_not_stable_success`、`test_skipped_and_unfinished_do_not_shrink_denominator`、`test_unsupported_capability_is_not_reported_as_supported`。
- [x] 寫 `test_replay_makes_zero_model_and_db_calls_and_keeps_original_run`、`test_regrade_records_source_hash_and_new_grader_version`。
- [x] 執行 `.venv/bin/python -m pytest tests/unit/test_query_pipeline_grading.py tests/integration/test_query_pipeline_runner.py -q` 確認 RED，再實作評分與 replay。
- [x] 評分拆開：規劃語意、能力承接、task-to-plan 一致性、SQL policy、固定支援面板整體成功、預期 pending／unsupported 正確性。schema 通過不自動給語意正確。
- [x] 人工評審需看到原文、catalog 及實際輸出；只記錄決策與引用證據，不索取模型私密思考。LLM judge 若加入，只能輔助並與人工校準，不能取代數值／契約 gate。
- [x] replay 保留原始 mode／input_origin；當前 source／catalog／schema 改變時另標 `source_drift` 或 `incompatible_replay`。重新評分產生新目錄，記錄來源與 grader 指紋，不覆寫歷史。
- [x] 輸出每題首錯與傳播後果；不強迫所有失敗只有一種標籤，首錯與附帶問題可分欄保存。
- [x] 執行新測試及原有 decomposition 評分回歸至通過。

**驗收：**能區分「錯誤切割被下游忠實執行」及「正確切割在下游失真」；replay 零模型、零 DB，歷史原件不變。

**實作證據：**完整方案配對不依賴 task ID／順序；期間、指標、粒度、integration mutation、首錯歸因、固定分母、pending、零模型／DB replay、來源漂移與獨立人工審查檔均已測試。原始失敗保留；stub／replay 不計自然成功。

## S1-08：固定版本自然評估與第一階段驗收

**依賴：**S1-07。**修改：**`evaluations/README.md` 新增獨立入口說明；新能力若改變架構再更新 `docs/architecture.md`。驗收產物放新 run 目錄。

**新增研究里程碑：**S1-08-BL 是本項第一輪自然 baseline，取得後才可啟動 R1。baseline 可以 FAIL；不要求先完成三輪。歷史單題 smoke 不算 BL，三模式、12 題、自然輸出／核准輸入來源與首錯條件見研究規格第 4 節。R1 不取代下列任何驗收步驟；建議 ADG-01 先於最終階段驗收決策，最晚 S2 前完成。

- [x] 先執行所有新測試與 S1-01 聚焦回歸，確認所用 HEAD／dirty diff、prompt、schema、catalog 及面板版本。
- [x] 執行既有產品介面回歸：`tests/integration/test_runtime.py`、`tests/integration/test_hilp_api.py`、`tests/integration/test_hilp_workflow.py`、`tests/integration/test_streamed_query.py`、`tests/unit/test_web_projects.py`。遇失敗先分類，保留命令與輸出。
- [ ] 依使用者選定的兩段模型設定，對同一面板依序跑 planning、sql、integrated，各三輪；每輪隔離 mapping／registry／artifact，固定 catalog 與生成參數，記錄模型實際版本。
- [ ] 先用支援面板各一題完成小樣本 smoke，再執行核准面板；smoke 成績另列，不加入正式三輪分母。provider 故障依規則停止，不用補抽成功覆蓋首錯。
- [ ] 對自然輸出逐題語意審查。預期歧義／能力不足案例驗證正確停下；另用 offline fault injection 驗證 provider、context、parse 及中途失敗，不刻意製造 live rate limit。
- [ ] 依 `task.md` 完成定義作判定；任一支援正向案例任一輪不通過，保留未完成狀態並建立具體修正項。不得只報最佳一次或只報 ready 率。
- [ ] 用離線 replay 重現一次語意失敗及一次成功，核對產物未變；replay 不計為新增自然 trial。
- [x] 文件明示目前不執行 DB、未支援的能力、`sql_ready` 語意，以及與舊單題入口的差異。
- [x] 填入產品回歸、自然品質及歷史研究狀態三份結果，再勾選 S1 清單。未經使用者指示不提交或推送。

**驗收：**符合主文件全部 S1 完成條件；若未通過，交付首錯、證據及下一個可重現修正項，不提前進入 S2。

**實作證據：**最終聚焦與產品回歸 322 passed（exit 0）；wheel／sdist build 通過。Ollama 三模式 smoke 共 4 次模型呼叫，全部未通過品質；planning anchor 與 legacy transport coverage 首錯已保存。完整 pytest 180 秒停止（exit 124），首個封存 binding 失敗另有紀錄。正式三輪與人工核准依使用者指示留待後續調校，S1 保持未完成。詳見 [實作紀錄](implementation-report.md)。

## S2：單 View 可靠取數與需求追蹤

**進入條件：**S1 完成且 ADG-01 已記錄設計決策與後續處理；設計 Gate 不豁免 S1。**主要檔案：**新增 `application/models/query_result.py`、`application/services/query_pipeline_execution.py`；修改既有 `domain/models.py`、`infrastructure/sql_compiler.py`、`application/services/sql_execution.py` 及實際 DB adapters；測試新增 `tests/integration/test_query_result_completeness.py`。

**輸入／輸出：**接受 S1 通過 gate 的單 task 與 SQL，輸出 `VerifiedQueryResult`，包含 task／需求對照、typed schema、粒度、來源、SQL hash、資料時間、資料版本或 snapshot 說明、列數與 `completeness=complete|truncated|unknown`。SQL 就緒不得直接等同資料已驗證。

- [ ] 把 S1 評估端需求清單擴充為正式版本化的 requirement ledger，讓必要需求可追溯到 task／結果；規劃 schema 變更須保留舊版評估。
- [ ] 逐項實作 S1 阻擋的 SQL 能力；conditional metric 與完整 DISTINCT metadata 集合各自有 QueryPlan、compiler、dialect 與結果測試，不一次全部開放。
- [ ] 先寫 199／200／201 筆、明確 Top N、空結果、GROUP BY 結果超限測試，再區分使用者 limit 與系統安全上限；採多取一列、分頁或已驗證的完整性策略。
- [ ] 用固定 DB fixture 經實際 adapter 驗證，不以回傳 201 筆的 fake executor 代替 DB 端上限行為。SQL Server／PostgreSQL 各報其實際已驗證範圍。
- [ ] 驗證 Decimal、日期／時區、NULL、鍵唯一性與 catalog 的型別／粒度宣告；未知資料時間不可宣稱同一時間點。
- [ ] 保留 existing SQL policy 與重編譯一致性；先在隔離 fixture 或明確授權的唯讀來源執行，不修改正式資料。
- [ ] 完整性未知或截斷時阻擋需要完整資料的總量／整合；完整空集合可以是合法結果，不能一律視為錯誤。

**驗收：**固定 fixture 的實際結果與人工核准 oracle 相符；同一錯誤不因 dialect 不同而被漏過；原單題行為相容。

**實作證據：**待填：能力版本、DB fixture 版本、adapter／DB 版本、完整性測試。

## S3：兩個獨立任務的確定性資料整合

**進入條件：**S2 的單 View 結果可靠。**主要檔案：**新增 `application/services/result_integration.py`、`application/models/integrated_result.py`、`tests/unit/test_result_integration.py`、`tests/integration/test_query_pipeline_results.py`。

**輸入／輸出：**接受核准 `IntegrationPlan` 與 `dict[task_id, VerifiedQueryResult]`，輸出整合資料、鍵／筆數／粒度／母體驗證、來源與需求對照；LLM 不執行資料合併。

- [ ] 先支援獨立 task 的 `one_to_one`、`many_to_one`；明確驗證 join key 型別、實際唯一性及缺值。
- [ ] 寫「庫存 100 個商品，只有 60 個有銷售」fixture，核准 left 母體的結果仍有 100 個商品；inner 規劃按其核准母體另外驗證。
- [ ] 注入重複鍵、錯誤期間、同名不同口徑指標、不同幣別／單位、部分結果及不一致 snapshot，確認不產生貌似完整的數值。
- [ ] 未匹配與值為零保持區別；合併前後驗證筆數膨脹、數值重複及需求覆蓋。
- [ ] 逐項加入 `aggregate`、`nest`、`pivot`、`attach_context` 的 typed 實作；未實作 preparation 或未核准 many-to-many 一律明確拒絕。
- [ ] 同 DB 的資料一致性可用同一 read snapshot 等實際支援方式；無法取得一致 snapshot 時記錄時間差與限制，不假裝全域一致。

**驗收：**兩來源端到端結果符合固定 DB oracle；故障注入不會被誤判為完整整合成功。

**實作證據：**待填：資料關係測試、snapshot 策略、母體與數值比對。

## S4：相依任務與結果綁定

**進入條件：**S3 完成，且 R3-01～R3-03 已完成架構比較與規格回饋。**主要檔案：**新增 `application/models/task_binding.py`、`application/services/task_scheduler.py`、`tests/unit/test_task_binding.py`、`tests/integration/test_dependent_query_pipeline.py`；修改外層 workflow 及其版本化契約。

**輸入／輸出：**`TaskInputBinding` 明列上游 task／欄位、下游 filter、型別、集合形狀與數量限制；scheduler 輸出每個 task 的執行狀態與綁定指紋。

- [ ] 以「先查符合條件會員，再查其消費」建立正向 fixture，驗證拓樸順序與必要條件未遺失。
- [ ] 循環、未知依賴、型別不符、超過參數限制、上游 truncated／unknown 皆在下游執行前停止。
- [ ] 空集合有明確語意：以空結果結束對應分支，不移除 filter 變成全表查詢。
- [ ] 綁定值透過受控 QueryPlan／compiler／adapter 契約處理，不拼接任意 SQL；若新增參數化介面，保留其參數與 SQL hash。
- [ ] 上游失敗只使受影響後代 blocked；必要 task 未完成不得回整體成功。執行預算明確化，不能把大結果默默截成小 IN 清單。
- [ ] 上游計畫、catalog 或結果版本改變時，對應下游結果失效；無相依資料是否能重用須由版本及 snapshot 規則判定。
- [ ] 依 R3-03 的來源／粒度／cardinality 缺口更新 binding 與 DAG 驗收案例，記錄哪些外部計畫能安全適配及哪些仍拒絕；不直接切換產品引擎。

**驗收：**有相依正向結果正確，負向不會查到錯誤母體或重用過期資料。

**實作證據：**待填：綁定 schema 版本、DAG 案例、失效規則測試。

## S5：澄清、有限修復與可恢復執行

**進入條件：**S4 完成。**主要檔案：**修改外層 workflow；新增持久化 checkpoint 設定及對應 `tests/integration/test_query_pipeline_recovery.py`。重用既有 confirmation registry，避免建立互相矛盾的第二套確認機制。

**輸入／輸出：**版本化 `ResumeInput` 綁定 run、owner、plan／catalog 版本與使用者回覆；錯誤分類對應固定允許動作。修復預算與停止條件為顯式設定，不在此文件任意指定額度。

- [ ] 建立語意澄清／詞彙確認到外層 task 的對照；使用者選擇不得被另一個 run 或 task 消耗。
- [ ] 分開處理 provider、parse、契約／能力、SQL generation、DB、資料完整性及 integration 錯誤；可修復範圍逐項核准，不全部交由 LLM 重跑。
- [ ] checkpoint 後重啟、重複 resume、同時 resume、catalog 漂移及 owner 不符均有測試。
- [ ] 模型修復保存原錯與前後計畫；若語意改變，重做能力及需求覆蓋驗證，必要時重新澄清，並使受影響後代失效。
- [ ] 已保存結果的 replay 與重新查 live DB 分開標記；不能以 checkpoint 保證 live 資料重查會相同。
- [ ] 持久化及節點恢復須避免重複 mapping 寫入或其他副作用；讀查重跑也要遵守資料時間及版本策略。
- [ ] rate limit 維持根目錄規則：保存、判讀、不直接重試。
- [ ] 將 R3-03 的外部錯誤／pending／恢復限制納入同一錯誤動作矩陣，保留每個候選的原始錯誤及共通分類，不默認套件內部可自動重試。

**驗收：**中斷可恢復且不跳過確認、不重複副作用、不沿用不相容結果；超出預算有可診斷終止狀態。

**實作證據：**待填：恢復測試、錯誤動作矩陣、修復前後證據。

## S6：附證據回答與完整自然流程驗收

**進入條件：**S5 完成。**主要檔案：**重用並擴充 `application/services/answering.py`；新增 claim／result 對照契約及 `tests/integration/test_query_pipeline_answers.py`，擴充 runner 以另列 SQL、取數、整合與回答階段成績。

**輸入／輸出：**回答只消費通過驗證的結果及需求 ledger；每個數值／衍生結論能追溯到 task、結果欄位、運算及資料時間。

- [ ] 先用固定格式呈現結果與限制，再加入自然語言摘要；統計與衍生值由程式計算。
- [ ] 每個必要 requirement 都標示滿足、待澄清、不支援或失敗；未知完整性、未匹配及部分成功不能被摘要改寫為完整成功。
- [ ] 測試憑空加數字、幣別／日期混用、四捨五入錯誤、NULL 當零、資料內容中的指令，確認回答只引用核准事實。
- [ ] 回答層本身用 gold 結果、真實已錄製結果及自然端到端三種輸入評估，分開呈現。
- [ ] 對固定版本完整跑原始需求到 DB／整合／回答，採固定 fixture 與明確授權的唯讀來源分開報告；同時維持舊單題回歸。
- [ ] 分別報告首次成功、三輪全成功、錯誤放行、正確澄清、未完成、成本與延遲。核准測試集上零錯誤放行不代表真實世界錯誤率為零。
- [ ] 建立通過品質門檻的參考模型設定後，再用相同題庫、契約、生成參數與明確差異比較本機模型／較低成本模型；品質未達標不以便宜補償。
- [ ] 納入 R3-03 的 claim／result lineage、母體／完整性缺口與成本比較；不同架構均依相同核准語意及 evidence 標準驗收。

**驗收：**答案可逐項驗證來源及計算；完整自然測試與各節點測試同時成立，限制與未完成需求公開呈現。

**實作證據：**待填：完整 run IDs、需求覆蓋、答案引用、模型比較與產品限制。

## 研究增補子任務

以下為可執行步驟規格。2026-10-22 依使用者後續指示開始離線實作，進度、命令與限制統一見 [研究實作紀錄](research-implementation-report.md)；下列未勾選步驟仍是完整驗收待辦，不能以局部程式測試代替。原 S1-01～S1-08 的測試命令與勾選不變。程式增補沿用本文件檔案責任配置；只有必要時增加 evaluation 內部模組，產品不得依賴研究程式。每項實際執行後須依決策規格填 HEAD／命令／退出碼／原件 hash／獨立審核與限制，不能只填 PASS。

### S1-02-E1：能力責任與最小評估 Adapter 邊界

**狀態：**介面程式已離線驗證，待獨立審查。**依賴：**既有 S1-02 與實際程式盤點。**預期產物：**責任矩陣、StrategyDescriptor／EvaluationInput／StrategyObservation／SemanticAssessment 規格及必要的 evaluation 薄封套；**證據：**見 [研究實作紀錄](research-implementation-report.md)，原未勾選項仍須依完整完成條件驗收。

- [ ] 對照現有 `QueryPipelineService` 注入、`plan`／`generate`、`TaskSQLInput`、managed contract hook，標示已可直接重用與缺口；A0 沒有 Coverage 欄位不得補造。
- [ ] 按研究規格第 2 節確認六項能力、三種 implementation_kind、輸入原生型別與候選版本；同責任才比較，不為 package 建固定 node。
- [ ] 確認完整候選可由薄 wrapper 進入既有 factory，局部候選只進 evaluation observation；如需新增介面，限制在 evaluation 層，保留正式 API／schema／雙節點。
- [ ] 未來以固定離線輸入驗證同責任候選接收相同快照、ID／版本可追溯、局部 Coverage 不會被當完整 plan、未觀測欄位不補值；驗證無新增產品依賴。

**完成條件：**介面責任、可比／不可比範圍及最小變更有審查紀錄，離線契約驗證通過；不存在要求所有 package 輸出 CPEA JSON 的規則。

### S1-06-E1：共用實驗識別與原件記錄

**狀態：**記錄與候選分流程式已離線驗證，真實研究未測。**依賴：**S1-02-E1、既有 S1-06。**預期產物：**runner 追加 metadata／manifest、逐節點 observation 及證據索引，沿用 `query_pipeline_runner.py` 與 private trial 路徑；**證據：**見 [研究實作紀錄](research-implementation-report.md)，原未勾選項仍須依完整完成條件驗收。

- [ ] 逐欄核對研究規格第 3.1 節與現有 `run.json`，只補缺項：Experiment／Strategy／Adapter、worktree、模型 digest／核實來源、上游注入核准與原生 schema 等。
- [ ] 分開 fake／stub 與研究 adapter 真實呼叫；不能讓既有 factory 的 stub 標記造成自然成績誤計，也不能以 candidate 設定自行宣稱 natural。
- [ ] 保存首次 Raw／Parsed／Normalized、各層錯誤與完整性 hash；整合 managed 產物的唯讀引用及 usage，不轉寫封存原件。
- [ ] 用離線偽回應及 provider／parse 中斷控制驗證零 DB、零網路、無自動重試，Raw 先於解析保存，未知用量保留 null，skipped／unfinished 不縮分母。

**完成條件：**三模式舊產物仍可讀；新候選與原件／輸入版本可追溯；manifest 缺項及錯誤停止行為都有離線證據，不冒稱本次已驗證。

### S1-07-E1：跨格式語意評分與 Replay 銜接

**狀態：**逐義務核心與重現已離線驗證，其他 validator 與規則核准待辦。**依賴：**S1-06-E1、既有 S1-07。**預期產物：**逐義務評分、六層 verdict、Oracle 誤拒／誤收對照、Replay／重評報告，延伸現有 cases／grading／runner；**證據：**見 [研究實作紀錄](research-implementation-report.md)，原未勾選項仍須依完整完成條件驗收。

- [ ] 建立原文義務與候選原生 evidence 的對照，沿用完整合法替代規則；區分 schema、引用、語意、integration、SQL 靜態、完整自然流程，不以 JSON 相同判成功。
- [ ] 對研究規格第 3.3 節所有指標指定分子／分母／適用責任；同 View scope、grain、own_gap 與依賴分開；不可比與未知不算 PASS。
- [ ] 用已核准等價、無關 identifier、漏條件、錯母體、source drift 等離線 mutation 校準 Oracle False Reject／False Accept；語意等價規則由非提案者獨立核准。
- [ ] 區分 managed Raw replay 與 pipeline response regrade；在相同指紋下重現原 FAIL／成功，來源漂移標不相容，產物永遠寫新目錄。
- [ ] 驗證完整自然分數排除注入／stub／replay，Independent Semantic Approval 綁定產物與規則 hash，S1 SQL 階段不會被報為 DB／結果／回答通過。

**完成條件：**能跨原生格式追溯每義務判定、首錯與 Oracle 分歧；兩種重現報告及獨立核准有明確責任，保留原 grader 成績。

### S1-08-BL：第一輪自然 Baseline 里程碑

**狀態：**未執行。**依賴：**S1-01 面板核准、既有 S1-07、固定兩段版本。**預期產物：**原 12 題三模式第一輪 run 與 baseline 報告，屬 S1-08 的子里程碑；**證據：**無，歷史 smoke 不適用。

- [ ] 凍結原面板／catalog／兩段模型／prompt／schema／source，沿原 S1-08 順序各執行第一輪，保存首次輸出、SQL 注入來源與 integrated 自然首錯。
- [ ] 報告完整計畫分母與所有 completed／failed／pending／unsupported／skipped／unfinished，保存 provider 診斷且不補抽成功。
- [ ] 若中斷，由獨立審核者依研究規格確認已有足夠自然 planning／integrated Raw 可定位問題；不足則本里程碑維持未取得，不用 stub／Replay 代替。

**完成條件：**可審核的第一輪 baseline 已取得，可包含語意 FAIL；僅開啟 R1 研究，S1-08 原三輪與 S1 Gate 仍未被豁免。模型執行需未來另行授權。

### R1-00：候選責任對齊與實驗凍結

**狀態：**未執行。**依賴：**S1-07-E1、S1-08-BL。**預期產物：**預先登錄 manifest、候選責任／版本矩陣、Pilot 與擴大案例核准、成本／試次設定；**證據：**無。

- [ ] 定義 A0～A3 版本及 A2／A3 相對現有研究的真正差異；確認 Coverage 內部組與完整 planning 組各自可比責任。
- [ ] 對 Regression／Diagnostic／Metamorphic／Holdout 分組及 lineage；保留歷史 38 題的已見身分、原 12 題驗收面板，另建待核准 4 題 Pilot／20 題研究設計。
- [ ] 解決 OQ-02／03：試次、語意／安全門檻、模型可比組、獨立 reviewer 與 Holdout 管理；凍結 hash，模型可見輸入排除答案。
- [ ] 先離線檢查證據、成本、固定分母與禁止 DB；核准後交 R1-A／B 各做 Pilot，再擴大，不自動重試。

**完成條件：**獨立核准的矩陣可直接執行且無隱藏 oracle／知識優勢；未確認資訊仍是 Open Question 時不啟動受影響實驗。

### R1-A：Planning／Coverage 對照

**狀態：**未執行。**依賴：**R1-00。**預期產物：**`r1-a-comparison.md`、ablation／逐義務評分與 Raw／Replay 索引；**證據：**無。

- [ ] 內部組用相同 Recall／責任卡／catalog 對照 A1 三階段、A2 Atomic＋Own、A3 deterministic dependency／status；先 Pilot，再依凍結矩陣擴大。
- [ ] 覆蓋部分鍵、無關 ID、own／dependency gap、View Scope、Grain、Population、Rename、日期邊界、unsupported、契約 evidence；缺證據不得用 deterministic 規則創造能力。
- [ ] 完整組以同原文對照 A0 與有完整規劃責任的候選；只有 Coverage 者不比完整 JSON，後補 Selection 的 calls／成本全數記錄。
- [ ] 逐格報六層 verdict／首錯／成本／未觀測，做離線重現及獨立語意審核；提出可歸因改進與剩餘風險。

**完成條件：**研究規格第 4 節的責任、案例與證據齊全，失敗／不可比均列報；完成研究不等於批准替換產品 planner。

### R1-B：SQL Generation 對照

**狀態：**未執行。**依賴：**R1-00、人工核准 Prepared Task。**預期產物：**`r1-b-comparison.md`、候選可行性、逐題 gate／AST／成本與重現；**證據：**無。

- [ ] 先查 LangChain／LlamaIndex 候選能否固定 catalog、禁止 DB 與修復重試；不適用者列實證原因，不啟用預設 DB agent。
- [ ] 同 Prepared Task 比現有 SQL service 與可行候選，先 Pilot 再擴大；不把預期 SQL 放入 prompt。
- [ ] 檢查欄位、全部條件、policy、compiler、source drift、額外操作、unsupported／pending 與 Tokens／Latency；SQLGlot 僅列靜態工具候選。
- [ ] 能無損適配 QueryPlan 才跑原 gate；原生 SQL 使用研究端等價核驗，記未適配產品 gate；靜態結果、Replay 及獨立審核分列。

**完成條件：**至少現有服務加一可行候選具可比結果，或交付所有外部候選受阻的完整證據；有零 DB 證據，未放寬產品守門。

### R2-01：外部引擎功能與適配性研究

**狀態：**固定版本研究草稿完成，待獨立審查。**依賴：**計畫確認、現有七 View／技術契約證據。**預期產物：**版本化 capability／license／部署矩陣、業務義務及待確認事項；**證據：**見 [外部引擎研究](external-engine-research.md)，不視為完整研究驗收。

- [ ] 優先 Wren MDL／規劃，接續 MetricFlow 指標／維度／Entity／Join；視治理需求研究 Cube，LangChain／LlamaIndex／Vanna 作基本生成對照。
- [ ] 核對官方實作及確切 release／LICENSE，列離線能力／模型／DB 需求、方言與部署限制；不把 Package 功能宣稱當成 CPEA 通過。
- [ ] 核對 manifest approved 與舊 draft 審查的效力差異；固定七 View 的技術用途快照及語意義務，未知鍵／口徑不自行補核准。

**完成條件：**Wren 優先 PoC 路徑及必要模型／語意介面已明確；其他候選可合理標暫不實作，缺口、授權待審與技術核准範圍均列出。

### R2-02：隔離 Wren 最小靜態 PoC

**狀態：**七 View 技術編譯探測完成，正式語意 Pilot 未完成。**依賴：**R2-01、S1-07-E1、技術測試語意義務核准。**預期產物：**隔離環境版本清單、七 View 轉換草稿、人工知識清單、plan／SQL 原件及靜態評分；**證據：**見 [研究實作紀錄](research-implementation-report.md)，原未勾選項仍須依完整完成條件驗收。

- [ ] 在另行授權的獨立 venv／容器固定版本；不改產品依賴、正式入口、原 YAML 或業務核准狀態，不提供 DB credentials。
- [ ] 逐欄記錄 YAML→外部 semantic model 的轉換、不可表示語意與新增人工知識，未知 cardinality／key 不臆測。
- [ ] 驗證 compile／plan 不會 introspect 或查 DB；若無法禁用，保留受阻診斷，不能用 DB 繞過 S1 限制。
- [ ] 依研究規格的四情境 Pilot 生成／編譯，分開自然模型與固定 semantic request 組，靜態評共通義務及反例，獨立審核與離線重現。

**完成條件：**最小 PoC 的可行或受阻結論可重現，零 DB，逐項標實測／未測；不將外部 Join 靜態成功稱為端到端勝出。

### R2-03：成本、缺口與可行性結論

**狀態：**成本與缺口草稿完成，待獨立審查。**依賴：**R2-02 成功或受阻證據。**預期產物：**可行性報告、實測／估算成本、新客戶導入假設、ADG 輸入；**證據：**見 [研究實作紀錄](research-implementation-report.md)，原未勾選項仍須依完整完成條件驗收。

- [ ] 逐項整理研究規格第 5 節的導入、semantic model、Join、指標／粒度／母體／缺值、方言、權限／部署、授權及未支援業務要求。
- [ ] 分開建模／修正／維護／升版工時、模型成本與新 ERP 估算；沒有新 ERP 代表樣本時列證據不足。
- [ ] 提供通過／失敗案例、語意風險、業務待審前提、建議重用能力及仍需自建項；交獨立審核，不替 ADG 預填成功結論。

**完成條件：**可據以決策而非只有功能列表，未實測項及限制清楚；失敗報告可完成研究交付，不能宣稱引擎通過。

### ADG-01：S2 前架構設計決策

**狀態：**未執行。**依賴：**R1-A、R1-B、R2-03 完整報告。**預期產物：**依決策規格填寫的架構決策紀錄與後續任務；**證據：**無，未選型。

- [ ] 依完整實測、反例、語意風險、維護／工程與新客戶成本、後續驗證及業務前提選 KEEP／ADAPT／REPLACE／INSUFFICIENT_EVIDENCE。
- [ ] 明列研究責任不可比與證據不足，不以單題 PASS、最佳答案或套件功能判替換；取得獨立審核。
- [ ] 對 ADAPT／REPLACE 另提遷移、回退、相容／新增驗收及實作授權；對 KEEP／不足結論列待修風險，未解安全 Gate 仍阻擋。
- [ ] 核對 S1-08 原自然三輪與 S1 全數完成條件；未通過保持未完成，不因已記錄設計決策而開始 S2。

**完成條件：**決策與證據、限制及後續可審核；此為設計 Gate，不是產品測試豁免或自動切換服務授權。

### R3-01：共同語意與受控 Fixture 規格

**狀態：**未執行。**依賴：**S3 驗收、ADG-01、S2／S3 環境授權。**預期產物：**同責任比較矩陣、固定 DB fixture／snapshot／oracle 指紋及執行限制；**證據：**無。

- [ ] 固定相同需求／資料可見範圍／方言，確認 CPEA Planner＋Integrator 與外部引擎承擔同等責任；必要時加入純 LangChain SQL Agent 組。
- [ ] 沿用 S2／S3 fixture，含重複鍵、100／60 母體、NULL／零／無列、日期／snapshot、fanout、背景 KPI、unsupported／clarification；事先獨立核准 oracle。
- [ ] 同 DB 與跨 DB 分組，明列來源、唯讀權限與預算；沒有受控 fixture 授權不得執行，正式資料不能當測試資料。

**完成條件：**雙方同等輸入、oracle 與成本責任可檢查；靜態與 DB 結果層範圍均已核准，不提前開放 S1 DB。

### R3-02：完整架構靜態與結果對照

**狀態：**未執行。**依賴：**R3-01、受控環境可用。**預期產物：**`r3-comparison.md`、plan／SQL／結果／完整性／成本與重現索引；**證據：**無。

- [ ] 先比較靜態語意、Join Cardinality、母體、Aggregation Safety，保留所有首次輸出及不支援處理。
- [ ] 僅在已核准固定 fixture 執行，依相同結果 oracle 比 CPEA 多查詢整合與外部 Join；驗 NULL／零／無列、完整性、重複指標，不要求 SQL 字串相同。
- [ ] 列 DB round trips、模型／轉換／執行成本及語意錯誤；驗故障與模糊需求是否安全停止，獨立審核結果，錄製及 Replay 不冒稱新的自然執行。

**完成條件：**相同 fixture 的靜態與實際結果比較及限制有證據；若未執行結果層，本項保持未完成。不可只用 S1 的多份 SQL 替代本項。

### R3-03：架構結論與 S4～S6 規格回饋

**狀態：**未執行。**依賴：**R3-02 報告、獨立語意審核。**預期產物：**新架構決策紀錄、S4～S6 規格影響對照與後續驗證項；**證據：**無。

- [ ] 依決策規格重新判讀完整責任證據，保留 ADG-01 舊結論，引用通過／失敗、成本、業務前提與未測能力。
- [ ] 逐項回饋 S4 binding／DAG／版本失效、S5 pending／錯誤分類／恢復、S6 requirement／claim evidence／完整自然驗收，標採納／保留／待確認。
- [ ] 必要變更另取得實作授權；證據不足明列工作及風險，不降低原 S4～S6 驗收或直接替換產品入口。

**完成條件：**可審核決策與具體規格回饋完成後交接 S4；所有未實測結論及需要業務核准的前提仍可追蹤。

## 依序實作與交接紀錄

下一個待驗收項目：**S1-01 人工面板核准、S1-08 自然承接修正與分階段調校**；不進入 S2。

新增研究工作依主計畫里程碑另列狀態與證據；本次均未執行。建議先確認增補計畫，再依研究規格第 8 節執行 S1 增補、BL、R1／R2／ADG；不自動開始原先修正或任何研究實驗。

| 階段 | 實際 HEAD／變更 | 驗證命令與結果 | 證據路徑 | 尚未解決 |
| --- | --- | --- | --- | --- |
| S1 | 起點 `11d55a5`；未提交變更 | 聚焦／產品 322 passed；完整套件未通過 | [實作紀錄](implementation-report.md) | 面板核准、planning anchor、legacy coverage、正式三輪 |
| S2 | 待實作 | 未執行 | 待填 | 待 S1 驗收 |
| S3 | 待實作 | 未執行 | 待填 | 待 S2 驗收 |
| S4 | 待實作 | 未執行 | 待填 | 待 S3 驗收 |
| S5 | 待實作 | 未執行 | 待填 | 待 S4 驗收 |
| S6 | 待實作 | 未執行 | 待填 | 待 S5 驗收 |
