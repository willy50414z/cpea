# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "取得原始失敗條件後才修改程式；保留目前通過的測試契約",
  "alternatives": [
    "依 14 的數量推測並直接變更程式"
  ],
  "reason": "完整產品 388、Unit/Contract 301 與 EDD 49 均通過，尚無支持根因的失敗證據",
  "risks": "原始失敗可能來自其他版本、環境或真實模型評估，尚未覆蓋",
  "revisit": "取得原始命令或失敗清單後立即恢復調查",
  "references": [
    "evidence/EV-20261020T025931-7bd52405.json"
  ],
  "at": "2026-10-20T03:01:29+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "source": "user",
  "question_id": "Q-001",
  "summary": "修復範圍為本對話已完成的 Retail MATCH v10 14 題各三次真實模型穩定性評估，非 14 個 pytest 失敗。原始指令及 42 筆結果在 projects/retail/artifacts/evaluations/20261019T115951Z-qwen-v10-samples14-stability3/rerun.py、results.jsonl、calls.jsonl；本回合使用者要求用 EDD 修復前述問題。",
  "evidence": "本對話前文 14 題重測、階段解讀與最新使用者訊息「用 $edd 修復」；本地 report.md / analysis.json 可核對",
  "at": "2026-10-20T03:07:28+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "採用v10分組欄位正規化、明確聚合驗證沿用同View修復、必要詞彙不相容候選排除及一次語意驗證回饋修復",
  "alternatives": [
    "僅改prompt，無法約束保存的錯誤輸出",
    "重設完整語意AST，超出本次已證實局部根因"
  ],
  "reason": "原始9筆分組缺欄回放全通過；6筆COUNT錯配現在被攔；合成負面/邊界與獨立139檢查及完整回歸通過。保留真實歧義與原Oracle。",
  "risks": "必要時增加一次語意模型呼叫；聚合辨識範圍是已測明確後綴，非完整自然語言證明；DB數值未驗證。",
  "revisit": "真實模型焦點重測失敗或新語法/來源契約出現時重新調查，不以題文特判。",
  "references": [
    "evidence/EV-20261020T033349-1c0893b0.json",
    "evidence/EV-20261020T033303-f1efa028.json",
    "agents/independent-review/task.md"
  ],
  "at": "2026-10-20T03:34:40+00:00"
}
```
