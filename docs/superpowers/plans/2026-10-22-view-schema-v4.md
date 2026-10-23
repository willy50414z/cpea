# View Schema v4 與正確率比對實作計畫

> **執行者要求：**使用 `superpowers:executing-plans` 在目前 worktree 逐項實作；以下以核取方塊記錄步驟。使用者審閱本計畫後開始產品變更。

**目標：**提供明確分工的 v4 view YAML。依使用者最新指示，先保留 Ollama 五題基準與錯誤紀錄，再用新版 schema 對同五題各測一次；Azure 20 題三輪前測獨立保存。

**架構：**沿用既有 catalog、retrieval 與 SQL workflow；以獨立的 v4 驗證模型限制新區塊，讓既有投影傳遞完整語意。七份明確編寫的 Retail v4 YAML 同時作為 generator 的語意來源，避免另一份重複的語意模板；DB 只核對來源、型別、定義 hash 與唯一約束。

**技術：**Python 3.12、既有 Pydantic／PyYAML／pytest／psycopg；不新增依賴。

**規格：**[view-schema-v4-design.md](../specs/2026-10-22-view-schema-v4-design.md)、[前後測規格](../specs/2026-10-22-view-schema-ab-evaluation.md)。設計規格已由使用者核准。

## 全域限制

- Markdown 與使用者回覆使用繁體中文；文字 UTF-8 無 BOM，保留既有換行。
- 不修改 MATCH v10、模型參數、檢索權重、候選比較策略、compiler 或原始 Oracle，不新增依賴、任意公式執行及題目特例。
- 原固定 `cases.jsonl` 的成功／失敗各 10 題與 Azure 60 trials 保留。此次後測只取已完成 Ollama 基準的同五題，各一次；SDK retries 0，併發 1，不代選確認、不重抽答案。
- 模型測試不執行 SQL、不查業務資料；schema 的唯讀 DDL metadata 核對另存證據。
- 必須先完成前測，才修改產品程式／profile；前測期間只能整理文件與讀取來源。
- 不自動 commit／push。後測前必須呈現具體變更與離線驗證，取得本機提交授權，以滿足既有 clean-worktree preflight；不繞過檢查。
- 即使結果沒有改善也保留首次後測、失敗與固定分母，報告為探索性自動評估。

## 審查重點

1. 未知版本不能落入 legacy，v3 合法契約不能因新增 v4 失效：Task 1。
2. 同名城市與時間軸不能失去所屬實體；新 metadata 必須抵達所有候選比較投影：Task 2。
3. 固定日期／無上界活躍條件不能被改寫成移動窗口；商品明細假唯一鍵必須移除：Task 3。
4. metadata source relations 不能變成可查詢 base tables，metric 計算文字不能進入可執行 SQL：Task 2／4。
5. 來源／case 指紋變更不能沿用人工核准；後測不能因縮分母或模型版本變更虛增改善：Task 5。

---

### Task 0：完成修改前基準

**檔案：**私有 `projects/retail/artifacts/view-schema-ab/20261022-20case-deepseek/`。

**介面：**沿用 `run_phase.py --phase before --profile baseline-profile`、既有 `_run_one`／`grade_view_matching`。輸出原始 calls／results、版本 metadata 與 diagnostic-summary。

- [x] 固定案例／snapshot 指紋與 20 題原 Oracle 通過驗證；僅從根 `.env` 取得 Azure 機密，不寫入摘要。
- [x] 啟動前測，保存 terminal output；profile 使用凍結 v3，Git 基準 `f5c97f5`。
- [x] 等待 60 trials 完成；若 provider 故障，保存首錯並停止，依規範處理，不補跑。
- [x] 核對 product source、settings 與 snapshot 未變；保存前測 summary。未通過也繼續保留原分數，不修改 baseline。

### Task 1：可驗證的 v4 契約與相容載入

**檔案：**新增 `src/cpea/infrastructure/catalog/view_contract_v4.py`、`tests/contracts/test_view_contract_v4.py`、`docs/view-schema-v4.schema.json`；修改 `src/cpea/infrastructure/catalog/yaml_catalog.py`。

