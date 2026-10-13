# Text-to-SQL Evidence 背景與實作利弊

本文件整理 CPEA 目前的查詢流程、曾討論的 evidence 設計，以及導入的正反意見。完整 evidence 架構已撤回，目前只保留模型的文字理由與既有安全驗證。以下導入方案是評估方向，不代表已決定實作。

## 1. 背景與目前決策

原本流程先呼叫 LLM 產生 FactDraft，再呼叫 LLM 做 schema mapping。Python 還會依固定中文詞、欄位名稱與識別碼／季度 regex 補 facts、強制產生 links，或排除「目前」等詞，容易過度依賴特定資料與語言。

使用者希望移除這些業務 hardcode，由 LLM 直接閱讀完整需求與 schema，決定如何查詢。最初曾把重構擴大成完整 evidence framework，包含來源引用、型別契約、sample IDs 等；之後確認這超出本次需要，因此撤回，採用較小的修改範圍。

目前流程：

```text
完整 request ＋ 單一候選 View schema ＋ samples ＋ policies
                              ↓
                             LLM
                              ↓
                       SchemaLinkDraft
          facts / links / view_satisfied / unresolved_facts
                              ↓
                  既有 validator → QueryPlan → SQL
```

- 不再獨立呼叫 FactDraft；facts 與 mapping 在同一份模型回覆中產生。
- 第一個候選直接成功時，mapping 只呼叫模型一次；格式修正、語意修正或換候選仍可能增加呼叫。
- 模型判斷哪些需求需要 SQL、哪些由 View 本身滿足、哪些無法滿足。
- 維持單一 View 限制。複雜 JOIN 與計算可依實際需求事先封裝成核准 View，避免模型任意組合。
- 保留原文引用、已回傳 facts 的承接、欄位能力、operator／aggregation、scope、filter grounding、QueryPlan 與 SQL policy 檢查。
- 目前 samples 用於理解語意；filter 值仍須來自對應 request fact 或明確 catalog term mapping，不能僅因 sample 中出現就新增條件。

## 2. State、Reason 與 Evidence 的差別

State／trace 是紀錄的載體，本來就能保存 facts、links、候選失敗原因、QueryPlan 與 SQL。Evidence 若導入，也可以放在相同 state／trace 裡，不需要另一套 log 系統。

| 項目 | 用途 | 能否由程式核對 |
|---|---|---|
| State／trace | 保存執行過程及結果 | 取決於保存的內容，不會因為有紀錄就自動完成驗證 |
| reason／explanation | 記錄模型為何做出判斷 | 可檢查非空，但不能直接證明文字理由正確 |
| 結構化 evidence | 指出具體原文、schema 欄位、sample 或 policy 依據 | 可核對引用是否存在、值是否相符，以及是否符合宣告規則 |

完整 evidence 增加的是「可驗證的來源契約」，不是單純增加 log。它也不是 LLM 能做 schema mapping 的必要前提。

## 3. 用「目前」比較兩種做法

使用者問：「目前各倉庫庫存」。View 已定義：

```yaml
view: demo.v_inventory
temporal_scope: current_snapshot
```

### 目前採用的輕量說明

```json
{
  "fact_text": "目前",
  "reason": "這個 View 提供目前快照，不需要額外時間條件。"
}
```

「目前」仍保留在 facts，並記錄為 view_satisfied，不產生 SQL filter。程式檢查它引用的 fact 存在、分類為 time、理由非空、View 有 temporal_scope，且沒有同時為該 fact 產生 link。

這些檢查不會核對理由的語意真假，也不能單憑 temporal_scope 存在就證明需求與 View 的時間語意相容。

### 曾討論的完整 evidence 範例

以下是已撤回設計的示意，不是目前回覆格式：

```json
{
  "fact_id": "f_current",
  "intent": "current_snapshot",
  "column": null,
  "evidence": {
    "source": "schema",
    "view": "demo.v_inventory",
    "fingerprint": "catalog-content-hash",
    "path": ["temporal_scope"]
  }
}
```

Validator 可核對 View 身分與契約內容摘要，讀取真正的 temporal_scope，確認它確實為 current_snapshot，而不是只相信模型寫的理由。

但「目前」應被理解為 current_snapshot，仍然由模型判斷。若模型把「去年」誤分類成 current_snapshot，即使引用的 schema 是真的，仍可能得到錯誤結果。Evidence 可驗證資料依據，不能完全證明自然語言理解。

## 4. 支持導入的理由

| 好處 | 實際作用 | 成立條件 |
|---|---|---|
| 攔截無來源的 filter 值 | 發現模型猜代碼、引用不存在的值或未觸發的 mapping | Validator 實際核對來源與觸發条件，而非只要求模型寫理由 |
| 核對 View 層承接 | 確認模型引用的時間能力或資料範圍確實存在 | Catalog 已明確定義相關能力 |
| 更容易查錯 | 分辨原文抽取錯、欄位選錯、mapping 錯或資料定義不足 | Trace 保留可重現的引用與驗證結果 |
| 評估模型與 prompt 變更 | 比較判斷依據與失敗類型，而不只看 SQL 字串 | 有固定案例與可核對的預期結果 |
| 支持更複雜的值轉換 | 在明確授權下，把名稱轉成正式代碼 | 有可信字典或正式映射規則；單筆 sample 不足以保證 |

部分好處目前已由既有 validator 提供，例如欄位存在、operator 合法及簡單原文 grounding。Evidence 的價值應評估為在這些檢查之上的增量，而不是把既有保護算成新功能。

## 5. 反對或暫緩導入的理由

### 實作與維護成本

