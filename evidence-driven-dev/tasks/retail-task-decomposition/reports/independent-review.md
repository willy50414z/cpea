# Retail 需求拆分獨立審查

**最新複核：`b16d117`（等價正規化、離線重評指紋及安裝後 Git 定位修補）為 PASS_WITH_WARNINGS，原六類問題未回歸，限範圍審查未發現新增 blocking。詳見文末附錄。以下保留先前各 revision 的審查證據。**

**最終 benchmark 只讀驗收亦為 PASS_WITH_WARNINGS：90 次原始模型呼叫及現行版本離線重播已逐項核對，統計與限制揭露一致，沒有尚存 blocking。詳見文末 final acceptance。**

## 審查結論

**REQUEST_CHANGES**。在 `2777983..fdf0ea36594da2520cc30481da7cd27bb602e08d` 的實作中發現 **6 個 Important、0 個 Critical、0 個另列 Minor**。問題集中在錯誤計畫仍取得可提交 requests，以及評分器把可確定的結構錯誤算為通過。建議修正並重跑獨立負面驗證後，再開始 Azure benchmark。

本報告描述上述固定 revision 的問題；審查期間主 agent 已開始補測試及修正題庫 `cross-view-14` 的條件計數 oracle，這些後續修正尚未列為本報告的驗收結果。報告所列原始行號均以 `fdf0ea3` 為準。

## 範圍與證據

- 審閱 19 個變更檔案（1,013 行新增、1 行移除），並對照已核准規格、實作計畫、Retail 契約及代表性題庫。
- 執行 `.venv/bin/python -m pytest tests/unit/test_task_decomposition_contract.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py -q`，結果 **26 passed in 3.37s**。
- 另以 `TemporaryDirectory`、`tests.decomposition_support` 的合成 catalog／fake LLM，及真實 Retail 契約執行下列負面案例；沒有修改產品程式，沒有呼叫 Azure、SQL compiler、SQL executor 或 DB。
- 靜態檢查與 fake LLM 訊息檢查未發現 case ID、完整題文特例或 expected tasks 進入 planner prompt。一般規劃 prompt 與 oracle loader／grader 有分開。
- 現有 runner 測試已證明 fake 30×3 題只呼叫 90 次、provider 失敗只呼叫一次並略過後續 29 題，以及根目錄 Azure 設定覆蓋 Ollama 設定。此結論只涵蓋離線 fake provider，不代表真實 Azure 介面已驗收。

## Important

### 1. 對調門市與商品的鍵配對仍可 dispatch，且評分為通過

位置：`src/cpea/workflows/task_decomposition/validation.py:99`、`evaluations/decomposition_grading.py:74`。

validator 逐對只比型別，grader 則將左右鍵轉成集合比較。`store_id` 與 `product_id` 都是 number，因此左右鍵順序對調會把門市 ID 合併到商品 ID，卻不產生錯誤。這是可由契約識別碼語意判斷的錯誤，不能只留給自然語言人工審核。

重現：以 `tests.decomposition_support.draft()` 為基底，只改：

```python
data['integration']['edges'][0]['right_keys'] = ['product_id', 'store_id']
```

使用同目錄支援函式建立 catalog，以 `DecompositionDraft.model_validate(data)` 呼叫 validator，再透過 fake LLM 呼叫 service、以 `case_for(catalog)` 評分，實際結果：

```text
validation_errors=[]
service_status=ready
prepared_requests=2
integration_keys_match=True
automated_pass=True
```

建議：保留左右鍵的逐對關係，檢查鍵的語意相容性；評分器應比對配對後的 task／鍵對，不能把鍵轉為無序集合而遺失對應關係。增加門市／商品對調及會員／門市城市錯配的負面測試。

### 2. left join 可保留錯誤母體，anchor 欄位不能阻止庫存列遺失

位置：`src/cpea/workflows/task_decomposition/validation.py:104`、`evaluations/decomposition_grading.py:79`。

目前只要求 `preserve_task == left_task`，沒有要求從 anchor 出發的整合步驟保留 anchor 母體。把整合改為 sales LEFT JOIN stock，同時保留 `anchor_task='stock'`，即可保留銷售母體而遺失沒有銷售的庫存商品。grader 也只檢查宣告的 anchor 名稱及 join mode，因此仍通過。

重現：在相同合成草稿上修改：

```python
data['integration']['edges'][0].update(
    left_task='sales', right_task='stock', preserve_task='sales'
)
```

