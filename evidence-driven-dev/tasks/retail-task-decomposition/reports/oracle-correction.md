# 首次模型實測前的題庫更正

`cross-view-14` 原始題文與 requirements 要求在所有庫存門市上條件計數 `stock_qty=0` 的商品，保留零缺貨門市。初稿 expected metrics 卻只有無條件 `count_distinct(product_id)`；會讓缺少條件的計畫誤過關。

更正為明確 `conditional_metrics`，不變更題文、來源、必要欄位、母體或驗收需求，並更新案例指紋。更正發生於首次 Azure 呼叫之前，沒有依模型答案修改 oracle。新增負面測試確認無條件計數不能替代條件計數。
