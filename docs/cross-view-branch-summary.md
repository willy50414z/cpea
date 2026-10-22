# feat/cross_view：目標、執行歷程與結果整理

整理日期：2026-10-22（Asia/Taipei）。本文件依目前分支程式、Task、checkpoint、實驗報告及獨立審核整理；歷史程式基準為 `bc09c67fc4078501599c37e4cdfecdee40af2ef8`，分支自 `e05db00` 的 `main` 分出。

**目前已建立跨 View 前置規劃服務及評估工具，但本機 Qwen 的完整自然三階段流程尚未通過。** 最新完成的第 24 輪為 FAIL；第 22–24 輪獨立方向審核已有 `REPLAN` 報告。這次提交保存目前程式、測試、研究候選與成功／失敗證據，不代表候選已通過正式驗收。

## 1. 分支要解決的問題

既有 SQL 生成流程一次只處理一個受治理 View。使用者提出「庫存對照指定月份線上銷售」「會員對照消費明細」等跨來源需求時，需要先決定資料分工，再把每份查詢交給單 View 流程。

本分支的規劃層負責：

1. 從自然語言需求辨識指標、條件、期間、粒度與必須保留的母體。
2. 在七個 Retail View 契約中選擇足夠且必要的來源。
3. 為每個來源建立獨立查詢任務，明列欄位角色、篩選、聚合、輸出粒度及相依關係。
4. 規劃來源間的對齊鍵、整合方向、子集合形狀及缺值政策，避免重複計算或刪除母體。
5. 驗證後產生可以交給單 View text-to-sql 的 `prepared_requests`。

本階段驗收終點是規劃及 request 準備；沒有實作跨 View SQL、執行 SQL、查詢資料庫、實際合併資料或計算採購量，也尚未把新入口自動串接既有網頁／SQL API。

相關文件：[原始設計規格](superpowers/specs/2026-10-20-retail-task-decomposition-design.md)、[執行計畫](superpowers/plans/2026-10-20-retail-task-decomposition.md)、[OpenSpec 提案](../openspec/changes/retail-task-decomposition/proposal.md)。

## 2. 已執行的項目與產物

| 項目 | 已有內容 | 目前界線／入口 |
|---|---|---|
| 跨來源題庫 | 30 題：28 題雙來源、2 題三來源，涵蓋七個 View | [題庫](../projects/retail/evaluations/task_decomposition_cases.jsonl)、[閱讀矩陣](../projects/retail/evaluations/task_decomposition_matrix.md)；自動結構與人工語意核准分開 |
| 型別化規劃契約 | 狀態、任務、欄位角色、filters、grain、integration、prepared request | [資料模型](../src/cpea/application/models/decomposition.py)；只有 ready 可提供 payload |
| 獨立規劃入口 | `load_contracts → plan_tasks → validate_plan → prepare_requests` | [Workflow](../src/cpea/workflows/task_decomposition/workflow.py)、[Service](../src/cpea/application/services/task_decomposition.py)；此版本只有 plan_tasks 呼叫 LLM |
| 驗證與護欄 | 欄位合法性、角色互斥、聚合、粒度、依賴、整合鍵、母體及時間 metadata | [驗證器](../src/cpea/workflows/task_decomposition/validation.py)、[prompt](../src/cpea/workflows/task_decomposition/prompt.py) |
| Benchmark 與重播 | 獨立 `cpea-plan-eval`、逐題評分、重複性統計、版本指紋及離線重評 | [使用方式](../evaluations/README.md)、[runner](../evaluations/decomposition_runner.py)、[grader](../evaluations/decomposition_grading.py)、[報告工具](../evaluations/decomposition_reports.py) |
| 診斷輸出 | 模型自填公開決策摘要、六類決策與依據；不宣稱取得私有思維鏈 | [decision summary 比較](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/decision-summary-comparison.md)、[decision chain 比較](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/decision-chain-comparison.md) |
| 三階段研究原型 | Recall、逐 View Coverage、Selection；保存 raw、驗證錯誤、usage、版本及重播 | [三階段設計](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/three-stage-view-selection-plan.md)、[基礎契約](../evaluations/three_stage_view_selection.py)、[受控 runner](../evaluations/managed_three_stage_runner.py) |
| Coverage 候選與隔離工具 | 固定需求槽位、來源事實綁定、own responsibility、kind mapping、責任卡與文字證據路徑候選 | [診斷模組](../evaluations/diagnostics/)、[診斷測試](../tests/diagnostics/)；各版本保留，不能以新版本回寫舊失敗 |
| 證據整理 | 契約盤點、完整證據表、精選閱讀包及架構候選比較 | [證據總表](task-decomposition-evidence-review.md)、[精選包](task-decomposition-review-selected/README.md)、[架構評估](next_enhance_advice.md) |

