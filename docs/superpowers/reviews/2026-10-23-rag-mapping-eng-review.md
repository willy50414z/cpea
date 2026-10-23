# RAG 需求映射流程工程審查

日期：2026-10-23。狀態：**DONE_WITH_CONCERNS**。角色：獨立 RAG／Text-to-SQL 架構審查。

審查標的是使用者提出的八步「建議調整後流程」，並對照目前實作與已核准原版；本報告所有推薦均為 **agent 建議，待使用者採納**，不是已核准需求或已實作變更。未修改產品碼、現有測試、原版 spec／plan、TODOS 或 EDD 完成紀錄。

## 主要結論

流程方向合理，但先處理下面五件事，才值得投入並行、多模型或新向量資料庫：

1. **缺來源不能直接宣稱 catalog 不支援。** 明確區分「查不到／預算不足／比較失敗」與「已確認不支援」，並讓有限次補查真正有終止條件。
2. **多需求檢索要保護完整來源集合。** 保留原句查詢、按具體資料需求與相關時間／粒度組查詢、保留每個需求的來源，再融合排名；不能只把所有分數取最大後全域 top-k。
3. **候選數與總成本要有可見預算。** cutoff ties 與明列欄位的全部 owner 都可能把 soft limit 撐到全 catalog；不可靜默硬切，也不可承諾固定 C+3。
4. **先重用引擎與移除重複載入。** 多查詢共用同一個 retriever；啟用 vector／CrossEncoder 時才處理其額外初始化成本。現行 lexical＋lexical 沒有 embedding／CrossEncoder 呼叫成本。
5. **建立新流程專用真實模型 eval。** 同一個 LLM 的二次審核並非獨立證明；手寫 staged response 的 173 個測試無法回答模型會不會把固定 30 日銷量當九月銷量。

不建議第一輪加入 per-stage 模型路由、無界補查、直接開大並行，或把完整契約改成只給欄位名稱。

## 套用 Skill 與執行界線

已完整讀取並套用 [指定 plan-eng-review SKILL.md](/home/willy/code/gstack/.agents/skills/gstack-plan-eng-review/SKILL.md)。scope 已由主代理確認；依 skill 的 spawned session 規則，逐議題自動選推薦方向完成 Architecture → Code Quality → Tests → Performance 四節，但選項全部仍待使用者採納。

依此次任務限制跳過 upgrade、first-run setup、routing injection、瀏覽器、遠端 telemetry／artifacts sync、brain 遠端查詢及額外 outside voice。此 subagent 本身即獨立審查者，沒有再啟動子代理或假稱跨模型共識。無互動 AskUserQuestion 工具不構成 blocker。已讀本地 learnings：`runtime-owned-in-memory-checkpoint` 與本次無 checkpoint／人工確認範圍不直接相關，不擴充 scope。repo 無 CLAUDE.md／TODOS.md；pytest 由 pyproject.toml 與現有測試確認。`jq` 可用。

安全 preamble 子集已執行：git status／branch／最近五次 log、gstack-slug、local learnings、review-read；artifacts_sync_mode 確認為 off。HEAD `095b612`，branch `feat/complex_req_test`。最近紀錄含 context budget override 與 schema v4 語意傳遞，故本次特別保護 budget 與 time／grain／scope。不把舊版本契約指紋失敗納入本次新回歸。

## Step 0：Scope Challenge

**What already exists**

| 子問題 | 目前可重用程式 | 審查方向 |
|---|---|---|
| 獨立入口與舊流程隔離 | application/services/schema_mapping_decomposition.py、schema_mapping_workflow.py | 原入口已存在，勿再新增第三個 planner |
| 無 schema 抽取與 span／related_ids | mapping_models.py:20、mapping.py:19、mapping_prompts.py:9 | 保留並移到 retrieval 之前，無需新 agent framework |
| 多來源明列識別碼與 ties | mapping_retrieval.py:13、schema.py:128 | 重用，補多 query provenance／coverage／budget |
| retriever cache | schema.py:363 | 可考慮既有 factory；第一步以 request-scoped engine 重用最簡單 |
| 同欄位真實引文 | mapping.py:51 | 重用，清楚標示只證明引文真實性 |
| 全域審核／allowlist／母體與期間綁定 | mapping.py:124、:255 | 重用，維持每個候選 View 比較閉合 |
| 最終草稿與 requests | validation.py:22、:206 | 原末段已支援多來源；本版不生成 SQL |
| 原 eval metadata 與評分 | evaluations/decomposition_runner.py:54 | 可重用基礎函式，不能把舊 service 的 eval 當新流程證據 |

**最小變更與複雜度挑戰。** 目前約 15 個新增檔是「已完成原版」，不是此提案要重做的 15 檔。完整加入多 query、補查、cache、並行、路由及 eval 很容易再次超過 skill 的 8 檔／2 新 class 警戒。推薦分階段：第一階段只改獨立 workflow／retrieval adapter／trace 與必要狀態，配 3 組專用測試；不新增 service、資料庫、agent framework 或模型路由。語意 eval、可觀測性、條件式效能調整另拆可驗收任務。這是 spawned 的 scope reduction 建議，沒有修改原版核准範圍。

**D0 agent 建議選 A，待採納。** A：先完成有界多需求召回與正確狀態（human 約 1–2 日／CC 約 1–3 小時，維護較少）；B：八步加所有效能機制一起做（human 約 3–5 日／CC 約 4–8 小時，變因及回歸風險較多）；兩者是交付階段差異，不給虛構 completeness 分數。完整錯誤路徑與測試仍必須納入各階段。

