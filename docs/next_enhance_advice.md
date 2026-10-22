
# CPEA 三階段任務拆分架構設計評估

## 1. 文件目的

本文件評估 CPEA ERP 查詢助手目前的三階段任務拆分架構，研究 Coverage 語意判斷不穩定的原因，並比較可行的改善方案。

本階段目標：

1. 確認現有架構的能力、限制與責任邊界。
2. 區分 LLM 語意錯誤、輸出契約錯誤、Oracle 錯誤與整合規劃錯誤。
3. 比較三種候選架構及其修改成本、風險與泛化能力。
4. 設計有辨識力的對照實驗。
5. 根據實驗證據決定最小必要修改。

**本階段不直接修改程式碼，也不預先決定採用某個方案。**

---

## 2. 專案目標與約束

### 2.1 產品目標

CPEA 是 ERP 自然語言查詢助手。

使用者輸入自然語言後，系統須完成：

1. 理解業務需求。
2. 找出受治理的資料來源與合法能力。
3. 拆分成可以由單一 View 執行的查詢任務。
4. 選擇適合的資料來源。
5. 規劃跨來源的安全整合方式。
6. 產出結構化的 prepared requests。

目前僅驗證規劃能力，不產生或執行 SQL，也不執行資料庫查詢。

### 2.2 技術約束

- 本地模型：Ollama `qwen3.8:27b`。
- 模型呼叫次數、等待時間及輸出 token 不設研究性上限。
- 目前模型設定：`num_ctx=32768`、`num_predict=-1`、`temperature=1`、`top_p=1`、`seed=42`、`think=true`。
- 目前測試範圍：七個 Retail View。
- 保留既有受治理 View 契約。
- 不允許模型引用不存在的欄位或能力。
- 不允許錯誤粒度、指標重複計算、母體流失。
- 不以重試抽中成功答案代替架構改善。
- 所有原始失敗紀錄、模型設定及證據 hash 必須保留。

### 2.3 契約狀態

`projects/retail/manifest.yaml`：

```yaml
profile_id: demo_retail_draft
contract_version: 3-draft
status: approved
```

已確認：

- `approved` 只代表技術測試允許使用。
- 七份 View 的業務契約尚未正式核准。
- 技術測試通過不代表業務契約已正式認證。
- `v_sales_detail` 的宣告唯一鍵存在已知矛盾，仍須保守處理。

此區別不應阻止技術研究，但不得以測試成功自動消除契約不確定性。

---

## 3. 現有架構

### 3.1 Pipeline

目前自然端到端流程：

```text
Natural Language Request
          |
          v
[1] Recall (LLM)
    - 辨識 requirements
    - 指標、條件、粒度、母體
    - scope_ids
    - grain_requirement_ids
    - grain_binding
          |
          v
[2] Coverage (LLM × 7 Views)
    - 每個 View 獨立映射
    - mappings
    - own_gap
    - status
    - contract_path
          |
          v
[3] Selection (LLM)
    - selected_views
    - assignments
    - exclusions
    - structured tasks
    - integration
          |
          v
[4] Deterministic Validation
    - Schema / evidence
    - filters / metrics
    - grain / population
    - Join / missing policy
          |
          v
Prepared Requests
```

正常流程共九次模型呼叫：

- Recall：1 次。
- Coverage：7 次。
- Selection：1 次。

主要執行入口：

`evaluations/managed_three_stage_runner.py::run_pipeline`

### 3.2 已具備的確定性能力

目前程式已實作：

- Requirement ID 完整性與唯一性檢查。
- Recall 原始文字索引引用。
- 所有 admitted View 的候選保留。
- 契約證據文字由程式取得。
- 依 requirement kind 使用不同 mapping schema。
- 必填的 typed JSON 欄位。
- 固定 grain evidence path。
- `scope_ids` 與 `grain_requirement_ids` 依賴缺口推導。
- 證據路徑與欄位合法性驗證。
- 模型輸出與原始 View 契約一致性檢查。
- supported-only assignment。
- Selection 與 prepared request 的 typed 驗證。
- 部分母體、Join、粒度及缺值政策檢查。
- 原始模型回覆、版本及證據的保存和重播。

