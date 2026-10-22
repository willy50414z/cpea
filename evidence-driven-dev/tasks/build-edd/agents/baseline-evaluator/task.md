---
{
  "parent_task": "build-edd",
  "agent_id": "baseline-evaluator",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "在隔離暫存 Repo 以一般開發流程執行三個離線案例，報告實測指標",
  "allowed_scope": [
    "隔離暫存 Git Repo",
    "evidence-driven-dev/tasks/build-edd/agents/baseline-evaluator/task.md"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/baseline_evaluator",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "一般流程在獨立暫存 Repo 完成三個離線案例：實測 30 個測試方法由失敗轉通過，加上 3 個修正後才加入的 holdout 測試方法，共 33 個測試方法通過；保存三次 threshold 失敗、單節點 Replay 與可重現指令。",
    "evidence": [
      "/tmp/edd-baseline-evaluation-ctzhw58t/REPRODUCE.md",
      "/tmp/edd-baseline-evaluation-ctzhw58t/all-tests-output.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/changes.diff",
      "/tmp/edd-baseline-evaluation-ctzhw58t/replay-output.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/threshold-0.3-failure.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/threshold-0.6-failure.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/threshold-0.9-failure.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/measurement.json",
      "/tmp/edd-baseline-evaluation-ctzhw58t/tests.py",
      "/tmp/edd-baseline-evaluation-ctzhw58t/holdout_tests.py",
      "/tmp/edd-baseline-evaluation-ctzhw58t/red-BoundsTests.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/red-RetrievalTests.txt",
      "/tmp/edd-baseline-evaluation-ctzhw58t/red-RoutingTests.txt"
    ],
    "risks": [
      "離線小型 Python fixtures 的結果不能外推至真實 LLM Pipeline 或證明 EDD 優於一般流程。",
      "恢復只驗證檔案與 Git 差異可讀，未測試真正 Session 中斷或 Context Compact。",
      "暫存 Repo 位於 /tmp，清理後證據將消失；Main Agent 應選擇必要摘要與小型輸出保存。",
      "Token、模型延遲與貨幣成本未提供，均為 NOT_MEASURED。"
    ],
    "next_step": "由 Main Agent 獨立讀取報告及實際輸出，與 EDD 組結果做有限範圍比較；不得由此推論真實系統的泛化效果。",
    "diff_reference": "/tmp/edd-baseline-evaluation-ctzhw58t/changes.diff"
  },
  "blockers": [],
  "question": null
}
---
# 基準流程評估報告

## 身分與隔離

依指定要求未載入 EDD Skills、未以 EDD Ledger 管理三個案例，未讀取另一位評估者結果。只讀取分派紀錄與兩個輸入 fixtures，所有實作與測試都在 `/tmp/edd-baseline-evaluation-ctzhw58t` 的獨立 Git Repo。未修改正式 CPEA 演算法、主 Task 或其他 Agent 紀錄。

暫存 Repo Base SHA：`3ace66c8fc0ef57782dc8989d54f7ef7487c8d77`。父任務原始 `base_git_sha` 保留於 Frontmatter，兩者代表不同 Repo。

## 案例一：包含端點的 bounded

根因是上限錯用 `maximum - 1`，與包含兩端的截斷契約不符。先寫 9 個測試方法執行，實際得到 4 個失敗；修正只移除 `- 1`，9 個方法全部通過。涵蓋上下端點、上下界外、內部值、單點區間、浮點、負區間及非法範圍。

方案採一行契約修正；較大方案可導入標準截斷工具或泛型數值介面，但此處沒有需要或證據，不擴大設計。單元函式直接重現，無需建立流程文件或詢問使用者。修正後另建立 100 組固定種子的未用於調整之區間 holdout，檢查結果在區間內且符合一般截斷定義；全部通過。沒有依測試 ID 或特定數值分支。

## 案例二：Retrieval Pipeline

第一個偏離契約的邊界是 `retrieve`。問題已轉成小寫，但 aliases 保持 `Revenue`／`SALES`，導致候選清單為空。先以原始程式執行單節點 Replay，取得 `[]`，並確認 SQL compiler 對此清單正確拒絕；因此不修改 compiler。

比較的方案：S 是比對時將兩側 aliases／terms 一致 casefold；M 是建立預先正規化的 alias index，適合規模與效能需求明確後；L 是改為語意檢索與重排序，需要額外模型、資源、語意正確性驗證，目前沒有必要。採 S；先用獨立實驗函式驗證 revenue、stock、unknown 及多匹配四個輸入，再改正式 fixture 的 retrieval 比對。