**Search check。** 已查官方 Python bounded executor、Ollama concurrency、Sentence Transformers batch predict、Elastic RRF 文件，詳見各 finding 來源；採標準能力而不加 orchestration 依賴，皆為 [Layer 1]。不直接假設 RRF 在本資料集優於 lexical，只把它當避免跨 query 原始分數相加的可比較基準 [Layer 3]。無新 artifact 類型，沿用 Python 專案執行／測試方式，無新增發佈管線需求。

## 建議流程與閉合條件

以下為待採納流程，與目前「先 raw retrieval 再 extract」有別：

```text
原文 + 已釘定 catalog fingerprint + request budgets
  |
  v
extract(no schema) -> validate spans/relations/classification
  | invalid -> error; 不查詢、不規劃
  v
query plan: 原句 backstop + 去重後的資料需求群組
  | time/value/grain 連回資料概念；purpose/prohibition 不各自盲目查一次
  v
同一 retriever -> 各 query ranks + requirement provenance
  v
union/dedup + 明列 owners + 必要關聯來源
  | 來源身分與 fingerprint 驗證；不得依原始跨 query 分數直接比較
  v
coverage-aware allocation + ranking + 預算判定
  | 超預算 -> 明示 incomplete；不可靜默丟來源後 ready/unsupported
  v
逐候選完整 View mapping -> schema/evidence validation
  | 目前仍採序列、遇錯早停；不得把失敗視為 unmatched
  v
coverage closure(data + time/grain + population + integration keys)
  | gap 且尚有 query/map/time/token budget
  +----> gap query -> 新 View mapping -> closure
  |       相同 fingerprint + extraction version 只 mapping 一次
  | 無進展／預算用盡 -> retrieval_gap / error code，不推論 catalog 不支援
  v
global LLM review(原文 + mappings + 完整相關契約)
  | 發現漏抽 -> 本輪早停（第一階段）；未來修補必須升版本並重新閉合
  | 歧義 -> needs_clarification; 非 ready 不可派送
  v
MappedDraft(draft + bindings)
  v
validate_mapped_draft + validate_decomposition + prepare_requests
  | fail -> error
  v
ready / 單 View prepared requests（不生成或執行 SQL）
```

建議在 schema_mapping_workflow.py 記錄此狀態圖，在 mapping_retrieval.py 記錄多 query 融合與 budget 圖。沒有改動現有 ASCII 圖；現有 README／原版 spec 描述的是舊順序，未來實作採納後才同步，這次不把它們改成未實作流程。

## 1. Architecture review

### 1. [P1] (confidence: 10/10) schema_mapping_workflow.py:120–124：候選缺口與 catalog 不支援混在一起

證據：`if r.required and r.kind in DATA_KINDS and r.id not in available` 後立刻 `return self._result(trace, 'unsupported', code='unmapped_required_requirement', ...)`；:106–107 空檢索也直接 `unsupported/empty_retrieval`。這符合原版 spec:49／:75，**不是原版違反核准設計的 bug**，但新提案要解除這個限制。

反例：庫存來源入選，支援九月銷量的 monthly View 被 cutoff 排除；現在會在全域 review 之前宣稱 unsupported。有限補查無結果也只能證明本策略尚未找到，不能證明全 catalog 不支援。

- **1A（agent 推薦，待採納）**：沿用公開 error status，增加 retrieval_gap／budget_exhausted 等明確 code 與缺口理由，unsupported 僅用於有可稽核否定依據（human 約 3h／CC 約 40min，低維護；完整處理可見失敗，Completeness 10/10）。
- 1B：為獨立 response 新增 incomplete 狀態並同步所有消費端（human 約 1 日／CC 約 2h，語意更直接但改動範圍較大，Completeness 10/10）。
- 1C：維持現況但只改訊息（human 約 30min／CC 約 10min，status 的錯誤語意仍會誤導呼叫端，Completeness 3/10）。

偏好依據：explicit > clever；新入口可擴充 code，不必改舊公開 enum。empty_catalog 可繼續明確 unsupported；needs_clarification 用於真實需求歧義，不拿來掩蓋 retrieval failure。必要鍵不相容可回明確整合不支援，但不能由單次未命中推論不存在其他來源。

### 2. [P1] (confidence: 9/10) mapping_retrieval.py:27–38：單 query 分數與 cutoff 不可直接擴成多 query 全域選拔

證據：`if name not in scores or score > scores[name]`、`select_with_ties(ranked, limit)`；目前 `ViewSelectionTrace.query: str`（mapping_models.py:132）也只有一個 query。這些程式在現有單 query 是合理的；**新提案尚未定義跨 query 融合與來源集合目標**。

反例：原句 top ranks 全是庫存，sales 子 query 只有第 4 名才有完整九月來源；直接跨 query max score 排名可能再次擠掉 sales。原始 query 確實可找回被誤抽詞的來源，但不能自動補回被 extraction 刪掉的 requirement 或 prohibition。

- **2A（agent 推薦，待採納）**：用原句＋按 related_ids 組合的去重子查詢，保留 query→requirement→View provenance，按需求保留候選，再以 rank fusion／共同原句 rerank 作次序（human 約 1 日／CC 約 2h，需驗 coverage，類型選擇不計 completeness）。
- 2B：每個 unit 不分種類各查一次、分數取 max（human 約 4h／CC 約 45min，fanout 較大且不保集合召回，類型選擇不計 completeness）。
- 2C：先維持 raw query，只加入 gap query（human 約 4h／CC 約 1h，變更較小但初查仍可能偏單來源，類型選擇不計 completeness）。