**因此 CPEA 並非缺乏確定性機制，而是尚未將所有適合確定性處理的責任與模型語意責任清楚分離。**

### 3.3 仍由 LLM 決定的項目

Coverage 模型目前需要直接輸出：

```json
{
  "status": "partial",
  "own_gap": false,
  "mappings": [
    {
      "column": "revenue",
      "aggregation": "sum",
      "conditions": []
    }
  ],
  "contract_path": "/columns/revenue/description"
}
```

其中：

- `mappings`：模型判定。
- `own_gap`：模型判定。
- `status`：模型判定。
- `contract_path`：模型選擇。

程式會檢查結果的一致性，但通常不會從完整契約中自動找回模型漏掉的能力。

### 3.4 partial 的既定意義

依目前設計：

`partial` 表示該 View 具有與需求相關的有用能力，但無法獨立完整履行該責任。

用途：

1. 保留部分能力的可追溯證據。
2. 描述缺少的自身能力或依賴。
3. 協助解釋來源為何未被選用。
4. 供 Coverage 語意完整性驗證。

既有限制：

- `partial` 不得直接指派完整 requirement。
- Selection 只接受 `supported` assignment。
- 目前沒有多個 partial 自動組成 supported 的規劃器。

因此，**跨來源 partial 合成不屬於本輪必要開發範圍**。

---

## 4. 問題分類與最新證據

### 4.1 問題一：有用部分能力遺漏

案例：

需求粒度為：

`門市 × 商品`

`daily_sales` 提供：

- `store_id`
- `sales_date`

但沒有：

- `product_id`

預期：

```json
{
  "status": "partial",
  "own_gap": true,
  "mappings": [
    {"column": "store_id"}
  ]
}
```

第 20 輪模型實際輸出：

```json
{
  "status": "unsupported",
  "own_gap": true,
  "mappings": []
}
```

問題不是契約沒有提供 `store_id`，而是模型把「無法完成完整粒度」當成「沒有有用的部分能力」。

### 4.2 問題二：自身缺口與依賴缺口混淆

`daily_sales.revenue` 已具備淨銷售額能力。

但需求另外要求：

- 線上通路。
- 門市 × 商品粒度。

這些需求在該 View 無法完整支援。

預期：

```json
{
  "status": "partial",
  "own_gap": false,
  "mappings": [
    {
      "column": "revenue",
      "aggregation": "sum",
      "conditions": []
    }
  ]
}
```

第 20 輪模型將 `own_gap` 錯誤設為 `true`。

正確的責任區分應為：

- 自身淨額能力：存在。
- 線上通路依賴：不完整。
- 商品粒度依賴：不完整。
- 最終完整需求：該 View 無法獨立支援。

### 4.3 問題三：證據表示格式錯誤

第 23 輪的最新自然測試，模型已正確保留：

- `store_id` partial。
- `revenue` 的 `own_gap=false`。

但輸出了：

```json
{
  "contract_path": "/columns/revenue"
}
```

此路徑指向物件，不是文字。

現有 `contract_text()` 要求路徑指向非空字串，因此被拒絕。

合法路徑例如：

```text
/columns/revenue/description
```

這是與能力識別不同的錯誤類型。

注意：

- 第 23 輪第一個樣本仍為 FAIL。
- 失敗時尚未完成全部後續語意驗證。
- 會員負例取得機器 PASS。
- 目前未取得五個樣本全部完成及獨立結案的證據。

不能因此推論新版責任卡已穩定解決 Coverage。

### 4.4 問題四：Oracle 過度限制

既有 Oracle 使用固定 expected JSON 直接比較 mapping。

例如：

