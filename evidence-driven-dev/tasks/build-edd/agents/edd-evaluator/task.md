---
{
  "parent_task": "build-edd",
  "agent_id": "edd-evaluator",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "在隔離暫存 Repo 載入 EDD Skills 執行三個離線案例，實測 Ledger 與恢復",
  "allowed_scope": [
    "隔離暫存 Git Repo",
    "evidence-driven-dev/tasks/build-edd/agents/edd-evaluator/task.md"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/edd_evaluator",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "依實際載入的 EDD Skills 在隔離 Repo 完成三案例，28 項契約回歸與 8 項新 holdout 通過；三次失敗守門、模擬 WAITING_USER/answer、fresh subprocess 恢復及舊證據過期偵測均實跑。",
    "evidence": [
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/summary.json",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/commands.jsonl",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/capabilities.json",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/simple-red.log",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/simple-green.log",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/retrieve-contract/task.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/retrieve-contract/experiments/EXP-001.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/route-contract/task.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/route-contract/experiments/EXP-001.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/route-contract/experiments/EXP-002.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/route-contract/experiments/EXP-003.md",
      "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/tasks/route-contract/experiments/EXP-004.md"
    ],
    "risks": [
      "同一 Agent 撰寫與執行 Oracle，非跨 Agent 獨立驗證",
      "八個 Superpowers Skills 實際探測 missing，使用 EDD references 降級",
      "受控 fixture 不代表真實 LLM/Text-to-SQL 演算法驗證",
      "Token 與完整模型費用 NOT_MEASURED；暫存證據尚未保存為永久評估附件"
    ],
    "next_step": "Main 讀取隔離 Task、EXP、CLI journal 與 Diff，獨立審查後彙整評估；勿將模擬 User Gate 視為真實批准。",
    "diff_reference": "/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/fixture-diff.patch"
  },
  "blockers": [],
  "question": null
}
---
# Subagent 任務：EDD 流程受控評估

## 身分與範圍

- 父 Task：build-edd；本 Agent：edd-evaluator。
- 正式 Repository Base SHA：014cee1aff3abcfb51bbe5af6db0abd2ef060225。
- 隔離 Repo：`/tmp/edd-eval-1z2tnuvr`。
- 隔離 baseline commit：`e85a5eb006ae04e7c69b735e3bd6ccb553b0768d`；先複製 fixtures、scripts、templates、config、README、.gitignore 與三 Skills 並 commit，排除原 tasks／reports／archive。
- 只修改正式 Repository 的本 Report；正式 CPEA 演算法未修改。未讀 baseline-evaluator 結果，未啟動新的 Subagent。

## 調查與實際 Skill 載入

閱讀 `edd`、`edd-investigate`、`edd-verify` SKILL.md，以及 workflow、decision-gates、experiment-design、verification-policy、anti-overfitting references，按主流程執行。

在隔離 Repo 執行 `python3 evidence-driven-dev/scripts/capabilities.py`，Codex CLI 0.163.0 的 app-server `skills/list` 實際回覆三個 Repo EDD Skills 為 enabled 且 readable，沒有錯誤。八個 Superpowers Skills 均 missing，因此採自身 references 降級，不宣稱第三方整合成功；沒有在此受控評估安裝任何第三方工具。

## 實驗與結果

| 案例 | 原始 RED | 最小實驗／修正 | 最終結果 |
|---|---|---|---|
| Simple bounded | 9 tests，3 failures | 確認 `maximum - 1` 把包含上限變成錯誤截斷，也破壞浮點輸入；只改一個運算式 | 9/9；包含上下界、超界、負範圍、相同界限、浮點及非法範圍；未建立 Task |
| Retrieval | 9 tests，2 failures、5 errors | 先建立 retrieve 單節點 Replay：baseline=[]，正規化原型=[sales_view]；原 compiler 已能編譯合法候選。確認第一偏離邊界是 query lower 與 aliases 原樣比較，非 SQL compiler | 修正 retrieve 對稱 casefold；9/9；SQL compiler 完全未改；無匹配、多匹配仍拒絕 |
| Repeated Failure | 10 tests，3 failures、1 error | 實跑 threshold 0.3（3 failures、1 error）、0.6（3 failures、1 error）、0.9（4 failures、1 error），各自建立 EXP、保留輸出並 REFUTED | 第四次同假設被 CLI exit 2 拒絕；重新審查 Oracle、記錄 reassessment 與 DEC；先純函式原型 5 assertions，再改唯一精確匹配；10/10 |

