# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者要求完整重跑group2 30×3，不使用混合回放",
  "alternatives": [
    "只跑6題或14失敗題不足以測回歸，不採用"
  ],
  "reason": "使用者於修復後明確要求跑穩定性測試，沿用原完整群組與測量參數",
  "risks": "可能耗時數小時且仍有歧義/Oracle失敗；無DB、draft待核准",
  "revisit": "provider錯誤或版本改變時保存狀態並先診斷，不盲目重試",
  "references": [],
  "at": "2026-10-21T01:32:50+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "source": "user",
  "question_id": "Q-001",
  "summary": "恢復測試，接續原程序且保留26個已完成tuple",
  "evidence": "本回合使用者明確訊息：繼續測試。恢復前已核對26筆原Oracle結果、資料/來源/模型digest不變；原runner socket有118534 bytes已收資料，優先保留在途回應，不重跑tuple。",
  "at": "2026-10-21T03:45:54+00:00"
}
```