```json
{
  "aggregation": "sum",
  "conditions": []
}
```

模型可能輸出完全相同且已獨立驗證的月份 AND 條件。

若該 metric 明示依賴的 scope 已完整驗證，這可能是合法的條件重列，而不是業務錯誤。

第 21～22 輪已加入有限等價判斷。

但其限制必須保留：

- 只接受同 View。
- 必須有明示且已完整驗證的 scope。
- 不能接受錯月份。
- 不能接受漏條件。
- 不能把不同通路視為等價。
- 不能將此機制擴張成未證明的任意 WHERE 等價。

### 4.5 問題五：測試結果層級混淆

下列結果必須區分：

| 結果 | 可以證明 | 不能證明 |
|---|---|---|
| HTTP 200 | 請求成功完成 | 業務正確 |
| JSON Schema PASS | 輸出形狀合法 | 能力識別正確 |
| Offline PASS | 確定性驗證符合測試 | 自然模型可產生正確答案 |
| Isolation PASS | 單一階段通過 | 完整 Pipeline 通過 |
| Machine PASS | 已實作檢查未發現錯誤 | Oracle 沒有漏判 |
| Semantic ACCEPT | 指定證據經獨立語意核對 | 跨場景泛化 |
| E2E PASS | 指定自然案例完整通過 | 新產業、新契約全面可靠 |

---

## 5. 架構改善候選方案

本次比較三種方案。

### 5.1 方案 A：保留現有責任卡，改善結構化輸出

#### 核心思路

保留：

- 現有三階段 Pipeline。
- Coverage 每 View 一次 LLM。
- `requirement_cards`。
- `mappings`。
- `own_gap`。
- `status`。
- 現有 Oracle 與最終守門機制。

優先處理證據引用與輸出結構問題。

#### 可研究的修改

A1. 限制 contract_path 合法選項。

根據實際 View 契約，產生可用的非空文字 JSON Pointer 選項。

例如：

```text
/summary
/grain/description
/columns/store_id/description
/columns/revenue/description
```

避免模型自行生成任意路徑。

A2. 研究是否能從模型已選擇的 mapping 欄位，由程式生成對應欄位證據。

注意：

- 現有程式已會從 mapping column 取得其 description 證據。
- 不能將「欄位存在」直接等同「業務能力完整」。
- 不能用程式憑空補上模型沒有選擇的 mapping。
- 若變更證據策略，必須作為新版本驗證，不得修改舊 raw 或翻轉歷史 FAIL。

A3. 精簡重複的責任說明與 Prompt。

僅移除已由 Schema 或程式確定保證、且不需要模型再次判斷的內容。

#### 優點

- 修改範圍較小。
- 保留已驗證的現有 Pipeline。
- 有機會解決第 23 輪的 contract_path 錯誤。
- 能先驗證責任卡是否已足以改善語意判斷。

#### 限制

- 模型仍直接決定 mappings、own_gap、status。
- 不能保證部分能力永遠不遺漏。
- 不能根本消除重複分類責任。
- 單一案例成功不能證明穩定性。

#### 研究價值

優先度：高。

建議先作為低成本基準改善實驗，而不是直接視為最終架構。

---

### 5.2 方案 B：Coverage 內部拆分語意判斷

#### 核心思路

保留最外層三階段：

```text
Recall
  |
Coverage
  |
Selection
```

但將 Coverage 內部拆成多個明確責任。

建議研究：

```text
[Coverage-1]
Atomic Capability Extraction
  |
  v
[Coverage-2]
Own Responsibility Evaluation
  |
  v
[Coverage-3]
Dependency & Status Evaluation
  |
  v
Validated ViewCoverage
```

#### Coverage-1：Atomic Capability Extraction

LLM 只回答：

> 這個 View 有哪些可證明與各項 requirement 相關的欄位、運算及部分能力？

例如：

```json
{
  "requirement_id": "GRN-001",
  "usable_mappings": [
    {"column": "store_id"}
  ]
}
```

