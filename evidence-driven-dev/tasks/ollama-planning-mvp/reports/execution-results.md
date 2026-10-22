# DeepSeek 優先 MVP 階段執行結果

本輪已依使用者授權完成 MVP0 離線定位，以及 B1 六題成對試驗。**B1 未達 MVP1 升級門檻，停止擴大**；十題、DeepSeek 兩輪 38 題與 Ollama 均未執行。這是失敗版本的完整階段證據，不代表最終模型目標完成。

## 離線定位

DeepSeek 原始首輪 30 筆的 raw、prompt、完整 context、response、prepared requests 與原 grader 分數全部重播一致。原始分數與回覆未回寫。原自動通過為 18/30、ready 為 22/30。

唯一已表達卻漏列 `required_columns` 的欄位，是第 26 題的 `order_count`，但來源沒有此欄位；不能自行改名成 `order_id` 或補造欄位。因此 A 欄位閉包的安全新增 ready 為 **0**，不足至少救回三題的門檻，只保留為研究護欄，不當成主要解法。

12 個不安全最小變異全部被 oracle 診斷辨識，其中只有 **7/12** 能由型別／契約護欄拒絕，其餘需要知道原需求，不能冒稱 runtime 全擋。六個合法參考控制、單純漏列通路欄位的安全閉包，以及六個人工核准骨架的編譯注入皆通過。注入成功只證明編譯器能力，未混入模型自然抽取分數。六組記憶體資料見證涵蓋未匹配母體、零缺貨、缺月份、背景重複與不同快照日期；沒有執行 SQL 或 preparation。

獨立 reviewer 核准原 30 題及題庫明列替代作為嚴格 sidecar 的參考語意，原 JSONL 的 `pending` 保留，由帶題目／契約指紋的 [review manifest](../agents/oracle-audit/review-manifest.json) 提供獨立核准 overlay。`v_sales_detail` 唯一鍵文件互相矛盾，因此禁用依該鍵導出的 FD、raw 唯一性與 COUNT 等價。日期 metadata 不能解除跨日期 SUM(stock_qty) 限制。

詳見 [MVP0 摘要](mvp0-summary.json)、[逐題三欄 sidecar](mvp0-sidecar.json)、[獨立離線審查](../agents/oracle-audit/mvp0-b1-review.md) 與[合成見證](relational-witnesses.json)。

護欄將 ready 從 22 降為 19，其中原 15、19 題的展示欄位其實可由 `contract_review.md` 明列的 stores 主鍵與來源關聯證明 FD，屬保守誤拒絕；沒有把同名欄位猜測成 FD，也沒有將此護欄直接啟用為產品規則。

原 30 筆歷史輸出另經[逐題獨立語意分類](../agents/oracle-audit/baseline-semantic-review.md)：18 題安全完整、9 題真語意錯、3 題機械錯，沒有待審等價或資訊不足。原 ready 中的 05、08、14、25 四題不安全；原自動分未過的 04、06、17 則有已核准等價。因此原自動 18/30 與語意安全 18/30 只是數字巧合，不能互相替代。

## 六題成對實測

固定開發題為 02、07、09、14、16、28，交替執行 fresh v3 與 B1，每題每 arm 一次。B1 將明示語意骨架編譯為既有 draft，導出重複欄位、分組、整合準備與 request；沒有從 oracle 注入模型答案，沒有修正後挑分。

| 首次結果，六題分母 | fresh v3 | B1 骨架＋編譯 |
|---|---:|---:|
| 原 grader 自動通過 | 1/6 | 2/6 |
| request ready | 3/6 | 2/6 |
| 獨立語意安全 ready | 2/6 | 2/6 |
| 不安全 ready | 1 | 0 |

B1 的安全題是 02、16；v3 的安全題是 14、28。淨增為 0，未達至少 5/6，亦未達「至少 4/6 且淨增 2」的替代門檻。即使四個錯誤題的部分節點正確，沒有完整 prepared requests 仍不能算端到端成功。

來源、母體、可執行根粒度三節點同時正確為 B1 **5/6**、v3 **3/6**，顯示節點品質有改善，但未轉成端到端成功；不能據此否定所有骨架方案，也不能因此略過 Gate。逐題完整審核見[十二筆獨立語意報告](../agents/oracle-audit/mvp1-semantic-review.md)。

- **07**：銷售查詢漏掉 store_id，只依 product_id 對齊，把不同門市混在一起，並多保留日粒度；另有日期角色重複。這是真語意錯，不能靠日期去重修好。
- **09**：店×商品×日子集合與根語意合理，但 snapshot_date 同時出現在 attribute 與 metadata，違反既有型別契約，沒有可提交 request。
- **14**：條件計數仍停在店×商品×日期，沒有完成每店彙總；並有日期角色重複。不能只因 conditional_metrics 存在就算對。
- **28**：日期既是 query grain 又是 metadata，違反欄位角色互斥。根粒度附加可由店×商品唯一鍵決定的日期，不能單憑多一欄就判語意錯；但本次仍未備妥 request。

v3 的第 09 題 ready 實際丟失每日維度，屬不安全結果。第 14 題以契約明示的「缺貨」狀態作條件計數則可核准等價，不應因與 canonical 寫法不同就拒絕。

12 次呼叫於同一凍結版本完成，約 **174.4 秒**，生成 token 共 **6,811**。v3／B1 的 input token 分別為 44,806／39,010，output 為 4,423／2,388；不同 prompt 與輸出上限下的少量延遲觀察，不當成泛化速度結論。全程 Azure DeepSeek、序列、SDK retries=0；沒有 rate limit、重試、局部修正、Ollama 或 SQL／DB 呼叫。

原始紀錄位於本 Task 的 `.local/mvp1-b1-20261020T125608Z-a7f325/`，保留逐呼叫 messages、raw、usage、耗時、骨架、draft、分數及 prepared payload。程式／prompt／schema／case／catalog 指紋見 [MVP1 摘要](mvp1-summary.json)。這是固定工作樹指紋的開發實驗，未冒稱乾淨 revision 的正式完整 Gate。

## 驗證與後續界線

相關契約、workflow、grader、runner 與新增反例測試合計 **78 passed**。獨立審查先抓到並以失敗測試重現兩個 sidecar 漏洞：COUNT(stock_qty) 冒充庫存原值、只用門市鍵冒充店×商品對齊；修正後反例與合法控制皆重驗通過。12 筆已存模型結果亦在新 subprocess 中逐字重播 raw→draft→payload→原分／sidecar，驗證完整性通過，不增加模型呼叫。

封存作者獨立建立 MVP2 十題（7 正／3 負）及完整 Gate 八題（6 正／2 負），兩組互斥，已保存 SHA256。只有作者結構自檢，新增語意 oracle 仍待獨立核准；八題內容未交給主 agent，未用來開發。因 MVP1 已失敗，不揭露或執行它們。

B1 保留為 evaluation 候選，產品 v3 預設未變。後續需先提出新版本的可否證節點假設，釐清輸出欄位角色互斥、店×商品對齊與每店條件計數，再做離線驗證；不能把本次四個錯誤交給人工補答案後宣稱通過。護欄仍有契約可證明 FD 的保守誤拒絕，sidecar 亦需保留人工等價審核。Runner 在本次內容已獨立重算核對的前提下執行；正式 Gate 前仍應將案例核准比較改成即時計算內容 hash，並以乾淨固定 revision 重新建立完整驗收版本。

DeepSeek 兩輪各 38/38 首次語意正確的 Gate 尚未通過，**不允許移轉 Ollama**。現階段沒有證據支持宣稱規劃問題已解決。
