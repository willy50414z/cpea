# 重構驗證報告

Change：`enterprise-foundation-refactor`。產品版本：0.1.0。驗證平台：Windows x64／CPython 3.12.3。

## 驗證結果

| 項目 | 結果 | 證據 |
|---|---|---|
| 原程式離線基準 | 11 passed | `artifacts/baseline/legacy-tests.xml`、`legacy-test-harness.zip` |
| 新套件離線回歸與契約／入口／評估測試 | 34 passed、1 skipped | `artifacts/verification/tests.xml` |
| Dependency lock 一致性 | `uv lock --check --offline` 通過，60 packages（含 product／dev） | `uv.lock` |
| Wheel／sdist 建置 | 通過 | `dist/cpea-0.1.0-py3-none-any.whl`、`dist/cpea-0.1.0.tar.gz` |
| Clean install | 全新隔離環境解析／安裝核心依賴，checkout 外執行通過 | `artifacts/verification/clean-install.json` |
| Import／API factory／Graph factory | 不需要原專案，建立 factory 不發送網路請求 | offline socket guard；clean-install JSON |
| CLI help／缺少 executor | Help 可用；execution exit 3／穩定 unavailable code | clean-install JSON |
| 私有資產與發行包 | 原契約／樣本／結果原 bytes 保留；wheel／sdist 排除私有資產 | `asset-preservation.json`、clean-install JSON |
| 原功能計畫 | `docs/dev_plan.md` SHA-256 與原始備份相同 | asset-preservation JSON |
| OpenSpec 格式／規格 | 嚴格驗證通過 | `openspec validate enterprise-foundation-refactor --strict --no-interactive` |

離線行為包含支持／拒絕需求、確定性 SQL、scope／時間／欄位規則、filter grounding、trace、執行一次、截斷、executor failure、答案引用、alternate schema 的 lexical／vector retrieval、profile／內容 cache 切換、env 優先順序、設定錯誤診斷、path escape、API payload、CLI／Graph、模型比較 prompt replay、shared JSON parsing、metadata 脫敏与產物不覆寫。

Symlink escape 的實際檔案案例因本機 Windows 不允許建立 symlink 而跳過。Loader 使用 resolve 後的 root boundary；一般相對／絕對 path escape 已驗證。具備 symlink 建立權限的 CI 還需執行該案例，沒有把 skip 視為實際 symlink 驗證通過。

## 安裝與 lock 的證據範圍

使用者已提供必要套件，另從本機 cache 取得 NumPy，因為既有 InMemoryVectorStore 的 cosine similarity 實際需要它。環境的 PyPI 下載限制仍存在，因此用已安裝／cache 的 distribution metadata 和本機 verification wheelhouse 離線解析依賴，驗證產品 wheel 可於乾淨環境正常安裝。驗證 wheelhouse 在 `.cache/`，不發行、不冒充 upstream 原始 wheel。

`uv.lock` 記錄標準 PyPI registry 與確定版本的 dependency graph，沒有杜撰 upstream wheel hashes；`uv lock --check --offline` 驗證它與 project metadata 一致。正式 registry 重新下載、artifact hash 補足、Linux 與其他 Python 版本沒有在此環境驗證。核心 lock 明確限定 Windows／Python 3.12。

## 實際服務評估

本次 process environment 沒有明確的 LLM model／base URL／env file 設定，也沒有專案 `.env`；因此沒有執行 opt-in 真實模型 no-DB 評估。預設 localhost 不是服務已配置或可用的證據。測試中 StubLLM 與 fake executor 的成績只證明重構行為，標示為 offline-synthetic，不能宣稱模型準確率。

沒有新增／連接真實資料庫，沒有執行客戶 ERP API；真實 adapter、資料庫權限、負載、資料語意與端到端正確率留待對應後續 change。

## 已知限制

- 預設只有 SQL generation；真實 query 需要部署方注入 executor 與 datasource binding，否則明確 unavailable。
- Trusted RequestContext、PolicyEnforcer、AuditEvent／Sink 與維運隔離只完成設計；沒有登入、RBAC／ABAC、稽核儲存或共享租戶 enforcement。
- 已保留原 compiler-only、單一 View 與現有業務欄位 heuristic。接新 ERP 契約仍需逐項確認 aliases、欄位能力、資料粒度、單位與時間語意，不推定可理解所有 ERP。
- 原客戶資料沒有通用分發授權；保存在被忽略的私有目錄與 artifacts，需部署方另做私有備份。
- 原 executor error 的截短不保證敏感內容脫敏；正式 adapter 接入前需完成 enterprise_design 定義的錯誤邊界。
- 產品化結構完成不代表正式商用的安全／可靠性 gate 已通過。

## 回復

遷移前 56 個原始檔案在 `artifacts/baseline/original-poc.zip`，manifest 帶各檔 SHA-256 與 archive SHA-256。新交付以 package、非機密設定、匹配契約版本／fingerprint 同步回復。本次沒有資料庫 schema migration。
