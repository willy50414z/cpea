# 獨立 Oracle 審查

審查者：/root/oracle_review，只讀，不實作、不呼叫模型或 DB。

通路26應明列 sales_channel IN [online,in_store]；契約沒有封閉enum及非空保證。orders計數可count，sales_detail須count_distinct。conditional pivot雖可表達兩通路，無該通路／缺來源之零值處理可能不同，不能無條件當成等價；本次保留分通路列的canonical，不放寬conditional/unconditional保護。

庫存日期不能由門市ID唯一決定。日期集合metadata合理，但不能作為跨日加總許可；必須保留來源時間且不得宣稱混合日期為單日總額。跨日禁止加總限制維持。現況成本估值合計與同日庫存量不同，僅準備request，本次不宣稱SQL或列數語意已驗證。

integration須同時檢查actual anchor及final相對oracle的必要維度；只有來源完整鍵與固定條件可證明冗餘，不從名稱推測FD。

採納：補通路篩選；以metadata_collections明示完整DISTINCT日期集合及下游時間限制；對actual/final兩端採同一保守唯一鍵證明；保留必要維度與缺值的反例。
