## Context

使用者確認採用 request＋schema＋samples＋policies → LLM → SchemaLinkDraft。FactDraft 不是必要前置步驟。「目前」應由 LLM 判斷是否已由 View 的快照語意承接，而不是由 Python 依字詞移除。

## Goals / Non-Goals

Goals：一次正常模型呼叫完成單一候選 mapping、移除 workflow 業務 hardcode、保留安全檢查與既有 trace。
Non-goals：完整 evidence framework、sample row IDs、mapping IDs、fingerprints、新 catalog 格式、profile migration、獨立評估平台或跨 View JOIN。

## Decisions

1. SchemaLinkDraft 增加 facts（沿用 QueryFact）、view_satisfied（fact_text 與 reason）、ambiguity、requires_join。事實抽取與 mapping 同時完成，不另外呼叫 FactDraft。每項明示 fact 必須由 link 或 view_satisfied 承接；unresolved 必須拒絕。
2. Prompt 直接收到完整原始 request 與現有 ViewDefinition.policy 的序列化內容，因此既有 samples、描述、aliases、capabilities、semantic metadata、term mappings 都可見，不新增 catalog API。超出預算則拒絕候選，不切掉安全規則。
3. LLM 決定 SQL role、欄位、值與時間語意。view_satisfied 僅用來記錄 View 本身已滿足的時間需求；validator 檢查原文及 fact kind、非空理由與 View 有時間契約，語意是否相符由 LLM 判斷。不能藉此跳過 entity、metric 或 dimension。
4. 保留原文 facts／links 檢查、required coverage、欄位與 role／operator／aggregation contract、scope policy、catalog mappings、filter grounding、衝突拒絕、QueryPlan 與 SQL policy。移除按特定業務欄位或值外觀推論的檢查。不再強制補 links。
5. filter value 允許原文或明確 catalog mapping。samples 用來理解語意，不因 sample 單筆共現自行新增代碼轉換授權。移除特殊繁簡轉換；需要代碼／名稱轉換時由既有 term_mappings 宣告。這是精簡範圍下保留 deterministic grounding 的取捨。
6. 沿用既有有限 semantic／JSON 修正及候選 fallback。保留 request_facts 與 candidate_attempts，View 層說明保存在 trace.links，不另建 log 系統。

## Risks / Trade-offs

- 同次呼叫可能同時漏掉 fact 與 link，validator 無法形式化證明自然語言完整性；用针对性測試且不宣稱可完全避免。
- 不新增完整 evidence，因此無法機械證明任意 View-level 語意說明正確；prompt 負責時間判斷，既有 SQL 安全邊界仍獨立保留。
- 不擴建通用 filter constraint solver；保留既有保守衝突檢查，複雜區間支援另案處理。
- 不保證不同候選提出相同 fact 切分；每個候選都收到完整 request。