偏好依據：重用既有 adapter；不引入新 search service。RRF 使用 rank 而非要求各來源分數同尺度；這不表示 RRF 可保證需求覆蓋，仍需每需求保留與後續 mapping。參考 [Elastic RRF 官方文件](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion)。

### 3. [P2] (confidence: 9/10) schema_mapping_workflow.py:113–117／:149–150：候選失敗隔離必須與 coverage 閉合一起設計

證據：`for view in views:` 每個 `_call`／`_check` 共用外層 `except _PlanningStop ... return ... 'error'`；mapping.py:130–131 明確要求 `completed comparison of every admitted view`。原版 spec:67 已核准任何候選失敗早停。

反例：不必要的 KPI View token 超限，阻斷已能回答的 stock＋sales。反過來，若將例外吞掉繼續，失敗來源可能是唯一支援「目前」快照語意的 View，不能聲稱比較完成或不支援。

- **3A（agent 推薦，待採納）**：第一階段保留 fail-closed，不重試、不改隔離策略，trace 明示 failed/unprocessed 和 coverage 不完整（human 約 1h／CC 約 20min，最低回歸風險，類型選擇不計 completeness）。
- 3B：未來引入 per-candidate failed 狀態，只有完整支援集合已閉合且可證明失敗候選非必要時才繼續（human 約 1–2 日／CC 約 3h，需調整審核契約與 ambiguity 評估，類型選擇不計 completeness）。
- 3C：任一候選失敗就跳過並進 review（human 約 2h／CC 約 30min，會破壞原本的全候選閉合保證，不推薦）。

偏好依據：先維持既有明確語意；單 GPU 過載／429 屬 shared provider 問題時全流程早停，不藉 candidate retry 繼續轟服務。

## 2. Code quality review

### 4. [P1] (confidence: 9/10) mapping.py:80–81／:130–145：補查不能用 stale extraction／mapping 通過閉合

證據：`set(ids) != set(requirements)` 要求每 View 完整回覆；review 要求 `set(names) == set(definitions)`，且 `missing_requirements` 非空直接錯誤。目前沒有補查 loop，因此這是**新 loop 必須保留的 invariant**，不是已發生 stale-cache bug。

反例：review 才發現「保留所有庫存商品」漏抽，僅把新詞加入 extraction 和新 View mapping，舊 View 結果不含新 requirement；若改成寬鬆驗證將產生不完整 ready。

- **4A（agent 推薦，待採納）**：第一階段只允許既有 extraction 的來源 gap 補查；以 fingerprint＋extraction hash 去重 mapping，新詞仍早停，另記 query round／progress（human 約 5h／CC 約 1h，維持閉合，類型選擇不計 completeness）。
- 4B：允許 extraction version 升版，每次重驗全部 admitted View／review／bindings 並另設呼叫上限（human 約 1–2 日／CC 約 3h，較能自動修復但成本大，類型選擇不計 completeness）。
- 4C：局部補詞且沿用舊 mapping（human 約 2h／CC 約 30min，stale mappings／ID collision 風險，不推薦）。

偏好依據：不弱化 validator 來通過新 loop。查詢 fingerprint 重複、無新 View、缺口集合無縮小、query/map/token/time 任一預算耗盡都必須終止；不能只限制 round，因每 round fanout 仍可膨脹。新 View 的必要輔助鍵缺口也要回到 closure，不讓 review 自己發明未 mapping 的新來源。

### 5. [P1] (confidence: 10/10) mapping.py:35–45／:65–70：結構有效與真實引文不能代替語意支持

證據：syntax 僅 punctuation 類型檢查業務文字；`item.quote not in value` 與 `item.path[:2] == ['columns', column]` 只證明同路徑引文。離線探針把「暫不計算採購量」改標 syntax，validate_extraction 回 `[]`；引文「不支援九月銷量」也讓 validate_evidence 回 `[]`。這正是原版 spec:59／:99 已揭露界線。

反例：mapper 和 reviewer 同時漏否定；或引文真實但固定窗口跨九十月；原句 retrieval backstop 仍不能保證恢復禁止條件。

- **5A（agent 推薦，待採納）**：保留 deterministic validators＋原文先讀 review，另以標註反例、真實模型 eval、必要 ambiguous 早停驗收（human 約 1–2 日／CC 約 2–4h，人工 oracle 成本不可省，Completeness 10/10）。
- 5B：再加同模型第三次投票（human 約 2h／CC 約 30min，增加 calls 但錯誤相關性仍在，Completeness 5/10）。
- 5C：用關鍵字否定 regex 取代語意審核（human 約 3h／CC 約 40min，改寫、隱含限制和反向否定易誤判，Completeness 3/10）。

偏好依據：測使用者行為與反例，而非只驗 JSON。未要求馬上換 reviewer 模型；不同模型亦需 eval，不能將多模型視為正確性保證。

## 3. Test review

### 6. [P1] (confidence: 10/10) evaluations/decomposition_runner.py:61／:81：現有真實模型 runner 驗的是舊 service

證據：`settings=azure_planning_settings(env_file,model)`、`service=TaskDecompositionService(...)`；測試支援檔:106–117 的 `StagedLLM` 回手寫 payload，usage 固定 10／20。現有測試充分驗證結構邊界，但沒有驗新 retrieval→mapping 的真實 qwen 語意與實際延遲。

- **6A（agent 推薦，待採納）**：另建新入口專用 eval／或受控 service injection，使用同一版本標註資料比較 baseline／提案，保留舊 runner 行為（human 約 1–2 日／CC 約 2–4h，含可重放 calls／停止規則，Completeness 10/10）。
- 6B：只跑現有 173 focused（human 約 10min／CC 約 2min，結構回歸有用但無真實品質證據，Completeness 4/10）。
- 6C：用同一 LLM 當唯一 judge（human 約 3h／CC 約 40min，方便但可能共享來源／否定誤判，Completeness 5/10）。

