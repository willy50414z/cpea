# EDD 與一般工作流程：受控評估

兩個真實 Subagent 各自使用獨立暫存 Git Repo，未讀對方答案、未修改正式 CPEA 演算法。相同輸入為 evaluation/fixtures 的三個契約案例；Baseline 禁用 EDD，EDD 組實際載入三 Skills 與 CLI。Main 已讀取兩組原始失敗、成功輸出、程式 Diff、測試與 Handoff，再將可重現的小型程式保存於 evaluation/results。

| 指標 | 一般流程 | EDD 流程 | 可支持的結論 |
|---|---|---|---|
| Root Cause Accuracy | 3/3 契約案例正確 | 3/3 契約案例正確 | 本樣本未證明準確率改善 |
| Reproduction Quality | 三案例 RED，Retrieval 節點 Replay | 三案例 RED，Retrieval 節點 Replay，EXP | 兩者均有重現；EDD 提供固定保存位置 |
| Alternative Coverage | 比較局部／索引／語意方案 | S/M/L 欄位、DEC、MVP | 兩者皆比較；EDD 可機器檢查必要欄位 |
| Experiment Efficiency | 節點原型先於 Pipeline 修改 | 節點原型先於 Pipeline 修改 | 沒有證明 EDD 更省工具或時間 |
| Regression Quality | 33 個方法，含 3 個新 holdout 方法 | 28 個方法 + 8 個新 holdout assertions | 測試集合不同，不能用數目比較品質 |
| Overfitting Risk | 無測試 ID／答案特例；邊界、負向、Unicode | 無測試 ID／答案特例；邊界、負向、Unicode | 都符合這組明確契約；非真實泛化證明 |
| Human Interruptions | 真實詢問 0 | 真實詢問 0，模擬事件 1 | 未過度詢問；模擬事件不是真實批准 |
| Subagent Coordination | 獨立暫存 Repo，單一 writer | 獨立暫存 Repo，Report + Main 整合 | 此處測真實派遣與 Handoff；雙 writer 衝突另有守門測試 |
| Recovery Reliability | Git、測試與輸出可讀；未測精確恢復 | fresh CLI resume、WAITING_USER/answer、stale evidence 實測 | EDD 的持久恢復機制有直接證據 |
| Token / Tool Cost | Token NOT_MEASURED；Agent 報告 17 個測試／實驗程序 | Token NOT_MEASURED；80 CLI，17 Ledger 測試程序，Simple 另兩次 | 紀錄成本增加；量測範圍不同，不做成本改善結論 |

Baseline measurement.json 的分類計數與其文字報告使用不同口徑，不能直接加總作為公平效能基準；完整 Token／模型延遲／貨幣費用均未提供。EDD 的 CLI 程序時間不是模型總延遲。本次沒有顯著性推論，也未隨機化多次重複。

## 重跑已保存的修正結果

```bash
(cd evidence-driven-dev/evaluation/results/baseline && python3 -m unittest -v tests holdout_tests)
python3 evidence-driven-dev/evaluation/results/edd/evaluation/checks.py all
```

原始 RED、三次 threshold 失敗、CLI journal 保存在 build-edd/.local，未提交 Git；原始 fixture 在 evaluation/fixtures，可用兩組 changes.diff 與獨立暫存 Repo 重建。EDD 執行證據 JSON 保存於 results/edd/records，原始命令含當時 /tmp 路徑，只作歷史追溯，不可當目前 Checkout 的 PASS。

## 失敗與限制

兩組都實跑 threshold 0.3／0.6／0.9 失敗。EDD 另外拒絕第四次同假設實驗；後續硬化版進一步要求結構化 reassessment，並拒絕繼續被否定假設。完整最終守門測試驗證新版本，行為評估快照位於較早的實作 Revision。

EDD 組曾因測試命令換行轉義造成 SyntaxError，保留失敗後修正 harness，未改 Oracle。該次不是有效產品測試。

這些是離線確定性 fixtures；未驗證真實 Text-to-SQL／LLM／資料庫、真實 Compact 中斷、跨 Agent 的業務 Oracle 或長期團隊效率。Superpowers 缺少、Hook 尚未信任；不宣稱這些整合通過。真實 Worktree 隔離另由自動測試建立兩個 Git Worktrees 驗證。