10 個測試方法修正前有 2 個失敗、7 個錯誤，修正後全通過；包含單節點、整段 pipeline、大小寫變形、另一個 view、無匹配、空輸入、多匹配、衝突 alias、compiler 拒絕契約及未見 alias。另在修正後加入三組未用於調整的 Unicode／一般 alias holdout（每組大小寫兩個輸入）全部通過。只測離線字串型 aliases，沒有驗證真實 Text-to-SQL、LLM 或資料庫。

## 案例三：連續 threshold 失敗

先對原始 `select_route` 實際執行 threshold 0.3、0.6、0.9，三次均對 `labels=['sales','stock'], query='s'` 回傳 `sales`，以 assertion exit 1 保存輸出。部分字元交集分數為 1，調整 threshold 無法表達正規化後的完全且唯一相等契約。停止 threshold 路線，採完全匹配並檢查候選數量。

替代方案包括繼續調整分數（已被三次反證，不採）、直接精確掃描（採用）與預先建立正規化索引（資料量未證明需要，延後）。保留 legacy threshold 參數以避免無謂破壞呼叫介面，但它不影響新契約；程式註解明示原因。

11 個測試方法修正前有 3 個失敗、1 個錯誤，修正後全通過。驗證部分匹配拒絕、完全匹配、trim 與大小寫、未知、空 labels、空 query、空白、重複完全匹配、正規化後重複、Unicode casefold 及未見 label。另用 6 種 labels 排列 × 5 個 threshold 的 30 個修正後 holdout 子案例，驗證精確結果、部分匹配拒絕與重複匹配拒絕；全部通過。

## 實際結果與成本

| 項目 | 實測結果 |
|---|---|
| 完整 Regression | `python3 -m unittest -v tests holdout_tests`，33 個測試方法，OK |
| 修正前基準 | 案例一 4 failures；案例二 2 failures／7 errors；案例三 3 failures／1 error |
| 最小 Replay | 1 次執行，4 組候選實驗比對通過，保留原始失敗邊界輸出 |
| threshold 歷史失敗 | 3 次實際 exit 1，並於修正後以 baseline snapshot 再現 |
| Holdout | 修正後才新增 3 個方法，133 個 subTest 組合；未據其輸出再次修改程式 |
| Python 測試／實驗程序 | 共 17 次：初始 RED 3、GREEN 3、完整 Regression 1、Replay 1、threshold 失敗 3、RED 重現 3、threshold 重現 3 |
| 必要使用者詢問 | 三個案例各 0；契約足夠清楚 |
| 協作 | 單一評估 Agent 在獨立 Repo 執行，未啟動額外 Agent，無共寫範圍 |
| 工具呼叫 | 此評估回合共 5 次 `functions.exec`（含輸入讀取與報告寫入），另 1 次進度訊息 |
| 執行時間 | 從暫存 Repo 建立後到最後完整驗證與重現檢查約 58.562 秒，不包含本報告寫作；非純模型延遲 |
| Token／貨幣成本／模型延遲 | NOT_MEASURED |

## 可重現性與恢復能力

完整測試、失敗與通過輸出、baseline snapshot、單節點 Replay、差異及實際指令均在暫存 Repo。`REPRODUCE.md` 提供修正後驗證及原始失敗命令，原始失敗命令已在修改後再次實際執行，避免依賴被覆寫的程式狀態。

一般流程可從檔案、Git 差異與測試輸出恢復技術脈絡；未建立逐步狀態 Checkpoint，因此精確的「最後執行動作」仍需讀紀錄推斷。未執行真實 Session 重啟或 Context Compact，不將此項標成已驗證。未測試真正平行 Worktree 合併、使用者決策等待或 Hooks；這些不屬本基準三案例的實測範圍。

## 過擬合風險與結論界線

修正皆依契約的一般規則；Regression 含負向、邊界、大小寫變形與未用於修改的 holdout。測試為同一評估 Agent 設計，不能替代獨立外部資料集或業務 Oracle。案例三的 threshold 保留是介面相容選擇，正式產品應另外決定棄用策略。

這些結果顯示一般工作流程也能在此組離線 fixtures 診斷與修復三種問題；不能單靠比較文件數、測試方法數或單次成功推論 EDD 有效性。請由 Main Agent 在讀取兩組實測輸出後，明確區分流程機制覆蓋與真實品質／成本改善。

## Handoff

DONE_WITH_CONCERNS。具體證據、未驗證限制與下一步均列於 Frontmatter handoff，未宣告父任務完成。