偏好依據：真實品質與成本分開驗，不能因手寫 response 全過就宣稱新流程有效。這次只跑離線測試，不連真實服務；eval 是待採納實作／執行任務。

### 程式分支與使用者流程 coverage diagram

```text
CODE PATHS（目前）                         USER FLOWS／提案新增路徑
service.plan -> workflow.invoke             庫存 + 九月銷量 + 全庫存母體
  +-- [★★★ TESTED] invalid/empty request       +-- [★★★ TESTED] stock+sales/monthly -> requests
  +-- [★★★ TESTED] retrieval error/empty       +-- [★★★ TESTED] 禁 inner／期間綁到每個 metric
  +-- [★★★ TESTED] extraction span/type        +-- [★★★ TESTED] allowlist/bindings/grain 不可掉
  +-- [★★★ TESTED] per-view evidence/IDs       +-- [GAP G1 ->EVAL] 真否定引文、漏否定/漏目前
  +-- [★★★ TESTED] call/parse/token fail       +-- [GAP G2 ->EVAL] 完整來源集合及等價解評分
  +-- [★★★ TESTED] review/draft reject         +-- [GAP G3 ->E2E] 子需求召回+原句 backstop
                                             +-- [GAP G4] rank fusion/每需求保留/去重
提案 extraction -> query plan               +-- [GAP G5] 100零分 ties/共享owner/查詢預算
  +-- data + related time/value/grain         +-- [GAP G6 ->E2E] gap補查成功/無進展/上限
  +-- purpose/prohibition不盲目查             +-- [GAP G7] version/fingerprint/cache失效
  +-- raw query backstop                     +-- [GAP G8] map失敗非unmatched/禁止partial-ready
proposal gap loop -> closure                 +-- [GAP G9] review漏詞仍早停/來源鍵完整性
  +-- gap/new view/progress/stop              +-- [GAP G10] 全域token與真實成本/可選並行次序
```

這是「審查群組」而非逐行 coverage：6 個既有程式群組／3 個既有用戶行為群組有測試證據；列出 10 個提案／真實模型 GAP。沒有量測 coverage 百分比，不能將 173 passed 換算為 100% coverage。TESTED 的證據分別在 test_schema_mapping_decomposition.py:23／:51／:78／:110／:162、test_schema_mapping_validation.py:15／:44、test_schema_mapping_review.py:20／:57／:91／:121／:130、test_schema_mapping_retrieval.py:31／:43／:56／:83／:95。品質 ★★★ 表示該群組合併有行為、邊界與錯誤案例；不代表真實 LLM 正確。

### 每個 GAP 的具體新增驗收要求

| GAP | 建議測試檔／類型 | 具體輸入與斷言 |
|---|---|---|
| G1 | 新 schema mapping eval dataset／真模型 eval | 九月 vs 固定 30 日、目前無最新快照保證、禁止量誤作語法、真實否定引文；錯來源不可 ready，正當歧義應 clarification |
| G2 | schema mapping eval grading／eval | gold 為可接受來源集合家族及 requirements→column→operation；交易聚合與 monthly 可等價，庫存母體、時間範圍、粒度、禁採購均獨立評分 |
| G3 | test_schema_mapping_decomposition.py／離線整合 | mapper 只在子 query 返回 sales；另 extraction 漏詞但 raw query 找回來源，仍需 review 回 missing requirement，不可誤認自動補詞成功 |
| G4 | test_schema_mapping_retrieval.py／unit | 原 query A 分數100、子 query B分數0.9，需求來源仍保留；query 重複不加權灌票、共同原句 rerank 不刪唯一來源 |
| G5 | test_schema_mapping_retrieval.py／unit | 100零分 ties、unqualified store_id全owner、qualified只釘owner；budget不足回明確 incomplete/error code，不能靜默截斷後 ready |
| G6 | test_schema_mapping_decomposition.py／離線整合 | 第一次缺sales、第二次新增monthly並成功；重複查詢、無新View、無gap改善、round/call/time/token上限各早停；新View只map一次 |
| G7 | test_schema_mapping_retrieval.py／unit | 相同profile/version但契約內容改變必須miss；不同tenant/path/provenance/model/tokenizer版本不可誤用；同request engine只build一次；cached result重驗 |
| G8 | test_schema_mapping_decomposition.py／unit | 最先非必要來源provider失敗仍維持原版早停；不出prepared requests；未來若隔離，failed必要來源不得 unsupported/ready |
| G9 | test_schema_mapping_review.py／unit | 補來源不改requirements版本；若新增requirements則全部舊mapping失效；關聯key/type/grain缺口不可由review補未經mapping來源 |
| G10 | test_schema_mapping_decomposition.py＋可選效能 harness | 各階段count前fail、sum usage不等max context、HTTP counter每stage恰一次；若採workers=2，乱序回傳仍catalog次序且failure不產partial-ready |

若後續實作造成舊 flow、字面識別碼、期間、母體或 ties 的行為回歸，對應測試是 **CRITICAL 必備**；本次只審查，沒有已實作新 diff，因此不虛構新回歸。

### 真實 eval 與 oracle 設計

先人工審定 30–50 個具代表性 challenge cases，再保留不參與 prompt 調整的 held-out 集；這是建議規模，不是已建立資料。每筆固定原文、catalog fingerprint、支援／歧義／不支援標籤、允許的完整來源集合家族、需求關聯圖、欄位用途、期間／粒度／母體與禁止條件，以及明確 hard negatives。Oracle 由人閱讀完整契約標註，不能以模型答案自己產 gold。

