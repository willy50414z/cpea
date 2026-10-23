# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者確認新增獨立入口，採 A 逐 View 需求候選證據與二次審核",
  "alternatives": [
    "B 完整逐詞逐欄矩陣",
    "替換原 task decomposition 預設流程"
  ],
  "reason": "使用者明確選擇獨立入口並於書面設計確認後回覆 A",
  "risks": "A 不保存全部拒絕組合；真實 LLM 語意仍需實測",
  "revisit": "使用者後續要求逐格拒絕稽核或整合既有預設流程時",
  "references": [
    "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
  ],
  "at": "2026-10-23T06:27:27+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依使用者追加要求，在新入口最前端重用既有View檢索，再對候選執行A流程",
  "alternatives": [
    "繼續逐個比對完整catalog，不作前置篩選",
    "直接套用單View所有明列欄位交集"
  ],
  "reason": "使用者要求最前端View篩選以避免過多Views；研究者選擇僅移除檢索識別碼並補回原文明列來源，保留多來源能力",
  "risks": "soft top-k可能因ties或明列欄位owners增加；檢索召回與真實模型品質未實測",
  "revisit": "候選過多或實測發現缺少必要來源時",
  "references": [
    "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
  ],
  "at": "2026-10-23T06:44:43+00:00"
}
```
