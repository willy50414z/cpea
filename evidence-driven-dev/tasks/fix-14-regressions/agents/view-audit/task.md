---
{
  "parent_task": "fix-14-regressions",
  "agent_id": "view-audit",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "唯讀診斷兩題 needs_clarification 是否是真實歧義或候選誤接受，以契約與原始 Replay 區分；不改產品程式或 Oracle",
  "allowed_scope": [
    "src/cpea/workflows/text_to_sql",
    "projects/retail/views",
    "tests"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/view_audit",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "已確認 SALES_DETAIL 三次不相容 order_no/SKU 來源因只驗 missing semantic subset 被放行，造成假 View 歧義；離線 Replay 與消融三次重現並分離因果。DAILY 原始候選均 COUNT 漂移，不足認定真需求歧義，須先修正聚合再驗。",
    "evidence": [
      "agents/view-audit/task.md",
      ".local/view-replay.py",
      ".local/view-replay-output.json",
      "projects/retail/artifacts/evaluations/20261019T115951Z-qwen-v10-samples14-stability3/results.jsonl",
      "projects/retail/artifacts/evaluations/20261019T115951Z-qwen-v10-samples14-stability3/calls.jsonl"
    ],
    "tests": [
      {
        "command": ".venv/bin/python evidence-driven-dev/tasks/fix-14-regressions/.local/view-replay.py",
        "exit_code": 0,
        "result": "兩題各三次原始 match/resolve/compare Replay 均 needs_clarification；僅消融明示不相容來源後 SALES_DETAIL 三次自然選定，DAILY 不變。"
      },
      {
        "command": "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/test_clarification_workflow.py tests/unit/test_business_clarification.py tests/unit/test_semantic_resolution.py",
        "exit_code": 0,
        "result": "32 passed in 7.05s"
      }
    ],
    "risks": [
      "未修改產品、測試或 Oracle；本次是 match 單節點 Replay，候選只保留原始成功集合並放大 context budget，非完整 retrieval 或端到端驗收。",
      "真 field refinement 與不相容來源必須分開；不能 blanket 丟棄 needs_refinement 或放寬 compare guard。",
      "DAILY 修正 aggregation 後仍需核對完整候選語意；目前不能宣稱真歧義或強選 Oracle。",
      "未呼叫真實 LLM 或 DB；模型穩定性未驗證。"
    ],
    "next_step": "Main 實作 required term 全量 preflight：明示不相容來源不能 successful；保留合法 field refinement。加入多來源負面與真 view ambiguity holdout；generic aggregation 修正後再驗 DAILY。",
    "blockers": []
  },
  "blockers": [],
  "question": null
}
---
# View 候選調查

## 任務與界線

以原始 42 筆評估中的兩題、六次 repetition 為證據，檢查是否是真實需求歧義。產品、測試與 Oracle 均未修改；未呼叫真實 LLM 或 DB。父 Task 與 decisions 已讀。實際使用 `.agents/skills/edd-investigate/SKILL.md`，並確認且讀取已安裝的 Superpowers systematic-debugging。

Base SHA：`014cee1aff3abcfb51bbe5af6db0abd2ef060225`。目前 HEAD 相同；啟動已有多項使用者未提交變更，包含 SQL dialect 編譯調整，本次未動。

## 觀察與第一個契約偏差

### SALES_DETAIL：已確認不相容來源被算作 fully matched

原始 `RETAIL-SALES_DETAIL-M3-01` 三次完全同型：

- `v_sales_detail` 與 `v_order_summary` 均進入 successful。
- `v_order_summary` 草稿把「商品庫存代碼 LIKE SKU-%」映成 `order_no LIKE SKU-%`。此欄契約明寫「訂單編號」，而來源契約沒有 SKU 欄。原草稿甚至對「商品庫存代碼」給 `same_concept=false`、`needs_refinement=true`，已提供明確否定證據。
- `clarification.requires_resolution()` 遇 `needs_refinement` 直接回 false；`semantic_choices()` 卻為空。這不是缺 metadata 修補，而是已明示沒有相容選項。
- `_match_candidates()` 只將 `requires_resolution=true` 的 uses 送 `_resolve_clarifications()`；該次 resolution 只包含其他五個 terms，`source_compatible=true` 並未確認 SKU。
- 其後直接 `successful.append()`，沒有對全部必要 terms 再檢查有效 semantic choices。故不相容的 order source 汙染 cross-view compare。
- 原始比較模型三次都選對 sales_detail，理由為「這行商品賣了幾件的單列最大值」對「本筆明細銷售件數」。伺服器要求 request evidence 必須逐字出現在契約；同義表達未達此門檻，因此退回 clarification。這是保守 guard 發揮作用，不能以放寬 guard 掩蓋上游誤接受。