原產品 planner 的 v3 預設保留；多階段 runner 與各種 prompt／wire 候選主要位於 evaluation 範圍。分支原有 12 個 commits 已建立入口、測試與初期修正；這次一併保存其後的研究工作樹內容。

## 3. 執行歷程：嘗試、結果與決策

### 3.1 建立單次規劃 baseline，先修正可定位的契約問題

初期以 Azure `gpt-6-sol` 對 30 題各跑三次，共 90 次真實規劃呼叫。View 命中為 90/90，但欄位覆蓋 79/90、request 就緒 88/90、完整自動結構僅 60/90。

調查定位到快照日期「可保留」與題庫「必須保留」不一致、額外名稱／日期分裂粒度，以及 grader 的來源鍵等價處理不一致。後續增加 `metadata_collections`、收緊粒度與整合驗證，並以獨立審查修正通路條件及條件計數的 oracle。

候選 v2 的固定 16 題先通過；擴測完成 23 題次後，發現「各通路」被限縮成契約例值，停止並保留結果。v3 明示例值不是封閉全集；全通路／指定雙通路六次控制通過。中止時結果未知的 in-flight 呼叫另列，沒有混成完整輪次。

證據：[初始 benchmark](../evidence-driven-dev/tasks/retail-task-decomposition/reports/benchmark-results.md)、[失敗調查](../evidence-driven-dev/tasks/retail-task-decomposition/reports/failure-investigation.md)、[修正與驗證](../evidence-driven-dev/tasks/retail-task-decomposition/reports/fix-results.md)。

### 3.2 同一 v3 題庫下比較三個模型

以下各取一個完整 30 題輪次；GPT 的第二輪 17 筆部分結果沒有混入。這些是**原始自動分數**，不是完整業務語意正確率。

| 指標 | Azure gpt-6-sol | Azure DeepSeek-V4.1-Flash | Ollama qwen3.8:27b |
|---|---:|---:|---:|
| 完成案例 | 30/30 | 30/30 | 30/30 |
| 主要 View 任務配置 | 30/30 | 27/30 | 29/30 |
| 來源與必要欄位原分 | 30/30 | 26/30 | 21/30 |
| Request 結構就緒 | 30/30 | 22/30 | 11/30 |
| 完整結構自動通過 | 30/30 | 18/30 | 7/30 |

核心題目、prompt、schema 與契約相同，但 Azure／Ollama 的輸出約束與部分生成設定不同；不能視為完全受控的模型排名。Qwen 本輪約 3.15 小時；欄位原分中另有四個已確認漏判，21/30 不代表 21 題欄位契約完整。

後續獨立語意分類把 DeepSeek 歷史 30 筆分成 18 題安全完整、9 題真語意錯、3 題機械錯。自動分數也是 18/30，只是數字相同：自動未過者有合法等價，自動 ready 者亦有不安全結果。

證據：[三模型比較與限制](../evidence-driven-dev/tasks/retail-task-decomposition/reports/ollama-results.md)、[DeepSeek 逐題獨立語意審核](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/oracle-audit/baseline-semantic-review.md)。

### 3.3 增加 prompt 檢查與切分模型階段，沒有得到穩定改善

| 嘗試 | 比較方式 | 觀測結果 | 處置 |
|---|---|---|---|
| 通用檢查步驟／三階段拆分 | DeepSeek 十題：原版 A、單次加檢查 B、分階段 C | 自動結構 A 7/10、B 2/10、C 2/10；C 用 37 calls，A 用 10 calls，且成功控制退步 | 不直接導入該原型；不能推論所有分階段方法無效 |
| 全量能力呈現與重寫 prompt v4／v5 | 先修欄位層級錯誤，再做完整成對比較 | v4 中止；v5 欄位 23→27，但 ready 21→15、結構 16→9 | 撤回產品變更，保留原型及失敗 |
| 較小 prompt 調整 v6 | 同批 30 題，v3／v6 各一次 | 欄位 25→26、ready 18→16、結構 15→16 | 未達「各指標不下降」門檻，恢復 v3 |
| A：確定性欄位閉包 | 重播 DeepSeek 原 30 筆 | 安全新增 ready 為 0；不能把不存在的 order_count 自動改成 order_id | 保留為護欄，不當主要解法 |
| B1：語意骨架＋編譯器 | 固定六題，fresh v3／B1 各一次 | 獨立語意安全 ready 都是 2/6；B1 不安全 ready 為 0，但安全淨增也是 0 | 未達升級門檻，不擴十題或完整 Gate |

