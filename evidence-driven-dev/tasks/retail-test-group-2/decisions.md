# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "固定14題為group1、排除後以seed20261020分層抽30題為group2，各3次；凍結當前產品並保留所有失敗",
  "alternatives": [
    "均勻隨機30題但可能缺難度/安全覆蓋"
  ],
  "reason": "滿足額外不重疊樣本並覆蓋七View及各難度，不按模型輸出重抽。使用者已授權額外30題穩定性測試，沿用每題3次。",
  "risks": "新測試組仍來自已知395題，不能視為從未見過的盲測；本地模型需要數小時；無DB數值驗證。",
  "revisit": "服務錯誤停止新呼叫後依完整記錄處理；本輪完成後若要修復失敗另立任務，避免污染穩定性測量。",
  "references": [
    "evidence/EV-20261020T050600-34a5fb8c.json"
  ],
  "at": "2026-10-20T05:07:43+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "保留第22次ReadTimeout為失敗，檢查服務與指紋後只繼續原排程尚未執行的68次",
  "alternatives": [
    "重跑整輪或重試逾時tuple，會抹去原穩定性失敗",
    "放棄剩餘68次，無法完成使用者要求"
  ],
  "reason": "原run按規則停止；服務可連線且模型digest、source/settings/Oracle/sample未變；持續授權90次測量，接續不重試失敗且不改設定。",
  "risks": "provider逾時影響一題三次結果，報告單獨揭露；同來源多segment執行，不宣稱單次不中斷。",
  "revisit": "再次服務錯誤立即停止新呼叫並查明，不盲目重試，不改模型或timeout。",
  "references": [
    "evidence/EV-20261020T050649-113b0aec.json"
  ],
  "at": "2026-10-20T06:21:13+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "使用者明確選擇「等它結束」；等cpea_terms的decomposition工作釋出共享Ollama後，只接續67次未做測量",
  "alternatives": [
    "中斷另一輪測試，使用者未選擇且不執行"
  ],
  "reason": "使用者最新訊息「等它結束」，保留全部23筆與兩次服務逾時，避免共享推論互相影響。",
  "risks": "等待期間不送新的測試生成，總耗時較長；服務恢復後仍需核對model/source/Oracle。",
  "revisit": "另一輪程序結束或使用者改變優先順序後恢復；不自動重跑已做tuple。",
  "references": [
    "evidence/EV-20261020T062744-cb642387.json"
  ],
  "at": "2026-10-20T06:33:57+00:00"
}
```

## DEC-004

```json
{
  "id": "DEC-004",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "90次同版本測量完整，研究任務可完成；產品僅48/90符合原預期，不宣稱全部穩定或正式核准",
  "alternatives": [
    "依結果修改產品、Oracle或重試失敗，會污染本輪固定版本測量"
  ],
  "reason": "三個segment的90個唯一tuple及575次呼叫均完整，原Oracle重評及報告審核成功，產品與模型指紋一致；失敗42次原樣保留",
  "risks": "14題三次皆失敗；2次provider逾時；pending draft Oracle；無DB數值與盲測驗證；同Main以獨立程序驗證",
  "revisit": "未來修復需另立任務與新版本重測，不改寫本輪原始結果；group1其餘8題修復版仍未新增重跑",
  "references": [
    "evidence/EV-20261020T141423-03800329.json",
    "evidence/EV-20261020T141613-15248dee.json"
  ],
  "at": "2026-10-20T14:16:43+00:00"
}
```
