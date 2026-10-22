# Retail test group 2 根因調查與修復

最終狀態 **PASS_WITH_WARNINGS**。已確認的產品缺陷完成通用修復，477 項產品回歸與 43 項獨立 probes 通過；最終六題混合節點驗證均符合原 Oracle。混合驗證保留逐字前序模型輸出，只對比較等變動節點重新生成，不能宣稱版本 C 完整 live E2E 或三次穩定性。

本任務接續原測量的失敗調查，保留原 48/90 與所有原始模型 I/O。未修改題庫 Oracle、核准契約、固定群組或正式人工審核狀態。

## 已確認根因與修正

1. WHERE／HAVING 依「筆數、平均、總和」等字串判斷，未分辨既有統計欄名與新增跨列操作。改為先取條件的業務名稱，核對自身契約及 aliases，再判斷外加聚合；對預計算指標提供具體修復回饋。
2. 逐列需求的錯誤草稿可新增 SUM／GROUP BY。新增逐欄操作授權，完整欄名中的統計字詞不構成聚合授權；真正指定的聚合仍保留。
3. 單一短片語字面命中可直接選 View，壓過其他條件與粒度。停用 v10 此捷徑；同義但非同字面選擇，須對每個競爭來源提出同一需求片語、逐字契約引用與結構化業務衝突。每個競爭來源至少有一項主要需求片語的有效反證；可另附互異且全部通過驗證的反證。共同描述、不相干片語、重複、無效類型或偏好排序均不能選定來源。
4. 不完整的 fields.text 丟失了指標定義內數字。保留 literal 防護，加入完整業務片語／時間數字修飾的映射指引與具體修復回饋，不以 ignored 跳過缺失。
5. 獨立審查發現新增逐列驗證會對未知欄位拋出例外；先沿用 Schema 拒絕流程再檢查操作。

## 14 個原失敗案例的分類

| 案例 | 分類與處理 |
|---|---|
| ORDER_SUMMARY-S1-01 | 確定產品問題：逐列被新增聚合；正確比較選擇又被過嚴字面門檻降為澄清 |
| CUSTOMER_VALUE-S2-02 | 確定產品問題：會員逐列被重建成明細聚合，單一「所在城市」命中導致錯選來源 |
| ORDER_SUMMARY-M3-01 | 確定產品問題：訂單總件數與商品明細件數的 MAX 口徑不同；比較須排除不符來源 |
| CUSTOMER_VALUE-H1-02 | 確定產品問題：平均每筆消費額本身是列指標，被誤作 AVG／HAVING |
| STORE_MONTHLY_KPI-H3-01 | 確定產品問題：月目標／完成單數被錯配實績／識別碼；比較須承接完整口徑 |
| INVENTORY_STATUS-H3-05 | 確定產品問題：欄位 text 只保留最大值，定義內的 30 被當成未承接 literal，原修復未補完整詞彙 |
| DAILY_SALES-M1-05、DAILY_SALES-M3-05 | 列條件誤判已修；日與月的單列最大值不同，原題文仍缺唯一粒度 |
| PRODUCT_MONTHLY-S2-05、PRODUCT_MONTHLY-M3-04 | 兩來源皆可承接但統計粒度不同；保留澄清，不強制原 Oracle 的唯一來源 |
| DAILY_SALES-S3-03 | 題文逐筆與日彙總預期不一致；保留口徑澄清 |
| CUSTOMER_VALUE-S3-03 | 原兩次 provider 逾時另列；「再回來買」與契約「近90日有任一已完成單」不同，「涵蓋期間」也未等同累計期間，不放寬安全來源檢查 |
| CUSTOMER_VALUE-B-02、INVENTORY_STATUS-B-05 | 原 SQL 拒絕通過，原映射評分失敗來自最後一份被拒絕草稿；不改 Oracle 使分數變綠 |

完整題文、契約與原始 call／result 行號見 [來源調查](agents/source-audit/task.md) 與 [Oracle 調查](agents/oracle-audit/task.md)。

## 驗證結果與限制

這輪真實模型為焦點單次驗證，不能宣稱三次穩定性，也不是重跑全部 90 次。語意判斷仍依模型；逐字引用與結構驗證不構成業務推論的邏輯證明。沒有執行 DB、驗證實際數值或正式核准 draft 案例。


## 模型實驗與失敗保留

Ollama `qwen3.8:27b`、Q4_K_M、temperature 0、seed 42；MATCH v10 原檔、原題庫／Oracle、核准契約與固定群組保持不變，實際上下文與比較指引的改動由產品 source fingerprint 追蹤。每題使用空白隔離詞彙檔，沒有代選 HILP。

| 版本／方法 | 原 Oracle 通過 | 新真實模型呼叫 | 逐字前序回放 | 解讀 |
|---|---:|---:|---:|---|
| A：六題完整真實模型各一次 | 3/6 | 46 | 0 | 訂單件數仍澄清、平均值條件位置錯誤、月目標反證範圍被拒；全部失敗保留 |
| B：固定 A 前序，變動節點重新生成 | 5/6 | 4 | 41 | 月目標正確選擇附帶兩項有效反證，仍被「每來源恰一項」門檻拒絕；失敗保留 |
| C：固定 B 前序，比較節點重新生成 | 6/6 | 3 | 42 | 映射及 SQL 結構均符合原 Oracle，來源版本於執行前後不變 |