此階段不輸出：

- status
- own_gap
- 最終來源選擇
- integration

程式驗證 mapping 欄位與契約證據。

#### Coverage-2：Own Responsibility Evaluation

使用第一階段已驗證的 mapping，判斷：

> 忽略明示的外部 scope/grain 依賴後，目前證據是否完整履行該 requirement 自身責任？

例如：

```json
{
  "requirement_id": "MET-003",
  "own_gap": false
}
```

此處仍屬語意判斷。

模型不能改動第一階段已確定的 mappings，若證據不足應保持未知或拒絕宣稱完整。

#### Coverage-3：Dependency & Status Evaluation

根據：

- mappings
- own_gap
- scope_ids
- grain_requirement_ids
- 其他 requirement 的 coverage

決定 status 及依賴缺口。

本階段有兩種值得對照的版本：

B1. 仍由 LLM 輸出 status，再交程式驗證。

B2. 由程式推導 status，模型不再輸出 status。

其中 B2 與方案 C 的研究方向重疊。

#### 優點

- 將能力識別與完成性判斷分開。
- 降低單次 LLM 同時處理多種責任的負擔。
- 各階段錯誤更容易定位。
- 可以針對個別語意錯誤建立測試。
- 不需要立即重建 View 契約。

#### 限制

- 模型呼叫次數增加。
- 中間資料契約增多。
- 若第一階段漏掉能力，下游仍無法自行修正。
- 需要嚴格避免第二階段重新捏造 mapping。
- 更細的拆分不必然提升準確率，必須實測。

#### 研究價值

優先度：最高。

這是最直接對應第 20 輪根因的架構實驗。

但是否正式採用，應取決於它能否明顯改善未見案例的語意正確率，而不是流程看起來比較清楚。

---

### 5.3 方案 C：Capability Evidence + Deterministic Coverage

#### 核心思路

由 LLM 識別無法純靠程式確定的業務語意，程式負責可確定的依賴及狀態推導。

概念：

```text
Natural Requirement
        |
        v
LLM Semantic Mapping
        |
        v
Verified Capability Evidence
        |
        v
Own Responsibility Assessment
        |
        v
Deterministic Dependency Evaluation
        |
        v
Coverage Status
```

#### 可以考慮交由程式的責任

1. Requirement ID 完整性。
2. 欄位是否存在。
3. Mapping 操作是否被契約允許。
4. 引用證據是否有效。
5. 明示 scope/grain 依賴是否 supported。
6. 在輸入狀態已可靠的前提下推導 Coverage status。
7. 判定有無滿足 Selection 的 supported-only 條件。

#### 不應假設能直接由程式完成的責任

1. 任意自然語言與欄位的業務同義判斷。
2. 任意指標的業務定義。
3. 有用部分能力是否完整列出。
4. 未結構化的來源母體限制。
5. 未受治理的跨 View Join 真實性。
6. 未經契約核准的函數相依。
7. 跨時間與跨粒度的指標可加性。

這些問題必須先取得足夠契約資訊或其他可靠證據。

#### 重要限制

假設：

```json
{
  "mappings": [
    {"column": "revenue"}
  ],
  "own_gap": false
}
```

即使程式可以根據依賴狀態推導 `partial`，也不能證明 `own_gap=false` 是正確的。

因此：

**確定性推導 status，不等於完整實現確定性 Coverage。**

需要明確區分：

- Evidence validation。
- Own capability completeness。
- Dependency completion。
- Final coverage classification。

若要進一步把 own_gap 也改成確定性推導，必須先研究契約是否有足夠的機器可讀能力定義。

#### 是否需要擴充 Semantic Layer？

目前七份 YAML 已提供：

- View 原生粒度。
- Grain keys。
- 欄位型別。
- Role。
- Description。
- 部分禁止聚合與操作。

尚未提供完整的：