三階段 C 的 tokens 約為 A 的 2.06 倍；更多呼叫沒有自動消除來源能力、欄位角色與粒度錯誤，還會把前段錯誤固定傳到後段。部分自動失分屬等價表示限制，報告保留原分與語意分析，沒有為候選改答案。

證據：[十題三 arm 結果](../evidence-driven-dev/tasks/retail-planning-stages/reports/results.md)、[v4–v6 prompt 比較](../evidence-driven-dev/tasks/retail-planning-stages/reports/prompt-view-matching-results.md)、[MVP0／B1 結果](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/execution-results.md)、[B1 獨立逐題審核](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/oracle-audit/mvp1-semantic-review.md)。

### 3.4 公開決策紀錄與第二模型審查，幫助定位但未讓生成通過

針對第 11 題，模型會選擇沒有通路欄位的商品月表，卻宣稱完成 online 篩選。增加決策摘要、六類決策依據、事後來源能力自評，以及「完整需求覆蓋優先」仍未讓該題通過。

改用 Markdown 高優先規則後，規劃器反而在月表加入不存在的 `sales_channel`。第二個獨立對話的 DeepSeek 能抓到核心缺證據問題並 reject，但部分附加 findings 沒有充分依據。因此分開記為「規劃 FAIL、審查 PASS_WITH_WARNINGS」，沒有把審查拒絕當作生成成功，也沒有自動修答。

證據：[覆蓋優先成對測試](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/coverage-priority-comparison.md)、[Markdown 與證據審查](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/markdown-evidence-review.md)、[來源選擇追問](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/source-selection-reasons.md)。

### 3.5 改為 Recall → Coverage → Selection，逐步移除表示負擔

新的 evaluation 原型將責任拆為：

```mermaid
flowchart LR
    R[自然語言與七個 View 契約] --> A[Recall：需求／角色／scope／粒度]
    A --> B[Coverage：每個 View 逐項能力與證據]
    B --> C[Selection：來源分工與 typed 整合計畫]
    C --> V[程式驗證母體／粒度／條件／缺值]
    V --> P[Prepared requests]
```

Python 負責原文裁切、契約引用、固定身分、來源事實與可證明的重複結構；模型仍負責業務映射、需求關聯、來源能力及整合選擇。不能從 oracle 補答案，也不能把多個不完整來源直接拼成未證明的完整能力。

早期 DeepSeek 三階段實測先遇到 `/grain/keys/0` 被程式誤拒；修正後重用相同 raw，續接在 inventory 的「路徑指向陣列、引文卻是字串」失敗，沒有完成最終選擇。這裡同時存在 validator 缺陷與模型引用錯誤，需分開歸因。

後續改為模型只輸出需求索引、Python 裁切原文；再讓 Coverage 只輸出契約路徑，由程式取引文與欄位描述。這能減少抄寫錯誤，但仍出現業務目的被當成有資料映射的 supported 需求。

Qwen 在 4096 output tokens 下曾被截斷；只解除時間限制仍未完成 JSON。EXP-019 同時解除輸出及 timeout 配額後，單次約 620.1 秒、輸出 4618 tokens，七組主要目標詞 7/7 精確完整，scope／角色核對符合本題要求。這只證明單題 Recall；隨後第二步 inventory 仍因證據契約失敗停止，完整三階段尚未成立。

證據：[三階段初次結果](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/three-stage-view-selection-results.md)、[索引式 Recall](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/indexed-recall-results.md)、[Qwen 解除上限結果](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/qwen-indexed-recall-uncapped-results.md)、[Qwen 第二步結果](../evidence-driven-dev/tasks/ollama-planning-mvp/reports/qwen-stage-two-results.md)。

## 4. 本機 Qwen EDD loop：24 輪的進展與失敗

