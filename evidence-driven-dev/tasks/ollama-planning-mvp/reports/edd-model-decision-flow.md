# EDD 模型決策理由比較流程更新

依使用者要求，已更新本機 Codex 全域 EDD skill。低成本模型在固定案例仍有語意錯誤時，先排除格式、環境與評分問題，再比較它與較強模型的簡短決策依據；據此形成可否證假設，決定後續最小實驗。

## 更新範圍

- `/home/willy/.codex/skills/edd/SKILL.md`：增加觸發條件與診斷入口。
- `/home/willy/.codex/skills/edd-investigate/SKILL.md`：加入理由、契約、typed 輸出及 request 的比較要求。
- `/home/willy/.codex/skills/edd-investigate/references/model-decision-comparison.md`：新增完整流程。
- `/home/willy/.codex/skills/edd-verify/SKILL.md`：加入原始結果、追加說明及矛盾的驗收核對。

## 流程要點

1. 保留原需求、契約、版本、raw、typed 計畫、實際 request 與首次評分。
2. 先重用既有理由；不足才選一個能區分假設的案例，兩模型各補一次簡短理由。較強模型也須依契約核對。
3. 比較選擇、依據、替代來源差異及必要條件覆蓋，找第一個可觀察分歧。
4. 理由足以決定下一個實驗便停止追加，不必耗盡預算；provider 錯誤不自動重試。
5. 生成時自述、事後說明與獨立證據分列；追加承認錯誤不改首次成績，理由不代替正確性驗收或執行指令。

## 驗證

三個 SKILL.md 通過 skill-creator quick_validate；四個修改／新增文字檔的 UTF-8 無 BOM、LF 與相對連結核對通過。外部 skill 檔案 SHA256 見 `edd-model-decision-flow.json`，修改前版本及 diff 保存在本 Task 的 `.local/edd-reason-skill-before/`。

依 writing-skills 做修改前、後獨立情境測試。修改前 agent 已會比較理由，但規劃四次呼叫且每次包含整批六題；修改後 agent 先選一題、使用兩次呼叫並設提前停止，已有理由的情境不新增診斷呼叫，也能指出粒度便利不能取代必要通路條件。這只有一次前測與一次含兩情境的後測，不宣稱統計穩定性或模型正確率改善。

本輪沒有新增 planner 供應商呼叫，沒有修改產品流程、原始計畫或評分。原 DeepSeek 完整 Gate 仍未通過。
