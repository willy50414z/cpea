請重構 
src/cpea/workflows/text_to_sql/sql_generation.py 
中的 
SQLGenerationWorkflow._match_candidates 
以及相關的 
_mandatory_links、_temporal_mismatch、_link_errors 
邏輯。 

目前程式中有許多針對特定業務與中文字詞的 hardcode，例如： 

- 品號、料號等固定欄位名稱 
- 倉庫、仓库等固定關鍵字 
- 英數識別碼的固定 regex 
- 季度、年份與目前快照的固定判斷 
- 產品代碼、倉庫條件與欄位之間的固定 mapping 

這些規則過度依賴目前的資料與語言，容易造成過擬合。請改成由 LLM 根據以下資訊推導需求與 schema 的對應： 

1. 使用者原始 request 
2. View 的完整 schema contract 
3. View 的欄位說明、aliases、capabilities、semantic metadata 
4. View 的 sample data 
5. catalog 中已定義的 policy 與 term mappings 

LLM 應負責：
 從 request 抽取 entity、metric、dimension、time、constraint 
- 根據 schema 與 sample data 判斷每個需求片段對應的欄位 
- 判斷某個值是產品代碼、名稱、倉庫、日期、數值或其他條件 
- 推導正確的 SQL role：filter、metric 或 dimension 
- 推導 filter operator 與 value 
- 判斷「各倉庫」這類語意應該是 dimension，而不是單一倉庫 filter 
- 判斷 identifier 應該使用精確比對，不能只依賴固定 regex 
- 回報無法對應、資料不足、時間範圍不支援或 sample data 無法證明的部分 

請移除或降低對以下固定字串與 regex 的依賴： 

- 品號、料號及其變體 
- 倉庫、仓库及其變體 
- 固定英數識別碼 regex 
- 固定季度與年份 regex 
- 固定欄位名稱集合 
- 固定的產品或倉庫 mapping 

請將這些判斷改為： 

- 由 LLM 根據 schema、sample data 與 request 推理 
- 由 catalog metadata 宣告欄位語意與能力 
- 由通用 validator 驗證 LLM 結果是否合法 

請保留 deterministic validation，不要讓 LLM 直接繞過安全檢查。程式仍必須驗證： 

- link 引用的 fact 必須出現在 request
- required fact 不得遺漏 
- 欄位必須存在於指定 View 
- role、operator、aggregation 必須符合欄位 contract 
- filter value 必須來自 request、sample data 可證明的對應，或明確 catalog mapping 
- 不得自行新增 request 沒有提出的條件 
- 不得產生互相衝突的 filter 
- 產生的 QueryPlan 與 SQL 必須通過既有 policy validation 
- 不支援的跨 View JOIN 仍應被拒絕 

請重新設計 LLM prompt，使它明確要求模型： 

1. 先閱讀 sample data，理解欄位實際代表的業務語意 
2. 不要因為欄位名稱相似就直接 mapping 
3. 不要猜測 sample data 中不存在、request 中也沒有的代碼或條件 
4. 對每個 mapping 提供 evidence，指出來自 request、schema、sample data 或 catalog policy 
5. 無法確定時放入 unresolved_facts 或 limitations，不要自行補值 
6. 回傳穩定、可驗證的 structured JSON 

請同步更新相關 Pydantic model、prompt、validator、測試與文件，並新增測試確認： 

- 不同欄位名稱但語意相同時，仍能正確 mapping 
- 欄位名稱不包含「倉庫」或「品號」時，仍能依 sample data 找出正確欄位 
- sample data 不足以證明 mapping 時，系統會拒絕猜測 
- request 中沒有的 filter 不會被 LLM 或程式加入 
- identifier、名稱、日期與數值欄位可以依 schema/sample data 正確區分 
- 現有安全驗證與 SQL policy 行為不被破壞 
完成後請執行完整測試，並說明哪些 hardcode 被移除、哪些 deterministic guardrails 被保留，以及新的判斷責任如何在 LLM、catalog 與 validator 之間分配。