- 跨 View Join 關係。
- Join cardinality 的治理證據。
- 通用函數相依。
- 指標公式圖。
- 完整時間可加性。
- 結構化母體包含關係。

目前沒有證據支持必須一次重建整套 Semantic Layer。

應採取漸進方式：

1. 先驗證能從現有契約推導哪些規則。
2. 找出無法推導的具體案例。
3. 只有在有明確業務需求及權威證據時才擴充契約。
4. 新契約須定義版本、Loader、驗證與業務審核。
5. 不為單一失敗測試硬編碼 Retail 特例。

#### 優點

- 降低重複分類與自相矛盾的機會。
- 可提高狀態推導的可重現性。
- 容易追溯判定依據。
- 有利於未來多模型及混合推論環境。

#### 限制

- 修改成本較高。
- 可能需要增加契約結構。
- 規則錯誤會系統性影響全部案例。
- 不完整的契約可能造成錯誤確定性。
- 不保證解決 LLM 漏掉原子能力的問題。

#### 研究價值

優先度：高，但需要先由 B 的結果確認語意邊界。

---

## 6. 三方案比較

| 評估面向 | A：改善責任卡 | B：拆分 Coverage | C：確定性推導 |
|---|---|---|---|
| 修改範圍 | 小 | 中 | 中～大 |
| 保留外部三階段 | 是 | 是 | 是 |
| 額外模型呼叫 | 可不增加 | 可能增加 | 視設計而定 |
| 修正證據路徑 | 直接 | 可處理 | 可處理 |
| 降低語意負擔 | 有限 | 高 | 視責任轉移程度 |
| 降低 status 重複推導 | 低 | 中 | 高 |
| 解決 mapping 遺漏 | 不保證 | 有機會 | 不保證 |
| 依賴契約完整性 | 較低 | 中 | 較高 |
| 架構複雜度 | 低 | 中 | 較高 |
| 主要風險 | Prompt 過擬合 | 階段間錯誤傳遞 | 不正確規則被固化 |
| 建議研究順序 | 第一 | 第二 | 第三 |

這是基於目前架構的工程假設，不是已量測的性能比較。

---

## 7. 建議的研究順序

### Phase 0：凍結現有 Baseline

正式實驗前：

- 固定 Git SHA。
- 固定模型 digest。
- 固定模型設定。
- 固定七個 View 契約。
- 固定 Prompt 與 JSON Schema。
- 固定原始模型輸入。
- 保留歷史 raw、FAIL 與 Oracle 結果。
- 第 23 輪尚未結案時不得把部分結果當成完整成功。

先完成現有責任卡五個固定自然控制案例的結果蒐集與獨立核對。

如果新結果已完成，可直接利用；不得為本研究覆寫既有結果。

### Phase 1：確認 A 的效果

對照：

A0：目前責任卡版本。

A1：限制證據引用格式的候選版本。

A2：減少重複欄位責任、使用既有契約證據生成機制的候選版本。

驗證：

- 是否仍遺漏 store_id / loc_key。
- 是否正確判定 own_gap。
- 是否正確識別無關會員鍵。
- 是否產生非法證據路徑。
- 是否改變原本正確的條件與負例。
- 是否增加新的錯誤。

若 A 已穩定通過既有與未見語意控制，應優先保留最小修改方案。

### Phase 2：驗證 B 的假設

若 A 仍存在語意不穩定，建立 B 的隔離原型。

比較：

- 一次完整 Coverage。
- 分開 Atomic Mapping 與 Own Assessment。
- 分開 Atomic Mapping、Own Assessment、Status Evaluation。

每個中間輸出都保存 raw 與 normalized evidence。

最重要的是分辨：

```text
Mapping 沒找到
    vs
Mapping 找到了但 own_gap 錯
    vs
Mapping/own_gap 正確但 status 錯
```

觀察增加模型呼叫後，是否真的降低語意錯誤，而不是只把錯誤移到另一個節點。

