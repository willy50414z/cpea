# Retail group 2 穩定性測試暫停報告

依使用者要求暫停測試；原程序以 SIGSTOP 保留，未終止共享模型服務。

已完成 **26/90** 次，通過 **9** 次、失敗 **17** 次；目前正確率 **34.6%**。尚有 64 次未形成結果，不納入評分。這是部分進度，不能代表完整90次穩定性。

已記錄 235 次完成的模型呼叫，provider 錯誤 0 次。生成狀態：{"ready": 12, "needs_clarification": 11, "unsupported": 3}。

| 案例 | 已完成 | 通過 | 生成狀態 |
|---|---:|---:|---|
| `RETAIL-SALES_DETAIL-S1-01` | 3/3 | 0/3 | ready, ready, ready |
| `RETAIL-ORDER_SUMMARY-S1-01` | 3/3 | 3/3 | ready, ready, ready |
| `RETAIL-STORE_MONTHLY_KPI-S1-01` | 3/3 | 0/3 | needs_clarification, needs_clarification, needs_clarification |
| `RETAIL-INVENTORY_STATUS-S2-04` | 3/3 | 3/3 | ready, ready, ready |
| `RETAIL-CUSTOMER_VALUE-S2-02` | 3/3 | 3/3 | ready, ready, ready |
| `RETAIL-PRODUCT_MONTHLY-S2-05` | 3/3 | 0/3 | needs_clarification, needs_clarification, needs_clarification |
| `RETAIL-DAILY_SALES-S3-03` | 3/3 | 0/3 | needs_clarification, needs_clarification, needs_clarification |
| `RETAIL-CUSTOMER_VALUE-S3-03` | 3/3 | 0/3 | unsupported, unsupported, unsupported |
| `RETAIL-DAILY_SALES-M1-05` | 2/3 | 0/2 | needs_clarification, needs_clarification |

暫停時正在執行 `('RETAIL-DAILY_SALES-M1-05', 3)`；其已完成的子呼叫保留，整個案例尚未計分。已送到模型服務的請求可能仍繼續完成，本地程序不再發起新呼叫。

原題庫、Oracle 與模型設定保持；尚未執行 DB、正式核准或完整90筆重評。原始紀錄見本 Task `.local/live-group2-postfix-20261021/`，凍結摘要與雜湊見 `.local/paused-snapshot-20261021.json`。

## 與原測量比較

同一批已完成26個tuple的原測量也通過9次。以下變化已依原Oracle在獨立程序重評核對，不是完整90次結論。

- 改善為3/3通過：`ORDER_SUMMARY-S1-01`、`CUSTOMER_VALUE-S2-02`（原皆0/3）。
- 回歸為0/3通過：`SALES_DETAIL-S1-01`（產生SQL但來源/欄位錯誤）、`STORE_MONTHLY_KPI-S1-01`（改為澄清，無SQL），原皆3/3。
- 其餘已完整測3次的失敗題：`PRODUCT_MONTHLY-S2-05`、`DAILY_SALES-S3-03`、`CUSTOMER_VALUE-S3-03`；`DAILY_SALES-M1-05`目前完成2次皆未通過。

[已完成結果逐筆核對證據](evidence/EV-20261021T033328-a40fca50.json)；完整三次案例8題的狀態與通過/失敗結果皆一致，但包含一致失敗。