實際結果仍為 `validation_errors=[]`、`service_status=ready`、2 個 prepared requests、`automated_pass=True`。

建議：依 anchor 建立有方向的母體保留路徑，驗證每一步 left join 的保留方向及與前一步結果的關係。評分器也需依實際保留的 matched task 判斷 oracle 母體，不能只比 anchor 的文字欄位。

### 3. 未聚合的明細可自行宣稱較粗 grain，繞過一對多保護

位置：`src/cpea/workflows/task_decomposition/validation.py:59`。

validator 只有存在 metrics 時才檢查 `group_by == output_grain`，沒有從來源契約 grain 驗證未聚合任務的輸出粒度。合成 sales 契約是門市×商品×日期×通路，去掉 SUM 及 group_by 後，仍能宣稱自己已是門市×商品。其後整合只讀這項宣告，無法發現資料仍為明細，可能重複庫存值。

重現：

```python
data['tasks'][1].update(metrics={}, group_by=[])
```

保持原本 `output_grain=['store_id','product_id']` 及 `one_to_one` edge。實際結果為 `validation_errors=[]`、`service_status=ready`、2 個 prepared requests。

建議：未聚合輸出的唯一性需由來源 grain 加上可證明固定維度的條件推導；需要縮減粒度時必須有明確聚合、去重或巢狀收集規則。不得把 LLM 宣告的 cardinality 或 output grain 當作唯一性證據。

### 4. 三來源可省略商品整合鍵並改成門市最終粒度，仍取得滿足結構的分數

位置：`evaluations/decomposition_grading.py:74`、`src/cpea/workflows/task_decomposition/validation.py:82`。

grader 只在兩任務時使用 oracle 的 keys，三任務完全沒有驗證商品 facts 應以 `store_id/product_id` 合併。最終 `integration.output_grain` 也未參與驗證或評分。即使各 task 完全命中預期答案，後續準備動作把商品全部彙總掉，也會被算成 `automated_pass=True`。

重現使用真實 `cross-view-28`：從 `expected_tasks` 複製三個合法任務（移除 `acceptable_alternatives`，各補非空 request），保持所有 task 欄位、filters、metrics 與 grain；integration 改為：

```python
integration = {
    'anchor_task': 'inventory',
    'output_grain': ['store_id'],
    'edges': [
        dict(left_task='inventory', right_task=right,
             left_keys=['store_id'], right_keys=['store_id'],
             mode='left', cardinality='one_to_one', preserve_task='inventory')
        for right in ['product_sales', 'store_kpi']
    ],
    'preparation': [
        dict(task_id=task['task_id'], kind='aggregate', keys=['store_id'],
             description='商品資料依門市彙總，移除商品明細。')
        for task in tasks
    ],
}
```

實際結果為 `validation_errors=[]`、`service_status=ready`、3 個 prepared requests，且 `integration_keys_match=True`、`automated_pass=True`。題文要求各店各商品，這個結果明確失去商品層級。

建議：把三來源 oracle 表達為逐邊 task／鍵關係，逐邊檢查商品 facts 與門市背景；對最終 grain 與 preparation 的輸入、輸出 grain 進行一致性檢查。未知的語意可標人工審核，但已知必須保留的商品鍵不得自動通過。

### 5. 有額外條件的 SUM 被視為無條件 SUM 的等價答案

位置：`evaluations/decomposition_grading.py:31`。

`_task_score` 把 conditional metrics 的欄位與聚合覆寫進一般 metrics 字典。只要 oracle 要求一般 SUM，就可用額外限縮資料的 conditional SUM 冒充；當 oracle 沒有 conditional metrics，`all([])` 又使該檢查直接通過。這會把錯誤通路／母體計算算為正確。

重現：在合成庫存加九月全通路銷量案例上修改：

```python
sales = data['tasks'][1]
sales['metrics'] = {}
sales['required_columns'].append('sales_channel')
sales['conditional_metrics'] = [{
    'column': 'quantity', 'aggregation': 'sum',
    'conditions': [{'column': 'sales_channel', 'operator': '=', 'value': 'online'}],
}]
```

actual 的一般 filters 保持原本九月期間。實際結果為 `service_status=ready`、`metrics=True`、`conditional_metrics=True`、`equivalent_tasks_match=True`、`automated_pass=True`。實際只加總線上，oracle 要全部通路。