### Phase 3：研究 C 的可確定性邊界

在 B 的能力識別結果可接受後，研究：

- 哪些 status 可由程式直接推導。
- 哪些 own_gap 必須保留語意判斷。
- 哪些可依既有 YAML 提供確定性證明。
- 哪些缺口需要新增機器可讀契約。
- 規則是否會錯誤擴大 supported 能力。

不得因程式產生合法 JSON 就當成業務正確。

### Phase 4：完整三階段驗證

採用候選方案後，進行：

1. 自然 Recall。
2. 全部七個 View Coverage。
3. 自然 Selection。
4. 完整 typed Integration。
5. Prepared Requests。
6. 獨立語意 ACCEPT。
7. 原歷史案例回歸。
8. 新增未見案例驗證。

不執行 SQL 或 DB。

---

## 8. 測試設計

### 8.1 必要測試類別

| 類別 | 測試目的 |
|---|---|
| Partial Capability | 有用部分鍵不得漏掉 |
| Unrelated Capability | 不得用無關 identifier 湊 partial |
| Own Responsibility | 自身缺口與依賴缺口分離 |
| Missing Scope | 不得借用其他 View 的條件 |
| Grain Compatibility | 不得宣稱不存在的完整粒度 |
| Metric Semantics | 淨額、折扣、毛利、庫存不得混淆 |
| Population | 不得遺失使用者要求保留的母體 |
| Evidence | 來源證據引用合法且相關 |
| Date Boundary | 完整月份、閏年、區間邊界 |
| Schema Renaming | 改名後不得依賴原欄位字串 |
| Negative Case | 不支援需求不能輸出 ready |
| Join Safety | 不得重複計數或不安全地放大來源 |
| Missing Data | 區分 NULL、無列與真正的 0 |
| Output Shape | Flat、nest、pivot 政策一致 |

### 8.2 Metamorphic Testing

建立受控的變形測試，例如：

- 欄位改名但語意契約不變。
- Requirement ID 改成任意字串。
- 日期改為不同月份及閏年。
- 同義問題改寫。
- 移除商品鍵。
- 新增與問題無關的欄位。
- 替換成不相關會員 View。
- 在保持相同業務語意的前提下重列完整 AND 條件。

對每種變形明確定義哪些結果應保持不變、哪些應改變。

特別注意：

- 欄位改名必須保留可證的相同語意。
- 不能假設新增任何欄位都應提升 Coverage。
- 不得接受錯誤月份或缺少通路的「近似等價」。

### 8.3 測試資料隔離

既有 38 題：

- 30 題原始案例。
- 8 題 Gate。
- 36 題預期 ready。
- 2 題預期負例。

其中部分案例已被多次使用作為診斷與修正依據。

因此：

- 既有案例可作回歸驗證。
- 不得將已曝光的 Gate 稱為完全未見測試。
- 應另建獨立未見問題與契約變形。
- 新未見案例須在模型測試前核准預期結果。
- 不得依據模型輸出反向修改唯一標準答案。
- 合法替代解法需要獨立語意核對。

### 8.4 測試指標

不能只看整體 PASS Rate。

至少記錄：

**Evidence Recall**

有用能力是否完整找到。

**Evidence Precision**

是否捏造或錯誤映射欄位。

**Own Gap Accuracy**

是否正確判定自身責任完整性。

**Dependency Accuracy**

是否正確保留 scope/grain 依賴。

**Status Accuracy**

Coverage status 是否符合自身能力及依賴狀態。

**Evidence Validity**

contract_path 與引用文字是否有效。

**Planning Safety**

是否錯誤產生 unsupported assignment、不合法粒度或母體損失。

**Oracle False Reject**

合法答案遭錯誤拒絕的比例。

**Oracle False Accept**

錯誤答案被機器接受的比例。

**Metamorphic Consistency**

等價輸入的結果是否保持預期一致性。

**Natural E2E Success**

完整自然流程是否通過獨立語意驗收。

