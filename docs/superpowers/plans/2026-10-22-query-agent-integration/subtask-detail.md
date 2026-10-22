# CPEA 查詢 Agent 子任務實作細節

> **執行方式：**使用者依序實作；agent 若受託執行，使用 `superpowers:executing-plans` 並遵守當次授權，不自行委派、commit 或 push。所有未勾選步驟均為待辦，測試命令的預期結果不是已執行結果。

**目標：**先完成可獨立驗證的雙節點 SQL 整合，再逐階段建立可靠取數及附證據回答。

**架構：**既有 `TaskDecompositionService` 與 `SQLGenerationService` 保持獨立；新增 typed pipeline、確定性交接 gate 及外層 LangGraph。第一階段保留相容 request 介面，所有下游輸出都須回頭核對核准任務。

**技術：**Python 3.12、Pydantic 2、LangGraph、pytest 與既有 catalog／compiler／policy。不新增產品依賴。

**規格：**[task.md](task.md)，包含全域限制、範圍、共同驗證方式與完成定義。

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

**進入條件：**S1 完成。**主要檔案：**新增 `application/models/query_result.py`、`application/services/query_pipeline_execution.py`；修改既有 `domain/models.py`、`infrastructure/sql_compiler.py`、`application/services/sql_execution.py` 及實際 DB adapters；測試新增 `tests/integration/test_query_result_completeness.py`。

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

**進入條件：**S3 完成。**主要檔案：**新增 `application/models/task_binding.py`、`application/services/task_scheduler.py`、`tests/unit/test_task_binding.py`、`tests/integration/test_dependent_query_pipeline.py`；修改外層 workflow 及其版本化契約。

**輸入／輸出：**`TaskInputBinding` 明列上游 task／欄位、下游 filter、型別、集合形狀與數量限制；scheduler 輸出每個 task 的執行狀態與綁定指紋。

- [ ] 以「先查符合條件會員，再查其消費」建立正向 fixture，驗證拓樸順序與必要條件未遺失。
- [ ] 循環、未知依賴、型別不符、超過參數限制、上游 truncated／unknown 皆在下游執行前停止。
- [ ] 空集合有明確語意：以空結果結束對應分支，不移除 filter 變成全表查詢。
- [ ] 綁定值透過受控 QueryPlan／compiler／adapter 契約處理，不拼接任意 SQL；若新增參數化介面，保留其參數與 SQL hash。
- [ ] 上游失敗只使受影響後代 blocked；必要 task 未完成不得回整體成功。執行預算明確化，不能把大結果默默截成小 IN 清單。
- [ ] 上游計畫、catalog 或結果版本改變時，對應下游結果失效；無相依資料是否能重用須由版本及 snapshot 規則判定。

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

**驗收：**答案可逐項驗證來源及計算；完整自然測試與各節點測試同時成立，限制與未完成需求公開呈現。

**實作證據：**待填：完整 run IDs、需求覆蓋、答案引用、模型比較與產品限制。

## 依序實作與交接紀錄

下一個待驗收項目：**S1-01 人工面板核准、S1-08 自然承接修正與分階段調校**；不進入 S2。

| 階段 | 實際 HEAD／變更 | 驗證命令與結果 | 證據路徑 | 尚未解決 |
| --- | --- | --- | --- | --- |
| S1 | 起點 `11d55a5`；未提交變更 | 聚焦／產品 322 passed；完整套件未通過 | [實作紀錄](implementation-report.md) | 面板核准、planning anchor、legacy coverage、正式三輪 |
| S2 | 待實作 | 未執行 | 待填 | 待 S1 驗收 |
| S3 | 待實作 | 未執行 | 待填 | 待 S2 驗收 |
| S4 | 待實作 | 未執行 | 待填 | 待 S3 驗收 |
| S5 | 待實作 | 未執行 | 待填 | 待 S4 驗收 |
| S6 | 待實作 | 未執行 | 待填 | 待 S5 驗收 |
