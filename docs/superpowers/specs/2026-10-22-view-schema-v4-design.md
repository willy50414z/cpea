# View Schema v4 設計規格

## 目的、範圍與完成定義

使用者要求 `summary` 僅描述 view，將粒度、欄位、使用情境及計算規則拆開，以明確來源語意改善 text-to-SQL。以既有成功 10 題、失敗 10 題及 Azure DeepSeek 比較修改前後結果；評估條件沿用 [前後測規格](2026-10-22-view-schema-ab-evaluation.md)。

本次包含 v4 YAML 契約、驗證與傳遞、七個 Retail views 的遷移、產生器修正及前後測。保留既有 SQL 能力、服務介面、v1／v2／v3 profile、MATCH v10、檢索權重、候選比較策略及原始測試 Oracle。不得新增任意公式執行、join compiler、模型 fallback 或依測試題文寫特例。

完成時提供可載入的七份 v4 YAML、欄位規格文件、必要回歸結果、前後逐題比較與限制。正確率未提升也如實交付，不反覆調整後測挑選最佳成績。

## 已有證據與架構限制

- 產生器將完整 DB comment 複製為 summary，又從同一段文字擷取 grain，因此資訊混雜會重現。
- v3 loader 僅接受 `version/view/summary/grain/columns`；不能直接添加新欄位。
- 檢索只收 summary／欄位描述，`candidate_schema` 與比較候選另有白名單投影；僅新增 YAML 會遺失語意。
- v3 依型別推導能力，並扣除明列禁止操作；v4 延續此規則，本次不改聚合能力推導政策。
- frozen v3 profile 指紋為 `e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc`。
- 本輪已以唯讀連線檢查七個 PostgreSQL view 定義、直接來源關係、欄位 metadata 與來源唯一約束，未讀業務資料列或修改 DB。證據保存在私有前後測目錄的 `source-evidence/postgres-metadata.json`。
- `v_sales_detail` 沒有輸出 `order_item_id`；來源唯一約束為 `order_item_id`、`(order_id,line_no)`，不能證明輸出的 `(order_id,product_id)` 唯一。新版 keys 必須為 null。
- `v_inventory_status.sold_qty_30d` 的 SQL 明確固定在 2026-09-15～2026-10-14；`v_customer_value.active_in_last_90d` 使用 `last_order_date >= 2026-07-17`，沒有上界，不能誤寫為完整有上下界的 90 日窗口。
- `v_store_monthly_kpi.is_complete_month` 是 `sales_month < 2026-10-01` 的固定判定，不是依執行當下月份動態計算。

## 方案選擇

採用新的 v4 結構化契約。只清理 summary 會使重要資訊無處保存；直接建立完整語意引擎則超出需求。v4 使用 5W1H 作資訊檢核，以明確欄位承載資訊，不以問題模板或敘事段落代替契約。

| 原則 | 欄位責任 |
|---|---|
| What | summary 描述 view；columns 描述輸出欄位 |
| Who | 欄位 description 與可選 entity 說明業務物件，例如會員城市／門市城市 |
| Where | source 記實際來源與 DDL 證據；scope 記母體、內建納入／排除及資料列是否出現 |
| When | time 記時間軸、涵蓋期間與固定／滾動窗口的真實規則 |
| Why | usage 記可支援與不支援的問題及原因 |
| How | grain 記每列意義／唯一鍵；metrics 記計算口徑與再聚合規則 |

## v4 欄位契約

v4 頂層必須包含下表所有欄位，拒絕未知設定；各物件也拒絕未宣告欄位。所有 description／文字規則須非空。未知值使用明確 null，不把空字串當未知。