**介面：**`ViewContractV4(BaseModel)` 定義已核准欄位；`validate_view_contract_v4(policy: dict) -> None` 驗證結構與交叉欄位引用。loader 僅在 version=4 呼叫，v3 路徑保留；version 缺省及 1／2 沿用 legacy，其他版本拒絕。

- [x] 新增 `test_v4_valid_contract_loads_and_preserves_policy`、`test_v4_rejects_invalid_shape_or_reference`：涵蓋 missing／unknown key、source hash／relations、空白文字、grain／time／metrics 不存在欄位、重複 keys，以及合法 null；斷言非法值在載入時拒絕且指出 view 檔案。
- [x] 新增 `test_unknown_version_is_rejected`（5、字串版本、bool）與 `test_v3_contract_remains_compatible`；執行 `.venv/bin/python -m pytest tests/contracts/test_view_contract_v4.py -q`，確認新 v4 行為尚未實作而失敗。
- [x] 用既有 Pydantic 的 strict／extra=forbid／非空字串與明確 Literal 建立模型；交叉驗證欄位引用、date dimensions、verified source 條件。保留原 dict 作 policy，不默默改寫 YAML。
- [x] 明確分派版本，將 v4 validation error 接回既有 contextual ValueError。由 `ViewContractV4.model_json_schema()` 產出 standalone JSON Schema。
- [x] 重跑新測試與 `tests/contracts/test_configuration_and_catalog.py`，預期全部通過；檢查產出的 JSON Schema 與模型相同。

### Task 2：將完整契約傳到檢索、候選與詳細 context

**檔案：**修改 `src/cpea/application/catalog_contract.py`、`src/cpea/infrastructure/retrieval/documents.py`、`src/cpea/workflows/text_to_sql/sql_generation.py`；新增 `tests/unit/test_view_contract_projection.py`。

**介面：**維持 `field_contract`、`_operators_for`、`detail`、`build_documents`、`candidate_schema` 的介面；v4 延續 v3 能力規則，candidate 的 source／scope／time／usage／metrics 原樣傳遞。

- [x] 寫 `test_v4_preserves_v3_capabilities_and_operators`、`test_v4_metadata_reaches_retrieval_candidate_and_detail`、`test_candidate_comparison_receives_v4_semantics`：使用合成 v4 profile，斷言 summary 仍為純描述、source／scope／time／usage／metrics 不遺漏、entity 會出現在 candidate 欄位、比較的 prompt evidence 完整。`test_source_relations_do_not_expand_sql_allowlist` 證明 base table 不被允許。
- [x] 執行 `.venv/bin/python -m pytest tests/unit/test_view_contract_projection.py -q`，確認失敗。
- [x] 將現有能力推導 version 判定擴至 3／4；detail 增加 v4 區塊；build_documents 索引新語意且延續欄位名稱遮罩，不改權重。
- [x] candidate_schema 增加新區塊／entity；候選比較 evidence、signature、contract_text 同步補區塊，不改選擇策略、prompt 或 SQL 生成能力。
- [x] 新測試及 `tests/unit/test_retrieval_ties.py` 通過。查核 formula 僅為 context，沒有新增 SQL 拼接／執行路徑。

### Task 3：七份 Retail YAML、來源核對與可重跑 generator

**檔案：**修改 `projects/retail/views/demo_retail/*.yaml`、`projects/retail/manifest.yaml`、`projects/retail/contract_review.md`、`scripts/generate_view_contracts.py`；新增 `tests/unit/test_generate_view_contracts_v4.py`、`docs/view-schema-v4.md`。

**介面：**新增 `build_view_contract(name, definition, columns, constraints, semantics, relations) -> dict`，只使用明列語意及 DB metadata，返回經驗證 v4 policy。generator `--semantic-profile` 預設 canonical `projects/retail`，`--root` 沿用輸出目的地；來源／輸出可相同，差異仍要求人工合併。

