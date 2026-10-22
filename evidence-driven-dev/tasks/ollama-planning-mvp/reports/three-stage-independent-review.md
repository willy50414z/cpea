# 三階段候選獨立審查

驗證者：`/root/three_stage_review`，與實作者分離；唯讀審查與 fresh subprocess，未呼叫模型、SQL／DB。初版受驗 HEAD `bc09c67`，契約檔 SHA256 `35f19e0293d7df1763e7678017cb09fb391333e27296b148614c5397b37e5e73`，runner `ff0fe74544d849158d6197a56bd9390badc7f8a3b1d3dc69811f8903dc1285ef`。

## 初版結果：FAIL

26個既有 focused tests 通過，但額外反例找出：

1. P1：把合法計畫的最終 output_grain 改成 product_id，新增庫存 aggregate preparation，仍 ready，遺失各店粒度。
2. P1：missing_data_policy 改為「未匹配銷售金額一律補零」仍 ready。
3. P2：provider-error 離線重播直接拋 RuntimeError，無法還原封存停止結果。
4. P2：封存目錄新增 injected-call.json、不改 manifest，重播仍 PASS。

## 主 agent 整合與修正

- 五個反例先實跑失敗（另拆 preparation 單獨刪鍵），再最小修正；31 tests passed。另追加實際 usage 超預算停止反例，先失敗後修正。
- final grain 明確綁定 grain 需求的已驗 key；preparation 不可移除最終或對齊鍵。
- 缺值政策只接受輸入明列的三個保留缺值 canonical 字串，模型必須選擇，程式不代填、不猜自然語句。代價為可能拒絕語意等價的自由描述；此限制在 prompt 明示。
- 離線重建 provider 錯誤型別／訊息；重播核對完整 artifact 集合，包含多出的檔案；成功九節點與失敗停止皆有測試。
- provider usage 超過 token budget 即保留 raw 並停止後續呼叫。
- 修正後新增及既有相關回歸 **125 passed**。依 executing-plans 採單輪修正，以 fresh tests 驗證，未派第二輪重複審查；不可宣稱獨立 reviewer 已再次核准修正版。

## 驗證界線

引文存在不證明需求完整、scope 語意或來源母體正確，仍需自然輸出與獨立 oracle 核對。population 目前只允許所有邊由 anchor 直接 left 連出，可能保守拒絕其他合法整合。缺值政策 canonical 白名單及 grain=最終粒度是本候選介面限制，尚非一般產品支援。模型自然生成品質須另實測。
