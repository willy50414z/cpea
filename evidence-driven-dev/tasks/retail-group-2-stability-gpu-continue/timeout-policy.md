# 穩定性測試逾時設定變更

依使用者「取消timeout或改成限制30分鐘」指示，採 **30分鐘（1800秒）**，只套用剩餘23次的新接續程序。以環境變數 `ASSISTANT_LLM_TIMEOUT_SECONDS=1800` 覆寫，不改專案 `.env`、產品預設、模型或Oracle。

實際Ollama同步與非同步HTTP client的讀取逾時均已驗證為1800秒；settings比對只有此一欄位改變。這是HTTP等待回應資料的逾時，不是整個多節點案例的30分鐘總預算。全批次另保留12小時執行上限。

前67次（36通過、31失敗）與原300秒逾時結果保持，不重跑。新23次與舊67次須分段呈現，合併結果不能宣稱為固定timeout與硬體條件的穩定性測量。

驗證記錄：`.local/resume-timeout1800-check.json`；新segment：`.local/live-gpu-timeout1800-20261021/`。