程式追蹤：`sql_generation.py` 約 520–569（semantic preflight / successful append）、628–709（cross-view compare）；`clarification.py` 19–32、61–99；後續 `_assess_semantics()` 725–780 與 `_make_clarification()` 943–983 其實會處理空 choices，但發生於跨來源選擇之後，無法救回已先送出的 view clarification。

### DAILY：原始 clarification 尚不能證明真需求歧義

`RETAIL-DAILY_SALES-M2-01` 三次皆有兩個 admitted candidates：daily 與 order。原題要求「成交訂單數的單列最大值」，但兩個草稿皆將 fields text 截成「成交訂單數」、aggregation=`count`，分別選 `order_count` 與 `order_id`。

原始 resolution 所收到的 required term 反而完整包含「單列最大值」，卻仍把這個完整要求宣告為 count recipe 的 same concept。`v_daily_sales.order_count` 契約是每門市日期列的已完成訂單筆數；`v_order_summary.order_id` 是每列唯一識別碼。`COUNT(order_count)` 是計算資料列，`MAX(order_id)` 是最大識別碼，均不是原題的最大單列訂單數。

因此當下 compare 所比較的兩個方案都沒有保留原始聚合要求。即使 compare 提問合理指出「每日總毛利 >=100」和「單筆訂單毛利 >=100」差異，也不足以證明「兩個完全符合原題的方案」存在。Main 應先修正 generic aggregation hard guard、允許正常 repair，再核對 daily MAX(order_count) 與 order 的實際能力。以現有單層 QueryPlan 來看，order 來源沒有 stored per-row order count，不能把 COUNT(identifier) 或 MAX(identifier) 當作可替代方案。

原題的 WHERE 粒度確有潛在語意差異；若拿掉最大單列訂單數要求，daily/order 的篩選先後差異可能需要真 clarification。不能因此將原始錯誤草稿直接認定為真歧義，也不能為了 Oracle 強選 daily。這一點仍需 Main 在正確映射後驗證。

## 可否證假設

- H-V1 CONFIRMED：候選只有必要詞彙的一部分通過 resolution，就被當整題語意有效，會讓明示不相容來源參與 compare。否證條件：原始草稿回放時 order source 已被排除；實驗觀察相反。
- H-V2 CONFIRMED：SALES_DETAIL 不需放寬 compare guard；排除已明示 incompatible 的來源後，只剩 sales_detail 可自然選定。否證條件：排除 order 後仍需 view clarification；實驗三次皆自然選定。
- H-V3 UNCONFIRMED：修正 DAILY 聚合後仍有兩個完整符合原始 request 的單層計畫。原始 candidates 都 count，不能支持；本次未修改產品或生成修正後模型輸出，因此沒有宣稱否定其所有可能性。

## 離線最小實驗

檔案：`.local/view-replay.py`、`.local/view-replay-output.json`。

命令：`.venv/bin/python evidence-driven-dev/tasks/fix-14-regressions/.local/view-replay.py`，退出碼 0。

直接執行真實 `_match_candidates()`；`_invoke_model` 替換成原始 `calls.jsonl` 回應的 Pydantic 驗證，沒有網路能力或 DB executor。候選集合只含原 trace 中已達 candidate 的來源，context window 提高至 100000 以排除 budget 變因，因此這是 match / semantic / compare 邊界 Replay，非 retrieval 或完整端到端驗收。

| 模式 | DAILY 3 次 | SALES_DETAIL 3 次 |
| --- | --- | --- |
| 原始候選與 calls | 3/3 needs_clarification | 3/3 needs_clarification，含錯誤 order source |
| 只消融明示所有選項不相容的來源 | 3/3 needs_clarification，沒有來源被消融 | 3/3 自然選定 sales_detail，不呼叫 compare |

每次 SALES_DETAIL 原始 Replay 另 assert/記錄：SKU `requires_resolution=false`，但 `semantic_choices=[]`。這證明「不用修補 metadata」不等於「source 完整有效」。消融條件只取原草稿已有的否定 flags，不讀 case ID、預期 View 或 Oracle，且未作為正式修正。

