# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者已設定好並繼續指示，只接續剩餘62項；保留舊28次並分段揭露硬體/image差異",
  "alternatives": [
    "重新全90次成本增加且不屬本次接續；不重跑原逾時"
  ],
  "reason": "使用者明確要求繼續，原Task已取消無法反轉；另立接續Task且不修改原記錄",
  "risks": "合併90結果不是單一固定服務環境；目前GPU仍部分offload，不自行改推論參數",
  "revisit": "來源/模型/設定改變或provider錯誤時先停止與保存，不盲目重試",
  "references": [],
  "at": "2026-10-21T04:10:03+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者授權改為30分鐘：新接續segment單次LLM HTTP讀取逾時1800秒，只跑剩23次",
  "alternatives": [
    "取消逾時可能無限等待；維持300秒持續中止，均不採用"
  ],
  "reason": "使用者明確指示「取消timeout或改成限制30分鐘」；實際Ollama同步與非同步client均已驗證1800秒，其他metadata.settings完全相同",
  "risks": "原67次仍依300秒計分，與新23次不是同一timeout協定；不能以總計代表固定條件穩定性。全批次仍保留12小時執行上限。",
  "revisit": "1800秒仍不足或服務錯誤時保存並停止，先診斷不盲目重試",
  "references": [],
  "at": "2026-10-21T15:05:25+00:00"
}
```
