# Qwen 第四次第一步測試

EXP-017：同題、相同Qwen模型與設定，新增1call，420秒整體硬上限終止（exit124），無完整答案、usage或可重播raw。語意NOT_VERIFIED／假設INCONCLUSIVE。呼叫時觀察GPU VRAM約12.6GB。

fresh subprocess離線核對請求／設定／來源／保存檔hash／外部逾時紀錄PASS，非模型品質驗收，非跨Agent審查。

使用者最新要求等到結束，但執行調整時上一筆已在07:36:22 UTC被終止，無法續接；因此另立EXP018取消網路與外部時間截止後再執行1call，明確分開保存。

- [呼叫證據](../evidence/EV-20261021T072922-45c135b4.json)
- [離線核對證據](../evidence/EV-20261021T073825-cc2b646a.json)
- [結果JSON](qwen-indexed-recall-fourth-results.json)