### 8.5 重複性與比較公平性

初步測試可每題執行至少三次，估計自然輸出穩定性。

但三次成功不代表泛化可靠。

A/B/C 比較時：

- 使用相同契約與題目集合。
- 固定模型版本及可控制參數。
- 另用多 seed 或不同受控條件檢查穩定性。
- 記錄每次首次輸出，不挑最好答案。
- 保存各階段耗時與 token 用量。
- 將語意品質與額外呼叫成本分開比較。
- 不因方案呼叫次數不同而改變正確性標準。

---

## 9. Oracle 改善原則

### 9.1 結構與語意分開

建立明確的驗證分類：

```text
RAW MODEL OUTPUT
       |
       v
Structural Validation
       |
       v
Contract / Evidence Validation
       |
       v
Requirement Semantic Validation
       |
       v
Planning Safety Validation
       |
       v
Independent Semantic Review
```

任何階段失敗，都必須記錄實際失敗點。

例如：

```text
MODEL_SEMANTIC_OMISSION
MODEL_OWN_GAP_ERROR
MODEL_STATUS_ERROR
INVALID_EVIDENCE_PATH
INVALID_MAPPING_SCHEMA
ORACLE_FALSE_REJECT
UNSAFE_INTEGRATION
```

其中 `ORACLE_FALSE_REJECT` 應由獨立審核確認，不得由測試作者自行宣告。

### 9.2 早期錯誤的診斷處理

例如第 23 輪：

- `store_id` mapping 已正確。
- `revenue own_gap` 已正確。
- `contract_path` 不合法。
- materialize 提前停止。

建議研究是否可以在隔離診斷中，針對原始 typed output 另外執行不具修復能力的語意觀察。

但必須遵守：

- 正式 Pipeline 繼續拒絕非法結果。
- 不修改 raw。
- 不將診斷上的語意正確視為正式 PASS。
- 不補模型遺漏的答案。
- 不以新診斷結果回寫歷史裁決。

目的只是讓研究者知道實際錯誤分布。

### 9.3 等價規則

優先支援具備明確證明的有限等價：

- 相同條件集合順序不同。
- 相同完整月份的合法日期邊界。
- 同 View 已獨立驗證的完整 scope AND 重列。
- 無業務差異的 task_id 重命名。

其他等價應保持需要審核，而非預設通過。

---

## 10. 架構決策標準

### 10.1 何時選擇 A？

如果：

- 責任卡已能穩定保留有用部分能力。
- own_gap 正確率達到預定標準。
- 主要剩餘失敗是證據格式或輸出契約。
- 修正後沒有新增語意回歸。

則優先採用 A。

### 10.2 何時選擇 B？

如果：

- A 修正後仍出現 mapping 遺漏。
- LLM 仍混淆自身與依賴缺口。
- 分離語意責任的隔離實驗有明顯改善。
- 增加呼叫沒有引入不可接受的錯誤傳遞。

則採用 B，且只拆分經證明需要分離的責任。

### 10.3 何時選擇 C？

如果：

- 已驗證的 mapping 與 own_gap 可以穩定取得。
- status 重複分類仍是主要錯誤來源。
- 現有契約足以支持明確的規則推導。
- 確定性規則在正反例及未見契約上均正確。
- 可用有限修改取代重複模型判斷。

則研究導入 C。

不得為了使用 Deterministic Planning 而假設契約已經提供所有業務資訊。

### 10.4 不應作為採用理由的證據

下列任何一項都不足以單獨決定架構：

- 單題 PASS。
- 模型 reasoning 看起來正確。
- JSON 合法。
- 離線測試數量增加。
- Prompt 更長、更詳細。
- 使用更多模型呼叫。
- 一次 38/38，但題庫已大量曝光。
- 確定性規則取代 LLM 後通過原本硬編碼的案例。

---

## 11. 風險與非目標

### 11.1 主要風險

