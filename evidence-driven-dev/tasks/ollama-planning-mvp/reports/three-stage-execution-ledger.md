# 三階段執行紀錄

計畫：`three-stage-view-selection-plan.md`。主 agent 依 executing-plans 直接實作；最後使用獨立 reviewer。既有 worktree `feat/cross_view`、HEAD `bc09c67`，不提交、不覆寫前輪變更。

## 決定與介面核對

- 沿用本 Task 作 ledger，不建立重複任務。計畫採核取表而非 task-start 的數字 Task 格式，因此手動保存逐項測試與結果。
- Requirement → ViewCoverage → SelectionResult 共用穩定 ID；每個 View 必須回報所有需求，部分支持不提前丟棄。
- SelectionResult → 原 DecompositionDraft → 原 validator/preparer；新增檢查只拒絕不成立的引用，不代填模型答案。
- 原文引文／契約引用只能證明引用存在，不能證明模型語意理解正確，另做語意驗收。
- 本輪使用者已授權依計畫執行；第11題通過才建立六題獨立 EXP。封存題不揭露。

## EXP-009 預算（模型呼叫前凍結）

- 範圍：第11題首次一次三階段流程；DeepSeek-V4.1-Flash，最多 9 次（需求1＋七來源7＋選擇1），序列，不追加 reviewer，不重試、不自動 repair。
- 每次 output 上限 4096 tokens；context 32768、safety 1024，輸入上限 27648 tokens；呼叫前實測 token budget，不裁切。
- 總輸入估計上限 150000 tokens、總輸出 reserve 36864 tokens、單次 timeout 300秒、總 wall budget 3000秒；剩餘時間不足一次 timeout 即停止。
- 價格：目前沒有可核實的 Azure deployment 計價表；不臆造美元成本，實際費用標為未知，保存供應商 usage 及 token 上限作成本依據。本預算以 calls/tokens/time 限制費用暴露。
- provider、解析、契約錯誤或版本漂移即停止；首次失敗完整保留。第11題不通過就不花費六題60次。

## 進度

- 恢復與基準：Git／Task／Checkpoint／原計畫已核對；既有相關 25 tests passed。
- 待辦：離線 RED→GREEN、三份 prompts、runner／重播、相關回歸、第11題、獨立 review、報告與Checkpoint。

## 離線實作與審查

- 契約階段：先因新module不存在失敗，完成後12 pass／7 fixture錯誤；修正fixture只對確有店商品鍵的來源造控制，再修正子任務可重用已驗證key映射，19 passed。
- Orchestration：7測試先因runner不存在失敗，實作三份prompts與序列／預算／保存，26 passed；dry-run 7109 input tokens。
- 獨立 reviewer 初判 FAIL：最終grain／補零2項P1，provider-error replay／新增artifact漏檢2項P2；五個反例實跑失敗後修正，31 passed。
- 追加實際usage超預算反例先失敗再修正；合計32 focused、125相關回歸 passed。
- 決定：grain 類需求代表最終粒度；缺值政策使用輸入canonical選項，不採任意自由描述判斷。限制是保守拒絕等價字句／更一般的多粒度設計，保留evaluation邊界。
- 本輪不提交；保留Ledger與原始證據，不執行流程中的commit／scratch刪除步驟，遵守使用者Git安全規則。

## 第11題實測與機械修正

- EXP-009：真實2calls，v1合法 `/grain/keys/0` 被檢查器當dict路徑誤拒；原版兩筆重播還原停止，EV-20261021T015206-fb32d89a。
- 新增索引正／反例，3 fail／4 pass；修正合法陣列索引而繼續拒絕負值、前置零、越界與非整數，39 focused passed。原raw離線重驗通過，不回寫第一次結果。
- 決定：原始模型輸入沒有改變，另列EXP-010，以兩筆cache續接未呼叫節點而不重跑模型；不當固定版本首次Gate。新prefix輸入／provider failure不可重試守門先RED後GREEN，42 focused／135相關passed。
- EXP-010：前兩raw逐字重用，新增2calls；inventory路徑引用到陣列而非字串而拒絕。全輪4次不同節點呼叫、13419 input／5550 output tokens、約47.72秒。依停止規則不再續接、不擴六題。
- 原版2筆與續接4邏輯節點皆已fresh replay；v1.1來源/測試指紋固定，原分及raw未變。產品v3及schema未改。
- 結果：離線契約PASS；自然完整流程NOT_VERIFIED，單題診斷門檻未達；效果假設INCONCLUSIVE。完整報告與下一步見three-stage-view-selection-results.md。
