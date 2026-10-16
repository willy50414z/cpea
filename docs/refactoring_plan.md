# 企業級應用架構重構計畫

對應 OpenSpec change：`enterprise-foundation-refactor`。本計畫提升獨立交付、設定、整合與品質驗證的結構，現有業務能力以單一 View MSSQL Text-to-SQL 為基準。

`docs/dev_plan.md` 保留為既有功能 PoC 計畫，複雜需求拆解、新 workflow、JOIN、ERP API、新資料庫與權限／稽核持久化皆另案實作。架構與企業級設計見 [architecture](architecture.md) 和 [enterprise_design](enterprise_design.md)。

## 分期與驗收

| 階段 | 交付 | 驗收 |
|---|---|---|
| 1. 基準 | 依賴／資產盤點、原始備份、離線行為案例 | 原程式 11 個案例可重現，原始檔 SHA-256 可核對 |
| 2. 獨立化 | src/cpea、pyproject、lock、模型與 workflow 歸屬 | 已安裝 wheel 可 import／啟動，既有成功與拒絕行為維持 |
| 3. 設定與契約 | 明確 env、部署 binding、profile、catalog port、索引 identity | 舊 `.env` 不被向上搜尋，兩份不同 schema 的合成契約可切換 |
| 4. 組裝與入口 | API／CLI／Graph bootstrap、顯式 executor | executor 缺失有 preflight，成功回應欄位與 execution trace 維持 |
| 5. 品質工具 | tests／evaluations／datasets／baselines／outputs 分開 | 離線回歸、評估 parser／metadata／output 行為通過 |
| 6. 企業級設計 | Context、授權、稽核、secret、限制、隔離、維運 | 責任、失敗路徑、後續 gate 清楚；不建立假成功 placeholder |
| 7. 交付 | 安裝、命令遷移、發行包與驗證報告 | Clean environment 和 checkout 外執行可用，發行包不含私有資產 |

以階段依賴與驗收排程，不將原一個月 PoC 時程當作正式商用承諾。細項進度由 OpenSpec tasks.md 管理。

## 支援環境與安裝

本次鎖定與驗證 Windows x64、Python 3.12。其他平台／Python 版本須另建立 lock 與驗證，不以 wheel 為 pure Python 就推定相容。Optional OpenAI-compatible provider 與 cross-encoder 依賴另列 `requirements/optional.txt`，核心 lock 沒有拉入大型模型 runtime。

```powershell
uv sync --locked --no-editable
Copy-Item .env.example .env
.\.venv\Scripts\Activate.ps1
cpea --help
cpea --env-file .env --request "請查詢 ZX100 目前各倉庫庫存數量"
```

需先提供可用 LLM；vector mode 還需要 embedding 模型。wheel 預設使用 `synthetic-demo`，其中 ZX100／倉庫皆為合成示例。使用客戶契約時設定 `CPEA_PROFILE_PATH` 或明確的 `CPEA_DEPLOYMENT_FILE`。機密只由部署端提供。

API 與 Graph：

```powershell
$env:CPEA_ENV_FILE='.env'
uvicorn cpea.interfaces.api.app:create_app --factory
# 如已安裝 LangGraph CLI，可用產品根目錄 langgraph.json 啟動。
```

LangGraph CLI 是外部開發工具，不是產品 runtime 必要依賴；`create_graph(runtime)` 可供 programmatic／離線驗證。`langgraph.json` 不含隱式上層 env 路徑，透過 `CPEA_ENV_FILE` 明確選取。

## 設定優先順序

Process environment 優先，其次為明確 `--env-file`／`CPEA_ENV_FILE` 指定的檔案，再套預設值。不自動搜尋 `.env`；env file 不寫入 process environment、不作 `${...}` interpolation。同一來源中 `ASSISTANT_*` 優先於既有 fallback alias；不同來源以 process 值優先，即使使用較舊 alias。