- [x] 寫 `test_generation_uses_explicit_semantics_not_comment`、`test_generation_rejects_definition_type_or_uniqueness_drift`、`test_generation_requires_semantic_definition`、`test_generation_does_not_overwrite_different_contract`。用既有 metadata fixture 模擬資料庫，不讀業務資料；先執行 `.venv/bin/python -m pytest tests/unit/test_generate_view_contracts_v4.py -q` 確認失敗。
- [x] 依已核對 DDL 填寫七份契約；sources 使用真實 relations／hash；sales_detail keys=null；確實區分會員／門市城市，記錄固定日期、無上界條件、目標母體與空值／零值。
- [x] 保留 102 欄名稱／型別／role／unit／disallowed；必要描述修正均對應 DDL，不對應測試失敗題。指標文字只記錄既有計算與再聚合限制。
- [x] generator 載入顯式 canonical v4 語意，核對 DDL hash、輸出欄位與型別、來源關係及 grain 證據後產生。缺語意或證據變動時拒絕；保留不覆寫保護與既有工具函式的可用介面。
- [x] manifest profile_id／status 保留，contract_version 改為 4；文件說明 5W1H 分工、完整 YAML 範例、未知值、metadata 核對與業務核准差異。
- [x] 驗證七份 YAML 可載入、欄位集合及能力未變；generator 新測試通過。原題庫與 frozen snapshot 的 bytes 必須完全未變。

### Task 4：聚焦回歸與變更審查

**檔案：**上述實作／測試；驗證紀錄保存在本計畫的私有工作目錄。

- [x] 執行三個新增測試檔，確認所有 v4 要求通過。
- [x] 執行既有 catalog、retrieval ties、HAVING、project evaluation、runtime、需求拆分與 SQL pipeline 的聚焦回歸，與 Git 重組時的 185 個測試範圍對照。
- [x] 若舊研究測試只因固定 profile fingerprint 過期失敗，保留失敗與原因，不回填原資料／核准或弱化 validator。新測試以合成 profile 驗證新行為。
- [x] 檢查 diff、UTF-8 無 BOM、未知版本、來源 allowlist 及固定 20 題 Oracle hash。獨立檢視契約是否被完整投影、generator 是否真的拒絕來源變動。
- [x] 更新進度紀錄，列通過、失敗、未測及 source／profile 差異；不聲稱全套或 DB 數值已通過。

### Task 5：固定後測與配對報告

**檔案：**沿用私有 `run_phase.py`／cases；新增比較報告與逐題表，不修改 grader。

- [x] 呈現具體 diff 與離線驗證結果後，請使用者授權本機提交；未授權前保留成果，不繞過 preflight。
- [x] 授權後只提交本次 schema／文件／測試範圍，檢查工作目錄乾淨；不 push。
- [x] 核對 grader／prompt／casefile／settings 與 Ollama 基準一致；以 `run_ollama_five_after.py` 對新版 profile 跑同五題，各一次、不代選、不重抽。隔離 checkout 只套 v4 變更，排除同時新增的 ef33325 provider／prompt 修正。
- [x] 讀取實際前後五題 results，產出逐題改善／退步、錯誤原因與 calls／latency 的配對報告；缺少／skipped 留在固定分母且另列未觀測。
- [x] 保留原嚴格成績；對可能合法的其他 view 僅另列語意審查，不改原 Oracle。報告附固定日期及假唯一鍵修正帶來的行為差異。
- [x] 確認 metadata 中 source／profile 未在各 phase 中改變，報告限制：歷史通過組五題、每題一次、探索性自動評分、未執行 SQL；模型 digest 與量化已核對一致。

## 目前狀態

Azure 前測已完成並保存；Ollama v3 基準同五題各一次為 4/5（80%）。Task 1～4 已完成；最終相關71 tests通過、root全套671通過／18失敗（舊指紋與固定斷言，詳見私有驗證報告）；後測依最新指示改為 Ollama 同五題各一次。另有使用者同步新增的 provider 提交 ef33325，保留於目前分支，但隔離後測排除它以固定基準 prompt。

## 本輪完成結果與未解限制

