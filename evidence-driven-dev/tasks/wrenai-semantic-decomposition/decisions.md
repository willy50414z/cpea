# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "獨立流程以真實 WrenAI 為主，混合架構待測試後評估",
  "alternatives": [
    "於既有 LangGraph 內自行重建 WrenAI 風格流程"
  ],
  "reason": "使用者本回合明確指定：這個獨立流程希望以wrenai為主,做了測試後,在看有沒有需要實作混和架構",
  "risks": "官方現行 main 與 legacy/v1 架構不同，仍需具體設計說明版本與接入邊界",
  "revisit": "取得新流程測試證據後才討論混合架構",
  "references": [
    "本回合使用者對 WrenAI 整合意圖的非同步答覆"
  ],
  "at": "2026-10-23T07:41:11+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "正式測試題庫由使用者另行準備",
  "alternatives": [
    "由本次實作代建正式 benchmark 題庫"
  ],
  "reason": "使用者明確表示：正式測試題庫我會另外準備",
  "risks": "正式模型語意成績待題庫與Oracle到位；不影響離線契約測試及載入介面實作",
  "revisit": "使用者提供題庫後核對catalog fingerprint及Oracle格式",
  "references": [
    "本回合使用者最新訊息"
  ],
  "at": "2026-10-23T07:48:01+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "source": "user",
  "question_id": "Q-001",
  "summary": "使用者已核准原設計整合審查七項推薦A方案後開始離線開發；不啟動真模型或正式benchmark。",
  "evidence": "2026-10-23本回合使用者：$edd 根據設計整合rag-eng-review後開始開發",
  "at": "2026-10-23T08:07:49+00:00"
}
```

## DEC-004

```json
{
  "id": "DEC-004",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者授權採納RAG工程審查F1-F7的A方案；先完整離線實作與驗證",
  "alternatives": [
    "保留原草案未具體化的接入邊界"
  ],
  "reason": "使用者明確要求整合rag-eng-review後開始開發；推薦A可保留真WrenAI方向並補齊隔離/觀測/驗證契約",
  "risks": "隔離依賴與真Qdrant接入仍需spike證據；不得以離線通過宣稱真模型語意品質",
  "revisit": "原生runtime可行性或獨立驗收顯示架構阻礙時回研究，不自動改混合planner",
  "references": [
    "evidence-driven-dev/tasks/wrenai-semantic-decomposition/rag-eng-review.md"
  ],
  "at": "2026-10-23T08:10:08+00:00"
}
```

## DEC-005

```json
{
  "id": "DEC-005",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "使用者後續授權先commit並push目前分支，測試等候後續指示",
  "alternatives": [
    "維持先前不提交/推送限制"
  ],
  "reason": "使用者明確指示：先commit & push,等等跑測試",
  "risks": "保留既有PASS_WITH_WARNINGS與23既有失敗證據；不把此次Git操作當成新增測試通過，不上傳runtime/原始log",
  "revisit": "使用者後續要求測試時依新commit版本建立新證據",
  "references": [],
  "at": "2026-10-23T09:34:52+00:00"
}
```
