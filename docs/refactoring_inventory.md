# 重構前盤點

對應 change：`enterprise-foundation-refactor`。以下保留首次盤點的遷移前狀態；依賴取得後已完成離線回歸與結構遷移，續作結果見文件末尾及驗證報告。

## 環境與依賴

- 工作目錄：`E:/code/cpea`；首次盤點時沒有獨立 `pyproject.toml`、lockfile、tests 或 Git repository。
- 可用 Python：3.12.3、3.14；隔離環境 `.venv` 使用 3.12.3。這是待驗證的目標版本，尚未通過完整依賴安裝與功能測試。
- 可用 uv：0.12.10。
- 直接 import 的核心依賴：FastAPI、Pydantic、LangGraph、langchain-core、langchain-ollama、python-dotenv、PyYAML、requests、tiktoken。
- 選用依賴：langchain-openai（llama.cpp／OpenAI-compatible embeddings）、sentence-transformers（cross-encoder）。
- 驗證／打包依賴尚待選定並鎖定；一般產品不引入 DB driver、ORM 或 migration。
- PyPI 安裝失敗：環境代理指向無法連線的位置，未變更網路限制。已檢查本機 uv cache 與工作目錄下的既有環境；部分 LangGraph／Pydantic／langchain-ollama 可找到，必要的 tiktoken 找不到。尚未成功安裝套件，也尚未執行原功能。

## 已知入口與耦合

| 位置 | 現況 | 重構處理 |
|---|---|---|
| 所有 `assistant.*` import | 假設原專案 package layout | 遷移到已安裝的 `cpea` package |
| `api.py` | 只有 router | 後續建立獨立 app factory 與 bootstrap |
| `main.py` | 人工 smoke-test，CLI 使用原 namespace | 遷移到套件入口，保留既有模式 |
| `graph/langgraph.json` | 上層依賴及 `.env`，factory 尚未定義 | 修正產品入口與明確設定來源 |
| `application/sql_execution.py` | 原專案 executor fallback、固定 datasource | 顯式注入；不新增 DB adapter |
| `infrastructure/schema_catalog.py`、`retrieval.py` | 固定 `gms2`、舊資源路徑 | 設定化 profile／catalog，保持查詢語意 |
| `settings.py` | import 時載入 `.env` | 後續改為 startup 明確載入 |
| `evaluation.py` | 引用不存在的 `_parse_model` | 後續共用既有回答解析邏輯 |
| `domain/models.py` | 混合領域、API、LLM draft 與 trace | 按責任拆分並維持序列化欄位 |
| `eval/` | 題庫与歷史執行結果混放 | 後續分開 datasets、baselines、outputs |

## 資產保存與分發

原始 `.py`、application/domain/graph/infrastructure/llm_tools、`ref/`、`eval/` 和 `docs/dev_plan.md` 已逐檔保存於 `artifacts/baseline/original-poc.zip`。`original-inventory.json` 保存各檔的相對路徑、大小、SHA-256 與分類；備份內檔案已與 manifest 核對。兩者屬本機私有交付資產，由 `.gitignore` 排除；需由維運另行保存，不能依靠 Git 恢復。

| 資產 | 分類 | 本次保存 | 後續目的地／分發規則 |
|---|---|---|---|
| 原始程式與文件 | 遷移來源 | 原位置及私有完整備份 | 經重構後的 package／docs；備份不進 wheel |
| `ref/db_schema/catalog.yaml`、View YAML | 客戶 integration 契約，分發權限待確認 | 原位置及私有備份 | `integrations/private/<profile>` 或部署外部資源；不內嵌通用 wheel |
| `ref/db_schema/samples/*.jsonl` | 客戶樣本，分發權限待確認 | 原位置及私有備份 | 私有 authoring evidence；不作公開 fixture、不進 wheel |
| `eval/dataset.jsonl`、`eval/query_reliability.jsonl` | 客戶題庫，分發權限待確認 | 原位置及私有備份 | 私有 datasets；另建立可分發的合成題庫 |
| 其他 `eval/*.jsonl` | 歷史結果／baseline，可能含 prompt、rows 與 trace | 原位置及私有備份 | `evaluations/private/baselines`；保留來源與設定可比性說明 |
| 後續合成 profile／fixture | 待建立，無客戶資料 | 尚未產生 | 可分發測試資產，明確區別於真實業務基準 |

初次盤點未刪除或搬移原始客戶資產，未推定已有對外分發授權。

## 依賴取得後的續作

- 使用者安裝必要依賴後，Python 3.12.3 執行原程式 11 個離線案例全部通過，報告位於 `artifacts/baseline/legacy-tests.xml`。原 test harness 另存於 `legacy-test-harness.zip`。
- 已建立 `pyproject.toml`、`uv.lock`、`src/cpea`、測試與評估工具；向量檢索另確認需要 NumPy，已明列為核心依賴。
- 原 `ref/db_schema` 已移至 `integrations/private/gms2`，原 `eval` 移至 `evaluations/private/legacy`；原始內容仍有完整備份。新 `manifest.yaml` 只增添 profile identity，不改寫客戶 View 政策。
- 已遷移 Windows x64／Python 3.12 的獨立 wheel，其他平台未驗證。Optional providers 不屬核心驗證 lock。
- 原 source／入口的退休副本位於 `artifacts/baseline/retired`；不會被產品 import 或發行。
- 詳細驗證及未實作能力見 [refactoring_verification.md](refactoring_verification.md)。
