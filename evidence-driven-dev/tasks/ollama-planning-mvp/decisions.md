# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依已核准計畫在既有feat/cross_view與指定Task就地執行，實作限evaluation候選，保留產品v3預設",
  "alternatives": [
    "另建工作樹或直接取代產品規劃流程"
  ],
  "reason": "Task/證據/未追蹤研究輸出已在使用者指定工作區；本輪是階段研究，候選未通Gate不進產品",
  "risks": "dirty工作樹僅可作研究，正式Gate需乾淨固定revision；新候選檔需獨立審查",
  "revisit": "候選通過小樣本並準備完整Gate時",
  "references": [],
  "at": "2026-10-20T13:00:48+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "A僅型別護欄；B1未達MVP1，依停止條件不升級十題或38題或Ollama",
  "alternatives": [
    "去重日期後重跑同批題追分，或先測Qwen"
  ],
  "reason": "A安全可救0；B1僅2/6 ready，且有店商品對齊與母體根粒度真語意錯，非只缺欄位",
  "risks": "尚未證明精簡骨架一般無效；僅否證B1本次凍結實作可採用。八題封存未揭露",
  "revisit": "形成新的可否證節點假設與預先門檻後，先離線驗證再另開版本",
  "references": [
    "EXP-002"
  ],
  "at": "2026-10-20T13:00:48+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "使用者新授權以Azure gpt-6-sol對B1失敗四題07/09/14/28各測一次並保存API可取得的推理摘要",
  "alternatives": [
    "沿用先前禁止GPT測試限制，或改prompt要求模型補寫逐步思維"
  ],
  "reason": "最新使用者明確指定gpt-6-sol；以Responses reasoning.summary=auto保存官方推理摘要，原B1 prompt/schema/compiler凍結，不補寫或假造內部推理",
  "risks": "Responses與Chat Completions、reasoning設定不同；僅診斷對照，不可取代DeepSeekGate或用GPT在線代答；摘要可能空白或provider不支援",
  "revisit": "四題一次結果保存後，不重跑挑分",
  "references": [],
  "at": "2026-10-20T13:12:25+00:00"
}
```

## DEC-004

```json
{
  "id": "DEC-004",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "使用者授權新增模型可見決策依據欄位並比較GPT與DeepSeek；採獨立Explained response型別，原v3 schema與預設流程不變",
  "alternatives": [
    "將逐步內部推理混入原v3必填schema，或只保留API不可讀加密reasoning"
  ],
  "reason": "用六類簡短決策摘要定位可觀察的語意分歧；只記錄可核對結論與契約依據，摘要不驅動驗證或request組裝。三題11/14/26各模型一次，共六次相同輸入。",
  "risks": "模型自述可能錯誤或與typed計畫矛盾，不能證明內部推理順序；新增說明會改變模型輸出與行為，非原版同輪對照。",
  "revisit": "六次首次結果與說明一致性審核後，不重跑挑分",
  "references": [],
  "at": "2026-10-20T15:24:30+00:00"
}
```

## DEC-005

```json
{
  "id": "DEC-005",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "使用者授權加入必填decision_chain，由模型填寫有序高層決策紀錄；用新診斷response型別保留前版schema",
  "alternatives": [
    "要求完整私有思維鏈，或由程式替模型補寫決策過程"
  ],
  "reason": "節點記錄簡短選擇、可核對依據、typed task引用與前置節點；只能描述公開決策而非內部思考歷程。第11題兩模型各一次確認，六類完整且摘要不參與SQL payload。",
  "risks": "自述依據可錯，依賴順序不證明真實內部推理順序；有序log的結構驗證不代表商業語意正確。",
  "revisit": "兩次首次結果保存後，不自動重跑或擴題",
  "references": [],
  "at": "2026-10-20T15:36:15+00:00"
}
```

## DEC-006

```json
{
  "id": "DEC-006",
  "source": "user",
  "question_id": "Q-001",
  "summary": "使用者要求恢復指定評測：修正前、後各跑同一套原始30題，各一次；僅必要準備、固定評測與結果分析，不恢復無限改善或原樣重抽。",
  "evidence": "本輪使用者訊息「那跑一次相同題庫測試」及澄清回答「修正前、後各跑同30題，各一次」。",
  "at": "2026-10-22T03:51:16+00:00"
}
```
