# Qwen 取消時間截止後的第一步結果

EXP-018：依使用者「等到它結束為止」，取消 HTTP 與外層時間截止。單次 `qwen3.8:27b` 實際約 **555.5 秒（9分15秒）**後結束。Ollama 回報 `done=true`、`done_reason=length`、輸出 **4096 tokens**，達既有輸出上限；JSON 在 requirements 第八個完整物件後截斷，缺少後續需求與 candidate_views，第一步解析 **FAIL**。不是本次時間逾時，也不能當成完整語意驗收通過。

前三次及第四次紀錄保留。第四次EXP017已於07:36:22 UTC被既有420秒上限終止；處理新指示時無法續接，已說明後另立本次單一呼叫。兩筆不合併或替換。

## 設定與耗時

核心 source、題文、完整 messages、prompt、schema、catalog 相同；thinking=true、temperature=1、top_p=1、seed=42、context32768、output上限4096。另建等待版harness保留原程式，改 HTTP timeout=None；由 EDD Ledger.run(timeout=None) 記錄。已在呼叫前實讀HTTP client的connect/read/write/pool均None。Budget的900秒僅供呼叫前預算核對，不會終止進行中的單次呼叫；本次無外部截止。

- 輸入6444 tokens、輸出4096 tokens；費用未知。
- Ollama載入約13.1秒、輸入處理約30.3秒、生成約511.8秒（約8.0 tokens/s）。這是本次provider metadata，不證明先前每次都在相同階段耗時。
- 未保存或分析私有推理內容；不能把全部4096 tokens當作可見JSON長度或斷言思考／答案各佔多少。

## 已輸出的部分片段

以下由原始截斷字串中已完整的物件取得索引，再由Python裁原題，只作診斷展示。沒有補括號、修復JSON或送回runtime，整份回答仍不合法。

| 需求 | 索引 [start,end) | Python裁切 |
| --- | --- | --- |
| 粒度 | [2,8) | 各店各商品的 |
| 庫存度量 | [8,14) | 盤點庫存件數 |
| 銷售月份 | [16,26) | 2026 年 9 月 |
| 銷售通路 | [26,30) | 線上通路 |
| 折扣度量 | [31,35) | 折扣金額 |
| 淨銷售度量 | [36,40) | 淨銷售額 |
| 盤點日期屬性 | [44,50) | 庫存盤點日期 |
| 用途背景 | [51,60) | 準備促銷後補貨評估 |

前述六個已出現目標詞索引完整，包括DeepSeek先前缺字的月份與日期；七組目標詞中的「保留所有庫存商品」尚未形成獨立完整需求，candidate_views也未輸出。不能把前綴的6個詞正確當作第一步6/7通過率。銷售度量綁定月份與通路filter，庫存度量及日期未綁這兩filter。部分population文字帶有「已完成訂單」，完整語意未審核，不能因索引正確而全部核准。

## 驗證與證據

fresh subprocess以原raw、同prompt/source重播：**PASS**，重現相同JSON EOF ValidationError。這代表保存與錯誤重現一致，第一步自然輸出依舊 **FAIL**；完整語意 **NOT_VERIFIED**，第二／三步未執行。驗證由同一主Agent執行，非跨Agent獨立審查。核心程式與prompt無變更，因此未重跑先前156項回歸、不冒稱新回歸通過。

- [單次模型呼叫](../evidence/EV-20261021T073912-568459f3.json)
- [截斷raw離線重播](../evidence/EV-20261021T074905-2b4c73bf.json)
- [完整結果JSON](qwen-indexed-recall-wait-results.json)
- [無截止等待版程式](run_qwen_indexed_wait_probe.py)
- [第四次已逾時紀錄](qwen-indexed-recall-fourth-results.md)

原始資料位於 `.local/qwen-indexed-20261021T073913Z-2c9172/`，原樣保留。固定4096輸出上限下的完整第一步標準未達，EXP018結論REFUTED，只針對本固定候選，不否定Qwen或索引方法。停止，不自動提高token上限、修補或重跑；任務回到PLANNING，正式38題Gate不變。
