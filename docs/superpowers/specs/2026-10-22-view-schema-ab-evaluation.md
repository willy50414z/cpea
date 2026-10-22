# View Schema 修改前後評估規格

## 目的與範圍

以既有正常查詢中歷史成功 10 題、歷史失敗 10 題組成固定測試集，使用 Azure `DeepSeek-V4.1-Flash` 比較 view schema 修改前後的 text-to-SQL 正確率與重複穩定性。

本規格只訂定評估條件，不代表新版 view schema 已核准或完成。先前提出的 schema 設計仍須形成並審閱完整規格，再進入實作。不得提前修改契約後才取得前測。

## 固定案例與選樣證據

- 歷史來源：`evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl`，共 90 筆原始 trial。
- 原始題庫：`projects/retail/evaluations/cases.jsonl`，不修改原文或預期答案。
- 僅納入 `normal` 類型；成功須歷史三輪 mapping、SQL 均通過，失敗須三輪均未完整通過。
- 歷史正常查詢有 12 題成功、12 題失敗。其中 `RETAIL-CUSTOMER_VALUE-S3-03` 包含 provider 逾時，不用傳輸故障作為 schema 語意失敗樣本；剩餘 11 題失敗可供選樣。
- 固定 seed `20261022`。依 View 名稱排序輪流取樣，各 View 內依 `SHA256(seed:case_id)` 排序，兩組各取 10 題；不依本次 Azure 輸出改選。
- 選樣 JSON、逐題歷史判分、原文與歷史來源 SHA-256、固定題庫及修改前 profile 快照保存在 `projects/retail/artifacts/view-schema-ab/20261022-20case-deepseek/`。
- `cases.jsonl` 是原題庫完整 JSONL 行的複本。模型只接收問題及允許的 catalog context，不接收 cohort、Oracle 或歷史結果。

| 歷史組別 | 案例 | 歷史通過 |
|---|---|---|
| 成功 | `RETAIL-INVENTORY_STATUS-S2-04` | 3/3 |
| 成功 | `RETAIL-ORDER_SUMMARY-H3-03` | 3/3 |
| 成功 | `RETAIL-PRODUCT_MONTHLY-H1-04` | 3/3 |
| 成功 | `RETAIL-SALES_DETAIL-H2-03` | 3/3 |
| 成功 | `RETAIL-STORE_MONTHLY_KPI-H2-04` | 3/3 |
| 成功 | `RETAIL-INVENTORY_STATUS-M2-05` | 3/3 |
| 成功 | `RETAIL-ORDER_SUMMARY-M2-03` | 3/3 |
| 成功 | `RETAIL-SALES_DETAIL-M2-02` | 3/3 |
| 成功 | `RETAIL-STORE_MONTHLY_KPI-S1-01` | 3/3 |
| 成功 | `RETAIL-INVENTORY_STATUS-H1-01` | 3/3 |
| 失敗 | `RETAIL-CUSTOMER_VALUE-H1-02` | 0/3 |
| 失敗 | `RETAIL-DAILY_SALES-S3-03` | 0/3 |
| 失敗 | `RETAIL-INVENTORY_STATUS-H3-05` | 0/3 |
| 失敗 | `RETAIL-ORDER_SUMMARY-S1-01` | 0/3 |
| 失敗 | `RETAIL-PRODUCT_MONTHLY-M3-04` | 0/3 |
| 失敗 | `RETAIL-STORE_MONTHLY_KPI-H3-01` | 0/3 |
| 失敗 | `RETAIL-CUSTOMER_VALUE-S2-02` | 0/3 |
| 失敗 | `RETAIL-DAILY_SALES-M1-05` | 0/3 |
| 失敗 | `RETAIL-ORDER_SUMMARY-M3-01` | 0/3 |
| 失敗 | `RETAIL-PRODUCT_MONTHLY-S2-05` | 0/3 |

歷史來源使用 Ollama `qwen3.8:27b`；它只提供選樣依據。固定樣本的歷史 50% 不能當成 Azure 前測正確率。

## 前後測條件