使用者後續授權只用本機 `qwen3.8:27b` 持續研究，每三輪獨立方向審核；沒有雲端呼叫。舊的 DeepSeek／Ollama 完整 Gate 保留，這項局部研究授權不等於 Gate 已通過。

### 4.1 各輪嘗試與結果

| 輪次 | 解法／實驗 | 結果及可證範圍 |
|---|---|---|
| 1–2 | 背景角色修正、受控 runner，再跑自然三階段 | 離線契約 PASS；自然流程 FAIL，Coverage 出現重複需求 ID |
| 3–4 | 固定需求槽位，來源 view／grain／keys／population 由契約綁定 | 離線 PASS；自然流程仍 FAIL，另暴露來源理由、過度支持與 typed 欄位遺漏 |
| 5–6 | evidence-bound 契約，明列需求／粒度關係及證據來源 | 離線 PASS；自然流程 FAIL，語意責任問題仍在 |
| 7–8 | 區別 own gap 與依賴 scope／grain 缺口 | 離線 PASS；自然流程仍 FAIL |
| 9–10 | kind mapping 與 Coverage／Selection 隔離 harness | 離線 PASS；建立固定輸入與 oracle，準備分辨錯誤來自哪一階段 |
| 11–14 | 獨立審查發現會員金額 partial oracle 不當；修正 fixture、重新綁定不可變證據，再獨立審核 | 第 11 輪 FAIL；12、13、14 輪 PASS。修正與原拒絕都保留，不能讓作者自審 |
| 15–19 | Selection 隔離、缺值政策及 flat／nest 形狀核對 | 15 FAIL；16–17 離線與獨立審核 PASS；18 自然 Selection PASS；19 父層隔離整合 PASS。上游 Recall／Coverage 為固定注入，非完整自然成功 |
| 20 | 三個 Coverage 隔離樣本 | FAIL／PASS／FAIL：遺漏有用的店鍵、own gap 誤判；另有同月份冗餘 AND 被 checker 過度限制 |
| 21–22 | capability projection 責任卡、有限 AND 等價；離線及獨立語意審核 | 兩輪 PASS；只證明候選／測試契約合理，尚未證自然模型效果 |
| 23 | 五個固定 Coverage 自然樣本 | FAIL／PASS／FAIL／FAIL／FAIL：四個引用指到物件，另有會員累計金額 partial 遺漏、庫存母體複合鍵及證據不足 |
| 24 | A1：契約證據限定非空文字 leaf enum／null，預建 9 案、65 rows、27 seed 格 | FAIL：focused 65 passed／1 failed；相關回歸 133 passed／16 failed。新候選 frozen replay、fresh review 與自然面板未完成 |

第 24 輪的失敗包括：新 `same_platform` 負例實際仍是不同平台，卻預期拒絕；既有測試把真實已 closed 的 21／22 輪再加入 synthetic completed 紀錄，觸發重複完成守門。這些需修正測試生命週期與新版本 provenance；不能把原第 24 輪 FAIL 改成 PASS，或削弱守門後直接跑候選。

核心證據：[24 輪暫停統計](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-pause-24/statistics.json)、[第 20 輪 handoff](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-coverage-isolation/handoff.json)、[第 23 輪 handoff](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-capability-natural/handoff.json)、[第 24 輪 handoff](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-text-leaf-contract/handoff.json)。

### 4.2 用量與完成程度

以下僅計 EDD loop，不含啟動前的 Azure／Ollama 歷史實驗；測試重跑沒有累加成獨立測試數。

| 指標 | 第 24 輪結束時 |
|---|---:|
| 已結算輪次 | 24：15 PASS、9 FAIL |
| 本機模型呼叫／重試／雲端呼叫 | 31／0／0 |
| 呼叫階段 | Recall 4、Coverage 24、Selection 3 |
| Input／Output tokens | 138,589／111,241 |
| Token 總量 | 249,830；不含 agent 平台自身推理用量 |
| 迴圈牆鐘時間 | 約 11 小時 41 分鐘 |
| Ollama 回報累計推理時間 | 約 5 小時 32 分鐘 |
| 完整自然流程嘗試／成功 | 4／0 |
| Root 驗收／歷史兩輪各 38 題 Gate | 尚未通過 |

暫停統計當時為 42 次 agent 派遣、7 次已登記方向審核。現行 Task 的派遣數為 43，且另有第 22–24 輪審核檔案；不能把較早統計當作最新控制狀態。

## 5. 遇到的主要困難與目前理解