建議：一般及條件聚合分別配對，完整的條件集合應是 metric 身分的一部分，不能只依 column 對應 aggregation。補上「一般聚合被額外條件限縮」的負面測試。`cross-view-14` 修正為條件計數後，另需驗證缺少 `stock_qty=0` 條件及使用一般 filter 刪除零缺貨門市都不能通過。

### 6. 缺值及型別不支援的 filter 仍產生可提交 request

位置：`src/cpea/workflows/task_decomposition/validation.py:51`。

目前只檢查 filter capability、明列禁止操作及 IN 是否為 list；沒有套用既有 catalog 的型別操作子規則，也不檢查比較值是否存在。`PlanningFilter.value` 預設為 None，因此模型漏填 value 會變成無意義的日期比較，卻仍可 dispatch。

兩個獨立重現：

```python
data['tasks'][1]['filters'][0]['value'] = None
# 或重新取得原始草稿後：
data['tasks'][1]['filters'][0].update(operator='LIKE', value='2026-09%')
```

`order_date` 是 date，既有 catalog 的 date filter 操作子不含 LIKE。兩者實際均為 `validation_errors=[]`、`service_status=ready`、2 個 prepared requests。

建議：重用既有 catalog filter 驗證規則，驗證操作子、值型別、非空 IN、日期格式，以及 NULL 操作子的值要求。若 planner 特別支援新的 NULL／NOT IN 操作子，應明確定義及測試，而非直接繞過既有契約。

## 其餘觀察與限制

目前沒有證據顯示需要刪除既有程式或擴大範圍重構。建議修正集中於 validation／grading 與對應負面測試，維持 planning-only 邊界。

原始 provider 失敗會寫入私有檔案並停止後續模型呼叫；真實 rate limit 的 quota.py 判讀仍應由主 agent 按使用者規則執行。此次沒有製造真實 rate limit，也沒有測試真實 Azure 認證、路由、模型參數及 token metadata。

本報告不宣稱 26 個現有測試足以驗收整體功能，也不以 `semantic_review_required=True` 抵銷上述已可確定的結構 false positive。

## 修補版本複核附錄

複核 revision：`bf626de`。結論：**PASS_WITH_WARNINGS**；原六類發現沒有尚存 blocking，允許開始只呼叫 planner、不生成 SQL、不查 DB 的 Azure 探索性 benchmark。

以 fresh Python process 重播原先獨立建立的變異資料，沒有依賴新增測試函式內的斷言自證。focused 測試命令與初審相同，本輪結果為 **35 passed in 3.58s**。測試同時保留合法單來源、task 順序／ID 不變性、合法替代來源、三來源 KPI 門市鍵、context 拒絕、一次模型呼叫及 provider 停止行為的檢查。

| 原發現 | 獨立重播實際結果 | 判定 |
|---|---|---|
| 1. 門市／商品整合鍵對調 | `integration keys lack an admitted semantic mapping`；service `error`、0 payload；`automated_pass=False` | 已修正 |
| 2. left join 反向保留銷售母體 | `integration direction cannot preserve the anchor population`；service `error`、0 payload；`automated_pass=False` | 已修正 |
| 3. 原始明細宣稱店×商品 grain | `raw output grain is not supported by source keys`；service `error`、0 payload | 已修正 |
| 4. 三來源只依門市合併、最終遺失商品 grain | validator 仍允許這個門市層級計畫，但 grader 對原本要求店×商品的 `cross-view-28` 回傳 `automated_pass=False` | 原 false positive 已修正 |
| 5. 線上條件 SUM 冒充全通路 SUM | 結構合法的條件聚合仍可規劃；grader 對無條件聚合 oracle 回傳 `automated_pass=False` | 已修正 |
| 6. NULL 日期比較、date LIKE | 分別回傳 `filter value type mismatch`、`LIKE requires a string column`；service 均為 `error`、0 payload | 已修正 |

兩個與 oracle 不符的案例仍可能取得 service `ready`，這代表服務驗證結構與契約，並不代表它已證明計畫符合原始自然語言。現在評分器能辨識這兩個具體反例，不會提高本題庫正確率；報告仍必須保留 `semantic_review_required=True` 及探索性標記，不應將自動分數宣稱為完整語意驗收。

`cross-view-14` 的條件計數 oracle 更正有獨立的 `reports/oracle-correction.md`；本輪新增測試包含「條件計數不能被一般計數取代」，且已通過。沒有為提高模型分數修改題文或把 pending 題庫升為人工核准。

