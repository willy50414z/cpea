# Qwen 第一階段第三次測試

EXP-016，依使用者最新「再一次」新增 **1 次** `qwen3.8:27b` 同題第一步呼叫。到 **420 秒整體硬上限**，EDD 終止子程序（exit 124），沒有完整模型答案。索引、分類、scope 與需求完整性均 **NOT_VERIFIED**，假設 **INCONCLUSIVE**。

與前兩次的題文、messages、模型 digest、prompt、schema、catalog、核心 source、harness 與設定核對相同。thinking=true、temperature=1、top_p=1、seed=42、context=32768、output上限=4096、網路read timeout=300秒、EDD hard timeout=420秒。

> 對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。

| 測試 | 停止原因 | 語意結果 |
| --- | --- | --- |
| 第一次 EXP-014 | 約300.4秒 ReadTimeout | 無法評分 |
| 第二次 EXP-015 | 420秒整體逾時 exit124 | 無法評分 |
| 第三次 EXP-016 | 420秒整體逾時 exit124 | 無法評分 |

本次 `/api/ps` 在呼叫進行時回報模型 `size_vram=12603401173`（約12.6 GB）、context=32768；與第一次觀察到的0不同。因此不能聲稱三次執行環境完全相同，也不能由這些數據判定耗時根因。即使觀察到GPU記憶體使用，本次仍未完成；後續應先定位載入、排隊、輸入處理或生成耗時，再決定實驗變項，而不是自動原樣重跑。

沒有完整回答、provider error或usage。實際token與費用未知。因硬終止跳過收尾，初始run.json的calls=0／stopped=null不能代表成功或零呼叫；budget.json已記錄一次嘗試，外部EDD證據記錄exit124。原始檔保持原樣，不補造回覆或錯誤。

fresh subprocess離線核對題文／messages、設定、來源指紋、全部保存檔hash、runtime觀察檔及外部逾時證據 **PASS**。這是檔案與程序驗證，沒有raw可重播，不能當模型品質通過。驗證由同一主Agent執行，非跨Agent獨立驗證。

- [模型呼叫及硬逾時證據](../evidence/EV-20261021T042057-87b8ad21.json)
- [離線驗證證據](../evidence/EV-20261021T042842-e7ac3938.json)
- [完整結果與hash](qwen-indexed-recall-third-results.json)

原始檔：`.local/qwen-indexed-20261021T042058Z-e7e449/`；runtime觀察：`.local/qwen-third-runtime-observation.json`。未修改核心程式或prompt、未執行第二／三步與SQL／DB。保留前三次結果，本輪停止，不自動第四次；主Task回到PLANNING，正式採用Gate不變。
