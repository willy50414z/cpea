# 參考 text-to-sql 篩選 View 的 prompt 調整結果

決策：**v6 未達標，恢復原 v3 預設；候選 prompt 與全部測試保留於任務產物**。這是固定三十題單輪的同批對照，並非統計顯著性或所有題目已正確的證明。

## 改動依據與最終候選

參考 `sql_generation.py::_match_candidates` 與 `prompts/match/v10.txt` 的候選映射：逐項檢查欄位語意、條件、粒度與口徑；來源名稱相近不代表可承接。planner 需要跨來源聯合覆蓋，所以不能把單 View 流程的整題單來源限制直接套過來。

v6 在既有 v3 上小幅修訂：

- 先把資訊、條件與期間分配到子需求，再逐候選確認指標、篩選欄位及合併鍵；無法承接就改選合法來源，不以文字冒充已完成的篩選。
- 各來源完成自己的部分即可，不要求每個 View 單獨滿足整題。
- 已有旗標／統計值不重問計算基準；準備評估資料不多問精確決策門檻。
- 顯示欄位須有明確輸出角色；頂層與 task 的 JSON 欄位分清楚。

日期、通路、條件計數、母體保留及 integration 規則沿用 v3。一次模型呼叫完成規劃，不新增檢索節點或多輪修補。兩版 human context、schema、View 契約、題庫與 grader 完全相同，只有 system prompt 改變。

## 最終成對結果

| 指標 | 原版 v3 | 候選 v6 |
|---|---:|---:|
| 主要 View 任務配置 | 27/30 | 27/30 |
| 來源與必要欄位原評分 | 25/30 | 26/30 |
| Request 結構就緒 | 18/30 | 16/30 |
| 完整結構自動通過 | 15/30 | 16/30 |

兩版各完成 30 次 Azure DeepSeek-V4.1-Flash 呼叫，provider 失敗／略過均為零；逐題輪替先後順序。共同設定 temperature=1、top_p=1、seed=42、context_window=16384、max_output_tokens=-1、timeout=300 秒、SDK retries=0、JSON object。

原版輸入／輸出 tokens：223,950／26,671；候選：230,220／27,648；總 tokens 比約 1.03。累計模型呼叫耗時分別為 161.9 與 236.9 秒，未控制快取／網路／服務負載，不推估計費金額。

自動結構改善案例：cross-view-02, cross-view-11, cross-view-17, cross-view-20, cross-view-24。

自動結構退步案例：cross-view-08, cross-view-10, cross-view-18, cross-view-28。

採用標準預先固定為來源／欄位、ready、自動結構皆不下降，且至少一項增加；本次 未達到。不因某單項進步就忽略其他退步，不針對候選改答案。

## 限制與未通過項目

- 所有題目都是既有、已見三十題，沒有新外部 holdout，未做多輪穩定性測試。
- 相同 v3 在先前不同執行已有 18/30、16/30 等不同結果，因此不能用跨批次分數代替本次成對比較，也不能把一次差異解讀為穩定因果。
- View／欄位原評分不是完整語意正確率。已知日期 alias 寬鬆規則可能放過使用欄位漏列；本批相關案例：{"v3_raw": [], "v6_raw": []}。原分保留。
- 自動評分未涵蓋所有等價表示，也可能放過額外聚合、必要值僅列 required_columns、未證明的單值屬性等問題。補充風險整理於 `prompt-v6-review.json`，需正式逐題人工語意審查；不自行加分或把所有自動未過視為真實語意錯誤。
- ready 只代表通過現有結構驗證並備妥 request，沒有生成或執行 SQL、查 DB、驗證實際資料或採購結論。模型輸入沒有 oracle、題號或 GPT 答案；本次沒有 GPT／Ollama 呼叫。

## 未採用的實驗

先嘗試明列解析後全部欄位能力與完整重寫 prompt。v4 因 task 專用 unbound_inputs 被放到頂層，執行到 16 筆完整回覆後中止；原始結果未覆寫，另有一筆 in-flight 結果未知且可能計費，不能當作完整輪次。

