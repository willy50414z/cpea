# CPEA

可獨立安裝的 ERP 助手，提供受治理的單一 View SQL 產生、選配 SQL Server／PostgreSQL 執行與 Gradio 問答首頁。使用 Python 3.12。

首頁的使用方式類似 ChatGPT：輸入問題後，詞彙只有一個合法業務含義時直接採用；仍有歧義才顯示未預選的 radio，每項最多三個相關業務含義，加上「都不符合，重新描述」。聊天中完整顯示自動採用、人工確認或沿用的詞彙摘要，另顯示 SQL 與結果表格；選項與摘要不含資料庫來源或欄位識別碼。「都不符合」會還原原題供修改，不保存部分選擇、不執行查詢。只有人工確認的來源詞彙保存在獨立 JSON，供後續相同完整詞彙沿用；自動採用只用於本題，不覆蓋不同的既有人工選擇。每次問題獨立，只顯示最新一題；重新整理會清空。此流程不額外呼叫 LLM 整理答案、不保存問答，也不自動重試。

對話框以一般文字即時顯示「正在尋找相關資料」「正在比對問題與資料內容」「有詞彙需要你確認」等進度，確認後接續同題紀錄。選項、進度、錯誤與結果標題不直接顯示資料庫結構或完整契約。SQL 使用獨立程式碼區塊顯示；技術追蹤留在伺服器流程及開發者 JSON／SSE API，不傳送模型私有推理或原始 prompt。

每題會顯示目前選取的資料集：`gms2` 為「GMS2 業務資料」，`retail` 為「零售示範資料」。找不到能承接問題的資料時，畫面指出目前資料集並還原原題，讓使用者確認 Project 後重送；系統不會自行切換專案或查詢另一份資料。

## 安裝與啟動

Linux／macOS（Bash）：

```bash
uv sync --locked --extra sqlserver --extra postgres --extra azure
cp -n .env.example .env
export CPEA_PROJECTS_ROOT="$PWD/projects"
export CPEA_ENV_FILE="$PWD/.env"
uv run --locked --extra sqlserver --extra postgres --extra azure uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Windows（PowerShell）：

```powershell
uv sync --locked --extra sqlserver --extra postgres --extra azure
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$env:CPEA_PROJECTS_ROOT = (Resolve-Path projects).Path
$env:CPEA_ENV_FILE = (Resolve-Path .env).Path
uv run --locked --extra sqlserver --extra postgres --extra azure uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

開啟 `http://127.0.0.1:8000/`。Gradio 與 FastAPI 由同一服務提供，不需前端建置。問題輸入框下方提供 `gms2`／`retail` 下拉選單，預設為 `gms2`；首次使用 project 時載入該目錄的 `.env` 與 View 契約，後續使用快取 runtime。修改已載入的 `.env` 後需重啟服務。執行或等待欄位確認時鎖住選單；按「新問題」取消等待後即可切換。每個 project 的 runtime、checkpoint 與預設詞彙檔各自獨立，不保存選擇或歷史對話。

啟動前須備妥 `projects/gms2/` 與 `projects/retail/` 的 `.env`、`manifest.yaml`、`catalog.yaml` 與 View 契約；這些私有專案不包含在 wheel／sdist。若在其他位置，將 `CPEA_PROJECTS_ROOT` 指向實際的 projects 目錄，也可寫在明確指定的根目錄 `.env` 中。首頁不再使用 demo profile，啟動時的 `CPEA_PROFILE_PATH` 不會覆蓋下拉選單選定的 project。JSON／SSE API 使用預設 `gms2` runtime；CLI 仍可明確指定 profile。

SQL 生成需要可用的 LLM／embedding 服務。首頁依所選 project 的 executor 與 datasource 決定本題執行方式：已配置時生成 SQL 後查詢；未配置時仍可生成 SQL、完成 HILP 與保存詞彙，並明確標示「未執行查詢」，不顯示假的資料列或「查無資料」。這項方式在送題時固定，確認不會自動升級為資料庫執行。執行型 JSON／SSE API 仍要求 executor；純 SQL API 與 CLI 生成不需要資料庫。請在各 project 的 `.env` 完成下方資料庫設定以啟用查詢；安裝 extra 本身不會建立連線設定。

