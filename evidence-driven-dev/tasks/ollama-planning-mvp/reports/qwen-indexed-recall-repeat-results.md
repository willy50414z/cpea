# Qwen 第一階段第二次測試

EXP-015，依使用者「再一次」新增 **1 次** `qwen3.8:27b` 第一階段呼叫。這次到 **420 秒整體硬上限**，EDD 終止子程序（exit 124）；未取得可保存的完整模型答案。語意結果 **NOT_VERIFIED**，片段完整率與分類無法評分，假設 **INCONCLUSIVE**。

與 EXP-014 的題目、完整 messages、模型 digest、prompt、schema、catalog、核心程式、診斷 harness 與設定逐項核對相同；thinking=true、temperature=1、top_p=1、seed=42、context=32768、output 上限=4096。網路讀取 timeout=300 秒，外部實驗硬上限=420 秒；300 秒不是整體執行上限。

> 對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。

| 測試 | 結果 | 索引／分類 |
| --- | --- | --- |
| Qwen 第一次 EXP-014 | 約300.4秒 ReadTimeout | 無法評分 |
| Qwen 第二次 EXP-015 | 420秒整體逾時，exit 124 | 無法評分 |

本次未回傳 usage，實際 token 與費用未知。不能僅由超過300秒推定串流內容、速度或逾時根因。因外部硬終止，`run.json` 最後收尾未執行，初始 calls=0／stopped=null 不代表零次呼叫或成功；`budget.json` 已記錄一次嘗試，外部 EDD 證據記錄 exit 124。原始檔均原樣保留，未補造模型 raw 或 provider error。

fresh subprocess 離線核對請求、設定、來源指紋、全部保存檔 hash 與外部逾時紀錄：**PASS**。沒有完整回覆，故無法進行模型 raw replay，不能把檔案核對當成模型驗收通過。驗證由同一主 Agent 執行，非跨 Agent 獨立審查。

- [呼叫與420秒硬逾時證據](../evidence/EV-20261021T041042-c4724be2.json)
- [離線檔案驗證證據](../evidence/EV-20261021T041812-51640ddf.json)
- [完整結果 JSON](qwen-indexed-recall-repeat-results.json)
- [離線驗證程式](verify_qwen_indexed_repeat.py)

沒有修改核心程式或 prompt，未執行第二／三步與 SQL／DB。兩次結果各自保存；本輪停止，不自動第三次、修改 thinking 或提高 timeout。任務回到 PLANNING，完整採用 Gate 不變。