修正欄位層級後，v5 完整三十題同批對照：來源欄位 23 → 27，ready 21 → 15，自動結構 16 → 9。整體未達標，已撤回 context／workflow 變更及其專用新增測試；原型、patch、失敗與 392/1 測試證據仍保留。不能僅由該組合對照區分是 prompt 還是 context 造成退步。

最終候選只改 prompt，不保留未達標的程式或契約呈現改動；本輪不再追加 prompt 調參。

## 驗證與版本

模型原始產物：`evidence-driven-dev/tasks/retail-planning-stages/.local/prompt-v6-20261020T113508Z`。原始輸入、最終 JSON、usage、prepared requests 與原分均保存。

候選固定 HEAD：`bc09c67fc4078501599c37e4cdfecdee40af2ef8`，另有已記錄的工作樹差異 SHA-256：`fa3eb2f3cdde636391cb376923ecf2f0bf36197a68143e08438093f217896aea`；不能只用 HEAD 當作候選版本。prompt／harness／題庫與契約指紋見 run.json；`prompt-v6-audit.json` 已 fresh 重播六十筆並逐題核對兩版 human context 相同。

恢復 v3 後完整回歸 **391 passed／1 skipped**，略過原因為缺少私有 SQL Server profile，證據 `EV-20261020T114258-46fc2ee0`。最終產品沒有保留程式碼變更。

在恢復後的相同 validator／grader 上，fresh 重播 v4 部分 16 筆、v5／v6 各 60 筆，合計 **136 筆已保存回覆**，原始訊息、回應、payload 與原分一致；證據 `EV-20261020T114415-e09774d7`。不包含一筆中止時在途且結果未知的呼叫。

調整版保留於 [v6 候選 prompt](../.local/prompt-v6-candidate.py)，對應 patch 為 `../.local/prompt-v6.patch`，供後續審閱；未作為產品預設。

測試與驗證均由同一主 agent 使用既有 oracle 與 fresh subprocess 執行，沒有冒稱跨 agent 獨立驗收。早期 EDD 任務及三階段負結果維持原樣。

## 逐題自動結構結果

| 案例 | v3 | v6 |
|---|---|---|
| cross-view-01 | 通過 | 通過 |
| cross-view-02 | invalid_plan | 通過 |
| cross-view-03 | 通過 | 通過 |
| cross-view-04 | ready | invalid_plan |
| cross-view-05 | 通過 | 通過 |
| cross-view-06 | 通過 | 通過 |
| cross-view-07 | 通過 | 通過 |
| cross-view-08 | 通過 | invalid_plan |
| cross-view-09 | invalid_plan | invalid_plan |
| cross-view-10 | 通過 | needs_clarification |
| cross-view-11 | invalid_plan | 通過 |
| cross-view-12 | 通過 | 通過 |
| cross-view-13 | 通過 | 通過 |
| cross-view-14 | ready | invalid_plan |
| cross-view-15 | 通過 | 通過 |
| cross-view-16 | invalid_plan | invalid_plan |
| cross-view-17 | invalid_plan | 通過 |
| cross-view-18 | 通過 | invalid_plan |
| cross-view-19 | invalid_plan | invalid_plan |
| cross-view-20 | needs_clarification | 通過 |
| cross-view-21 | invalid_plan | invalid_plan |
| cross-view-22 | invalid_plan | invalid_plan |
| cross-view-23 | invalid_plan | invalid_plan |
| cross-view-24 | invalid_plan | 通過 |
| cross-view-25 | invalid_plan | invalid_plan |
| cross-view-26 | ready | invalid_plan |
| cross-view-27 | 通過 | 通過 |
| cross-view-28 | 通過 | invalid_plan |
| cross-view-29 | 通過 | 通過 |
| cross-view-30 | 通過 | 通過 |