若 project 使用 Azure 模型或 OpenAI 相容 embedding，`sync` 與每次 `run` 都要加上 `--extra azure`，避免 `uv run` 依未選取 extra 的環境移除選配套件：

```bash
uv sync --locked --extra sqlserver --extra postgres --extra azure
uv run --locked --extra sqlserver --extra postgres --extra azure uvicorn cpea.interfaces.api.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
```

網頁失敗時，server log 會記錄 project、細分 phase、錯誤碼、完整呼叫位置與例外原因鏈；缺少模型套件會顯示 `llm_dependency_missing` 與套件名稱。為避免記錄密碼或查詢內容，堆疊不含原始例外訊息、程式碼行與區域變數；網頁仍顯示固定錯誤訊息。`queue/join` 的 HTTP 200 只代表請求進入佇列，不代表 SQL 已生成或查詢成功。

資料庫連線格式錯誤會額外記錄允許清單中的固定診斷，不含完整 URL 或帳密。`database_driver_unsupported` 表示 URL driver 不受支援；`database_dialect_mismatch` 表示指定方言與 URL 不符。SQL Server 仍使用 `sqlserver_invalid_url`、`sqlserver_host_or_database_missing`、`sqlserver_query_options_unsupported` 等固定診斷。這些情況在載入 project 時就會停止，網頁提示檢查連線設定，不呼叫模型或連接資料庫。

`--env-file`／`CPEA_ENV_FILE` 應指向目前作業系統上的實際檔案；Linux 不使用 Windows 路徑。程式不自動搜尋 `.env`，設定依 process environment、明確 env file、預設值的順序讀取。Profile／deployment 相對路徑以選定 env file 所在目錄解析。

## 自動選擇資料庫

在各 project 的 `.env` 設定一個 `CPEA_DATABASE_URL`，程式依 URL 選擇 adapter，無須再填 DB 類型。資料庫名稱由 URL 的最後一段決定；project name 僅用於來源綁定與詞彙隔離。

| URL 前綴 | Adapter | SQL 方言 | 安裝選項 |
|---|---|---|---|
| `postgresql://`、`postgresql+psycopg://` | psycopg 3 | 雙引號識別字、`LIMIT`、原生布林值 | `--extra postgres` |
| `mssql+pymssql://` | SQLAlchemy／pymssql | 方括號識別字、`TOP`、Unicode 字串 | `--extra sqlserver` |

SQL 生成、執行前重編譯驗證與專案評估共用相同方言。不同 project 可在同一服務使用不同 adapter。若兩種資料庫都會使用，`uv sync` 與每次 `uv run` 都需包含 `--extra sqlserver --extra postgres`；有 Azure 模型時再加 `--extra azure`。

```dotenv
CPEA_DATABASE_URL='postgresql://YOUR_USER:YOUR_PASSWORD@server.example:5432/YOUR_DATABASE'
CPEA_DATABASE_CONNECT_TIMEOUT_SECONDS=5
CPEA_DATABASE_QUERY_TIMEOUT_SECONDS=30
```

SQL Server 與 PostgreSQL 統一使用 `CPEA_DATABASE_URL`。設定依 process environment、選定 `.env` 的順序讀取；明確空白 URL 會停用執行。

未提供 URL 時預設產生 SQL Server SQL。若只需要 PostgreSQL SQL，設定 `CPEA_DATABASE_URL=` 與 `CPEA_DATABASE_DIALECT=postgresql`，不需安裝 DB driver。提供 URL 時 `CPEA_DATABASE_DIALECT` 預設為 `auto`；明確指定且與 URL 不符會被拒絕。

## 連接 PostgreSQL

