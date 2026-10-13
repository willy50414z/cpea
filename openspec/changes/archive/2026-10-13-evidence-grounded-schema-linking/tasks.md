## 1. 收斂範圍

- [x] 1.1 更新 proposal、design 與 specs，採用單次 mapping，撤銷完整 evidence 要求。
- [x] 1.2 只撤回本輪擴大實作與工具，保留使用者原有修改。

## 2. 精簡實作

- [x] 2.1 SchemaLinkDraft 同時包含 facts、links、View 層滿足說明及 unresolved，移除獨立 FactDraft 呼叫。
- [x] 2.2 用完整 request 與既有 policy／samples 建立單一 mapping prompt，移除 workflow 業務 hardcode 與強制 links。
- [x] 2.3 沿用原文 grounding、schema／policy／SQL 檢查、有限修正、fallback 與 trace。

## 3. 驗證與交付

- [x] 3.1 更新 fixtures 與針對性測試，驗證一次成功呼叫、目前無額外 filter、歷史拒絕、欄位改名、缺漏／額外條件與安全檢查。
- [x] 3.2 執行完整測試及 OpenSpec strict validation，更新必要架構文件並檢查最終 diff。（python -m pytest -q -o pythonpath=src：48 passed、1 skipped；OpenSpec strict valid。此為離線驗證，不宣稱真實模型準確率。）