| 欄位 | 形狀及驗證 |
|---|---|
| version | 整數 4；loader 明確分派版本，未知版本拒絕，不落入舊版解析 |
| view | 現有 qualified view identifier，與 catalog entry 相同 |
| summary | 非空單段 view 描述；不放欄位清單、粒度、情境、篩選、期間或公式。語意分工由文件與案例審查確認，不以關鍵字禁詞推定意思 |
| grain | `description: str`、`keys: list[str]或null`；keys 非空時不得重複且須存在輸出欄位。description 僅描述每列對象／組合，納入／排除移至 scope |
| source | `verification: metadata_verified或unknown`、`relations: list[str]或null`、`definition_sha256: 64位小寫hex或null`。metadata_verified 必須提供來源與 hash；unknown 不得冒填 verified。這不是業務核准狀態，也不提供模型查詢 base tables 的權限 |
| scope | `population: str`、`included: list[str]`、`excluded: list[str]`、`row_coverage: str`。內建條件作事實描述，不轉成重複 WHERE 或不存在欄位 |
| time | `kind: event/aggregate/snapshot/cumulative/mixed/unknown`、`dimensions: dict[日期欄位,str]`、`coverage: str或null`、`rules: list[規則]`。規則包含 `columns: list[str]`、`description: str`；引用須為現有欄位，不要求規則只能引用日期型別 |
| usage | `supported: list[str]`、`unsupported: list[項目]`；每個項目為 `question: str`、`reason: str`。不支援情境必須交代資料不足原因，不以否定關鍵字直接拒絕需求 |
| columns | 延續 v3 型別、role、description、unit 與 disallowed 設定；v4 只新增可選非空 `entity`。本次不改現有欄位名稱與型別，不擴大 SQL 能力 |
| metrics | `dict[指標名稱,定義]`，允許 `{}`；定義為 `description: str`、`columns: list[str]`、`calculation: str`、`aggregation_notes: str`。所有 columns 引用須存在；calculation 只作可審查的語意證據，不執行、不拼接到 SQL、不賦予 compiler 新能力 |

空陣列代表已確認沒有該類規則／情境；未知完整涵蓋期間使用 `time.coverage: null`。`source.relations: null` 是來源尚未知，不能用空陣列冒充沒有來源。除 v4 外，其餘既有版本的合法輸入及行為保持相容。

`time.dimensions` 說明可篩選的時間軸；`time.rules` 說明篩某欄對累計／窗口指標不會產生的效果。例如會員 registered_on 是註冊日期，不會把 lifetime_spend 限制成該期間的交易金額。日期範圍與樣本資料分布分開，不從查到的 min/max 推定契約涵蓋期間。

## 訂單 view 範例

以下為核心節錄；實作必須包含完整 columns、metrics 與真實來源 hash，不能直接拿節錄當完整 profile。

```yaml
version: 4
view: demo_retail.v_order_summary
summary: 訂單銷售彙總資料。
grain:
  description: 每筆訂單一列
  keys: [order_id]
scope:
  population: 有商品明細且能連結門市與會員的已完成訂單。
  included: [已完成訂單]
  excluded: [未完成訂單]
  row_coverage: 沒有商品明細的訂單不會出現。
time:
  kind: event
  dimensions:
    order_date: 訂單成立日期。
    order_month: 訂單成立月份首日。
  coverage: null
  rules:
    - columns: [order_date, order_month]
      description: 日期與月份都來自訂單成立時間，不代表付款時間。
usage:
  supported: [訂單筆數與訂單銷售金額分析, 銷售通路分析]
  unsupported:
    - question: 商品層級銷售分析
      reason: 商品明細已彙總，沒有輸出商品維度。
```

## 下游資料流與相容性