| 項目 | 固定條件 |
|---|---|
| Provider／deployment | Azure／`DeepSeek-V4.1-Flash`，沿用既有模型設定 |
| Azure 認證 | 根目錄 `.env` 的專用 endpoint／key；機密不寫入報告 |
| 被測流程 | 現有單題 text-to-SQL，自然檢索、映射、選 View 與 SQL 生成；不改測 query pipeline 或注入 gold View |
| Prompt | MATCH v10，前後 system／human／response schema 指紋相同 |
| 模型參數 | temperature 0、top_p 1、seed 42；context 16000、max output 8192、timeout 300 秒 |
| 檢索與編譯 | lexical、原 rerank／candidate 設定、PostgreSQL、compiler 與判分器固定 |
| 次數 | 每階段 20 題 × 3 輪 = 60 trials；兩階段共 120 trials，模型呼叫數另計 |
| 併發 | 1，前後題目及重複次序相同 |
| 詞彙／確認 | 每 trial 空白隔離詞彙 repository，不代選確認答案 |
| DB | 不執行 SQL、不讀取業務資料；SQL 靜態正確與資料數值正確分開 |
| 唯一允許差異 | 核准的 view schema／YAML 與使其完整傳遞所必要的 adapter／renderer；不得同時調整模型、prompt、選樣、Oracle 或比較策略 |

前測使用凍結的 v3 profile；後測使用完成核對的新版 profile。兩階段保存 profile 指紋、source／settings／prompt／判分器指紋及來源差異。版本無法由 provider 證實時明記限制。

現有 live evaluator 要求乾淨工作目錄。原工作目錄有使用者文件變更，須使用經同意建立的隔離 worktree，不撤銷變更、不繞過 preflight。修改後尚未提交的版本如何固定為乾淨評估來源，須在實作計畫明確處理；不得擅自提交。

## 判分與比較

沿用 `grade_view_matching` 的原 Oracle，只有 mapping 與 SQL 同時通過才算嚴格通過。JSON 可解析、SQL 可編譯、回傳 ready 或三次 SQL 相同，均不能單獨算正確。正常查詢的非預期 pending／澄清／unsupported 列為未通過，不代選後重試。

主要報表：

1. 每輪正確率：各輪通過數／20，前後列百分比與百分點差。
2. 全 trial 正確率：每階段通過數／60，保留固定分母。
3. 三輪全通過率：三輪均通過題數／20；另列混合結果與三輪全失敗。
4. 歷史成功／失敗兩組：各組通過數／30，以及三輪全通過題數／10。
5. 配對轉移：每個 case／repetition 的前後通過狀態，列改善、退步、持續成功與持續失敗；另列題目層級轉移。
6. 分層診斷：檢索是否包含原目標 View、mapping、SQL、澄清／確認、provider／parse／contract error、呼叫數、tokens 與延遲。

某些問題可能有其他合法 View／SQL。保留原嚴格成績，另外審查替代方案的欄位、資料母體、粒度、期間與計算是否等價；不能在看過後測結果後放寬 Oracle，再宣稱原測試改善。

三輪不是 60 個獨立業務問題；此測試集以已知成功／失敗各半組成，並非真實流量或盲測。報告不以小樣本宣稱整體產品正確率。

## 產物、錯誤與狀態

- 每次執行寫新目錄，保存逐題 generation、mapping／QueryPlan／SQL、原始 call trace、錯誤及版本 metadata；不覆寫歷史紀錄。
- SDK retries 為 0；不因錯誤或低分重新抽答案。保留產品既有解析修復呼叫並計入實際模型成本。
- provider 故障立即保存診斷、停止後續呼叫，後續題列 skipped／未觀測；不得刪題縮分母，也不得把未觀測說成語意失敗。
- rate limit 不重跑，依 repository AGENTS.md 的 quota.py 流程處理。
- 題庫與自然輸出仍未人工核准，結果標為探索性自動評估；不冒充正式人工驗收。
- 最終比較表在前、後測實際完成後才填數字，未測維持未測。

目前已完成選樣、20 題原 Oracle validator 驗證及 v3 profile 快照一致性檢查。尚未呼叫 Azure；前測與後測皆未執行。
