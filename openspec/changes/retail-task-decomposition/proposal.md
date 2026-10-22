# Retail 前置資料分工規劃

既有單 View 流程無法準備跨來源需求。新增獨立 planner，輸出子任務、來源欄位、整合計畫與待提交 requests；本次不生成或執行 SQL。

已核准規格：[書面規格](../../../docs/superpowers/specs/2026-10-20-retail-task-decomposition-design.md)。

實作及驗證：[實作計畫](../../../docs/superpowers/plans/2026-10-20-retail-task-decomposition.md)。使用 Azure `gpt-6-sol`，30 題三輪，無模型呼叫次數上限；供應商錯誤不自動重試。