固定模型 digest／provider／tokenizer／prompt hashes／schema hashes／retrieval設定與預算，比較：舊 raw-first baseline、新extract-first＋raw backstop、新gap retrieval；有可證明 missed recall 才試 hybrid／reranker。分開做 gold-extraction retrieval（隔離檢索品質）、gold-candidate mapping（隔離語意能力）、full pipeline eval（實際用戶結果）。若非確定生成，建議同案至少3次，但不宣稱 seed 保證再現。

核心指標：任一完整可接受來源集合是否全召回、逐需求來源召回率、錯誤 unsupported率、false-ready率、時間／粒度／母體／禁用約束違反率、等價解通過率、映射語意正確率、clarification 合理性；另報 C／tokens／calls／錯誤率／P50/P95及cold/warm，不能只報 top-1 View 或平均相似度。小資料集報 numerator/denominator 與案例，不用無依據顯著性。exact contract evidence 是硬 gate，語意支持仍需人工抽查。

門檻建議：已核准既有正例全不回歸；hard-negative 安全語意案例不得 false-ready；其餘新策略須提高完整集合召回且在使用者採納的成本預算內。不存在已核准延遲 SLO，這次不私訂 P95 數字。實際 runner 須統計每一個 stage 的 calls，rate limit 立刻保存並停止，依 AGENTS quota 流程處理，不盲目重跑。

## 4. Performance review

### 7. [P1] (confidence: 10/10) schema.py:146–148／mapping_retrieval.py:59–65：soft limit 不是實際工作量上限

證據：`return items[:top_k] + ... if score >= threshold`；未限定欄位採 `owners = qualified or [view.name for view in views if column in ...]`。離線 100 個零分候選、limit=5，實得 C=100。這是核准的 ties／owner 召回保護，**不能逕改為 top5 硬切**。

反例：逐需求各查一次再 union，C 接近 N，每個完整契約都進 LLM；「目的」「禁止事項」也各查一次只增加無關 ties。限制 rounds=1 仍可能發出 R 個查詢與 N 個 mappings。

- **7A（agent 推薦，待採納）**：先定 Q_max、unique-mapping call上限、總tokens與deadline，合併等價query、保留需求來源；超預算明示未完成及未比較集合（human 約 5h／CC 約 1h，Completeness 10/10）。
- 7B：直接硬截 C≤5（human 約 1h／CC 約 15min，召回與原核准語意受損，Completeness 3/10）。
- 7C：不設預算只記錄 C（human 約 1h／CC 約 15min，保召回但無成本控制，Completeness 5/10）。

偏好依據：成本要可解釋，完整性不能靠靜默丟棄模糊候選交換。精確數值以代表資料測試後由使用者採納，不在 review 任意指定5/10/20就是正解。

### 8. [P2] (confidence: 10/10) mapping_retrieval.py:23／schema.py:197–201／:295–296：共用 engine 才能避免重建

證據：`engine = retriever if retriever is not None else SchemaRetriever(settings, catalog)`；vector store 為 instance `@cached_property`，首次 `store.add_documents(self.documents)`；CrossEncoder 為 `encoder = self._cross_encoder or self._build_cross_encoder()`，沒有賦回 self。已有 get_schema_retriever:369 的 key 含 settings/profile/version/fingerprint/id(catalog)，容量4。

離線確定性計數：預設 adapter 3 queries → build_documents 3次；注入共享 engine 後3 queries追加0次（初始化1次在計數前）。fake CrossEncoder 啟用情境下，3 queries → factory 3次。未呼叫真實 embedding／CrossEncoder；目前 lexical＋lexical 只涉及 documents 重建，條件式模型成本未量測。

- **8A（agent 推薦，待採納）**：同一次plan重用一個engine（可沿用注入），若採跨request factory則保持既有安全key；真的啟用CrossEncoder再保存instance（human 約 3h／CC 約 40min，低維護，類型選擇不計 completeness）。
- 8B：現在就加持久向量索引與全stage result cache（human 約 2–3 日／CC 約 4h，失效／部署／隱私面更大，類型選擇不計 completeness）。
- 8C：每query全新engine（零新增工作，多query與vector模式時重複成本保留，類型選擇不計 completeness）。

偏好依據：先重用既有 factory／injection，不造新 cache service。catalog fingerprint 只在 yaml_catalog.py:73 載入時計算，若同一 object 被原地改 policy，key 不會自己變；因此要釘 immutable snapshot 或重新載入，不是每query重hash全 catalog。跨request cache至少分tenant/access scope、profile/version/fingerprint、provenance root、retrieval/reranker/embedding設定與model revision；mapping結果另含raw request、extraction hash/version、prompt/schema/model/decoding設定。token cache另含tokenizer/template版本與實際序列化內容。可先只cache contract documents／index，別預先cache不確定性LLM判斷。cached mapping取出仍驗exact paths與allowlist；故障/negative/incomplete不長期cache。

CrossEncoder 已用一次 predict 處理多 pairs，而非一對一 HTTP；若啟用後調batch_size，先量測，參考 [Sentence Transformers 官方 CrossEncoder.predict](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)。vector索引重用後每query仍有query embedding，不能宣稱零embedding呼叫。

### 9. [P2] (confidence: 9/10) schema_mapping_workflow.py:126–138／:40：逐 View 分流沒有消除全域 context 瓶頸

證據：review 帶全部 mappings 與所有有候選 View 完整 policy；draft 仍帶全部 mappings、review及選定 View policy；response `context_tokens=max(...)` 只呈現峰值。_call:51 每階段各計數一次並檢查預算，已正確避免超限呼叫；observer:74–77 有原始usage，但 trace未彙總總token與tokenize耗時。

