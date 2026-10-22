# 任務拆分精選審查包

共10個檔案，含本README。保留5份完整核心原碼、契約權威文件、七View契約集合及最新證據；沒有把整個專案藏進壓縮檔。主文只引用本資料夾內檔案，無超連結。

## 閱讀順序

| 檔案 | 用途 |
|---|---|
| `02_managed_three_stage_runner.py` | 自然Recall→七View Coverage→Selection、受控HTTP、保存與重播的主流程 |
| `03_managed_capability_projection.py` | 最新Coverage責任卡、有限AND Oracle、固定五樣本、委派與版本守門 |
| `04_managed_node_diagnostics.py` | 隔離engine完整流程：原始輸入／raw→parse→compile／materialize→Oracle→錯誤 |
| `05_own_responsibility_managed_contract.py` | status／own_gap與同來源scope／grain缺口的程式推導 |
| `06_three_stage_view_selection.py` | Coverage與Selection守門、supported-only assignment、母體／粒度／typed驗證 |
| `07_contract_review.md` | 既有DB metadata／View結構人工審核與已知矛盾 |
| `08_manifest.yaml` | profile、契約版本與draft狀態 |
| `09_view_contracts.yaml` | 七份原View YAML的多文件集合，各段保留原檔名與內容 |
| `10_latest_results.json` | 最新快照、已完成自然樣本實際輸入／原始回答／錯誤、21／22輪已結案handoff摘要與來源指紋 |

## partial的實際用途

目前partial保留有用能力與缺口，供Coverage診斷及未選來源的排除理由；**不能直接指派完整需求，也沒有把多個partial自動合成supported的規劃器**。最終assignment與child key重用均只取supported entries，見 `06_three_stage_view_selection.py`。

例如daily有store_id及revenue，但缺商品與online：應保留部分能力，卻不能和另一來源的通路條件直接拼成商品online營收。本題成功規劃依靠inventory與sales_detail各自完整履行分工。

若產品預期partial參與可執行的跨來源合成，仍需另定合成運算、鍵／基數、可重建性及母體證明；這項意圖尚無已核准實作。未選來源partial是否必須阻塞最終計畫驗收，也應與「完整Coverage語意驗收」分開決定。

## 最新結果與已知矛盾

`10_latest_results.json`沿用來源包的UTC快照，附當時已完成的第23輪樣本：第一個FAIL，第二個機器PASS，整輪尚未結案。

第一個樣本已保留store_id partial與revenue own_gap=false，但contract_path指到欄位物件，未指向非空文字節點，因此先在materialize被拒絕。這不代表整份語意或完整Pipeline通過；當時尚無第23輪最終handoff。

`07_contract_review.md`指出sales_detail的(order_id,product_id)未必唯一，與YAML宣告矛盾；不能據其推導FD或COUNT等價。`08_manifest.yaml`仍為draft。

## 範圍

這是精選判讀包，刻意省略其他imports及完整執行環境，不能獨立啟動Pipeline。五份核心程式均為完整原檔，未刪函式；模組關係可沿imports判讀，未收錄依賴不能假定不存在。本次只整理文件，沒有執行模型或測試，沒有修改原程式、Oracle及歷史結果。
