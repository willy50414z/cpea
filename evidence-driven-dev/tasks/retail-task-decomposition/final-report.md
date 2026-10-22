# Retail 前置需求拆分交付與驗收

已完成獨立 planner、text-to-sql request 準備、30 題跨 View 題庫與 Azure `gpt-6-sol` benchmark。模型品質尚未全題通過，以下分數及限制是本次交付的一部分，不代表所有自然語言需求都能無人工審核執行。

## 實作

- `TaskDecompositionService.plan(request)` 封裝 `load_contracts → plan_tasks → validate_plan → prepare_requests`。
- Pydantic 契約記錄來源、欄位、條件、聚合、粒度、相依及逐邊整合方式；非 ready 不產生可提交 payload。
- 契約驗證拒絕未知來源／欄位、不合法型別／聚合、循環、錯鍵、母體方向錯誤與無法證明的粒度。
- `cpea-plan-eval` 使用根目錄 Azure 專用設定與明確模型，不設呼叫次數上限，不自動重試，不載入 SQL／DB 流程。
- 題庫 28 題雙來源、2 題三來源，涵蓋 7 個 View；預期答案不進入模型 context。

## 真實測量

30 題三輪，90 次真實 Azure 呼叫，provider 失敗 0、略過 0；90 個回覆均可解析。供應商回報 input tokens 657,600、output tokens 112,053，共 769,653 tokens，未推估金額。

當前版本離線驗證及重評：View 選擇 90/90、來源與必要欄位完整 79/90、可準備 request 88/90、整體結構檢查 60/90。三次皆選對 View 的案例 30/30，三次皆涵蓋必要欄位 24/30，三次皆準備 request 28/30。

未通過差異包含快照日期遺漏、額外分組維度與其他聚合／整合表示；保留原始失敗，不改答案提高分數。最後 2 題次保守拒絕，因額外名稱分組的唯一性無法由目前契約證明。

詳見 [實測報告](reports/benchmark-results.md)、[機器可讀稽核](reports/live-benchmark-audit.json) 及 [30 題矩陣](../../../projects/retail/evaluations/task_decomposition_matrix.md)。

## 版本與證據

原始真實呼叫採 `bf626de` 已載入版本；期間修改離線評分及 deterministic 驗證，EDD 原始實驗明確為 `source_unchanged=false`。該證據不當作最終版本的乾淨 live 通過證據。

以 `b16d117` fresh subprocess 逐一核對 90 個 request 的 prompt/schema/契約/題文及 raw response→draft，再重跑目前 validator／request 準備與評分。原始 run 所有檔案 SHA 不變，另外保存新結果及程式 SHA，額外模型呼叫為 0。模型生成 prompt、response schema、契約與題庫在這 90 次呼叫中沒有變更。

- 最終離線稽核：`evidence/EV-20261020T051900-4f8ad1f6.json`，exit 0，來源未變更。
- 完整回歸：`evidence/EV-20261020T051301-71c1c927.json`，370 passed、1 skipped，來源未變更。
- wheel／sdist 建置及安裝後 CLI smoke 通過；私有 Projects 與 `.env` 未打包。
- [獨立審查](reports/independent-review.md)：原 6 類 Important 已修補、負面重播未回歸；獨立 reviewer 再次從原始檔重算 90 項 response/score，與主 agent 結果一致，結論 PASS_WITH_WARNINGS。

## 驗收界線

本次完成規劃功能與 baseline 量測，沒有設定或宣稱模型 100% 正確的通過率門檻。79/90 欄位完整與 60/90 整體結構分數仍是需改善的品質差距，不能把 View 命中率當作整體正確率。

題庫人工審核仍為 pending；自然語言 request、完整整合語意、實際 SQL、資料數值、資料合併與採購決策均未驗證。既有網頁與 SQL API 尚未自動串接新 planner。1 項既有 SQL Server 測試因缺少私有部署 profile 略過。

所有產品變更已提交並保留在 `feat/cross_view`；沒有推送或合併分支。EDD ledger 與私有產物保留於目前 worktree，供後續恢復與稽核。
