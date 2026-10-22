# S1 實作與驗證紀錄

日期：2026-10-22（Asia/Taipei）。實際起點 `11d55a54a4e58591c67c11c32a4ad05ff8a098ca`，分支 `feat/progressive-view-retrieval`；起始僅計畫目錄未追蹤。所有變更尚未 commit／push；未修改 `.env` 或正式資料。

## 交付狀態

S1-02～S1-07 的程式與離線驗證已實作。新增獨立 application service、兩個核心 LangGraph node、typed 交接、整批能力 preflight、QueryPlan／SQL gate、owner 生命週期清理、三模式 runner、完整方案語意評分與離線 replay。產品入口與既有服務行為保留；僅抽出既有 renderer 共用。

**S1 尚未驗收完成。** S1-01 的面板人工核准仍 pending；S1-08 的正式三輪自然評估依使用者指示留待分階段調校。現有 smoke 均未通過自動品質檢查，未宣稱自然成功，不進入 S2。

## 離線與產品驗證

| 驗證 | 實際結果 | 證據 |
| --- | --- | --- |
| 新基準：計畫指定八個既有測試檔 | 170 passed，exit 0 | `.superpowers/sdd/query-agent-integration/baseline-tests.txt` |
| 新測試、指定兩段回歸、confirmation lifecycle、五個產品介面回歸檔 | 322 passed，42.51s，exit 0 | `.superpowers/sdd/query-agent-integration/verified-tests.txt` |
| RED／GREEN | 契約、gate、adapter、workflow、grader、runner 及錯誤分類均有失敗與通過紀錄 | `.superpowers/sdd/query-agent-integration/*-red.txt` 及對應結果 |
| wheel／sdist | build 通過，兩種封裝均包含 pipeline／runner | `.superpowers/sdd/query-agent-integration/final-build.txt`、`dist/` |
| 完整 pytest | 180 秒停止，exit 124；未取得完整結果 | `.superpowers/sdd/query-agent-integration/full-suite.txt` |
| 完整套件首個失敗定位 | 1 failed、17 passed；封存研究 binding 指紋不符 | `.superpowers/sdd/query-agent-integration/full-first-failure.txt` |

首個完整套件失敗為 `tests/diagnostics/test_managed_capability_projection.py::test_inputs_only_project_coverage_and_keep_noncoverage_policy`。不更新封存研究指紋、不弱化 guard，也不把聚焦通過宣稱為全套通過。

sentinel 與 socket 測試驗證 offline 不建構 executor／execution runtime、不連網。真實 HILP registry／checkpoint 驗證 pending 無 run_id 時仍清理本次 owner，且不自動確認或寫入產品 mapping。

## 面板與 stub

synthetic 與 Retail 各 12 題，六正向、六負向／pending；全部維持 `review_state=pending`。六題正向候選均通過既有規劃 validator，尚未有人工核准紀錄。版本與能力矩陣見 [capability-matrix.md](capability-matrix.md)。

新基準、套件版本及矩陣指紋：`projects/retail/artifacts/query_pipeline/20261022-baseline/`。三模式 stub 及 replay：`projects/retail/artifacts/query_pipeline/offline/`；每模式 12 次、0 模型呼叫，11 次自動通過，**0 次自然成功**。`dependent_input` 的候選包含 unbound input，既有 planning validator 本身拒絕；pipeline 正確回 unsupported，但 grader 保留 planning contract 失敗。此候選仍待人工修訂與核准，未為提高分數更改判分。

離線 replay 重現一個 stub 成功及自然 planning 失敗，保留原產物，新增 grader／來源指紋；replay 不計為新增自然 trial。另有測試確認 case／catalog 漂移拒絕、source 漂移標記、人工輸出審查從獨立檔載入、model task_id 不可逃逸產物目錄，以及 provider 與 evaluation error 分別停止並保存私有診斷。

## Ollama 連通 smoke

兩段皆為 `qwen3.8:27b`，端點 `http://127.0.0.1:7401`；使用者提供網址的雙冒號視為筆誤。已核對 `/api/tags`，digest：`aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`。只使用 `raw_inventory` 一題、每模式一輪，設定 lexical retrieval、停用 reranker、64K context、8000 output tokens；不是正式面板三輪評估。

| 模式 | 模型呼叫 | 最終狀態 | 首錯節點 | run ID |
| --- | --- | --- | --- | --- |
| integrated | 1 | error | planning | `20261022T061201221417Z-e5dfd4cf` |
| planning | 1 | error | planning | `20261022T060008473867Z-00eeba8c` |
| sql | 2 | unsupported | sql_generation | `20261022T060332854580Z-1dc3af4c` |

共 4 次模型呼叫，零 DB 呼叫；自動通過與人工核准自然成功均為 0。原始資料保存在 `projects/retail/artifacts/query_pipeline/smoke/<mode>/<run-id>/private/`；公開摘要無原始 prompt／response。smoke 在實作期間執行，沒有宣稱 source 固定或正式品質成績；版本限制另記在 `projects/retail/artifacts/query_pipeline/smoke/provenance-note.json`。

planning／integrated 的 `invalid_plan`：模型缺少合法 integration anchor，被既有 validator 阻擋。

SQL 獨立模式：既有 MATCH／semantic coverage 將 legacy request 的指令與 JSON 封裝視為未覆蓋文字，因此拒絕。已用固定且明確的技術欄位 mapping、真實 SQL service 與隔離 repository 離線重現，不只是模型是否連通的問題。證據：`projects/retail/artifacts/query_pipeline/20261022-baseline/offline-handoff-probe.json`（0 次真實模型呼叫、2 次 stub 呼叫）。未藉此略過文字覆蓋、HILP、compiler 或 SQL policy。

## 後續仍需完成

1. 人工核准 12 題原文需求、完整候選與替代，先修訂 dependency 候選的 planning 契約問題。
2. 修正 planning 的 integration anchor 輸出；設計並驗證 legacy transport 與舊語意覆蓋檢查的承接方式，保留原單題與確認守門。這是目前自然串接的具體首錯，不能僅憑 schema 合法或停用檢查解決。
3. source、prompt、schema 與模型固定後，依使用者指示逐段調校，完成三模式各三輪與逐題人工語意審查。
4. 完整歷史套件另行釐清封存證據／binding 問題；本次不修改歷史驗收。
