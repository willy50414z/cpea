# 測試結果與恢復摘要

保存日期：2026-10-20。使用者要求壓縮上下文並保留測試結果；後續恢復時不要自動重新執行模型測試。

## 狀態與範圍

- 程式版本：`bc09c67fc4078501599c37e4cdfecdee40af2ef8`，分支 `feat/cross_view`。
- EDD 任務已完成；測試僅驗證跨 View 需求拆分、欄位與準備 text-to-sql request，不生成或執行 SQL。
- 主 agent 直接實作與測試；最新 Ollama 單輪已完整結束。
- 程式回歸：391 passed、1 skipped（缺少私有 SQL Server profile）。

## 三模型完整單輪

| 指標 | Azure gpt-6-sol | Azure DeepSeek-V4.1-Flash | Ollama qwen3.8:27b |
|---|---:|---:|---:|
| 完成題數 | 30/30 | 30/30 | 30/30 |
| 主要 View 任務配置命中 | 30/30 | 27/30 | 29/30 |
| 來源與必要欄位原評分 | 30/30 | 26/30 | 21/30 |
| Request 結構就緒 | 30/30 | 22/30 | 11/30 |
| 完整結構自動檢查 | 30/30 | 18/30 | 7/30 |

- 題庫、prompt v3、Human 訊息 schema、View 契約、grader 相同；Azure temperature=1、JSON object；Ollama temperature=0、thinking=True、native JSON schema，生成設定並非完全相同。
- Ollama 01、03、05、19 共四題漏列使用欄位，原 grader 日期 alias 規則仍算對，但 validator 已阻擋。因此 21/30 不是完整欄位正確率；僅扣除已確認漏判為 17/30，原始分數不回寫。
- ready 與結構通過均不代表全面語意核准；所有逐題正式人工語意審查仍 pending。
- GPT 第一輪完整 30 筆；第二輪中途依使用者要求停止，另有 17 筆已完成結果，不混入完整單輪比較；一筆停止時仍在途的結果未知，可能計費。
- 本地完整 30 次模型呼叫，失敗 0、略過 0，耗時約 3 小時 9 分鐘；與既有本地工作共用服務，不能視為隔離效能測試。
- Ollama digest：`aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`，Q4_K_M；SDK timeout 900 秒；未修改 .env。

## 原始結果與證據

- 完整繁體中文報告：`reports/ollama-results.md`。
- 統計、設定與雜湊：`reports/ollama-audit.json`。
- 離線重播程式：`reports/audit_ollama_round.py`；已重新驗證雲端 77 筆與本地 30 筆，合計 107 筆。
- 本地實測證據：`EV-20261020T061323-aa90f27b`，exit 0、source_unchanged=true。
- Fresh 重播證據：`EV-20261020T092232-0cabb01a`，exit 0、source_unchanged=true。
- 本地原始產物：`projects/retail/artifacts/task_decomposition/20261020T061325410052Z-bc09c67f-ollama-0e14eb`。
- DeepSeek 原始產物：`projects/retail/artifacts/task_decomposition/20261020T055210984742Z-bc09c67f-432a10`。
- GPT 原始產物：`projects/retail/artifacts/task_decomposition/20261020T054500378064Z-bc09c67f-26fc31`。
- 既有修正與雲端比較：`reports/fix-results.md`、`reports/model-comparison-audit.json`。

## 恢復注意事項

保留所有原始回覆與原始分數。依使用者下一個指令繼續；不要為保存上下文重新測試、改 grader、查詢資料庫或停止其他本地工作。不要輸出 .env 密鑰或原始私有 reasoning 內容。