最終 fresh subprocess 全套 **28 tests 通過**，另於實作後才設計 **8 個新 holdout assertions 通過**。新案例涵蓋浮點上界、希臘 aliases、另一 view、標點拒絕、tab/newline trim、Unicode casefold 重複與 `İ`／`I` 非相等。原測試內名為 holdout 的方法在 baseline 已執行，不能視為獨立保留集；真正新保留案例是最終 argv 中的 8 assertions。

### 方案與 MVP

Retrieval：S 對稱 casefold 採納；M 正規化 alias index 延後（只有實測掃描性能退化才重評）；L embeddings 拒絕（契約不需語義模型，帶來非確定性與維運成本）。MVP 0 Baseline／Replay，MVP 1 單函式修正，通過即停。方案完整欄位與停損條件保存於 retrieve-contract/task.md，決策在 decisions.md。

Route：S 調 threshold 被三次實測否定；M 唯一精確匹配採納；L 分類器拒絕。字元集合重疊對 `s` 可得滿分，沒有門檻能同時表達完整匹配、唯一性和空值拒絕；不是單純門檻太低。保留 threshold 呼叫參數以免擴大介面變更，演算法不再使用它。三次 EXP 的 Input、threshold、實際輸出與 evidence fingerprint 均保留；第四次拒絕後沒有無限調參。

### 恢復與模擬 User Gate

- 模擬測試事件：Q-001 明確標示 `[模擬測試事件]`，source=evaluation-simulation，獨立 simulated-user-event.json 標記 simulation=true，**非真實用戶批准**，也不作正式需求決策。
- ask 後實際進入 WAITING_USER；保存 previous_status=PLANNING、來源、問題、影響及恢復條件。新 CLI subprocess resume 成功恢復 Checkpoint 與 unresolved Q-001。
- answer 引用模擬事件檔且答案明確包含 SIMULATED，狀態回到 PLANNING；真實 User 詢問數 **0**，模擬事件 **1**。
- 多 Task 同時存在，均用明確 Task ID。Case 3 變更同一 fixture 後，Case 2 resume 實際 exit 1，揭露舊證據過期／工作樹不一致。重新跑全套和 holdout、更新 fingerprint 後 validate、resume 均成功，沒有重跑有副作用的操作。
- 兩個隔離 Task 最終均為 COMPLETED，verification.result=PASS_WITH_WARNINGS；Main 仍需獨立審核本評估，不以 DONE 字樣代替驗收。

## 實際命令與可追溯證據

完整 argv、退出碼、CLI 時間與 JSON 結果：`/tmp/edd-eval-1z2tnuvr/evidence-driven-dev/.local/commands.jsonl`。實際 root 為隔離 Repo。

```bash
python3 evaluation/checks.py simple
python3 evidence-driven-dev/scripts/edd.py init --id retrieve-contract --goal '修正檢索第一個失敗邊界並保留拒絕契約' --scope evidence-driven-dev/evaluation/fixtures/cases.py --complexity moderate
python3 evidence-driven-dev/scripts/edd.py run --id retrieve-contract --kind baseline -- python3 evaluation/checks.py retrieval
python3 evidence-driven-dev/scripts/edd.py run --id retrieve-contract --kind experiment -- python3 evaluation/replay.py
python3 evidence-driven-dev/scripts/edd.py resume --id retrieve-contract
python3 evidence-driven-dev/scripts/edd.py run --id route-contract --kind experiment -- python3 evaluation/threshold.py 0.3
python3 evidence-driven-dev/scripts/edd.py run --id route-contract --kind experiment -- python3 evaluation/threshold.py 0.6
python3 evidence-driven-dev/scripts/edd.py run --id route-contract --kind experiment -- python3 evaluation/threshold.py 0.9
python3 evidence-driven-dev/scripts/edd.py run --id route-contract --kind experiment -- python3 evaluation/route_prototype.py
python3 evidence-driven-dev/scripts/edd.py run --id route-contract --kind regression -- python3 evaluation/checks.py all
python3 evidence-driven-dev/scripts/edd.py validate --id retrieve-contract
python3 evidence-driven-dev/scripts/edd.py validate --id route-contract
```