隔離提交 `2e673d4` 後，Ollama 原五題各一次，前測4/5（80%）、後測3/5（60%），下降20個百分點。25次模型呼叫、0次呼叫錯誤，沒有補跑；原 Oracle、MATCH prompt、設定與模型 digest 一致。完整比較與錯誤紀錄保存在私有 `projects/retail/artifacts/view-schema-ab/20261022-20case-deepseek/ollama-five-after-20261022T100911055059Z/`。

未解：新版明細契約在初次比對超出預算；月KPI在首次誤放HAVING後，修正回合也超出預算，正確候選被排除。商品月彙總轉通過伴隨明細候選遭排除，不能視為語意能力提升。本輪不為提升分數調整輸入或重跑。測試與報告完成不代表新版契約已達全面採用條件；下一步應處理契約context體積與修正回合預算。

## 使用者要求解除 context budget 的補測

在隔離測試分支提交 `095b612`，新增預設啟用保護的 enforce_budget 開關。補測注入 false，只解除候選契約與呼叫前的應用預算檢查；保留實際token計數，Ollama num_ctx16000／max_token8192未變。開關及相關回歸88通過。原工作目錄未套用這份實驗開關，未push。

同五題各一次，補測4/5（80%）、36次模型內部呼叫、0次呼叫錯誤、0候選因預算排除。交易明細及門市月KPI恢復通過；商品月彙總仍為月彙總／明細的粒度澄清，原Oracle記未通過。通過集合與v3相同，尚未顯示v4準確率提升。

三階段比較、完整錯誤、來源diff、provenance與SHA見私有 `projects/retail/artifacts/view-schema-ab/20261022-20case-deepseek/ollama-five-no-budget-20261022T105036502953Z/`。既有v3／v4首次結果保持不變；本次為使用者另行授權的補測phase。

## 2026-10-23 歷史失敗組五題重測

依使用者要求，固定historical_failure組前五題，各一次，沿用095b612／v4／Ollama原參數／停用應用預算。結果3/5（60%）：會員、庫存與訂單通過；每日銷售與商品月彙總停在粒度澄清，依原Oracle計未通過。39次內部呼叫，0呼叫錯誤、0預算排除、無跳過。五題離線重評一致，未修改產品、YAML或Oracle。

合併同設定的歷史成功組4/5，目前已測十題7/10（70%），尚非完整20題；剩餘名單見私有ollama-v4-unrestricted-coverage.json。本次沒有補跑同版本v3基準，不能把歷史失敗組零通過直接當作schema受控提升證據。報告及完整錯誤位於私有ollama-historical-failure-five-20261022T152042723217Z/。

## 2026-10-23 同條件舊版確認與三輪穩定性補測

後續依使用者指示補齊同條件 v3 基準，並將兩版各補兩輪。固定相同10題、程式095b612、模型／提示／參數／原Oracle與應用預算停用設定，僅切換profile。v3三輪皆6/10，合計18/30（60%）；v4三輪皆7/10，合計21/30（70%）。每版逐題通過狀態與結果結構均三輪一致。每輪唯一改善為RETAIL-ORDER_SUMMARY-S1-01，沒有退步；這是固定10題的通過率與重複性結果，不能推論一般穩定度。

所有60筆原Oracle離線重評一致。有效面板444次模型呼叫，0呼叫錯誤、0候選預算排除；另保留最初服務未啟動的10次連線失敗。背景程序曾於32/40次中斷，原因未知，保留已完成結果，只續跑剩餘8題後完成；沒有重跑已完成題目。

可提交的完整彙總見[三輪比較紀錄](../reports/2026-10-23-view-schema-v4-evaluation.md)，包括耗時、來源指紋、中斷處理與限制。私有原始證據仍留在忽略目錄。工作分支保留ef33325，但隔離實驗排除此provider提示修正；應用預算實驗開關也未套入工作分支，因此不將70%當作目前分支預設設定的已驗證結果。

使用者已要求commit及push。提交前目前分支完整回歸671通過／18失敗，維持已記錄的舊契約指紋與固定斷言問題；v4與provider專項61項全部通過。保留原始題庫與驗證，未為提交改寫Oracle或核准。產品預算保護與provider修正均保留。
