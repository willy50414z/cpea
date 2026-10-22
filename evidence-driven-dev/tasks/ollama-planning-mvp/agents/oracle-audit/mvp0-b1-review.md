# MVP0／B1 獨立離線審查

結論：**PASS_WITH_WARNINGS，可開始六題研究；目前無未解 blocking issue。** 這不是完整 Gate 核准，也不代表任何新模型結果已通過。審核過程零模型、網路、SQL、DB 呼叫，未修改 source、產品或原 oracle；未讀 Gate 封存題文。

## 已核對的證據

- 原 30 筆的 response、原分、system prompt 與完整 context 均重新計算且完全一致，raw 檔案 hashes 一致；30 筆 sidecar 亦可重新計算。
- A 的 `new_ready=0`，不足至少救回 3 題的升級門檻，因此只保留為型別護欄、改研究 B 合理。
- 12 個不安全變異中，runtime 拒絕 **7/12**，oracle 診斷拒絕 **12/12**。兩者不可混稱 runtime 全擋；其餘五個需求錯誤仍需模型理解及獨立語意評分。
- 六個注入骨架 02、07、09、14、16、28 的來源、欄位角色、條件、母體、查詢及根粒度、child集合、三來源背景皆正確，編譯 response 可逐字重現。這只證明編譯器，不是模型自然抽取成績。
- 既有六個 grader 盲點目前均被 sidecar 拒絕，包括欄位只有required但未輸出、額外度量、缺值填零、錯request、nest改aggregate及未證實COUNT等價。

## 發現並已修正的 blocking issues

1. singleton 上把 `stock_qty` 原值改 `COUNT(stock_qty)` 仍被 sidecar 判安全；單列 COUNT 為 1，不等於一般庫存值。修正後只接受可還原單列原值的聚合，反例已拒絕。
2. 商品對照改僅用 `store_id` 並將全店商品 nest 給每個庫存商品，仍被判安全。修正後逐 edge 核對 oracle 完整語意鍵，反例已拒絕。

Fresh pytest 為 **12 passed**，兩個反例已重新執行，詳見 JSON 的 `post_fix_recheck`。保留修正前錯誤證據，沒有覆蓋為成功歷史。

## Compiler 與 Runner

未發現 compiler 偷補來源、日期、通路、度量或母體；它只搬移明示語意欄位、依型別導出required_columns/group_by/request/preparation。缺期間不臆補、未知欄位不改名。預設保留未匹配缺值屬已核准政策，不能代替模型選對母體。

Runner 固定六題成對 Azure DeepSeek，至多12次，SDK retries=0。已強制單次 timeout=300秒，剩餘階段窗口不足300秒不開新呼叫；每次核對凍結的 source/prompt/schema/cases。Fresh preflight 最高輸入8118，輸出預留7168、安全1024，合計 **16310≤16384**。七個完整契約保留；B1輸入比v3略長，不能宣稱縮短context。

目前六題的實際內容hash已由審核者重算，均匹配獨立核准manifest。Runner只比較題庫內存放的case_sha256，而非重新計算內容hash；本次當前內容已被獨立確認，因此不擋本次研究，正式Gate前應補上重算。

累計generated-token檢查是停止門檻；若baseline沒有相同單次上限，不能宣稱它是嚴格的總生成token硬上限。結果應保存實際每次usage。sidecar仍須獨立逐筆審核未列等價、pivot形狀、額外欄位用途、負例理由與背景禁止重加總。

## 後續

可執行已凍結版本的六題自然抽取研究，不能因注入6/6或sidecar safe就升級。模型輸出後需另審12筆來源、欄位、條件、粒度、母體、缺值、整合與request；依預定MVP1門檻決定是否擴至十題。完整兩輪38/38 Gate與Ollama移轉尚未核准。
