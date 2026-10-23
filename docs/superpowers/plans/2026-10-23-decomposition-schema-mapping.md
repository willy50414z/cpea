# 需求與來源證據對照實作計畫

> **執行者：** 使用 `superpowers:executing-plans` inline 執行三個 TDD 交付步驟；完成後由 Main 安排 fresh reviewer。使用者已授權執行，不重複要求批准。

**目標：** 新增獨立的逐 View 候選證據對照與全域審核入口，產出可稽核的 DecompositionDraft 與 prepared requests。
**架構：** 前置 View 檢索後，進行原文抽取、完整契約逐候選 View 比對、全域審核、受限制草稿；共用原有 validation／prepare。新 service 回傳既有 DecompositionResponse 的 trace subclass，原流程不變。
**技術：** Python、Pydantic、既有 LangChain provider binding 與 token counter；不新增依賴。
**設計：** [已核准方案 A](../specs/2026-10-23-decomposition-schema-mapping-design.md)。

## 全域限制

- 原 workflow／service／validation／evaluation／tests 與使用者 prompt 修改不動；只新增檔案與更新這份計畫、設計。
- UTF-8 無 BOM、繁體中文 Markdown；不建 worktree、不 commit／push、不呼叫真實模型或 DB。
- 每次呼叫先檢查 budget；provider／解析／驗證失敗不 retry，保留部分 trace，不派送未驗證草稿。
- 模型可證明引用存在，不能由字元覆蓋宣稱語意完整；遺漏審核不允許 ready。

## 審查重點

- 重複詞、重疊業務 spans、語法及標點分類正確且不可漏字。
- 真實引文也可能語意不符；同路徑與同欄位檢查不能取代人工語意審查。
- 輔助鍵／盤點日期必須有證據，草稿不可擴張核准來源／用途。
- 母體、期間、禁止計算須保留結構化決定，且對照實際 task／欄位用途。
- 任一階段失敗不得漏掉已有 trace、繼續 provider 呼叫或洩漏 raw error。

### Task 1：需求區間、逐 View 候選及證據驗證

**新增檔：** `src/cpea/workflows/task_decomposition/mapping_models.py`、`mapping.py`；`tests/schema_mapping_support.py`、`tests/unit/test_schema_mapping_validation.py`。
**介面：** `RequirementExtraction`、`ViewMapping`；`validate_extraction(request, extraction) -> list[str]`、`validate_view_mapping(mapping, extraction, view) -> list[str]`。

- [x] 先寫測試：Unicode 區間／覆蓋／重複 ID／關聯、禁止與目的無需欄位、逐詞回覆、假欄位與錯路徑／跨欄引文拒絕。
- [x] 執行 `.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py`，預期缺少新模組而失敗；保留輸出。
- [x] 實作嚴格中間契約與無模型呼叫的驗證 helper；同指令通過。

### Task 2：審核與受限制草稿的跨階段驗證

**新增／延伸檔：** 上述新 models／mapping；新增 `tests/unit/test_schema_mapping_review.py`。
**介面：** `MappingReview`、`MappedDraft`；`validate_review(request, extraction, mappings, review, views)`、`validate_mapped_draft(extraction, mappings, review, mapped, catalog)`，皆回傳錯誤清單。

- [x] 先寫測試：漏詞審核／引用不存在、未證實輔助欄位、必要詞無 task binding、來源／用途擴張、期間更改、庫存母體被換、禁止用途，及等價來源的有效草稿。
- [x] 執行 `.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_review.py`，確認新介面缺失而失敗；保留輸出。
- [x] 實作 candidate／aux allowlist、結構化約束與 task binding 驗證，共用原 validator；跑兩組新測試。

### Task 3：獨立入口、可稽核回應與完整流程

**新增檔：** `schema_mapping_workflow.py`、`mapping_prompts.py`、workflow 目錄 `README.md`；`src/cpea/application/models/schema_mapping_decomposition.py`、`src/cpea/application/services/schema_mapping_decomposition.py`；`tests/unit/test_schema_mapping_decomposition.py`。
**介面：** `SchemaMappingDecompositionService(llm,catalog,*,settings,token_counter=None,observer=None,retriever=None,view_limit=None).plan(request)` → `SchemaMappingDecompositionResponse(DecompositionResponse)`；正常候選 C+3 次模型呼叫。

- [x] 先寫測試：兩種等價來源 happy path、完整 View 契約曝光、V+3 calls、stage/usage、每階段 budget/provider/parse 失敗、部分 trace、原流程仍一次呼叫。
- [x] 執行 `.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_decomposition.py`，確認新入口缺失而失敗；保留輸出。
- [x] 實作可重入的無狀態獨立流程、提示詞、專用 response trace 與使用文件；跑新增三組測試及原四組 66 項基準。
- [x] Main 最終驗收執行 `.venv/bin/python -m pytest -q` 完整離線套件；完整輸出留檔，對照原基準 23 failed／666 passed／1 skipped，不修無關舊失敗。
- [x] 追加前置篩選 TDD：先寫 `tests/unit/test_schema_mapping_retrieval.py`，red9（新模組缺失）→green；新增新service參數與縮減流程 red4→green；literal誤釘 red4→green。
- [x] 新增 `mapping_retrieval.py`，重用原 SchemaRetriever，檢索時解除單 View 欄位交集；原文明列來源與欄位所屬 View 補回，保留 cutoff ties、可注入 retriever／soft view_limit、候選及排除 trace。
- [x] 最終 focused 重新納入 retrieval 新組；完整套件仍由 Main 執行。