## 最小安全修正與選項

S（建議優先）：在加入 fully successful 之前，覆蓋全部 uncertain required terms；不能只檢查 missing subset。已有 proposal 明示所有 options 都 `same_concept=false`／`grain_compatible=false` 者，作 semantic-source rejection 並繼續其他來源，不能以 `needs_refinement=true` 或其他 subset 的 `source_compatible=true` 洗掉否定證據。空 options 也不能被算作已驗證候選。

必須保留不同狀態：

1. 缺失／格式不合的 metadata：既有一次 resolution repair。
2. 明示無同概念／無相容粒度：排除此來源，繼續其他候選。
3. 真正的 field ambiguity／超過三個相關選項：保留 clarification_rephrase／field refinement 通道，不能直接視為不相容而靜默丟棄，更不能列為「已通過全題驗證」的 view 候選。

M：將候選語意狀態顯式分為 fully_valid、field_pending、incompatible；先篩選來源，再產生適當的 business confirmation。能清楚避免單一 source unresolved 與多 source ambiguity 混淆，但改動大於 S。

L：為契約引入正式 metric lineage 與 grain compatibility，長期改善 count recipe vs stored count；不適合本次最小修正，也不應加 Retail 專屬 keywords。

不要放寬 compare 的逐字唯一證據 gate；不要禁止所有 `MAX(identifier)`（使用者明確要最大編號時合法）；不要以 case ID、題目原句、預期 source 或 retrieval 排名強選。

## 負面與 Holdout 測試建議

- 原始 SALES_DETAIL 三次 calls 離線回放；order_no 不能承接 SKU，即使其他 required subset 的 resolution 宣告 source_compatible=true，該來源仍不得進 compare。驗證 candidate_attempt 的 rejected 原因，避免只驗最終選對。
- 改寫合成 profile：來源 A 的必要篩選詞只有 incompatible proposal，來源 B 完整可承接；更換 View／欄名、排序、候選順序，仍只保留 B。不要使用 Retail 題 ID。
- 沒有任何完整來源時，返回 unsupported/refinement，無 SQL、無 DB 呼叫、無無效 view options；需要維持既有單來源 clarification_rephrase 契約。
- unrelated term 的 source_compatible=true 不能蓋過 unresolved 必要 term；空 options、負 flags、invalid evidence、單詞缺失各自覆蓋。
- legitimate >3 related choices 的 needs_refinement=true 仍要求重述，不可隨意裁前三個、強選另一來源或列為 fully successful。
- 真多 View ambiguity holdout：同一句「逐筆銷售金額」對 order/detail 兩者都有完整 valid choices，仍 needs_clarification；維持 `test_comparison_cannot_select_using_a_shared_ambiguous_term`。
- DAILY：COUNT 草稿不得通過 max 原題；正確 MAX(stored count) 可過；MAX(identifier) 不得以「訂單數」語意通過；明確「最大訂單識別碼」仍可過。
- 真 daily/order grain ambiguity：去掉 stored-count MAX、只問收入合計與毛利門檻，需確認條件是單筆／門市每日，不能因字面「每日」就消除 row-filter 差異。
- 所有比較 guard：不在 request 的 request_evidence、兩候選共享 evidence、contract evidence 捏造，仍不可強選。

## 已執行既有回歸

`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/test_clarification_workflow.py tests/unit/test_business_clarification.py tests/unit/test_semantic_resolution.py`

結果：32 passed in 7.05s，退出碼 0。這些測試主要覆蓋 v9 真 view ambiguity 與單來源語意選項，缺少 v10 多來源的 incomplete semantic preflight，能解釋原有綠燈卻發生此回歸。

## 風險與交接

本次只證明問題邊界與消融因果，未實作修正。v3 contracts 不宣告完整 metric lineage，僅靠模型布林值不能證明任意自然語言的真實同義；必須保留 fail-closed 與原始 evidence。DAILY 在正式 aggregation 修正後還需重驗，不能預填通過。真實 LLM 穩定性與 DB 結果未驗證。

Main 下一步：以 S 的必要 term 完整性 guard 修正明示不相容來源誤接受，加入多來源負面／holdout；先解 generic aggregation drift，再評估 DAILY 的殘餘需求歧義；保留 compare 原契約。