| 困難 | 具體證據 | 已嘗試／尚未解決 |
|---|---|---|
| 找到來源不代表完整覆蓋 | 商品月表有金額卻沒有通路；daily 有店鍵與淨額但無商品／online | 已加逐需求 Coverage；模型仍會遺漏有用 partial，或誤把依賴缺口當自身缺口 |
| 條件不能跨錯來源 | 銷售月份與 online 只應限定銷售，不能刪庫存母體 | 已有 scope、同來源條件與整合 guards；自然語意穩定性未過 |
| 粒度與母體容易被破壞 | 額外日期／分類分裂根粒度；inner join 或先篩缺貨刪除應保留列 | 增加 typed preparation、anchor、left／nest 與缺值驗證；只有隔離 Selection 已通過 |
| 模型重複填可推導資訊 | ID 重複、路徑與引文型別不合、證據指到物件 | 固定槽位、Python 裁切／取引文、責任卡、文字 leaf 候選；最新候選仍有離線前置失敗 |
| Oracle 同時有漏判與誤拒 | 自動 ready 可漏業務責任；合法日期／FD／冗餘 AND 表示可能失分 | 保留原分，另作版本化 sidecar、合成見證與獨立語意審核，沒有事後放寬答案 |
| 契約尚有業務不確定性 | sales_detail 的 `(order_id, product_id)` 與人工審核的明細唯一性矛盾 | 不據該鍵推導 FD、raw 唯一性或 COUNT 等價；技術准入不等於正式業務認證 |
| 本機推論成本與輸出完整性 | 4096 tokens 截斷、單次 Selection 可超過半小時 | 解除研究用輸出／timeout 配額並保留 context 限制；較久等待不能解決語意錯誤 |
| 證據與授權生命週期複雜 | 原作者／審者、closed ticket、manifest hash、frozen replay 彼此綁定 | 有 provenance 與完整性守門；新版本需有真實新來源，不可改舊票據洗成通過 |

目前證據支持「表示負擔」及「Coverage 責任分類」都是問題，但不足以把所有失敗歸因於模型同時負擔太多責任，也不足以支持直接全面重建 Semantic Layer。

`partial` 目前保留有用能力及缺口供診斷與排除理由使用；最終 assignment 仍要求 supported，尚無把多個 partial 自動合成可執行 supported 的規劃器。契約現有欄位語意、粒度與聚合限制，但跨 View 關聯／基數、一般 FD、指標公式及時間可加性尚未形成完整機器可讀系統。

進一步說明：[契約人工審核](../projects/retail/contract_review.md)、[精選包的 partial 說明](task-decomposition-review-selected/README.md)、[架構候選 A／B／C](next_enhance_advice.md)。後兩份是較早研究快照，須與第 23／24 輪原始結果並讀。

## 6. 最新狀態、文件落差與後續工作

### 6.1 Task 與審核檔案的狀態落差

[主 Task](../evidence-driven-dev/tasks/ollama-planning-mvp/task.md) 為 `PLANNING`，checkpoint 仍寫「第 24 輪 FAIL，下一步委派獨立方向審核」；loop 內最後登記審核仍為第 21 輪。

但磁碟已有[第 22–24 輪 review](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-22-24/review.json) 與[最終核對](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-22-24/final-verification.json)，結論為 **REPLAN**。該審核核對 1,233 筆輪證據 hash、五份 raw 的 33 列，保留 22 PASS、23 FAIL、24 FAIL。final-verification 的 PASS 指審核證據完整，不是候選或 root 通過。

因此不能再說「完全沒有審核」，也不能假設 controller 已完成接納；本次僅記錄落差，不修改歷史 Task 或自動續跑。Task 尾端完成摘要仍停在較早的 Recall 5/7，證據總表也是第 21 輪快照；最新判讀應以本節與相應 handoff／review 並讀。

### 6.2 已記錄但尚未完成的前後比較

Task 保存了使用者後續要求：「修正前、後各跑同一套原始 30 題，各一次」。現有審核要求先固定以下前置，尚無完成的 60 個案例結果可報告：

