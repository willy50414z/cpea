# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "本次DeepSeek三階段原型未改善，保留原產品流程；後續候選優先型別化中間契約與結構編譯，尚未宣稱有效",
  "alternatives": [
    "直接採用三階段原型：自動2/10、ready5/10、有控制退步",
    "維持原prompt流程，保存三arm實驗與失敗，先處理來源/欄位角色/粒度契約再另做比較",
    "繼續增加審查與模型修補：變因及成本更高，本次不擴張"
  ],
  "reason": "固定十題成對結果A7/10、B2/10、C2/10；三個表示差異另列，C仍不優於A且不符合C優於B/控制無退步條件",
  "risks": "小樣本單次且已見案例；grader等價盲點、來源覆蓋與母體語意仍需驗證，不能推論所有多階段策略皆無效",
  "revisit": "中間契約設計清楚且有新成對/重複及未參與調整案例支持時",
  "references": [
    "reports/results.md"
  ],
  "at": "2026-10-20T09:50:21+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "依text-to-sql候選映射完成v4/v5/v6 prompt調整與DeepSeek驗證；v5及v6未達預先門檻，保留候選與原分，恢復v3預設，不再追加調參",
  "alternatives": [
    "採用v5完整改寫及resolved context：來源欄位提高，但ready及結構大幅降低",
    "採用v6小幅prompt：欄位25→26、結構15→16，ready18→16",
    "保留v3預設，將候選/patch/全量回覆/結果交付供後續設計使用"
  ],
  "reason": "v6只改system prompt且human context相同，仍有實際格式/欄位/粒度回歸；局部提升不足以符合預先三項核心指標門檻。",
  "risks": "已見題庫單輪且模型結果波動；自動評分有等價與語意盲點；本次無SQL或DB驗證。",
  "revisit": "若後續有明確契約生成、受限修正或其他新假設，再以固定對照與新案例驗證，不沿用相同prompt反覆調參。",
  "references": [
    "reports/prompt-view-matching-results.md"
  ],
  "at": "2026-10-20T11:44:16+00:00"
}
```