本次複核未執行真實 Azure 或 DB，也未修改產品程式。真實部署路由、參數、token metadata、模型輸出品質及 rate limit 的 quota.py 判讀，仍須由主 agent 在接續的實測與產物審查中確認。

## 等價正規化與離線重評複核附錄

複核範圍為 `bf626de..0604c7d385049b0790d6c918a3f102c1def2fa9e` 的等價正規化與離線重評，以及本輪新增的重評程式／diff 指紋與固定 Git cwd 修補。結論為 **PASS_WITH_WARNINGS**，未發現新增 blocking，原六類反例未回歸。本輪只審查這些變更，沒有為改善模型成績修改 oracle 或要求模型結果全通過。

本輪 focused 命令與前兩輪相同，結果為 **44 passed in 5.55s**。固定 Git cwd 的最後小修後，另外重跑離線重評及快照 FD 成對測試，結果亦通過。

獨立負面及等價重播確認如下：

| 規則 | 正例 | 反例 |
|---|---|---|
| 月份與每日範圍 | 九月月份條件等價於 9/1 至含 9/30 | 多包含 10/1 不等價 |
| 單列原值與聚合 | 固定單月，來源唯一鍵證明店×商品只有一列，raw units_sold 可等價 SUM | 跨兩個月份的 raw 月資料不可當成店×商品彙總 |
| COUNT 與 COUNT DISTINCT | 來源鍵、分組與固定條件共同保證被計數欄位唯一時接受 | 未固定月份、可跨月重複商品時不接受 |
| 額外日期維度 | 原始店×商品唯一鍵能決定該列 snapshot_date，冗餘日期不會增列，可接受 | 跨商品彙總到店後再按 snapshot_date 分組，不可從契約證明日期唯一，仍判 grain 不符 |
| 必要時間 metadata | 依需求保留 snapshot_date | 刪除必要 snapshot_date 仍判欄位缺漏 |

「額外 snapshot_date grain 仍保留失敗」已釐清為上表的跨商品彙總反例，不是拒絕所有由唯一鍵決定的冗餘欄位。此判準有來源契約依據，不需要題目 ID 或完整題文特例。

原先的整合鍵對調、反向保留母體、raw grain 宣告、NULL 日期與 date LIKE，獨立重播仍回傳 error 且 0 payload。條件聚合冒充一般聚合，以及真實 `cross-view-28` 漏掉商品鍵／最終商品粒度的反例，仍為 `automated_pass=False`。

另在臨時目錄建立 fake 30 題原始 run，分別執行一次普通重評與一次 `revalidate=True` 重評。獨立檢查結果：

- 原始 run 所有檔案的 SHA-256 完全不變，新報告各自使用新目錄。
- fake LLM 呼叫數一直是原始 30 次；兩次重評各自 `additional_model_calls=0`。
- 新報告的 `source_results_sha256` 與原始 results 檔案一致。
- `grading_code_sha256`、`validation_code_sha256`、`response_models_sha256` 均逐項比對實際程式檔內容而通過；另保存 `grading_revision` 與 `grading_diff_sha256`，不再只以 HEAD 冒充未提交程式的版本。
- `revalidated` 能區別只重評與重新驗證／準備 requests；原模型 revision 與原始回覆仍由 source run 保存。

本次最後審閱的 `evaluations/decomposition_reports.py` SHA-256 為 `77484708464df3ab9b02fbfe685c3facd887e5d648396389af8ed451c677aa2e`，grader 為 `41682cdf2c9754240bd7d9c5cc42497954f51ec40d1790ebab07adef1b429cc8`，validator 為 `b46ffdc34f8f28da21d6f9f50b5078bd0ed549378aea638b371f56779570b26c`。

上述最後小修已由主 agent 提交為 `b4ef63e5219c27abfffbbc68a1478115bbf55117`；報告程式內容 SHA 與審閱時一致。最後兩項 focused 測試結果為 **2 passed in 2.66s**。

限制仍為自然語言 request 與完整整合語意未經本報告全面人工驗收。本輪沒有呼叫真實 Azure 或 DB，沒有變更正在執行的真實 baseline 產物，也不把離線重評當成新增模型實測。

## 安裝後 Git 定位快速複核

`b16d117a2a3168a61c3cdbd889fc0e54ab079625` 只把 runner／regrade 的 Git 工作目錄改由 `evaluations.metadata.git_workspace(profile)` 尋找，依序檢查 profile、cwd、metadata 模組所在位置及其父目錄。`.git` 使用存在性檢查，也能涵蓋 worktree 的 `.git` 檔案。找不到時明確失敗，不會把 site-packages 當成 Git root；沒有改變模型呼叫或評分邏輯。