最終 evidence：

- Retrieval Regression：`tasks/retrieve-contract/evidence/EV-20261019T151621-7ea3e70b.json`。
- Retrieval 新 holdout：`tasks/retrieve-contract/evidence/EV-20261019T151622-6fe354e1.json`。
- Route Regression：`tasks/route-contract/evidence/EV-20261019T151622-f67163ce.json`。
- Route 新 holdout：`tasks/route-contract/evidence/EV-20261019T151623-d0b6fc25.json`。

以上相對於隔離 Repo 的 evidence-driven-dev/。原始輸出在各 Task `.local/EV-*.log`；證據 JSON 保存版本、Diff 指紋、命令、時間、退出碼與輸出雜湊。最終 source Diff：`evidence-driven-dev/.local/fixture-diff.patch`。

## 發現與限制

| 指標 | 本次觀察 |
|---|---|
| Root Cause Accuracy | 三個人工定義契約案例均定位到一般性邏輯錯誤；不外推真實系統準確率 |
| Reproduction Quality | Simple 有實際 RED；Retrieval 有完整失敗及單節點 Replay；Route 有三個獨立失敗門檻 |
| Alternative Coverage | Retrieval、Route 均比較 S/M/L 並記錄採納、拒絕與重啟條件 |
| Experiment Efficiency | 先節點／純函式原型，再正式 fixture 修改，最後全套回歸 |
| Regression Quality | 最終 28 tests + 8 新 holdout assertions；保留缺失、多匹配與非法範圍拒絕 |
| Overfitting Risk | 不以 Test ID、題目全文或 sales_view 答案 Hardcode；只用一般性正規化與契約規則 |
| Human Interruptions | 真實 0；模擬 1，明確區分批准來源 |
| Subagent Coordination | 本評估依指令不再 spawn；未測多 Subagent 協作，不能宣稱 PASS |
| Recovery Reliability | fresh CLI subprocess Checkpoint／WAITING_USER／answer 可恢復；舊證據實際被辨識 |
| Token / Tool Cost | Token=NOT_MEASURED；80 次 CLI 呼叫、17 次 Ledger 測試程序，外加 Simple 兩次直接測試；CLI 合計約 9.155 秒，Ledger 測試 metadata 合計 3 秒（秒級解析度）；模型總牆鐘成本未測 |

沒有遇到阻礙完成案例的 EDD CLI Bug。一次新 holdout 命令在評估 harness 的 Python 字串換行轉義錯誤，產生 SyntaxError；保留失敗 evidence `EV-20261019T151616-f93b20a9.json`，修正 harness 後重新執行，沒有修改 EDD CLI 或測試 Oracle。該次失敗屬環境／測試命令構造錯誤，不是產品根因或有效測試 PASS。

## 變更檔案

正式 Repository 僅本 Report。隔離 Repo 新增 evaluation/checks.py、replay.py、threshold.py、route_prototype.py；修改 fixtures/cases.py；建立 retrieve-contract 與 route-contract Ledger／EXP／DEC／evidence，以及 .local 執行日誌。未 commit 最終變更，保留 baseline 與可讀 Diff 指紋，不能稱為乾淨 Revision 正式 Benchmark。

## 待釐清問題

無阻礙本次受控案例的問題。Superpowers、真實模型 Pipeline、跨 Agent 獨立驗證、多 Agent 衝突、真實 Session Compact 與 Hook 皆不是本 Subagent 此次驗證範圍。

## Handoff

DONE_WITH_CONCERNS。Main 請審核實際證據及限制，再整合評估結果；所有結論僅限受控離線 fixtures，暫存證據如需長期保留應由 Main 轉存經審查的精簡附件。結構化 Handoff 在 Frontmatter。
