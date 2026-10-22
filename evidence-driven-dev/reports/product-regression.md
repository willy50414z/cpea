# 既有 CPEA 回歸

實際執行：`.venv/bin/python -m pytest tests/unit tests/contracts -q`。

實際工具輸出：`301 passed in 23.29s`，退出碼 0。未重跑或修改正式產品測試。

只驗證 Unit／Contract；外部服務 Integration／LLM／資料庫不在本次實測範圍。
