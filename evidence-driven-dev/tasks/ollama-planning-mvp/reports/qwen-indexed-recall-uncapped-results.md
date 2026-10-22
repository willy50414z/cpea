# Qwen 解除輸出與時間上限的第一步測試

EXP-019：同題同Qwen及索引prompt，新增 **1次** 自然第一步呼叫。移除輸出token配額與HTTP／外層時間截止後，模型約 **620.1秒（10分20秒）**正常結束，`done=true`、`done_reason=stop`，輸出 **4618 tokens**，完整JSON通過解析與Python裁切。

本題七組主要目標詞 **7/7精確完整**，對應角色、銷售scope、庫存母體與門市×商品粒度符合需求；共9項需求、7個候選views。這是本單題診斷結果，不代表原始基準兩輪38/38或後續來源映射通過。

## 題目與設定

> 對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。

核心source、schema、catalog、messages與前次相同；模型digest、thinking=true、temperature=1、top_p=1、seed=42不變。本次另建uncapped harness，原始及前次harness與結果保持原樣。

- Ollama `num_predict=-1`；評估器input/output累計token配額、wall配額皆取消。
- HTTP connect/read/write/pool timeout與EDD Ledger.run timeout均為None。
- 模型context保留32768，這是模型處理上下文的設定；仍保留輸入可放入context的檢查、單次呼叫守門、索引／角色／scope／View結構驗證。
- 呼叫前離線驗證5001輸出tokens不再被4096配額拒絕、第二次呼叫仍被擋、client確實num_predict=-1與timeout=None；未因此額外呼叫模型。

## 結果

| 需求 | 索引 [start,end) | Python裁切 | 角色 |
| --- | --- | --- | --- |
| 庫存度量 | [8,14) | 盤點庫存件數 | metric |
| 銷售月份 | [16,26) | 2026 年 9 月 | filter |
| 通路 | [26,30) | 線上通路 | filter |
| 折扣度量 | [31,35) | 折扣金額 | metric |
| 淨銷售度量 | [36,40) | 淨銷售額 | metric |
| 盤點日期 | [44,50) | 庫存盤點日期 | attribute |
| 保留母體 | [61,69) | 保留所有庫存商品 | population |

另有「各店各商品的」grain與「準備促銷後補貨評估」metadata，共9項。grain表達門市×商品；未另外拆key類項目，僅憑類別是否出現不自行判失敗，下游實體鍵映射尚未測試。

折扣與淨銷售僅綁定F_TIME／F_CHANNEL；庫存度量與盤點日期沒有這兩個scope。庫存母體明定保留缺貨、需補貨及正常。銷售population中的「已完成訂單」與v_sales_detail契約的summary／grain一致，沒有依該文字額外注入runtime篩選。

七個准入views全數保留，符合第一步recall設計，尚未選最終來源。理由亦指出商品月表無通路欄位、明細表可同時滿足通路及商品級銷售度量；這些理由不替代第二步逐需求契約映射。

## 與前次比較及驗證界線

| 項目 | EXP018只解除時間 | EXP019解除輸出與時間 |
| --- | --- | --- |
| 輸出設定 | 4096上限 | num_predict=-1 |
| 實際輸出tokens | 4096 | 4618 |
| 停止原因 | length | stop |
| 耗時 | 約555.5秒 | 約620.1秒 |
| JSON | 截斷、解析失敗 | 完整、解析通過 |
| 七組目標詞 | 前綴僅見6組 | 7組精確完整 |

輸入6444 tokens。Ollama回報載入約13.1秒、輸入處理約30.3秒、生成約576.3秒（約8.0 tokens/s）。費用未知，亦未量化私有思考／可見JSON各佔多少tokens。此單次比較支持4096上限會截斷這份回覆，不能推論所有題或所有輪次皆正確。

fresh subprocess沿用本次uncapped配額政策，重用既有replay的artifact hash、版本、messages、raw、parsed、Python-derived結果及節點數核對：**PASS**。沒有放寬索引或語意契約。額外fresh subprocess核對7/7目標邊界／角色、scope、母體、7views與契約相容性均通過。

驗證由同一主Agent執行，沒有新增跨Agent獨立oracle核准；此題是先前改寫診斷題，不覆蓋原題oracle及分數。正式Gate與完整端到端仍NOT_VERIFIED，第二／三步未執行。核心source／prompt未改，不冒稱重跑先前156項回歸。

- [無配額設定與single-call守門離線驗證](../evidence/EV-20261021T075735-f75bf9ac.json)
- [本次唯一模型呼叫](../evidence/EV-20261021T075801-cb351f74.json)
- [完整raw重播](../evidence/EV-20261021T080912-146f3d0c.json)
- [目標索引與角色scope核對](../evidence/EV-20261021T081050-aa48bdf2.json)
- [完整結果JSON](qwen-indexed-recall-uncapped-results.json)
- [本次執行程式](run_qwen_indexed_uncapped_probe.py)

原始資料：`.local/qwen-indexed-20261021T075802Z-66d3ec/`。EXP019對此單次診斷假設為SUPPORTED；主Task回到PLANNING。未重試、未自動進第二／三步、未產生SQL或查DB。最新無輸出token／timeout上限偏好持續有效。