1. YAML loader 驗證版本、結構、所有欄位引用與來源證據形狀；建立既有 ViewDefinition，不新增並行 catalog。
2. CatalogContract 讓 v4 沿用 v3 能力及 operator 推導；detail／model_schema_context 同步呈現新語意區塊。
3. build_documents 索引 summary、grain、scope、time、usage 與指標語意，保持既有移除實體欄位名稱的策略。summary metadata 保留純描述，不將全部資訊塞回 summary；檢索權重及 cutoff 規則不改。
4. candidate_schema 完整傳遞 v4 區塊與可選 entity。候選比較既有 evidence、signature、contract_text 投影補上新區塊，但不改比較策略／MATCH prompt。完整 raw DDL 與題庫答案不進入模型 context。
5. term mapping 契約指紋沿用包含完整 policy 的既有作法，變更契約後不沿用過期確認。
6. v3 的既有 temporal_scope／data_scope 處理保留；v4 不從 kind=snapshot 自動推定現在，也不新增一套會擅自改寫時間條件的行為。

## Retail 遷移與產生器

- 七份 summary 改為單純描述。grain 去掉母體篩選文字，移至 scope；修正 sales_detail 不可證實的 keys。
- source 依直接依賴關係與 pg_get_viewdef hash 填寫；完整證據另存，不把 base table 加進允許查詢集合。
- scope 如實記錄 inner／left join 母體、沒有交易日不出現、月目標母體與未下單會員是否保留。
- time 如實記錄固定 30 日窗口、只有下界的會員活躍判定與固定完整月份判定；庫存 snapshot_date 不被宣稱一定等於最新日期。
- 保留既有 columns 的名稱、型別、role、單位與禁止操作。只有在 DDL 證據顯示描述錯誤／漏掉關鍵時間語意時才更正；不得依模型失敗題調整詞句或建立特例。
- metrics 記錄已存在的欄位公式、訂單計數口徑、比率／單價／快照的再聚合限制；不能因出現公式就宣稱產品能生成新的任意比率。
- generator 不再由完整 comment 推定 summary／grain／情境。使用顯式、經檢視的 Retail 語意定義與唯讀 metadata 合成 v4；沒有語意定義或 DDL／唯一性證據變動時拒絕產生，不猜測。
- generator 既有不覆寫及差異要求人工合併的保護保留。更新 contract_review.md，區分 metadata 核對、技術可載入及尚未完成的業務核准。
- manifest profile_id 不變，contract_version 更新為 4；維持現有 status，不回填任何新的業務／案例人工核准。

## 驗證與公平比較

- 前測在修改任何產品程式或 profile 前完成；本輪已啟動，60 trials 全部保留固定分母。
- 針對 v4 合法／非法形狀、未知版本、引用、source hash、未知值及 v3 相容性先寫能失敗的測試，再實作。
- 驗證 v4 內容能抵達檢索、candidate_schema、候選比較及詳細 context；來源 table 不能被加入 SQL allowlist。
- 聚焦驗證 catalog、retrieval、text-to-SQL、需求拆分與 SQL pipeline 受影響路徑；新失敗先找根因，不弱化原 Oracle。
- 後測保持固定案例檔案不變。只為對新 catalog 執行結構驗證，在記憶體建立新的 pending fingerprint 綁定；原 Oracle、內容 hash 與人工核准不變。
- 前後測使用同一份已凍結 harness、grader、prompt、模型設定與題目順序；保存逐次原件及來源差異。
- live evaluator 要求乾淨工作目錄。產品變更完成離線驗證後，需要明確授權的本機提交才執行後測；不繞過 clean preflight、不自動 commit／push。具體變更與驗證將在提交前呈現。
- 比較報告分開原成功／原失敗、每輪／全部 trial／三輪全通過、改善／退步、首錯及成本。正確性僅指原 Oracle 與 SQL 靜態檢查，不宣稱 DB 數值正確。

## 審閱狀態

本規格已依本輪唯讀 metadata 檢視，使用者已核准規格及後續實作計畫，指定在目前 worktree 依序實作。v4 遷移與後續同條件三輪測試已完成；實際範圍、驗證與未解限制見[實作計畫](../plans/2026-10-22-view-schema-v4.md)及[評估紀錄](../reports/2026-10-23-view-schema-v4-evaluation.md)。使用者已另行授權本機提交與 push。
