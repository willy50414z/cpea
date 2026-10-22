# 明確盤點庫存題：時間語意診斷

**結果：模型將盤點日期列為輸出屬性，沒有再建立庫存日期篩選；但第一步逐字引用檢查失敗，庫存View對照未執行。** 本次不是整題通過，也尚不能證明來源映射正確。

## 題目與驗收範圍

> 對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。

新題使用獨立ID `cross-view-11-explicit-snapshot`。移除現有契約沒有保證的「目前」，明示顯示盤點日期，不假設資料最新。原題、oracle、契約、prompts、schemas及歷史raw／分數均不修改。

預定兩次fresh DeepSeek：需求拆解、指定庫存View映射各一次，僅隔離時間語意，不測其他六來源或最終選擇。EXP-011在呼叫前保存：最多2calls、30000 input、8192 output reserve、單次4096 output、context32768、safety1024、timeout300秒、wall900秒、SDK retries=0；錯誤停止、不repair或續接。

## 已觀察輸出

| 項目 | 原題實測 | 本次改寫題實測 |
|---|---|---|
| 庫存時間需求 | 「目前庫存」分類為filter | 「並顯示庫存盤點日期」分類為attribute |
| 額外庫存日期filter | 有，後續映射成IS NOT NULL | 第一步沒有建立；第二步尚未執行 |
| 銷售條件 | 九月、online約束兩項金額 | 九月、online仍約束兩項金額 |
| 最終輸出粒度 | 第一步未單列grain需求 | 明列各店各商品的grain需求 |
| 程式檢查 | 原題第一步通過 | 本次第一步引用檢查失敗 |

本次11個需求、全部七View候選；盤點日期項目的原文：

```json
{"quote":"並顯示庫存盤點日期","business_object":"庫存","kind":"attribute","scope_ids":[]}
```

這顯示時間角色拆解方向符合改寫，但尚未真正映射到 `snapshot_date`，不能把概念上的attribute直接當成欄位映射已正確。

## 實際停止原因

淨銷售額需求的quote被模型寫成：

> 2026 年 9 月線上通路的...淨銷售額

題目沒有 `...`。規則要求quote是原題逐字連續片段，因此 `validate_recall` 回報 `req_online_channel_net_sales_2026_09: request quote does not exist`。其餘10項quote存在，但整份第一步仍拒絕；第二次呼叫未花費。沒有自動刪省略號、替換引文或重新詢問來換取通過。

另外，第一步把「準備促銷後補貨評估」列為metadata；是否會造成不必要欄位需求尚未驗證，不能宣稱其餘語意全部正確。

## 契約與原題答案的判讀補正

現有庫存契約只定義店×商品唯一列、盤點日期，並未保證最新或目前。既有[契約審查](../../../../projects/retail/contract_review.md)也明記View不限制snapshot_date、歷史儲存模式待確認。因此原題對「目前」的疑慮應標為題目／契約時間語意不足，不能僅憑舊oracle就定為模型錯誤。舊oracle與分數保留，原題作為必須ready正例的適用性待重新審核；庫存證據路徑格式錯誤仍是獨立問題。

## 證據與結論

- 實際新增 **1次DeepSeek**，input5611／output1482 tokens，約14.03秒；Azure部署美元成本未知。未使用剩餘一次預算。
- [首次實驗證據](../evidence/EV-20261021T030934-e2fd34ef.json)：source unchanged，第一步quote檢查錯誤停止。
- [Fresh subprocess重播](../evidence/EV-20261021T031036-7617dfc7.json)：1筆raw重播與相同停止結果一致，artifact集合／hash核對通過。
- [機器摘要](snapshot-inventory-probe.json)、[診斷腳本](run_snapshot_inventory_probe.py)。raw位於Task `.local/snapshot-inventory-20261021T030935Z-3d22d9/`，不覆寫歷史結果。
- 同一主agent執行及核對，沒有新增獨立oracle或跨agent核准；本輪沒有產品／契約／prompt／schema變更，未重跑先前135個單元測試。新兩節點診斷harness先以離線注入資料完成smoke，再以實際raw重播驗證。
- **時間分類有符合預期的觀察，但庫存映射與完整流程NOT_VERIFIED；EXP-011整體INCONCLUSIVE。** 不擴題、不自動修正或重跑；無SQL／DB／Ollama／提交／推送。