1. 還原真正 loop 前的可執行 baseline；只有 hash 不代表完整 bytes 已可重現，不能用 DeepSeek 歷史分數或第 20 輪代替修正前 Qwen。
2. 確定修正後 arm：已核准的 capability 候選或仍失敗的 text-leaf delta，必須說清楚版本、合法入口、provenance、freeze 與必要測試。
3. 在看到新回答前，固定共用完整 30 題語意 oracle、容許等價與獨立評分方式。
4. 固定模型 digest、生成設定、契約／題庫與執行順序；兩個 arm 各題只取首次結果，不修答重抽。
5. 每題首錯保存後接下一個獨立案例；60 指案例結果，不是總 HTTP 呼叫數。未執行者另列，不能充作已跑 FAIL。
6. 完成後列成對改善／退步、失敗類型、calls、tokens 及耗時，再停止本次有限比較。

詳細裁決：[方向審核與下一步研究問題](../evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-22-24/direction-findings.json)。本次文件整理與提交沒有啟動此比較，也沒有恢復無限改善。

### 6.3 仍未完成的正式驗收

- 最新候選的必要測試、完整 frozen replay、fresh 獨立語意核准。
- 自然 Recall、全部七個 View Coverage、自然 Selection、typed Integration 與 prepared requests 的完整成功。
- Coverage 父層、所有祖先整合與 fresh final verifier 的 root ACCEPT。
- 歷史規劃中的固定版本兩輪各 38/38 完整首次語意驗收；未因單題或隔離 PASS 而解除。
- 真正 SQL 生成／執行、資料結果整合與業務決策驗證；這些仍在本階段範圍之外。

## 7. 本次整理與提交的驗證紀錄

本次重新核對 Git、Task、checkpoint、暫停統計、主要報告與審核；沒有新增模型／SQL／DB 呼叫。

本次以 `.venv/bin/python -m pytest -q` 執行 21 個規劃相關單元／整合測試檔及 `tests/diagnostics`，使用 `--tb=short`：**826 passed、79 failed，耗時 996.40 秒（16 分 36 秒），exit code 1**。這是目前工作樹的相關測試，不是全專案完整回歸。

| 失敗測試檔 | 數量 | 實際錯誤／限制 |
|---|---:|---|
| [test_managed_node_diagnostics_v2.py](../tests/diagnostics/test_managed_node_diagnostics_v2.py) | 62 | `ValueError: fixed v2 diagnostic design/lineage differs`；在診斷套件載入／lineage 守門被拒，尚未逐項驗證後續行為 |
| [test_managed_capability_projection.py](../tests/diagnostics/test_managed_capability_projection.py) | 16 | `ValueError: capability review lacks closed provenance`；與前述真實 closed 輪次及測試生命週期問題並讀 |
| [test_managed_text_leaf_evidence.py](../tests/diagnostics/test_managed_text_leaf_evidence.py) | 1 | `reviewer-same_platform` 預期拒絕但沒有拋出 ValueError；對應第 24 輪已記錄的負例設定問題 |

這次沒有修改上述程式、測試、fixture 或歷史結果來取得通過；依使用者要求，將目前未通過的研究狀態一併保存。

文件與證據檢查：

- 本文件相對連結均確認存在且不被 Git 忽略，UTF-8 無 BOM。
- 暫停統計、第 24 輪 handoff，以及第 22–24 輪審核的兩份 proof hash，均與既有登記一致。
- 待提交內容已作憑證樣式掃描，並比對本機 `.env` 的三個有效長憑證值，未發現這些值外洩；樣式命中經核對為既有合成測試字串、耗時／用量數字及證據識別碼。新摘要的掃描無命中。
- 本文件及兩個既有修改的產品原碼通過 `git diff --cached --check`。整批快照檢查未通過：31 份既有歷史 `.log` 有 1,450 筆空白格式問題；全部位於證據或 review-bundle，為保留原始內容及 hash，沒有改寫這些 log。

既有驗證紀錄需按版本閱讀：產品 v3 曾有 391 passed／1 skipped；三階段原型曾有 135 passed；它們都不是目前全部工作樹的最新結果。第 24 輪已有測試失敗，本次會保留證據及候選狀態，不以歷史通過數替代現況。

`.env`、原本受 Git 忽略的 `.local/` 與私有 artifacts 不強制加入提交。既有 review-bundle 中另有整理好的 `.local` 快照副本，屬未被忽略的檔案，依此次「所有分支變更一起提交」納入並檢查。部分 handoff／manifest 仍引用未收錄的本機 raw、絕對路徑或外部工具；Git 中的凍結程式與摘要不保證足以在另一台機器完整重播。這些引用是歷史證據，不是可攜式執行環境的承諾。
