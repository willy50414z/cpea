# Retail group 2 穩定性測試停止紀錄

使用者要求停止測試。本輪程序已於 UTC 2026-10-21 03:50:55 因 provider ReadTimeout（300秒）自行退出，未自動重試。

完成 **28/90** 次，通過 **9** 次、失敗 **19** 次；共 237 次模型呼叫，provider逾時1次。尚未完成62次，不宣稱完整穩定性。

目前 `docker exec ollama ollama ps` 明確顯示 `qwen3.8:27b` 為 `100% CPU`；日誌顯示 CPU model/KV/compute buffers。當前image為 `ollama/ollama:0.40.7-rc1-rocm`。

此現況不能回推所有既有案例皆用CPU；執行期間服務image有更新，須保留環境變動限制，不能作為同一凍結服務環境的完整測量。

原始資料、雜湊、目前容器非敏感設定與CPU證據保存於 `.local/stopped-snapshot-20261021.json`。尚未修改GPU設定、重啟共享服務或重新測試。

[先前26次部分結果](pause-report.md) · [原完整測量](../retail-test-group-2/final-report.md)