另將 B 的完整模型請求／回應序列於 C 逐字回放，45 次請求內容完全相同，六題均按原 Oracle 通過，驗證最後變更是反證接受規則；不是對同一失敗模型呼叫盲目重試。A、B、C 合計 53 次新的模型呼叫，與原穩定性測量的 575 次呼叫分開保存。

| 案例 | 原三次測量 | 最終 C 混合驗證 | C 新比較呼叫／前序回放 |
|---|---:|---|---:|
| `RETAIL-ORDER_SUMMARY-S1-01` | 0/3 | 映射／SQL 通過 | 1/8 |
| `RETAIL-CUSTOMER_VALUE-S2-02` | 0/3 | 映射／SQL 通過 | 0/7 |
| `RETAIL-ORDER_SUMMARY-M3-01` | 0/3 | 映射／SQL 通過 | 1/7 |
| `RETAIL-CUSTOMER_VALUE-H1-02` | 0/3 | 映射／SQL 通過 | 0/6 |
| `RETAIL-STORE_MONTHLY_KPI-H3-01` | 0/3 | 映射／SQL 通過 | 1/8 |
| `RETAIL-INVENTORY_STATUS-H3-05` | 0/3 | 映射／SQL 通過 | 0/6 |

## 回歸、獨立審查與原資料核對

- Main：完整產品 **477 passed**，聚焦 **101 passed**。
- 獨立 reviewer：產品 477 ＋原 26 ＋新增多重反證 17，共 **520 passed**；與 Main 重疊，不相加為不同測試。
- 修正前證據：重建初始產品並核對初始 SHA-256，同一回歸 fixture 為 18 failed／9 passed；B 邊界反例於 A 為 10 failed／8 passed；最後多重反證先失敗再通過。所有早期錯誤與測試失敗均保留。
- 原 90 筆全部以原 Oracle 重評仍 **48/90**；575 calls／90 results、題庫／契約／群組及原 grader 雜湊不變。
- 相對初始工作樹僅改兩個既有產品檔，新增兩個正式測試檔；其餘既有 dirty 內容已按初始封存比對保留。UTF-8 無 BOM 與差異空白檢查通過。

EDD 工具於台北跨日後有一項既有測試失敗：`test_archive_collision_does_not_destroy_task` 以本地 10/21 建立衝突目錄，`archive()` 使用 UTC 10/20，故未發生預期衝突。原始 48 通過／1 失敗保留；以 `TZ=UTC` 重跑 **49/49 通過**。本任務未修改 EDD 工具或測試，這項時區缺陷另列限制。

## 產物與證據

| 證據 | 用途 |
|---|---|
| [最終版本產品回歸](evidence/EV-20261020T160434-aedefc76.json) | 477 passed |
| [最終聚焦回歸](evidence/EV-20261020T160338-5d4d7338.json) | 101 passed，含安全／未知欄位／literal／多項反證 |
| [C 混合節點驗證](evidence/EV-20261020T160432-80e626a0.json) | 六題原 Oracle 全通過，3 新呼叫／42 回放 |
| [B 完整輸出於 C 逐字回放](evidence/EV-20261020T160403-f71c0c4d.json) | 六題全通過，45 次相同請求 |
| [最終產物核對](evidence/EV-20261020T160828-4a5da74b.json) | provenance、版本、原 Oracle 與量測、初始 dirty、UTF-8 |
| [EDD 本地時區失敗](evidence/EV-20261020T160435-e65330b9.json)、[UTC 重跑](evidence/EV-20261020T160618-7f110dce.json) | 如實保留時區差異 |
| [獨立審查](agents/independent-review/task.md) | 43 個獨立正反例、版本 C 520 passed 及限制 |

原始大型 I/O 保存於本任務 `.local/live-focus-20261020/`、`.local/hybrid-focus-B-20261020/`、`.local/hybrid-focus-C-20261020/`；逐次回放／新生成來源見各混合執行 `provenance.jsonl`。這些原始資料不提交 Git。舊穩定性報告見 [retail-test-group-2](../retail-test-group-2/final-report.md)。

HEAD `014cee1aff3abcfb51bbe5af6db0abd2ef060225`；最終工作樹指紋 `42e793d060d4fbbc8b4e1a7d8ad7661b949ce2563c9030b188852398e18d418c`；產品 source fingerprint `dfd3aa72b4133db6def2cefd203695198393251f6cf316a0143cb9eda2eabfbf`。

## 未驗證範圍

- 未對最終版本完整重跑 30×3 或全部 395 題；混合驗證不能代表完整 live E2E 或三次穩定性。
- 未執行 DB 或核對實際數值；draft 案例的正式人工審核仍為 pending。
- 來源的語意衝突仍由模型判斷；逐字引用、類型與結構驗證不構成推論的邏輯證明。
- 原題文／Oracle 的粒度及回購／活躍口徑歧義、兩個安全拒絕的 raw mapping 評分問題保持原樣，沒有用強制選來源或改 Oracle 提高分數。
- 原 provider 逾時未被改寫或重試；本輪不能證明所有共享服務逾時已消除。
