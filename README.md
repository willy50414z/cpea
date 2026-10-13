# CPEA

可獨立安裝的 ERP 助手核心，保留受治理的單一 View MSSQL 產生、外部執行器注入與來源可追溯回答。

本次重構以 Python 3.12 驗證。實際 ERP DB／API adapter、登入、授權與持久化稽核另案實作。

```powershell
uv sync --locked --no-editable
Copy-Item .env.example .env
uv run --locked --no-editable cpea --env-file .env --request "請查詢 ZX100 目前各倉庫庫存數量"
```

預設 profile 為合成示例；需要可用的 LLM／embedding 服務才會生成 SQL。真實 SQL 執行需要部署方顯式注入既有 executor。HTTP app 入口為 `cpea.interfaces.api.app:create_app`，使用 uvicorn 的 `--factory` 啟動。

完整安裝與設定說明見 [重構計畫](docs/refactoring_plan.md)、[架構](docs/architecture.md) 與 [企業級設計](docs/enterprise_design.md)。
