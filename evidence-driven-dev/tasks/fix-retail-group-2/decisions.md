# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "採通用局部修復；原題庫與測量保持，合理歧義不代選，來源比較需逐競爭反證",
  "alternatives": [
    "放寬引用或強制14題產生唯一View，會錯放語意；重建AST或換模型成本高且不能解決字串guard"
  ],
  "reason": "使用者已授權查根因並修復；雙agent確認6確定Bug、2 guard兼粒度歧義、3合理澄清、1語意兼逾時與2安全拒絕評分問題。先失敗/後通過測試支持最小方案。",
  "risks": "引用與結構化衝突不構成邏輯證明，語意仍依賴模型；不宣稱所有14題皆應ready",
  "revisit": "新增反例、真實模型仍錯或三次實質修復失敗時重新評估；不修改Oracle迎合輸出",
  "references": [
    "evidence/EV-20261020T152659-c2ca1298.json"
  ],
  "at": "2026-10-20T15:28:52+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "凍結版本A，6個確定產品問題各一次真實模型焦點驗證，保留所有失敗及不執行DB",
  "alternatives": [
    "直接重跑90次耗時高且尚非新版穩定性任務；僅離線測試不足以衡量來源語意"
  ],
  "reason": "本輪是根因修復；真實模型驗證另存新run，並非取代原三次穩定性測量。Ollama已無loaded model、digest未變。",
  "risks": "一次不能宣稱三次穩定；審查發現未知欄位逐列新guard可能例外，等待版本A結束後修為B並另作完整回歸",
  "revisit": "模型錯誤/transport問題停止新呼叫且保存，不盲目重試；若需修改版本先封存A",
  "references": [],
  "at": "2026-10-20T15:28:52+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "C只修有效多項反證的驗證條件：每來源至少一項主要片語反證，額外反證需全部grounded且互異",
  "alternatives": [
    "重試相同B模型或只接受第一項、忽略無效附加反證，均不處理真實gate根因"
  ],
  "reason": "B模型已正確選Store並提供計數/識別碼、目標/實績兩項合法反證；同一B完整輸出逐字回放在C六題全部符合原Oracle，新增多項反證測試先紅後綠。所有既有負例仍通過，prompt與Oracle未改。",
  "risks": "引用仍非語意邏輯證明；C混合驗證保留B前序，不宣稱新版本完整E2E/三次穩定性。若第三次實質方案仍失敗即重新審查。",
  "revisit": "C真實比較節點、獨立多來源反例或完整回歸失敗時停止同假設調參並重新研究",
  "references": [
    "evidence/EV-20261020T160403-f71c0c4d.json"
  ],
  "at": "2026-10-20T16:05:11+00:00"
}
```
