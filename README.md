# CPEA

可獨立安裝的 ERP 助手，提供受治理的單一 View MSSQL 產生、選配 SQL Server 執行與 Gradio 問答首頁。使用 Python 3.12。

首頁的使用方式類似 ChatGPT：輸入問題後先看到 SQL，再看到查詢結果表格。每次問題獨立，只顯示最新一題；重新整理會清空。此流程不額外呼叫 LLM 整理答案、不保存問答，也不自動重試。

## 安裝與啟動

Linux／macOS（Bash）：

```bash
uv sync --locked
cp .env.example .env
uv run --locked cpea --env-file .env --request "請查詢 ZX100 目前各倉庫庫存數量"
export CPEA_ENV_FILE="$PWD/.env"
uv run --locked uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Windows（PowerShell）：

```powershell
uv sync --locked
Copy-Item .env.example .env
uv run --locked cpea --env-file .env --request "請查詢 ZX100 目前各倉庫庫存數量"
$env:CPEA_ENV_FILE = (Resolve-Path .env).Path
uv run --locked uvicorn cpea.interfaces.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/`。Gradio 與 FastAPI 由同一服務提供，不需前端建置。預設 profile 為合成示例；SQL 生成需要可用的 LLM／embedding 服務。沒有 executor 時仍可用 `/api/assistant/sql` 與 CLI 生成 SQL；首頁與執行 API 則回報執行不可用。

`--env-file`／`CPEA_ENV_FILE` 應指向目前作業系統上的實際檔案；Linux 不使用 Windows 路徑。程式不自動搜尋 `.env`，設定依 process environment、明確 env file、預設值的順序讀取。Profile／deployment 相對路徑以選定 env file 所在目錄解析。

## 連接 SQL Server

內建 adapter 使用 SQLAlchemy 的 `mssql+pymssql`，支援平台的 pymssql wheel 已包含 FreeTDS，不需要安裝 unixODBC 或 Microsoft ODBC Driver，也不需要執行先前的 ODBC sudo 腳本。Linux／Windows 都先安裝 Python 選配依賴；若平台沒有相容 wheel 而需從原始碼建置，才需要編譯工具與 FreeTDS 開發檔案。[pymssql 安裝說明](https://pymssql.readthedocs.io/en/stable/intro.html)

```bash
uv sync --locked --extra sqlserver
# 在 checkout 外可使用：python -m pip install "cpea[sqlserver]"
```

在自己選定的 `.env` 填入以下欄位。範例中的主機、資料庫、帳號與密碼都是佔位文字：

```dotenv
CPEA_PROFILE_PATH=integrations/private/gms2
CPEA_DATASOURCE_ID=gms2-readonly
CPEA_SQLSERVER_CONNECTION_STRING='mssql+pymssql://YOUR_USER:YOUR_PASSWORD@server.example:1433/YOUR_DATABASE'
CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS=5
CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS=30
```

`CPEA_DATASOURCE_ID` 是邏輯 binding，也可由 deployment YAML 提供；它不是 database 名稱。`gms2` 是 View schema，實際 database 由 URL 路徑決定。帳密中的 `@`、`:`、`/`、`#`、`%` 等特殊字元須 URL encode；也可用 SQLAlchemy `URL.create()` 建構 URL，避免手動拼接。此欄位不再接受 ODBC 的 `Driver=...;Server=...` 格式，也不接受 URL query options；timeout 使用既有獨立欄位。[SQLAlchemy pymssql 文件](https://docs.sqlalchemy.org/en/20/dialects/mssql.html#pymssql)

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
- `/api/assistant/query`：既有查詢與 LLM 答案 JSON API，仍接受 history。
- `/api/assistant/query/stream`：只接受 `{"request":"問題"}`，不接受 history、SQL 或 datasource。SSE 序列為 `sql → result`、`sql → error` 或 `error`，只有一個終止事件。

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

若僅針對串流路由設定，需同時涵蓋 `/api/assistant/query/stream` 與 `/gradio_api/queue/`。其他代理或 CDN 也需要相同設定。已開始的同步 DB 工作不保證在瀏覽器離線時立即取消，會在完成或 driver timeout 後釋放資源。

## 驗證

```bash
uv run --locked --extra sqlserver pytest
uv build
uv run --locked cpea-query-eval --env-file .env --dataset evaluations/datasets/query_reliability.jsonl --runs 3 --progress
```

離線測試使用合成 profile 與 fake driver／executor，不能代表真實 ERP 權限或資料正確性。實際 GMS2 smoke test 需要可用的 pymssql、部署設定與核准 View 的唯讀權限。

上述 reliability test 會呼叫 `.env` 指定的真實模型，使用 GMS2 題庫時須設定對應的私有 GMS2 profile。`--runs 3` 對每題重複三次；它只驗證 SQL 生成，不執行資料庫查詢。

多模型治理比較可共用同一份 reliability JSONL 題庫與評分規則。先在獨立、乾淨的 Git worktree 準備模型矩陣與 provider 依賴，再執行：

```bash
uv run --locked cpea-governance-eval compare \
  --cases evaluations/datasets/query_reliability.jsonl \
  --models evaluations/config/models.json --env-file .env \
  --runs 3 --concurrency 1 --max-failures 3 --live
```

`compare` 預設只跑一次，因此比較穩定性須明確加上 `--runs 3`；`stability` 則只測 `.env` 的單一模型。每模型達到 `--max-failures` 後停止該模型，未完成題目不計入通過率。結果包含逐次通過狀態、provider 回報的 token 用量與耗時，詳見 [品質評估](evaluations/README.md)。

完整架構與延伸設計見 [架構](docs/architecture.md) 與 [企業級設計](docs/enterprise_design.md)。