**風險 A：測試過擬合**

反覆修正同一個 daily_sales 案例，卻沒有改善新 View 的泛化能力。

**風險 B：確定性規則過度推論**

將 `grain.keys` 或欄位 role 當成超出契約所保證的業務事實。

**風險 C：忽略業務語意**

欄位可 SUM，不代表該 SUM 在特定時間、粒度與母體下有業務意義。

**風險 D：誤用 partial**

將部分映射拿去完成 unsupported 的完整 requirement。

**風險 E：測試 Oracle 成為唯一真相**

為通過固定 expected 而拒絕合法替代方案，或接受不安全的輸出。

**風險 F：過早重構**

在現有責任卡尚未完成自然對照時，直接重建整套 Semantic Layer。

### 11.2 本階段非目標

- 不實作 SQL Compiler。
- 不執行 SQL 或資料庫查詢。
- 不優化模型推論速度。
- 不評估雲端模型替代方案。
- 不進行跨 View partial 自動合成。
- 不一次導入完整 Semantic Graph。
- 不修改未正式核准的業務契約。
- 不以產品正式部署為本階段驗收目標。

---

## 12. 最終建議

本次評估的初步優先順序：

```text
先確認第23輪責任卡的自然效果
              |
              v
        A：最小修改
              |
      語意是否穩定？
         /        \
       是          否
       |            |
       v            v
  完整回歸      B：拆分語意判斷
                    |
                    v
            判定哪些責任可程式推導
                    |
                    v
              C：有限確定性推導
```

目前最值得驗證的研究假設：

> Coverage 不穩定，可能源自模型同時承擔能力識別、自身責任完整性判斷、依賴判斷與最終狀態分類，而現有輸出契約又要求模型額外處理可由程式約束的證據表示。

這個假設目前只有部分證據支持，尚不能視為完整確認的根因。

第 23 輪的結果尤其重要：

- 責任卡可能已改善原本的語意錯誤。
- 但又出現 contract_path 不合法的問題。
- 尚不足以證明應立即拆分更多 LLM 節點。

因此：

**先完成責任卡的固定自然驗證，再以 A/B/C 對照實驗選擇最小必要架構，是目前最有依據的研究順序。**

---

## 13. 本階段完成標準

本次架構研究完成時，應產出：

1. 現有架構與責任邊界的確認報告。
2. A/B/C 各方案最小可行修改範圍。
3. 目前錯誤類型與可確定性邊界。
4. 固定的對照測試設計。
5. 獨立核准的正反例與變形測試。
6. 每個方案的實際自然模型測試結果。
7. 對品質、穩定性、成本與風險的比較。
8. 最終建議採用的方案及其理由。
9. 未解決風險與後續驗證要求。

在完成對照實驗前，不以個人偏好或架構複雜度決定最終方案。

---

## 14. 審查依據

本文件根據以下既有工件：

- `task-decomposition-evidence-review.md`
- `evaluations/managed_three_stage_runner.py`
- `evaluations/diagnostics/managed_capability_projection.py`
- `evaluations/managed_node_diagnostics.py`
- `evaluations/kind_mapping_managed_contract.py`
- `evaluations/own_responsibility_managed_contract.py`
- `evaluations/evidence_bound_managed_contract.py`
- `evaluations/referenced_view_coverage.py`
- `evaluations/three_stage_view_selection.py`
- `projects/retail/contract_review.md`
- `projects/retail/manifest.yaml`
- 七份 `projects/retail/views/demo_retail/` YAML
- `10_latest_results.json`

狀態基準：

- 已確認第 21、22 輪離線完成。
- 第 23 輪為提供時的部分自然結果快照，非完整結案結果。
- 原歷史 Coverage FAIL 必須保留。
- 完整自然三階段 E2E 尚未完成驗收。
- 業務 View 契約仍為草稿。

本文件屬架構研究與設計評估，不代表已實作、已通過測試或已取得正式業務核准。
