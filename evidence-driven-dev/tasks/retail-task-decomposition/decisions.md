# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "source": "user",
  "question_id": "Q-001",
  "summary": "使用者贊同獨立前置 planner 方案；要求依現有資料建立 30 個跨表需求，Azure 連線資訊位於 ./.env。",
  "evidence": "本回合使用者訊息第 1、2、3 點",
  "at": "2026-10-20T04:22:16+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "source": "user",
  "question_id": "Q-002",
  "summary": "使用者同意書面規格；指定 Azure 模型／deployment 為 gpt-6-sol，解除 Azure 模型呼叫次數上限。限流不自動重試的既有規則仍適用。",
  "evidence": "本回合使用者訊息第 1、2、3 點",
  "at": "2026-10-20T04:38:58+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "source": "user",
  "question_id": "Q-003",
  "summary": "使用者選擇主 agent 直接實作；依核准計畫執行，完成後獨立 reviewer 檢查。",
  "evidence": "本回合使用者明確回覆：主agent直接實作",
  "at": "2026-10-20T04:49:57+00:00"
}
```

## DEC-004

```json
{
  "id": "DEC-004",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者最新指示停止GPT第二輪，改Azure DeepSeek-V4.1-Flash完整30題作第二輪；不再自行完成原GPT第三輪。",
  "alternatives": [
    "保留GPT第一輪完整30與第二輪已完成17作部分結果，DeepSeek同prompt/schema/oracle跑30",
    "繼續原GPT三輪（與最新使用者指示不符）"
  ],
  "reason": "使用者明確要求：暫停第二輪，改用azure DeepSeek-V4.1-Flash測試第二輪",
  "risks": "已終止的GPT批次有一筆in-flight結果未知，可能計費；DeepSeek模型差異不得混入GPT三輪穩定性分母。",
  "revisit": "使用者另行要求第三輪或恢復GPT時",
  "references": [
    "本輪使用者訊息"
  ],
  "at": "2026-10-20T05:52:10+00:00"
}
```

## DEC-005

```json
{
  "id": "DEC-005",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者要求，新增本地Ollama qwen3.8:27b完整30題一輪；不替換既有Azure結果。",
  "alternatives": [
    "本地同題庫/prompt/schema及相同主要生成設定比較，另外記錄native schema/reasoning差異",
    "重跑Azure或改其他本地模型（與使用者指定不符）"
  ],
  "reason": "使用者最新明確指定：本地ollama qwen3.8:27b測試一輪。",
  "risks": "本地服務另有執行中工作，延遲不能視為隔離效能benchmark；native schema約束與reasoning設定須揭露。",
  "revisit": "使用者改模型或要求調整設定時",
  "references": [
    "本輪使用者訊息"
  ],
  "at": "2026-10-20T06:11:20+00:00"
}
```
