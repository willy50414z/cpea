# Qwen 第二步逐View覆蓋測試

EXP-020：重用EXP019第一步的9項需求與全部7個候選，不重跑第一步。實際新增 **1次** Qwen呼叫，在第一個 `v_inventory_status` 完成回覆後，因契約證據驗證失敗停止。**嘗試1個、合法通過0個、尚未執行6個**；不能稱全部7個View皆失敗，也不能說第二步全部完成。第三步未執行。

## 設定與停止位置

同一模型digest、thinking=true、temperature=1、top_p=1、seed=42、context32768；維持num_predict=-1，無input/output token配額、HTTP／外層timeout。序列每View最多一次、最多7次，首個provider／解析／契約錯誤保存停止，不自動repair或重試。

本次約 **646.6秒（10分47秒）**，輸入2706、輸出5220 tokens，`done_reason=stop`，JSON完整且Pydantic解析成功。失敗位於第二步第一個節點 `map-01` 的 `validate_coverage`，不是時間或輸出截斷。

## 已確認的證據問題

1. **首個停止原因**：R_GRAIN的entry evidence填 `path=/grain/keys`、`quote=store_id`。實際該路徑是清單 `[store_id, product_id]`，不是可逐字引用的字串，因此報 `invalid contract evidence quote /grain/keys`。JSON pointer可定位清單，但本契約的quote必須引用字串值；如引用清單元素，需要元素路徑，而非把清單當字串。
2. **額外未修補稽核發現**：R_POPULATION的store_id映射只有summary evidence，缺少規定的 `/columns/store_id/description`。
3. **同類缺漏**：R_POPULATION的product_id映射缺少 `/columns/product_id/description`。

三處皆在原始未修改輸出核對。沒有修路徑、補引文、重跑模型或繼續下游。程式驗證規則與prompt保持原樣。

## 庫存View的對照內容

以下「狀態」為**模型自報**；整份ViewCoverage未通過契約，不能把自報supported當正式採用結果。

| 第一步需求 | 模型狀態 | 映射／觀察 |
| --- | --- | --- |
| 門市×商品粒度 | supported | store_id、product_id；頂層grain/keys正確，但entry的keys證據路徑型別錯 |
| 盤點庫存件數 | supported | stock_qty、sum；欄位與引文符合需求 |
| 2026年9月銷售期間 | unsupported | 正確辨認snapshot_date不是銷售日期，sold_qty_30d不是指定月份 |
| 線上通路 | unsupported | 庫存View沒有通路欄位 |
| 折扣金額 | unsupported | 未把庫存成本當折扣 |
| 淨銷售額 | unsupported | 未把sold_qty_30d銷售件數當金額 |
| 庫存盤點日期 | supported | snapshot_date、attribute；欄位與引文符合需求 |
| 促銷後補貨評估用途 | unsupported | 辨認為業務背景，不捏造輸出欄位 |
| 保留所有庫存商品 | supported | 描述保留三種庫存狀態，但兩個識別鍵映射缺少各自欄位描述證據 |

上述主要庫存／日期映射及缺口方向合理，這不豁免證據契約。population文字還寫「依快照日期存檔」，來源契約未保證多期歷史資料，不能由此推論有日期粒度的歷史庫存。完整語意仍不能作獨立核准。

## 其餘Views

`v_product_monthly`、`v_sales_detail`、`v_order_summary`、`v_daily_sales`、`v_store_monthly_kpi`、`v_customer_value` 均 **NOT_EXECUTED**。因此本次沒有月表partial或明細帶月份／通路度量的自然映射結果，不以第一步召回理由替代。

## 驗證

- 模型呼叫前，離線合成控制確認7個coverage節點、沒有recall／selection呼叫；第二個合成回覆證據錯時停止且保留raw／parsed／error。控制不是模型正確率證據。
- fresh subprocess重播唯一自然raw，核對原始第一步來源hash、core source/prompt/schema/catalog、第二步messages與全部保存檔hash，重現相同parsed輸出與 `/grain/keys` 錯誤：**PASS**。
- 另一fresh subprocess直接掃描原始coverage，確認上述三個證據問題與六個view未執行：**PASS**。這是失敗稽核通過，**ViewCoverage本身仍FAIL**。
- 驗證由同一主Agent執行，沒有新增跨Agent獨立oracle。核心source／prompt未改，未重跑先前156項回歸、不宣稱新回歸通過。

證據：

- [離線序列／停止控制](../evidence/EV-20261021T100747-34878c00.json)
- [本次唯一模型呼叫](../evidence/EV-20261021T100802-33d75213.json)
- [自然raw離線重播](../evidence/EV-20261021T101943-dfb8648d.json)
- [三個證據問題核對](../evidence/EV-20261021T102130-1fa8fe6e.json)
- [完整結果JSON](qwen-stage-two-results.json)
- [第二步接續程式](run_qwen_coverage_uncapped_probe.py)

原始資料：`.local/qwen-coverage-20261021T100803Z-e0f13d/`，含請求、raw、parsed與error；EXP019第一步資料保留原樣。固定自然第二步的全數合法標準未達，EXP020結論REFUTED，不能否定所有逐View方法或未執行的六個View。主Task回到PLANNING；無token／timeout上限偏好持續有效，不自動補答案、重試或第三步。