反例：每個 View 個別可放入，C個View合起來review仍超限；不能藉逐View就宣稱context問題已解。若HTTP token counter啟用，這條新workflow是每stage1次HTTP，不是ContextPacker的逐doc多次；目前Ollama只有設定 token_count_endpoint 才會走HTTP，否則tiktoken。

- **9A（agent 推薦，待採納）**：先量每stage serialized size、token-count/model elapsed及總usage；移除重複JSON／無候選mapping只留拒絕摘要，完整mapper契約保持不變，任何projection須用原契約驗證（human 約 5h／CC 約 1h，類型選擇不計 completeness）。
- 9B：所有階段只給命中欄位摘要（human 約 4h／CC 約 45min，容易丟time/grain/scope/usage與auxkeys，且違反原完整契約承諾，類型選擇不計 completeness）。
- 9C：context不夠就持續加大num_ctx（human 約 1h／CC 約 15min，VRAM／延遲增加且不能根治總量，類型選擇不計 completeness）。

偏好依據：先可觀測再最佳化。對 review/draft 的契約縮減是待使用者採納的後續優化，必須保留全 View scope/time/grain/usage/metrics、選定欄位、日期約束、必要join keys及反證；相同stage內容cache key不等於只用View name。tiktoken非Qwen精確token，安全reserve與真實usage差距需量測，不能直接用較快counter替換正確預算。若 review 仍過大，先明確fail或較小的可閉合來源集合；分層review會改動全域一致性，需另立eval。

### 10. [P3] (confidence: 8/10) schema_mapping_workflow.py:113／:64–67：序列 mapping 的並行效益尚未證實

證據：`for view in views` 同步 `llm.invoke(messages)`；全stage共用 `self.llm`，沒有per-stage路由。已確認部署設定為本機 Ollama qwen3.8:27b、lexical retrieval/reranker；未量VRAM、GPU比例或server parallel slots，不能假定GPU完全容納27B或workers=2就快兩倍。

- **10A（agent 推薦，待採納）**：先維持workers=1；測完整小樣本後才比較1／2，改善wall latency且無錯誤或記憶體惡化才啟用有界並行（human 約 3h／CC 約 45min＋真服務測試，類型選擇不計 completeness）。
- 10B：立即thread pool全候選並行（human 約 4h／CC 約 1h，可能只把串行工作排隊並增加KV記憶體及503，類型選擇不計 completeness）。
- 10C：立即拆小模型mapper＋大模型review（human 約 1–2 日／CC 約 3h，需路由／tokenizer／品質eval，單GPU可能來回換模型，類型選擇不計 completeness）。