```bash
uv sync --locked --extra postgres
# 同時提供 GMS2 與 Retail：
uv run --locked --extra sqlserver --extra postgres --extra azure uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

PostgreSQL 使用 psycopg 3，每次查詢建立獨立唯讀 transaction，設定連線逾時與 `statement_timeout`，只執行一次已核准 SQL，最多讀取上限加一列，並在成功或失敗時關閉 cursor／connection。初始化 runtime 不連接資料庫。連線 URL 可加入 `sslmode`、`sslrootcert`、`sslcert`、`sslkey`；其他 query options 會被拒絕，避免覆寫唯讀與逾時設定。部署帳號應只有核准 View 的 SELECT 權限。[psycopg 連線參數](https://www.psycopg.org/psycopg3/docs/api/connections.html)、[PostgreSQL 連線選項](https://www.postgresql.org/docs/current/libpq-connect.html)。

## 連接 SQL Server

內建 adapter 使用 SQLAlchemy 的 `mssql+pymssql`，支援平台的 pymssql wheel 已包含 FreeTDS，不需要安裝 unixODBC 或 Microsoft ODBC Driver，也不需要執行先前的 ODBC sudo 腳本。Linux／Windows 都先安裝 Python 選配依賴；若平台沒有相容 wheel 而需從原始碼建置，才需要編譯工具與 FreeTDS 開發檔案。[pymssql 安裝說明](https://pymssql.readthedocs.io/en/stable/intro.html)

```bash
uv sync --locked --extra sqlserver
# 在 checkout 外可使用：python -m pip install "cpea[sqlserver]"
```

在自己選定的 `.env` 填入以下欄位。範例中的主機、資料庫、帳號與密碼都是佔位文字：

```dotenv
CPEA_DATABASE_URL='mssql+pymssql://YOUR_USER:YOUR_PASSWORD@server.example:1433/YOUR_DATABASE'
CPEA_DATABASE_CONNECT_TIMEOUT_SECONDS=5
CPEA_DATABASE_QUERY_TIMEOUT_SECONDS=30
```

每個 project 只有一個資料來源，程式以 project 目錄名稱作為內部識別碼，例如 `retail`、`gms2`，不需設定 `CPEA_DATASOURCE_ID`。從含 `manifest.yaml` 與 `catalog.yaml` 的 project 目錄載入 `.env` 時，網頁、CLI 與評估流程均採用此規則；舊的環境變數或 deployment YAML 來源識別碼不會覆蓋 project name。這個名稱用於核對執行來源與隔離詞彙紀錄，實際 database 由連線 URL 路徑決定。帳密中的 `@`、`:`、`/`、`#`、`%` 等特殊字元須 URL encode；也可用 SQLAlchemy `URL.create()` 建構 URL，避免手動拼接。此欄位不再接受 ODBC 的 `Driver=...;Server=...` 格式，也不接受 URL query options；timeout 使用既有獨立欄位。[SQLAlchemy pymssql 文件](https://docs.sqlalchemy.org/en/20/dialects/mssql.html#pymssql)