完整方案需要證據格式、來源引用、版本一致性、驗證規則、錯誤修正與測試。若引入新的 sample IDs、mapping IDs、semantic metadata，還要處理 catalog 維護與相容性，範圍會明顯超過修改 prompt。

### 模型負擔與誤拒風險

較大的 structured JSON 增加輸出 token、格式錯誤及漏填欄位的機會。過度嚴格的規則可能把原本可回答的需求拒絕，尤其是模型能力或 context／output budget 有限時。更長的 evidence 不等於更好的答案。

### 無法保證需求完整或語意正確

模型可能同時漏掉 fact 與 link；也可能引用正確的 schema，卻套用到錯誤的需求。引用核對通過，只代表特定來源與結構成立，不代表整體答案正確。

### Sample 的證明力有限

Sample 中沒有某個代碼，不代表資料庫中沒有，不能因此拒絕使用者明確指定的值。反過來，一筆 sample 同時出現某名稱與代碼，也不代表全域唯一對應。若要授權轉換，必須確認對應的唯一性、範圍與資料有效性。

### 目前受限場景的增益可能不大

若大多數問題都是核准單一 View、條件值直接來自 request，既有 compiler 與 validator 已限制不少錯誤。此時完整 evidence 的成本可能大於增益。對名稱轉代碼、跨來源對應及需要詳查錯誤依據的場景，其價值才更明顯。

## 6. YAML 是否必須增加大量案例

不必。需要補的是缺少的資料定義，並非為每種問法寫一個答案。

| 目的 | 合理的 YAML 資訊 | 不應依賴的做法 |
|---|---|---|
| 判斷目前快照 | temporal_scope: current_snapshot | 列出「目前、現在、此刻」逐一對應的問答規則 |
| 判斷欄位可否篩選／加總 | capabilities、operators、aggregations | 依特定題目寫死欄位選擇 |
| 區分識別碼與名稱 | 明確欄位描述或必要的語意定義 | 看到某種英數外觀就認定是產品代碼 |
| 名稱轉代碼 | 可信字典、主檔或明確 term mapping | 看到單一 sample 共現就假定唯一映射 |

既有定義足夠時，輕量 schema evidence 可直接引用它，不需要改版整份 catalog。穩定 ID 與 fingerprint 主要解決引用及版本追蹤問題，不是所有 evidence 用途都必須一開始具備。

## 7. 過擬合與新 hardcode 的風險

增加 YAML 不會直接造成模型訓練層面的過擬合，但可能造成系統層面的過度特化：已見題目能通過，新問法、不同欄位名稱或新資料就失效。

容易過度特化的方向是「遇到各倉庫就選某固定欄位」「遇到 ZX100 就篩某固定欄位」。把這些規則從 Python 搬到 YAML，並不自動消除 hardcode。

較可泛化的方向是描述資料本身：View 的時間範圍、欄位代表的對象、允許的操作，以及正式业务字典。明確業務 mapping 可以保留，但應來源可靠且有適用範圍，不能為了讓單一測試通過就逐題補規則。

可用以下方式檢查是否正在走向過度特化：

- 同一需求換句話說，是否不改 YAML 也能運作。
- 欄位改名但語意不變，是否只需更新 schema，而不需修改核心邏輯。
- Request 明確提供 sample 外的識別碼，是否仍可查詢。
- 移除非必要 sample 後，是否仍遵循正式 contract，而不依賴某一筆樣本。
- 用未參與 prompt／規則調整的案例評估，並分開記錄錯誤接受與錯誤拒絕。

原則是：新問法應沿用相同資料定義；資料能力或業務規則改變時，才需要更新 catalog。

## 8. 可採取的漸進方案

以下是建議順序，尚未授權實作：

1. **Filter 值來源**：先針對最容易改變查詢結果的條件，清楚區分原文 literal 與 catalog mapping，核對對應來源。
2. **View 層滿足依據**：讓模型引用既有 policy 欄位，例如 temporal_scope；可保留 reason 供人閱讀，不必同時加入完整 evidence framework。
3. **Sample 映射證據**：等確實需要由 sample 推導名稱／代碼時，再處理唯一性、完整性、有效範圍及引用格式。

Evidence 可以由目前的一次 mapping 呼叫一起回傳，不需要重新引入獨立 FactDraft 階段。是否值得導入，應比較同模型、同題庫下的錯誤接受、錯誤拒絕、延遲、token 成本與人工查錯時間，再決定是否擴大。

## 9. 驗證紀錄與解讀界線

- 精簡版目前的離線回歸結果為 48 passed、1 skipped；略過項目與 Windows symlink 權限有關。這不是模型理解準確率。
- 已撤回的完整 evidence 版本曾做 10 題合成真實模型評估，通過 5 題：5 題預期拒絕案例都拒絕，5 題預期可回答案例全被拒絕。
- 該次評估尚未完成根因分析，也沒有同題的精簡版對照；不能據此推論 evidence 必然有害或能提升準確率。
- Evidence 不取代執行端的資料庫權限、資料隔離、查詢逾時或資源限制。單一 View 與 TOP 筆數限制也不保證低查詢成本。

## 10. 相關實作與文件

- [目前架構](architecture.md)
- [原始 hardcode 問題描述](hardcode.md)：其中部分要求已由後續討論收斂，不應視為完整 evidence 已獲准實作。
- [目前 SchemaLinkDraft 與 ViewSatisfiedFact](../src/cpea/workflows/text_to_sql/schemas.py)
- [目前 mapping prompt 與 validator](../src/cpea/workflows/text_to_sql/sql_generation.py)
- [收斂後的 OpenSpec 設計](../openspec/changes/archive/2026-10-13-evidence-grounded-schema-linking/design.md)
