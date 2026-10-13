## Why

目前需求抽取與 schema linking 分成兩次模型呼叫，Python 又依固定字詞／regex 補 facts、強制 mapping 或排除「目前」。改由 LLM 同時讀取完整 request 與 View contract，直接決定需要的 SQL links、由 View 滿足的需求與無法满足的需求。

## What Changes

- 每個候選 View 正常情況只呼叫 LLM 一次，直接回傳 SchemaLinkDraft；移除獨立 FactDraft 呼叫。
- 在同一回覆保留原文 facts、links、簡單的 view_satisfied 說明與 unresolved_facts，沿用 state／trace。
- 提供既有完整 View policy（含欄位、aliases、samples、term mappings），不新增 catalog 格式或 evidence ID。
- 移除 workflow 的業務字詞／識別碼／季度 regex、強制 links 及特殊繁簡轉換；保留通用原文 grounding、schema／scope／plan／SQL 安全檢查。
- 保留有限次修正及候選 fallback；一次呼叫指正常成功路徑，不是禁止安全修正。

## Capabilities

### New Capabilities

- `evidence-grounded-schema-linking`: 單次完整需求 mapping、View 層滿足結果與安全檢查。

### Modified Capabilities

無；沿用現有 catalog 契約與 workflow 邊界。

## Impact

主要變更限於 SQL generation workflow、workflow schemas、測試 fixtures 與必要文件。撤回本輪新增的完整 evidence、catalog metadata 遷移及獨立評估工具；不修改 SQL compiler、catalog port／loader／profile 格式或公開 API。較早的 docs/hardcode.md 以本次使用者確認的精簡範圍為準。
