# GPT-6 Sol：B1 失敗四題的單次診斷

依使用者新授權，對上一輪 B1 失敗的 07、09、14、28 各呼叫 Azure `gpt-6-sol` 一次，沒有重試或局部修正。B1 的語意 prompt、SemanticPlan schema、七個 View、編譯器與護欄均維持凍結版本；原始失敗與分數不改。本輪是診斷對照，不能替代 DeepSeek 完整 Gate 或啟動 Ollama。

**端到端安全可用為 3/4。四份語意骨架皆可依既有 oracle 與契約證據核准；第 14 題被凍結護欄的已知 FD 誤拒擋下，仍算端到端失敗。** 本輪逐題語意審查由主 agent 執行，使用前輪獨立核准的 oracle、FD 與等價依據，未另派獨立 reviewer。

| 題目 | 凍結流程 | 可見規劃決策與核對結果 | 推理 token |
|---|---|---|---:|
| 07 | ready，通過 | 庫存為店×商品母體；九月 online 銷量按店×商品彙總，以兩個完整鍵 left merge，沒有混合不同門市。 | 322 |
| 09 | ready，通過 | 銷售保留店×商品×日查詢粒度與含 9/14 的期間，再 nest 回店×商品；snapshot_date 只放 attribute，沒有日期雙角色。 | 213 |
| 14 | error，不通過 | 每店條件 COUNT(product_id WHERE stock_qty=0)，保留零缺貨門市、日期 metadata 與九月目標；額外 store_name 被護欄拒絕。 | 386 |
| 28 | ready，通過 | 庫存成本與單月商品毛利按店×商品對齊，KPI 僅按店作背景；固定月份下單列原值合法，沒有按商品重加總目標。 | 398 |

上表是從可見結構化輸出核對的規劃決策，並非模型內部思維鏈或模型回傳的推理摘要。

## 第 14 題的失敗邊界

實際凍結流程唯一錯誤為 `inventory_by_store: attributes lack uniqueness proof`。`store_name` 可由 `projects/retail/contract_review.md` 的 stores 主鍵與 inventory JOIN 主鍵證據，證明由 store_id 決定；前輪獨立 reviewer 已對原第 15 題核准同一來源、同一展示欄位的 FD。凍結護欄尚未編碼這項證據，因此保守誤拒。

COUNT 與 COUNT DISTINCT 在庫存來源的真 store×product 唯一列下等價；條件留在 conditional_metrics、未變成全域 filter，零缺貨門市仍保留。以記憶體列見證兩者均得到 `{1: 1, 2: 0}`。這項證明不適用於唯一鍵有爭議的 sales_detail。

另做一次**零模型的離線診斷**：相同 draft 通過原有 validator，能組裝兩份 payload（586、399 字元）。沒有改寫本次 error，也沒有把這兩份診斷 payload 計入端到端成績；B1 的護欄與產品程式未修改。

## 推理資料保存

本輪使用 Responses API，明確傳入 `reasoning={"effort":"medium","summary":"auto"}`。回應將摘要設定記為 detailed，但四筆 reasoning item 的 `summary` 都是空陣列，沒有可讀的 reasoning content；四筆均附有 `encrypted_content`，已原樣保存，沒有解密或另請模型補寫。

[官方文件](https://developers.openai.com/api/docs/guides/reasoning)說明 API 不公開完整原始推理 token，可明確要求推理摘要。本輪的可讀推理摘要仍為 **0/4**，因此不能聲稱已取得可閱讀的完整推理過程。推理 token 數與加密內容也不能當成可讀推理文字。

完整保存位置為本 Task 的 `.local/gpt-sol-b1-failures-20261020T131351Z-7d555a/`：

- `cross-view-XX-request.json`：實際 API 請求，包含原 prompt、契約與 schema。
- `cross-view-XX-raw.json`：完整 SDK 解析回應，包含 API 回傳的加密 reasoning。
- `cross-view-XX-reasoning-items.json`：另外封存的 reasoning item，包含原始 encrypted_content；不可讀、未解密。
- `cross-view-XX-reasoning.json`：摘要缺測狀態及推理 token 記錄。
- `cross-view-XX-result.json`：可見 JSON、SemanticPlan、編譯 draft、prepared requests、原分及 sidecar。
- `run.json`：呼叫數、設定、時間、指紋與原檔 SHA256。

逐題 reasoning 封存路徑與 hash 見[機器摘要](gpt-sol-failure-probe.json)的 `reasoning_archive`。原始回應與加密內容均留在 Git 忽略的本機目錄。

## 用量、驗證與限制

總計 **4 次呼叫、約 33.5 秒**，input 26,846、output 2,840、total 29,686 tokens；output 內含 1,319 reasoning tokens，不重複相加。單次輸出上限 7,168，SDK retries=0，store=false；沒有 SQL／DB 或 Ollama 呼叫。

四筆 raw→可見輸出→骨架→編譯→payload／原分／sidecar 均在新 subprocess 中重播一致，原始檔 hash、凍結版本與題目核准指紋一致；相關回歸 **81 passed**。證據為 `EV-20261020T131348-0144f2c0`、`EV-20261020T131636-0594c38e`、`EV-20261020T131406-a2a6f2ba`。

這四題是已見失敗集，且 GPT 使用 Responses／medium reasoning，DeepSeek 前輪使用 Chat Completions；本輪未傳 temperature、top_p、seed，不能當成只有模型名稱改變的嚴格同設定比較。結果支持先離線改善欄位角色一致性與契約 FD 證據表達，沒有證明 DeepSeek 已通過六題、十題或兩輪 38/38 Gate。