## 執行紀錄

Ruling: 依本次明確授權直接在共享工作區實作、不 commit／worktree；本計畫兼作 inline ledger，不執行要求 commit 的 skill scripts。
Pre-flight: Task 1 的 extraction／candidate 被 Task 2 審核使用；Task 2 的驗證被 Task 3 workflow 使用，介面一致。獨立 trace 回應維持父模型 status／draft／prepared_requests 契約。

Task 1: complete — red 17 failed（新模組缺失）→ green 17 passed；命令：`.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py`。證據 `/tmp/cpea-schema-mapping-task1-{red,green}.txt`。
Ruling: 新測試不得假設 catalog 首筆為 stock；改以完整名稱選取測試契約，避免 YAML key 排序影響證據測試。

Task 2: complete — red 25 failed（MappingReview 介面缺失）→ green 42 passed（含 Task 1）；命令：`.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py tests/unit/test_schema_mapping_review.py`。證據 `/tmp/cpea-schema-mapping-task2-{red,green}.txt`。
Ruling: 禁止行為以核准欄位操作 allowlist 與 `forbidden_uses` 做可執行核對；自然語言任意目的仍需語意審查。草稿使用 task binding 連回需求，不能以無證據的用途宣告繞過。

Task 2 審查修補：期間局部條件／拆 task 繞過 red 2 failed，final grain 降維 red 1 failed；新增合法 conditional metric 正例後核心46 passed。時間限制沿雙向 related_ids 對應所有實際輸出，conditional metric 只約束自己；必要 grain 閉合到最終 anchor output。證據 `/tmp/cpea-schema-mapping-{period-red,grain-red,core-review-green,holdouts-green}.txt`。

Task 3: complete — red 33 failed（新 service 缺失）→ green 33 passed；後續補 token counter 例外、空契約、無候選及 non-ready 草稿。counter 7 個階段 red 7 failed（raw exception）→ 最終 green；先建立失敗 stage，回 `token_count_error` 不洩漏原錯誤，也不呼叫模型。證據 `/tmp/cpea-schema-mapping-task3-{red,green}.txt`、`/tmp/cpea-schema-mapping-counter-red.txt`。
Ruling: population 的相關需求若已明列，anchor 必須由這些需求的採納候選支持；新增反例 red 1 failed → 最終 green，證據 `/tmp/cpea-schema-mapping-population-red.txt`。
最終 focused：`.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py tests/unit/test_schema_mapping_review.py tests/unit/test_schema_mapping_decomposition.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_task_decomposition_contract.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py` → **156 passed in 10.89s**（新增90、原66）；證據 `/tmp/cpea-schema-mapping-focused-green.txt`。無真實模型／DB 呼叫。
Ruling: 依 Main 明確分工，完整套件留至 fresh review 後由 Main 執行並保存同版本證據，避免重複約72秒的既有失敗驗證；本實作者到 focused 與文件驗證完成即停止改檔。
Ruling: 使用者追加「最前面如 text-to-sql 篩選 View」後，延伸 Task 3，不改原檢索；所有完整性驗證的 View 範圍改為前置候選，trace 公開排除項與 recall 限制。正常模型呼叫數改 C+3，前置檢索不新增 LLM 呼叫。
追加 retrieval 證據：`/tmp/cpea-schema-mapping-retrieval-{red,green}.txt`、`/tmp/cpea-schema-mapping-retrieval-integration-{red,green}.txt`、`/tmp/cpea-schema-mapping-retrieval-literals-red.txt`；retrieval與workflow合計60 passed。
最終含 retrieval focused：前述7組命令再加入 `tests/unit/test_schema_mapping_retrieval.py` → **173 passed in 9.27s**（新增107、原66）；輸出 `/tmp/cpea-schema-mapping-focused-with-retrieval-green.txt`。`git diff --check` 無錯，15個新增檔皆已確認 UTF-8 無 BOM。程式碼及文件停止修改，交 Main final review／完整套件驗收。

Main 最終整合：含 retrieval 的 focused **173 passed**（新增107、原66）；完整套件 **773 passed／23 failed／1 skipped**，JUnit 核對失敗 ID 與修改前23項完全一致，無新增失敗。完整證據 `evidence-driven-dev/tasks/decomposition-schema-mapping/evidence/EV-20261023T065113-4d7bf5d2.json`；fresh reviewer 結論 PASS_WITH_WARNINGS，未驗證真實 LLM／embedding／reranker 品質與成本。