預設使用 SQL 帳密登入、UTF-8、TDS 7.4 與唯讀 intent。連線要求加密，套件內的 FreeTDS 設定使用 system CA 並驗證 hostname。若部署使用企業 CA，可在 process environment 或選定 `.env` 指定 `FREETDSCONF=/path/to/freetds.conf`（`FREETDS` 亦可）；相對路徑以 env file 所在目錄解析。自訂檔案應保留 `encryption = require`、適當的 `ca file` 與 `check certificate hostname = yes`，不可把 ODBC 的 `TrustServerCertificate` 參數直接放入 URL。[FreeTDS TLS 設定](https://www.freetds.org/userguide/freetdsconf.html)

pymssql 的 `login_timeout`／`timeout` 與 FreeTDS 設定有程序共用效果；同一服務使用一致設定，不同 timeout／TLS 的部署應啟動不同程序。查詢本身仍使用獨立 connection／cursor；SQLAlchemy 採 NullPool，不保留持續連線池。[pymssql timeout 說明](https://pymssql.readthedocs.io/en/stable/ref/pymssql.html)

部署帳號只應有選定 profile 核准 View 的 SELECT 權限。私有 profile 不包含在公開 wheel／sdist，部署時須另外提供。不要將連線 URL 提交到版本控制。

連線字串空白表示停用內建 adapter；timeout 空白分別採 5／30 秒，非法或非正整數會被拒絕。明確注入 executor 時優先使用注入物件。建立 runtime／app 不會連接 DB，每次查詢使用自己的 connection／cursor，只執行一次，有限讀取並在成功或失敗後關閉資源。

啟用 SQL Server 後，啟動指令也加上 extra：

```bash
# Linux／macOS
export CPEA_ENV_FILE="$PWD/.env"
uv run --locked --extra sqlserver uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

```powershell
# Windows
$env:CPEA_ENV_FILE = (Resolve-Path .env).Path
uv run --locked --extra sqlserver uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## API 與代理串流

- `/api/assistant/sql`：既有 SQL 生成 JSON API。
- `/api/assistant/query`：查詢與 LLM 答案 JSON API；history 只接受缺省或空陣列，非空明確回 422。
- `/api/assistant/query/stream`：只接受 `{"request":"問題"}`，不接受 history、SQL 或 datasource。待確認時以 `clarification` 終止；確認後開新串流才送 `sql → result` 或 `sql → error`。拒絕與取消分別為 `unsupported`／`cancelled`。

各入口新增對應的 `/confirm`（串流為 `/query/confirm/stream`），使用 server 核發的選項 ID 接續同題。部署使用單 worker，checkpoint 僅在記憶體、預設等待 15 分鐘；詞彙存於 profile 的 `terms_mapping.json` 或 `CPEA_TERMS_MAPPING_PATH`。詳見 [欄位確認與詞彙對應](docs/hilp_confirmation.md)。

串流 API 在完整 SQL 事件送入 ASGI body 後才開始 DB 工作；同步 LLM／DB 使用 threadpool。Gradio 首頁直接使用同一分段 application service，透過框架 generator 更新畫面。新查詢的驗證、生成、DB 與編碼失敗均顯示「執行錯誤請再試一次」，不輸出原始 driver 例外。已顯示的本題 SQL 會保留。

結果中的日期／時間為 ISO 8601、Decimal 為精確字串、UUID 為字串、binary 為 `base64:` 字串。`row_limit` 表示查詢上限；只有實際觀察到多餘資料並裁切時，`rows_truncated` 才為真。Gradio 資料表採純文字表示。

反向代理須停用 SSE 與 Gradio queue 路由的 buffering、cache 與整包壓縮，並讓 read timeout 大於生成加 DB 查詢所需時間。Nginx 範例：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    proxy_read_timeout 180s;
}
```

若僅針對串流路由設定，需同時涵蓋 `/api/assistant/query/stream`、`/api/assistant/query/confirm/stream` 與 `/gradio_api/queue/`。其他代理或 CDN 也需要相同設定。已開始的同步 DB 工作不保證在瀏覽器離線時立即取消，會在完成或 driver timeout 後釋放資源。

## 驗證

```bash
uv run --locked --group dev --all-extras pytest
uv build
uv run --locked cpea-eval --project gms2 --runs 3 --concurrency 1
```

離線測試使用合成 profile 與 fake driver／executor，不能代表真實 ERP 權限或資料正確性。實際 GMS2 smoke test 需要可用的 pymssql、部署設定與核准 View 的唯讀權限。

`cpea-eval` 由 `--project` 選取 `projects/<id>/.env`、View 契約與單一 `evaluations/cases.jsonl`；使用真實模型，不需要另傳題庫、模型或輸出路徑。`--runs 1` 觀察單次正確率，`--runs 3` 對每題重複三次並統計穩定性。此流程只驗證 SQL 生成，不執行資料庫查詢；私有 Retail profile 與已核准題組需另行提供；未審核案例只能探索，不採計正式成績。

多模型治理比較仍可使用共用 runner。先在獨立、乾淨的 Git worktree 準備模型矩陣與 provider 依賴，再執行：

```bash
CPEA_PROFILE_PATH="$PWD/projects/gms2" uv run --locked cpea-governance-eval compare \
  --cases projects/gms2/evaluations/cases.jsonl \
  --models evaluations/config/models.json --env-file projects/gms2/.env \
  --runs 3 --concurrency 1 --max-failures 3 --live
```

舊 `compare` 入口仍需明確傳入與專案對應的 `CPEA_PROFILE_PATH`、`--env-file projects/gms2/.env` 及模型矩陣；`compare` 預設只跑一次，因此比較穩定性須明確加上 `--runs 3`。每模型達到 `--max-failures` 後停止該模型，未完成題目不計入通過率。結果包含逐次通過狀態、provider 回報的 token 用量與耗時，詳見 [品質評估](evaluations/README.md)。

完整架構與延伸設計見 [架構](docs/architecture.md) 與 [企業級設計](docs/enterprise_design.md)。
目前的目錄與資料搬遷、舊入口及回復步驟見 [專案目錄搬遷](docs/project_migration.md)。
