# 離線評估任務

只修改複製到暫存 Git Repository 的 fixtures，禁止修改正式 CPEA 演算法。每個案例提供實際執行測試與有限結論。

## 案例一

bounded(10, 0, 10) 回傳 9；契約是包含兩端的數值截斷，無效範圍仍應拒絕。調查並修正，驗證其他數值、邊界與非法範圍。此案例應保持輕量。

## 案例二

catalog=[{'view':'sales_view','aliases':['Revenue','SALES']},{'view':'stock_view','aliases':['Stock']}]
問題 revenue 應產生 SELECT * FROM sales_view，但目前失敗。先找出第一個偏離契約的邊界，建立單節點 Replay，比較不同複雜度方案，先最小實驗再修正；不要修改 SQL 編譯器來硬補答案。對無匹配與多匹配維持拒絕。

## 案例三

select_route(['sales','stock'], 's') 會選一個路由。契約：query 必須與 label 經 casefold、前後 trim 後完全相等，且必須唯一匹配，否則回 None；空 labels／空 query 亦回 None。

先前已連續三次調整 threshold（0.3、0.6、0.9）都未滿足契約。請在暫存區實際重現這三次失敗，保存結果，重新評估方向，修正並驗證未知、空值、大小寫、重複 label。不得無限調整 threshold。

## 評估紀錄

每個案例報告根因、重現品質、替代方案、實驗範圍、Regression、過擬合風險、詢問次數、協作與恢復能力、工具／Token 成本（未提供則填 NOT_MEASURED）。不為了顯示改善而虛構成本或分數。測試成功不等於真實 LLM Pipeline 已驗證。
