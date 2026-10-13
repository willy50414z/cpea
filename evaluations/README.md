# 品質評估

`runners/` 保留 query reliability 與固定 prompt 的多模型比較。`datasets/` 僅含可分發的合成題庫；`private/legacy/` 保存原專案題庫及歷史結果，分發權限尚未確認，不納入 wheel／sdist。原始檔另有 `artifacts/baseline/original-poc.zip` 與逐檔 SHA-256 manifest。

執行 no-DB 評估前明確選擇模型服務與 profile：

```powershell
cpea-query-eval --env-file .env --runs 3
```

`cpea-model-eval --dataset <私有題庫> --models <模型A> <模型B>` 需要已注入既有 SQL executor 的 runtime；單純安裝產品沒有該依賴，會在模型呼叫前明確失敗。部署端可透過 Python 的 `compare_models(..., runtime=runtime)` 提供既有 callable，無須新增 DB driver。離線測試使用 `kind="offline-synthetic"`，不能作為真實模型品質報告。

預設結果位於 `artifacts/evaluations/<run-id>/`；明確指定 `--output` 也不能覆寫已存在檔案。每個 record 帶 run ID、UTC 時間、產品版本／程式摘要、模型／供應商、非機密設定摘要、profile／契約版本及內容摘要、題庫摘要。Optional provider 和 cross-encoder 依賴列在 `requirements/optional.txt`，不屬本次驗證的核心 lock。

評估產物可能包含使用者題目、SQL、trace、final prompt、context 或結果列，應當作私有資料保存。設定 metadata 只採允許的非機密欄位；credential 與含認證資訊的 endpoint 不輸出。原歷史結果缺少部分版本資訊，保留其原始內容，但不能和新設定下的延遲／正確率直接比較。

保存、存取與清除由部署方管理。本次沒有提供 durable audit、retention job 或資料庫。不要將 `private/`、`artifacts/` 加入公開版本或通用發行包。
