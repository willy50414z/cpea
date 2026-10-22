# 完整需求涵蓋優先：DeepSeek 成對測試

已新增候選 prompt `v3-coverage-first-1`，在原有政策之前明列優先順序；本輪候選未通過單題語意門檻，產品 v3 預設沒有切換。

## 優先順序

1. 完整涵蓋必要欄位與資訊，包括輸出／度量、條件／期間、粒度、母體、整合鍵及子任務 request；條件欄位即使不顯示仍是必要欄位，文字承諾不能代替來源與 typed 結構。
2. 只在完整涵蓋需求的來源組合中選足夠且必要的來源；已彙總或粒度接近不能抵銷條件缺漏，有合格來源就應選用。
3. 再比較來源數、彙總工作與整合便利性；確實沒有合法組合才回報 unsupported，需求資訊不足才 needs_clarification，不可帶缺口回傳 ready。

## 需求與方法

> 對照各店各商品目前庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，準備促銷後補貨評估；保留所有庫存商品。

使用 DeepSeek-V4.1-Flash，原版與候選各一次首次生成，依序原版再候選；沒有提供歷史回答、GPT 答案、oracle 或事後追問內容。共同使用同一完整七 View 契約、decision_summary／decision_chain schema、temperature=1、top_p=1、seed=42、輸出4096、context16384、timeout300秒、SDK retries=0。

兩組 messages 唯一差異是 system 中的優先序。原版輸入估計10711 tokens，候選11053；候選加輸出4096與安全預留1024為16173，符合16K。兩次合計約51秒。GPT 沿用先前安全參考，不新增 GPT 呼叫。

## 結果

| 項目 | 本輪原版 | 本輪候選 |
|---|---|---|
| 銷售來源 | v_product_monthly | v_product_monthly |
| 銷售 filters | sales_month = 2026-09-01 | sales_month = 2026-09-01 |
| online 條件 | 缺漏 | 缺漏 |
| 兩項金額 | sum(discount_amount)、sum(net_sales) | 相同 |
| 草稿狀態 | ready | ready |
| 未解事項 | unsupported_reasons 非空 | unbound_inputs、clarifications、unsupported_reasons 非空 |
| 驗證後狀態 | error | error |
| 下游 prepared requests | 0 | 0 |
| 原自動分 | FAIL | FAIL |
| 主 agent 依既有 oracle／契約核對 | 不符合需求 | 不符合需求 |

候選草稿的 unbound_inputs 原文：

> v_product_monthly 契約不含 sales_channel 欄位，無法在來源層套用線上通路條件；若需嚴格限定 online，需改用含 sales_channel 的 v_sales_detail 並自行彙總，或由外部提供通路歸屬。

候選草稿還詢問是否允許改用 `v_sales_detail`，但題目沒有禁止該來源，契約也明示 `order_month` 可供月度篩選。這是已知合格來源存在、卻仍保留不合格來源並列出不必要澄清的可觀察結果；不能據此斷言其內部錯誤成因。

候選的庫存計畫另使用 `sum(stock_qty)`，原版保留庫存屬性並多選備貨欄位；這些差異完整保留，沒有自動修正。主失敗判定只需已確認的銷售來源與通路條件缺漏，不依賴額外差異。

本輪兩個 raw 草稿都自稱 ready，但既有驗證器均拒絕並沒有產生下游 payload；不可與前次曾回傳 unsafe ready 的歷史結果混為一談。

## 驗證與界線

兩筆 raw→draft→response／原分／sidecar 重播一致；artifact hash、程式／契約／題文指紋、messages 唯一差異及歷史原版 messages 一致性均核對通過。四個既有 schema SHA256、原 v3 prompt 常數與預設版本不變。相關回歸96 passed。

同一主 agent 依既有獨立 oracle 與契約判讀，沒有新增跨 agent 審核。H8 在這個固定單題、每版一次的實驗未獲支持；不能推論所有優先序提示都無效，也不能估計整體正確率或確認因果。沒有自動追加模型重跑、擴題、SQL／DB 或 Ollama 呼叫。

完整草稿、六類決策紀錄、原分與診斷見[機器比較資料](coverage-priority-comparison.json)。原始 request／call／result 保存在本 Task 的 `.local/coverage-priority-20261020T160325Z-d48244/`。