已審閱這項提交與新增回歸測試，執行 `test_installed_runner_finds_workspace_git_not_site_packages` 得到 **1 passed in 2.28s**。本項未發現新增 blocking，整體仍為 **PASS_WITH_WARNINGS**。沒有新增真實 Azure 或 DB 呼叫。

## Final acceptance：真實 benchmark 只讀驗收

最終產品 revision 為 `b16d117a2a3168a61c3cdbd889fc0e54ab079625`。驗收結論為 **PASS_WITH_WARNINGS**，沒有尚存 blocking。這是對功能邊界、證據、離線重播及結果揭露的驗收，不是宣稱模型每題都正確。

審閱 `reports/audit_live_benchmark.py`、`reports/live-benchmark-audit.json`、`reports/benchmark-results.md`，並讀取原始 run 與重評 run。沒有重新執行會寫入新產物的 audit 腳本；另外以 fresh Python process 執行只讀核對，在記憶體中重新解析、驗證、準備與評分，確認：

- 30 題×3 輪的 90 個 case/run 配對完整、唯一；全部為 completed，provider failed=0、skipped=0。
- 全部 90 次原始 request 的 system prompt、完整 response schema、7 個 View 契約及題文與現行檔案相同；context 只含 request／views／response_schema，沒有 oracle 或案例 metadata。
- 90 個 raw responses 均可解析，且逐項等於原 run 保存的 draft。
- 以現行 validator／prepare_requests／grader 在記憶體重播後，90 筆 response 與 score 均和保存的重評結果完全一致，6 筆 ready/error 狀態變更也一致。
- 原始 results SHA 與重評 metadata 的 source SHA 相符；grader、validator、models SHA 與實際程式內容一致。只讀審查前後，原始 run 全部檔案 SHA 完全不變。
- usage 90 次皆有回報，合計 input 657,600、output 112,053、total 769,653 tokens；這是保存的 provider metadata 加總，沒有補造未知用量。

核對後的主要數字如下：

| 指標 | 結果 |
|---|---:|
| 真實原始模型呼叫 | 90 |
| 額外模型呼叫 | 0 |
| 主要 View 命中 | 90/90 |
| 來源與必要欄位涵蓋 | 79/90 |
| 現行驗證器通過並準備 requests | 88/90 |
| 自動結構全通過 | 60/90 |
| 三輪皆選對 View | 30/30 案例 |
| 三輪皆涵蓋必要欄位 | 24/30 案例 |
| 三輪皆準備 requests | 28/30 案例 |

兩筆拒絕為 `cross-view-05` 的 `run=1` 與 `cross-view-12` 的 `run=2`（原始資料使用 0-based run）；都回報 `finer output grain requires an explicit preparation`。跨商品彙總後再加門市名稱等維度，沒有已編碼的契約 FD 證據可證明唯一性，因此保守拒絕合理。必要欄位遺漏包含 snapshot_date 等時間 metadata，報告有逐案例列出，沒有為取得通過而放寬 oracle。

已核對 EDD focused 證據 `EV-20261020T051900-4f8ad1f6` 與 regression 證據 `EV-20261020T051301-71c1c927`，兩者 exit_code=0、source_unchanged=true，且 raw_output SHA 與紀錄一致；回歸 log 確認為 **370 passed, 1 skipped**。

原始 live 證據 `EV-20261020T050125-de42b8c9` 的 `source_unchanged=false` 已確認，不把它當成現行版本的新鮮 live 驗證。原模型程序載入 `bf626def01a2bb9bf5e623b28075222688a9bcfe`；執行期間另提交離線評分與驗證修補，最後以 `b16d117` 對保存的原始草稿重播。報告明確分開兩個版本、原始產物與重評產物，且逐次實際訊息核對證明生成 prompt/schema/契約沒有改動，因此保留原 run 並離線重評的證據處理合理，不需要再次消耗模型呼叫來冒充同一輪實驗。

保留的限制：題庫人工審核仍為 pending，本次為探索性 benchmark；60/90 自動通過並不代表完整自然語言與業務語意正確；沒有驗證 SQL、DB 權限、數值、真正資料合併、採購決策或既有網頁／SQL API 的自動 dispatch。此次 reviewer 沒有發出 Azure 或 DB 呼叫；只讀驗收沒有新增或改寫原始／重評 benchmark 產物。