偏好依據：boring by default。需要時採 Python 內建 [ThreadPoolExecutor(max_workers)](https://docs.python.org/3/library/concurrent.futures.html)，不加新佇列基建；worker不共寫trace，回收後依catalog序合併、每stage驗證、錯誤不得partial-ready。Ollama官方指出並行需要額外記憶體、忙碌可回503且新模型可能等待載入，參考 [Ollama FAQ concurrency](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests)。本次未操作server設定或測吞吐。

## 呼叫、成本與延遲模型

令 N 為 catalog View 數、R 為抽取的語意單位數、U 為合併去重後資料查詢群組數、G 為額外 gap queries、C₀ 為初始唯一候選、ΔCᵢ 為每次新增且尚未mapping的 View。

```text
Q = 1(raw) + U + G，且 Q <= Q_max
C = |union(initial/gap/pinned/relation Views)| <= N
K_LLM = 1(extract) + C + 1(review) + 1(draft) = C + 3
        前提：抽取不修補、每View只map一次、review只做一次、無retry、成功走完
K_LLM_with_reextract = E + sum(C_mapped_each_version) + V_reviews + D_drafts
K_tokenize_HTTP = K_attempted_stages（只有HTTP counter時；超限stage也先count）
T_serial = sum retrieval/query/rerank + sum token_count
           + T_extract + sum T_map + T_review + T_draft + T_validation
input_tokens_total = tokens_extract + sum tokens_map + tokens_review + tokens_draft
peak_context_tokens = max(each stage input tokens)  !=  total tokens
```

同一次 `SchemaRetriever` 的 vector store 是 lazy cached；若每query新instance，約為 Q 次document embedding/index初始化＋Q次query embedding；共用後約1次document初始化＋Q次query embedding，warm instance的document初始化為0。這是依程式路徑推導，不是已量實際HTTP batch數。lexical是每query掃描文件並排序，約 O(Q·N·D + Q·N log N)，D是文件處理成本；先重用已建文件，倒排索引是否需要由N與耗時決定。現有build_documents還會逐欄替換識別碼，實測規模前不宣稱它是最大瓶頸。

mapper每View必須回全部R需求，因此輸出至少 O(C·R)，即使候選欄位稀疏；全域review另接所有mapping與多份契約，不能只估算單View成本。候選call上限與tokens上限是不同限制。理想獨立資源workers=P的mapper下限約ceil(C/P)批，但單GPU服務可能排隊／offload，**不宣稱線性加速**。本機模型無可由API單價估算的真實貨幣成本，先以GPU時間、tokens、calls與記憶體報告。

**已量到的離線確定性結果：**

| 探針 | 結果 | 限制 |
|---|---|---|
| 100同分候選、soft limit=5 | 保留100 | 真正的既有select_with_ties函式 |
| 3 queries預設adapter | build_documents=3 | 臨時fixture、lexical、無外部服務 |
| 已建共享engine再查3次 | 追加build_documents=0 | 建構本身1次在計數前 |
| fake CrossEncoder啟用3queries | factory=3 | mock model；現行lexical部署不走這路 |
| 禁止條件誤標syntax | extraction validator errors=[] | 重現已知語意界線 |
| 真實否定引文 | evidence validator errors=[] | 真實性不等於語意支持 |
| focused suites | **173 passed in 10.33s** | 全為離線mock／fixture；不是服務延遲 |

focused命令：`.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py tests/unit/test_schema_mapping_review.py tests/unit/test_schema_mapping_decomposition.py tests/unit/test_schema_mapping_retrieval.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_task_decomposition_contract.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py`。

未重跑全套。主代理既有證據為773 passed／23既有failed／1skip，23個失敗ID與改前相同；本報告未獨立重驗該整套差集，不將其當新失敗。未測真實LLM／DB／embedding／reranker、P95、吞吐、VRAM或任何效能百分比。

## Failure modes 與使用者可見性

| 新路徑 | 真實失敗 | 目前測試／處理 | 採納後必要行為 |
|---|---|---|---|
| extract→query plan | 漏禁止詞、period未連sales | span／relations有檢查；語意須eval | global review/clarification，不可靠raw retrieval當語意修復 |
| query fanout／fusion | 重複query灌票，唯一sales來源被擠掉 | 新路徑GAP，尚未存在 | provenance＋每需求來源保護與gold-set eval |
| candidate allocation | ties或owner膨脹超預算 | ties測試已有；總預算GAP | 明示未完成、不出requests |
| gap loop | 同query反覆補查、無新View仍持續 | 新路徑GAP，尚未存在 | query簽章去重、無進展／預算早停 |
| 新View mapping | 時間來源有了但join key不相容 | 原validator檢查key；新closureGAP | 持續標gap或明確不能整合，不硬選欄位 |
| cache reuse | policy改動但fingerprint沒重載 | cache失效GAP | snapshot不可變／rebuild，重驗cached evidence |
| candidate provider failure | 503／invalid JSON被當unmatched | 原版有早停測試與error | 保留fail-closed；未來隔離不得partial-ready |
| global review | 同模型肯定了真實但反向證據 | 引文真實性有驗；語意eval GAP | 人工oracle、hard negatives、原文重新讀 |
| draft/prepare | 沒sales商品被inner丟掉、漏output grain | 已有回歸測試／拒絕 | 沿用allowlist／binding／母體限制 |
| optional concurrent mapping | 回應亂序、shared trace互相覆寫 | 新路徑未實作且無測試 | 先不啟用；採納才測界限／合併／停止 |

**Critical gaps：2項提案風險**，不是已部署新增silent bug：若沒有GAP狀態仍把未查全當unsupported，以及若融合策略靜默丟唯一需求來源，將造成看似成功的錯誤結論；需在新提案第一階段有測試、明確處理與可見trace。已知同模型語意共錯則是獨立驗收風險，不能靠這兩項結構修正宣稱消失。

## NOT in scope

- SQL生成／DB執行／真實資料查詢：本入口只規劃requests。
- 重寫舊TaskDecompositionService：保留原介面與一次LLM行為。
- 改現有已完成spec／plan／EDD紀錄：此報告為新提案審查。
- per-stage多模型、第三次LLM投票：需品質／載入成本證據，目前無必要。
- 持久向量DB、hybrid檢索預設啟用、完整欄位拒絕矩陣：已有方案與已知輸出成本，先證明實際缺口。
- 無界修補、候選錯誤後靜默繼續、retry外部服務：破壞閉合或增加不可控成本。
- 目前就改tokenizer／加大num_ctx／全候選並行：未有服務效能證據。
- 修全套既有23失敗、建立缺失私人Retail.env、commit/push/工具升級：不屬此次review授權。

## Implementation Tasks

以下為可採納後執行的平面任務，全部未執行。工時為粗估，不是承諾；repo未提供AI工時對照表。P1表示採納新流程前必要，不代表要求修掉已完成原版。

- [ ] **T1（P1，human約3h／CC約40min）** — workflow — 明確區分retrieval gap／budget／unsupported，沿用公開status、擴充code與trace。
  - 來源：finding 1；檔案：schema_mapping_workflow.py、mapping_models.py、test_schema_mapping_decomposition.py；驗證：G5／G6、必要來源缺失不得unsupported。
- [ ] **T2（P1，human約1日／CC約2h）** — retrieval — 將抽取移前，建立raw＋關聯需求查詢、來源provenance與coverage-aware融合。
  - 來源：finding 2；檔案：schema_mapping_workflow.py、mapping_retrieval.py、mapping_models.py、test_schema_mapping_retrieval.py；驗證：G3／G4＋原literal/qualified/ties測試。
- [ ] **T3（P1，human約1日／CC約2h）** — closure — 實作固定extraction版本的有界gap補查、query去重、unique mapping與完整閉合，保留原fail-closed。
  - 來源：finding 3／4／7；檔案：schema_mapping_workflow.py、mapping.py、mapping_models.py、test_schema_mapping_decomposition.py、test_schema_mapping_review.py；驗證：G6／G8／G9，provider故障／無進展／預算均不出requests。
- [ ] **T4（P1，human約1–2日／CC約2–4h）** — evaluation — 建新入口eval與人工gold來源集合／語意反例，不改舊runner預設行為。
  - 來源：finding 5／6；檔案：新增evaluations/schema_mapping_runner.py、evaluations/schema_mapping_cases.py、evaluations/schema_mapping_grading.py及對應專用tests；驗證：G1／G2，離線先驗runner統計與oracle，真實LLM須另按使用者預算執行。
- [ ] **T5（P2，human約3h／CC約40min）** — retrieval — 重用request engine；啟用CrossEncoder時保留model instance並測fingerprint／scope失效。
  - 來源：finding 8；檔案：mapping_retrieval.py、schema_mapping_workflow.py；條件式schema.py；test_schema_mapping_retrieval.py；驗證：G7，N queries只build一次，policy/profile/model改變不可誤用。
- [ ] **T6（P2，human約5h／CC約1h）** — observability — 記stage token_count/model elapsed、總usage、query/mapping budget與未比較集合，先量全域context。
  - 來源：finding 7／9；檔案：schema_mapping_workflow.py、application/models/schema_mapping_decomposition.py、專用tests／eval metadata；驗證：G10，max與sum分開，HTTP counter每stage一次，既有observer不洩敏感資訊。
- [ ] **T7（P3，human約3h／CC約45min＋服務測試）** — performance — 以固定eval比較workers=1／2與必要projection；只有品質無回歸且延遲／記憶體實測有益才提出啟用。
  - 來源：finding 9／10；檔案：獨立performance harness／test plan；若獲採納才改schema_mapping_workflow.py及其並行測試；驗證：G10及相同模型warm/cold/P95／失敗率，無服務時保持deferred。

T1→T2→T3同主模組應序列實作，T5可納入T2共用engine的小改動避免重複；T4測試標註可在介面固定後獨立進行，但runner整合仍等T1/T2。跨同一workflow與mapping目錄的產品變更不建議多worktree同時寫。**Sequential implementation, no parallelization opportunity** 適用第一階段程式修改；本次沒有啟動平行實作。

TODOS.md不存在且使用者限制不改TODOS；僅提出2個可選deferred項目供採納：T7（需要T4/T6基準，優點是可驗證延遲收益，代價是服務資源與並行維護）；extraction自動修補version loop（需T3/T4，優點恢復漏抽，代價重map全部來源／模型呼叫增加）。兩者上下文、依賴已在finding 4／10說明；不視為已新增專案待辦或已批准實作。

## 完成摘要與限制

- Step 0：已完成scope challenge；agent推薦縮成有界召回／正確狀態，待採納。
- Architecture：3項；Code Quality：2項；Tests：1項主要finding、10個GAP群組；Performance：4項。
- NOT in scope、What already exists、ASCII流程／測試圖、失敗模式、成本公式與平面tasks均已提供。
- Failure modes：2項新提案critical gaps；未證實任何新上線回歸。
- Outside voice：此獨立RAG subagent已執行；額外codex/claude challenge skipped，未假稱完成。
- Lake Score：4/4有coverage差異的主要finding（1、5、6、7）推薦完整選項；不同種類的選項不給假分數。
- focused：173 passed in 10.33s；離線計數與反例已執行；完整套件／真實模型／真實服務效能未重驗。
- review artifact與test plan為新增文件；未寫產品碼、未commit/push，所有10項finding的推薦均未獲使用者批准。
- 測試計畫：`docs/superpowers/reviews/2026-10-23-rag-mapping-test-plan.md`；QA本機副本：`~/.gstack/projects/willy50414z-cpea/willy-feat-complex_req_test-eng-review-test-plan-20261023-071911.md`。
- Skill JSONL：`~/.gstack/projects/willy50414z-cpea/tasks-eng-review-20261023-071911.jsonl`，7個tasks均由jq序列化且標記`proposed_pending_user_adoption`。
- `gstack-review-log`已成功執行，本機review-read確認1筆issues_open、5個待採納決策、2個critical gaps、同HEAD；metadata的19是3 architecture＋2 code quality＋4 performance＋10 test GAP群組，不重複加計test主要finding。同步設定off，沒有執行remote sync／telemetry。沒有使用者durable決策，不把agent建議寫成已採納decision。
- UTF-8無BOM、review report為最後章節及最後未解決事項行皆已核對；`git diff --check`通過。

```text
REVIEW READINESS DASHBOARD（本次提案）
Eng Review   | 1 run | 2026-10-23 07:19 UTC | issues_open (PLAN) | required
CEO/Design/DX/額外Outside Voice | 0 | skipped
VERDICT: NOT CLEARED；本次審查已完成，提案決策與驗證仍待採納
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---|---|---|
| CEO Review | 未執行 | 無新商業範圍 | 0 | skipped | 無 |
| Codex Review | 獨立RAG subagent | 使用者明確要求的outside review | 1 | DONE_WITH_CONCERNS | 本報告；非跨模型投票 |
| Eng Review | plan-eng-review | 架構、品質、測試、效能 | 1 | issues_open (PLAN) | 10項finding／10個GAP群組／2項critical gaps |
| Design Review | 未執行 | 無UI | 0 | skipped | 無 |
| DX Review | 未執行 | 本次限定工程審查 | 0 | skipped | 無 |

**VERDICT:** DONE_WITH_CONCERNS；工程審查完成，建議尚未採納，不能宣稱新流程 ready to implement 或已提升效能；eng review required（採納後更新計畫並驗證）。

**UNRESOLVED DECISIONS:**
- 是否採納第一階段縮範圍與retrieval_gap／budget錯誤碼，保留原版status／fail-closed。
- 是否採納原句＋關聯需求查詢、coverage-aware融合與有界gap補查，並依評估結果設定query／mapping／token／time預算。
- 是否採納固定extraction版本補來源，將漏詞自動修補留待獨立version-loop設計。
- 是否採納新流程專用人工oracle與真實模型eval，並指定後續服務測試預算。
- 是否採納request engine重用與可觀測性；CrossEncoder／vector cache、projection與workers=2維持條件式或延後。
