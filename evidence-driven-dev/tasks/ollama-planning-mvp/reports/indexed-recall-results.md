# 第一階段原句索引與 Python 裁切

**實作完成，程式驗證通過；本次模型的精確索引及語意分類尚未通過。** 第一階段LLM輸出不再包含quote，只回傳start/end，Python負責產生內部引用。產品v3保留，未執行第二／三階段或SQL／DB／Ollama。

## 介面與驗證

- `IndexedRecallResult`／`IndexedRequirement`作為模型wire schema，不允許quote欄位。
- 使用0-based Python Unicode code point，start包含、end不包含；Python計算 `request[start:end]`。提供原句逐字索引表，包含空白、標點、換行及emoji。
- 嚴格整數拒絕bool／float／str；拒絕負值、越界、反向、空片段及純空白，不clamp、不自動移位。既有需求ID／scope／七來源驗證保留。
- raw、parsed indices、Python衍生quote分別保存為 `recall-call.json`、`recall-parsed.json`、`recall-result.json`，不覆寫模型原始輸出。
- 後續內部Requirement仍帶quote，來源是Python切片。此次只處理第一步原句引用；View契約證據屬另一層驗證。

新增[索引型別與裁切](../../../../evaluations/indexed_requirement_recall.py)、[索引prompt](../../../../evaluations/prompts/three_stage/recall_indexed.md)，接入既有[runner](../../../../evaluations/three_stage_view_selection_runner.py)。新增recall-only／request-file診斷模式：自訂題只能跑第一步，不能直接當正式benchmark評分。

## 離線與獨立審查

21個新增測試涵蓋中文、空白、標點、emoji、CRLF、重複詞、禁止模型quote、索引反例、原scope驗證、索引表與runner保存／停止。原42個測試的模型fixture改用index wire，合法完整九節點控制仍可準備request，沒有削弱驗證。

**63 focused、156相關回歸通過**：[回歸證據](../evidence/EV-20261021T033818-dd272774.json)。獨立review `/root/indexed_recall_review`實跑63測試及synthetic邊界／重播／CLI檢查，未發現P1／P2必修問題；[handoff](../agents/indexed-recall-review/handoff.json)明記不包含自然模型索引品質核准。額外synthetic artifacts僅在/tmp，未永久保存，驗證強度以既有測試及正式EV為主。

## 一次真實模型測試

沿用EXP-011相同「盤點庫存並顯示盤點日期」題文，不再產生舊quote版。EXP-012呼叫前限定最多1call、30000 input、4096 output、32768 context、1024 safety、timeout300秒、wall900秒、SDK retries=0。temperature=1、top_p=1、seed=42，Azure DeepSeek-V4.1-Flash。

結果：1call約8.17秒，input6707／output982 tokens，價格未知。模型未輸出任何quote欄位，7組索引全部通過範圍／型別檢查，Python裁切及儲存正常。

| 需求 | 模型start:end | Python實際裁切 | 完整目標詞的範圍 |
|---|---|---|---|
| 庫存件數 | 8:13 | 盤點庫存件 | 8:14「盤點庫存件數」 |
| 保留母體 | 61:69 | 保留所有庫存商品 | 61:69，邊界正確但被分類為filter |
| 期間 | 16:25 | `2026 年 9 ` | 16:26「2026 年 9 月」 |
| 通路 | 26:30 | 線上通路 | 26:30，正確 |
| 折扣金額 | 31:34 | 折扣金 | 31:35「折扣金額」 |
| 淨銷售額 | 36:39 | 淨銷售 | 36:40「淨銷售額」 |
| 盤點日期 | 44:49 | 庫存盤點日 | 44:50「庫存盤點日期」 |

精確完整詞彙邊界 **2/7**，其餘5組end比完整詞的exclusive邊界少1。不是Python切錯，而是模型選出的邊界較短；部分片段仍能提示原本語意，不能把邊界分數當成整體業務答案錯誤率。程式沒有擅自補字或全部end加1，因為另有兩組邊界已正確。

語意另有問題：模型把「保留所有庫存商品」列成filter並綁到庫存度量／日期屬性，而非population需求；也未明列key／grain類需求。這些不是切片函式能自行修正的內容。盤點日期仍列attribute，未要求目前或最新日期。

因此分列：

- wire／索引結構／Python裁切：PASS。
- 本固定版這次自然輸出的完整詞彙邊界與需求分類：未達預先標準。
- 第二／三步及端到端語意：NOT_VERIFIED。

本次原始節點自動狀態為structurally_valid，semantic_status=REQUIRES_REVIEW；主agent事後判讀另存[機器摘要](indexed-recall-results.json)，不回寫raw或自動結果。固定候選這次測試不支持直接採用，不能推論所有索引方案無效，也不能由單次輸出估計整體準確率。

## 重播與保存

[首次實驗](../evidence/EV-20261021T033920-61ce56e4.json)、[fresh replay](../evidence/EV-20261021T034118-e12c74ed.json)核對source不變、1筆raw、parsed與衍生結果一致。raw資料夾：Task `.local/three-stage-20261021T033921Z-6e4146/`，權限600／700且Git忽略。

改版前原第一步source／測試快照存 `.local/index-recall-prechange/`。歷史raw／分數未變；舊版fingerprint會拒絕用新schema靜默重播或續接，不把新結果混入先前實驗。

本輪依單次預算停止，不自動重問、調prompt或續跑。後續可另比較更易選擇的索引邊界表示，但需新版本、預先驗收及預算；目前只交付第一階段索引候選，主Task維持PLANNING。
