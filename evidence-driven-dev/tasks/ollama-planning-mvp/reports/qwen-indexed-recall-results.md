# Qwen 索引版第一步單次測試

EXP-014：已呼叫 `qwen3.8:27b` 一次，約 **300.4 秒後 ReadTimeout**，未取得模型答案。片段完整率、角色分類與 scope 均為 **NOT_VERIFIED**，不能算成 0/7，也不能判定 Qwen 的語意能力失敗。

## 題目與設定

> 對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。

與 EXP-013 的題文、完整 messages、來源、schema、catalog 與程式指紋均相同。採樣為 temperature=1、top_p=1、seed=42，context=32768、輸出上限=4096、網路 timeout=300 秒；thinking 沿用本機 true。Ollama 使用 `format` JSON schema，先前 Azure 使用 prompt schema 與 JSON object，因此不是單一模型變項的嚴格比較。

模型為 27.3B、Q4_K_M；digest：`aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`。本輪使用者明確授權此單題第一步 Ollama 診斷，完整兩輪 38/38 採用門檻保持不變。

## 結果與限制

| 項目 | DeepSeek 上次 | Qwen 本次 |
| --- | --- | --- |
| 新模型呼叫 | 1 | 1 |
| 耗時 | 14.2 秒 | 300.4 秒後逾時 |
| 完整目標詞 | 5/7 | 無答案，無法評分 |
| 母體分類 | population | 無法評分 |
| 第二／三步 | 未執行 | 未執行 |

Ollama `/api/ps` 觀察到此模型已載入、context=32768、size_vram=0；未使用 GPU VRAM 可能影響速度，但未證實逾時根因。未收到 usage，實際 token 與費用均未知；run metadata 的累計 0 是尚未取得 usage，不能當成沒有消耗。

## 驗證與證據

fresh subprocess 離線核對請求、所有保存檔案 hash 與停止原因一致：**PASS**，重播的是一次 provider timeout，沒有模型 raw answer。先前 DeepSeek 保存結果也重新離線重播一致。驗證由同一主 Agent 執行，非跨 Agent 獨立品質審核。

- [單次模型呼叫證據](../evidence/EV-20261021T035649-bb08cfa3.json)
- [Qwen provider 錯誤離線重播](../evidence/EV-20261021T040200-432414fb.json)
- [舊 DeepSeek raw 重播](../evidence/EV-20261021T035728-92bbb829.json)
- [結果 JSON](qwen-indexed-recall-results.json)
- [診斷執行程式](run_qwen_indexed_probe.py)

原始請求與錯誤保存在 Git 忽略目錄 `.local/qwen-indexed-20261021T035651Z-ab0b06/`。未改核心程式／prompt、未重試或追加呼叫，未執行 SQL／DB 或第二／三步；舊結果與分數保留。本次假設結論為 **INCONCLUSIVE**，任務回到 PLANNING。
