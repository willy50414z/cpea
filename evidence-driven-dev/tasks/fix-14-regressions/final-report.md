# Retail v10 修復與驗證報告

原未完整通過的 6 題，各以目前版本真實模型重測 3 次，**18／18 次映射與 SQL 結構檢查通過**；每題三次產生的 SQL 各自完全相同。結果為 PASS_WITH_WARNINGS，限制見下方。

## 根因與修正

問題分布於映射、候選來源與語意驗證，並非所有 View 已選對後只卡在 SQL 編譯。原 42 次評估中，9 次只缺映射分組欄位但 SQL 正確、6 次待 View 口徑澄清、3 次語意選項生成失敗。

1. v10 將已存在於 group 的維度補入非空 fields；不增加篩選欄位、不讓被拒絕的來源復活。
2. 明確聚合與欄位逐一綁定，COUNT／MAX 等錯配交由既有同 View 修復；修復仍錯即排除。保留統計詞彙本身為核准欄名的情況，並測試標點及相鄰欄位名稱邊界。
3. 必要詞彙的候選若全部明示概念或粒度不相容，該來源不能進入可行候選。真正的來源歧義仍保留原澄清規則。
4. 語意選項未通過驗證時最多追加一次帶具體回饋的修復；逐字證據、完整必要詞彙、eligible columns 與業務標籤驗證均保留，失敗仍拒絕。

未修改題庫預期答案、MATCH prompt、核准契約或 HILP 正式核准狀態；正式程式無案例 ID／完整題文特判。保留啟動時已有的 PostgreSQL 等未提交變更。

## 真實模型結果

Ollama `qwen3.8:27b`、MATCH v10、PostgreSQL、temperature 0、seed 42、context 16000、max output 8192、lexical retrieval。每次使用空白隔離詞彙檔，待確認不代選，未注入 SQL executor。

| 案例 | 原問題 | 修復前完整通過 | 修復後 | SQL三次一致 | 呼叫數 |
|---|---|---:|---:|---|---:|
| `RETAIL-DAILY_SALES-M2-01` | 明確MAX被誤作COUNT，候選錯配造成澄清 | 0/3 | 3/3 | 是 | 27 |
| `RETAIL-INVENTORY_STATUS-H3-01` | fields缺少分組維度 | 0/3 | 3/3 | 是 | 18 |
| `RETAIL-INVENTORY_STATUS-M2-04` | 語意標籤含識別碼且無驗證回饋修復 | 0/3 | 3/3 | 是 | 21 |
| `RETAIL-SALES_DETAIL-M3-01` | 不相容SKU候選來源造成多餘澄清 | 0/3 | 3/3 | 是 | 21 |
| `RETAIL-STORE_MONTHLY_KPI-H1-01` | fields缺少分組維度 | 0/3 | 3/3 | 是 | 27 |
| `RETAIL-STORE_MONTHLY_KPI-M3-03` | fields缺少城市維度，需保留混合聚合與WHERE | 0/3 | 3/3 | 是 | 30 |

本輪共 144 次模型呼叫，約 83.1 分鐘；輸入 653,978 tokens、輸出 53,244 tokens。這是原未完整通過六題的焦點驗證，不將其他八題舊版成功結果算成修復版成功。

## 驗證證據

- 完整產品：431 passed；EDD：49 passed、7 subtests passed。
- Main 聚焦回歸：102 passed；另由獨立 reviewer 執行 22 條自建 probe 與 117 條正式回歸，共 139 passed，4 項 finding 均已修復；這些數量有重疊，不加總為互異測試。
- 原始節點回放：9 筆分組遺漏正規化後通過且 SQL 不變；6 筆原 COUNT 錯配現在均有明確 hard error。
- 最終產物核對：18 組唯一案例／次數、144 次呼叫關聯、原始 I/O 雜湊、完整原題庫預期與 prompt、契約、設定、版本與 UTF-8 無 BOM 均通過。

| 證據 | 用途 |
|---|---|
| [evidence/EV-20261020T033303-f1efa028.json](evidence/EV-20261020T033303-f1efa028.json) | 完整產品回歸 |
| [evidence/EV-20261020T033303-864ff95f.json](evidence/EV-20261020T033303-864ff95f.json) | EDD 回歸 |
| [evidence/EV-20261020T032938-ee2b0aef.json](evidence/EV-20261020T032938-ee2b0aef.json) | 語意與映射聚焦測試 |
| [evidence/EV-20261020T033349-1c0893b0.json](evidence/EV-20261020T033349-1c0893b0.json) | 修復後原始資料 Replay |
| [evidence/EV-20261020T033302-48366dc8.json](evidence/EV-20261020T033302-48366dc8.json) | 18 次真實模型 |
| [evidence/EV-20261020T045644-6e4ea027.json](evidence/EV-20261020T045644-6e4ea027.json) | 最終產物核對 |
| [獨立審查](agents/independent-review/task.md) | 139 項檢查與反過擬合審查 |

原始模型 I/O 與逐次結果保留於任務 `.local/live-six-20261020T0331/`；其餘驗證摘要在 `.local/final-verification.json`。這些大型原始資料不提交 Git。

## 版本與限制

HEAD：`014cee1aff3abcfb51bbe5af6db0abd2ef060225`；EDD 工作樹指紋：`3e860a198c01c8d8dc1cf8c16f1e3b4c2a59566da7177b1db153c969fe651ac1`。真實模型執行前後、獨立審查與 Main 回歸版本一致。產品 source fingerprint：`14a65caf5324ecc612bfa726effa95f47cc7f933c9883e6396db91e5152acafb`。

- 未執行 DB，未驗證實際資料或數值結果。
- 案例與契約仍為 draft，正式人工核准 pending；本輪屬探索性驗證。
- 其餘 8 題未在本修復版本重跑真實模型；本輪 6 題各 3 次不能證明所有未來模型輸出皆正確。
- 明確聚合檢查只涵蓋已測語法；新增語法仍需相應驗證。
- 本輪有額外有界修復成本；本地模型不提供雲端費用估算。