| 設定 | Alias／說明 |
|---|---|
| `ASSISTANT_LLM_PROVIDER/BASE_URL/MODEL/API_KEY/TEMPERATURE/SEED` | 對應 `LLM_PROVIDER/BASE_URL/MODEL/API_KEY/TEMPERATURE/SEED` |
| `ASSISTANT_LLM_NUM_CTX`／`ASSISTANT_LLM_NUM_PREDICT` | `LLM_CONTEXT_WINDOW`／`LLM_MAX_OUTPUT_TOKENS` |
| `ASSISTANT_EMBEDDING_PROVIDER/BASE_URL/MODEL/API_KEY` | 對應 `EMBEDDING_*` |
| `ASSISTANT_RETRIEVAL_MODE/K` | `RETRIEVAL_MODE/K` |
| `ASSISTANT_RERANKER_PROVIDER/MODEL`、`ASSISTANT_RERANK_TOP_K` | `RERANKER_PROVIDER/MODEL`、`RERANK_TOP_K` |
| `ASSISTANT_TOKEN_COUNT_ENDPOINT/ENCODING` | 對應 `TOKEN_COUNT_*` |
| `ASSISTANT_MAX_ROWS`、context safety／history／timeout | 以 `.env.example` 與 settings.py 定義為準 |
| `CPEA_PROFILE_PATH` | 外部 profile 根目錄，省略使用合成示例 |
| `CPEA_DEPLOYMENT_FILE` | 部署 YAML；內部 profile_path 相對於 YAML 檔案 |
| `CPEA_DATASOURCE_ID` | 显式綁定既有 executor 的來源 ID，無 JHD default |

Env file 內的相對設定路徑依該 env file 的位置解析；部署 YAML 內的路徑依 YAML 位置解析。無設定檔且明確給定相對路徑時，以啟動目錄為基準。Default 套件資源由 importlib.resources 取得，不需要 checkout。

## Executor 注入

本專案未提供真實 DB adapter。部署端供給既有 callable：

```python
from cpea.bootstrap import AssistantRuntime
from cpea.interfaces.api.app import create_app

# existing_executor 由部署方提供；接受 datasource, sql，回傳 columns, rows。
runtime = AssistantRuntime.from_env(
    '.env', executor=existing_executor, datasource_id='deployment-datasource'
)
app = create_app(runtime)
```

缺少 executor／datasource binding：HTTP query 回 503／`sql_executor_unavailable`，CLI `--execute` 非零退出，DB-dependent 評估 preflight 失敗。純 SQL generation 仍可用。Fake executor 限於 tests，不作 production fallback；不新增 DB driver、pool、交易或資料庫。

## 入口與路徑遷移

| 原位置／用法 | 新位置／用法 |
|---|---|
| `assistant.*` | `cpea.*` 責任模組；internal import breaking change |
| `assistant.main`／root main.py | `cpea` 或 `python -m cpea` |
| `assistant.api.router` | `cpea.interfaces.api.app.create_app(runtime)` |
| `graph/workflow.py` | `cpea.workflows.text_to_sql.sql_generation` |
| `settings.py`、`llm_config.py`、`context_budget.py` | `config/settings.py`、`infrastructure/llm/` |
| `ref/db_schema` | 現行私有工作目錄為 `projects/gms2`；原遷移位置 `integrations/private/gms2` 已封存於本機 `artifacts/project-migration/legacy-integrations/gms2`，profile 仍可外置 |
| `eval/` | 原始內容封存於 `artifacts/baseline/original-poc.zip`；現行專案題庫位於 `projects/gms2/evaluations/cases.jsonl`，舊合成題庫保留於 `examples/legacy-evaluation-cases` |
| `eval_main.py`、`query_reliability_eval.py` | `cpea-governance-eval`、`cpea-query-eval` |

HTTP 路徑與成功 payload 保留；不提供回頭引用原專案的 import shim。舊 `gen_sql(request)` 的程式呼叫移至 `AssistantRuntime.from_env().generate(request)`。

## 驗證、產物與回復

```powershell
uv run --locked --no-editable pytest -q
uv build
```

產品 metadata 在 `uv.lock` 鎖定具體版本。此次環境受限，lock graph 由已安裝 distribution metadata 離線解析後記錄標準 PyPI registry；未虛構 upstream wheel hash。驗證用的重包 wheelhouse 只放 `.cache/`，不發行。正式重新下載仍需可用 registry，發行方应在可連線環境補足 artifact integrity／跨平台驗證。

原始 source／資產備份、遷移前後測試報告與 clean-install 結果在 `artifacts/`，私有資料不進 Git 或 wheel。原客戶檔案分發權限待確認，須另行私有保存。沒有 Git repository 時，回復依靠 `original-poc.zip` 與其 SHA-256 manifest；新版本也以應用套件、設定與契約版本作為完整回復單位。

本次結果和剩餘限制記錄於 [驗證報告](refactoring_verification.md)。正式模型評估為 opt-in，沒有已明確配置的服務就記錄未執行，不能用 stub 成績宣稱真實正確率。權限／稽核只有設計，正式商用須完成 enterprise_design 的後續 gate。
