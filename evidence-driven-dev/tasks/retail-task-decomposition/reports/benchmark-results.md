# Retail 任務拆分實測結果

使用 Azure `gpt-6-sol`、根目錄 `.env` 的 Azure 專用連線資訊。30 個跨 View 需求各跑三次，共 90 次真實模型呼叫；不設模型呼叫次數上限，無隱藏重試。未生成或執行 SQL。

| 指標 | 題次／案例 |
|---|---:|
| 預期主要 View 選擇 | 90/90 |
| 來源與必要欄位完整涵蓋 | 79/90 |
| 現行 validator 通過並準備 request | 88/90 |
| 條件、聚合、粒度、整合鍵等自動結構檢查全通過 | 60/90 |
| 三次皆選對 View | 30/30 |
| 三次皆涵蓋必要欄位 | 24/30 |
| 三次皆準備 request | 28/30 |

## 方法與可重現性

原始模型呼叫使用 `bf626def01a2bb9bf5e623b28075222688a9bcfe` 的已載入規劃程式；實測期間修補離線評分及 deterministic 驗證，沒有改動生成 prompt、response schema 或 View 契約。90 次 request 已逐一比對目前 prompt/schema/契約及題目，沒有把預期答案或案例 metadata 放入模型 context。
以 `b16d117a2a3168a61c3cdbd889fc0e54ab079625` 的驗證器與評分器重播保存草稿，額外模型呼叫 0 次，原始 run 所有檔案 SHA-256 維持不變；6 題次的 ready/error 狀態因驗證修補改變。重評產物另存 source results、grader、validator 及 models SHA-256。
原始實測與現行版本重播分開保存，不將舊程式的結果冒稱為新版本 live 呼叫。題庫人工審核皆為 pending，本次屬探索性 benchmark；自動正確不等於完整業務語意、資料整合或 SQL 正確。

原始產物：`/home/willy/code/cpea_terms/projects/retail/artifacts/task_decomposition/20261020T050127310992Z-bf626def-7b4f2d`。
重播／重評產物：`/home/willy/code/cpea_terms/projects/retail/artifacts/task_decomposition/20261020T050127310992Z-bf626def-7b4f2d-regrade-018243`。

## 必要欄位差異

| 案例 | 至少一次遺漏的主要來源必要欄位 |
|---|---|
| cross-view-05 | snapshot_date |
| cross-view-06 | snapshot_date |
| cross-view-12 | snapshot_date |
| cross-view-14 | snapshot_date |
| cross-view-26 | order_date |
| cross-view-30 | snapshot_date |

必要欄位依原始題庫標註判斷，未因模型輸出修改答案；部分差異是快照時間 metadata。日期 filter 的月份／日期等價表示與可由唯一鍵證明的單列／計數等價已由一般規則處理。額外 grain 或其他語意差異仍需審核，不能只看 View 命中率。

## 驗證界線

- 已新增獨立前置規劃服務及 benchmark CLI，既有單 View 網頁與 SQL API 尚未自動串接。
- 不驗證實際 SQL、資料數值、DB 權限、真正合併結果或採購決策。
- 真實呼叫失敗或限流不重跑；本次 completed/failed/skipped 以 run metadata 為準。
- 獨立 code review 與負面重播為 PASS_WITH_WARNINGS；自然語言 request 與整合語意仍需人工審核。
