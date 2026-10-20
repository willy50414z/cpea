# 專案目錄與評估資料搬遷

## 現行結構

```text
projects/<project-id>/
├── .env
├── manifest.yaml
├── catalog.yaml
├── views/
├── samples/                         # 選用
├── evaluations/cases.jsonl          # 一份分類題庫
└── artifacts/evaluations/<run-id>/  # 私有執行紀錄與報告
```

`--project` 選定整個目錄。`projects/` 被 Git 忽略，也排除於通用 wheel／sdist。若部署時專案不在 checkout，設定 `CPEA_PROJECTS_ROOT` 指向受保護的專案根目錄。project ID、profile ID、deployment ID 是不同識別，不以 SQL schema 名稱代表企業。

GMS2 的 `.env` 已從本機原有設定複製到 `projects/gms2/.env`，移除重複的 `CPEA_PROFILE_PATH`；本機 FreeTDS 設定複製為 `projects/gms2/freetds.conf` 並調整相對路徑。原根目錄 `.env` 保留供舊入口回復使用，其 profile 路徑已改為 `projects/gms2`。Retail 是 draft profile，目前有自己的設定檔佔位，但沒有正式題庫與已核准的模型設定；執行專案評估會在外部呼叫前拒絕。

## 資料去向

| 舊位置 | 現行位置 |
|---|---|
| `integrations/private/gms2/`、`integrations/private/retail/` | `projects/gms2/`、`projects/retail/`；搬遷前副本保存在本機 `artifacts/project-migration/legacy-integrations/` |
| `evaluations/datasets/query_reliability*.jsonl` | 32 題核對後合併為 `projects/gms2/evaluations/cases.jsonl`；原檔保存在 `examples/legacy-evaluation-cases/` |
| 舊合成 demo profile | 已移除；首頁改由 `gms2`／`retail` 專案選單指定來源 |
| `artifacts/evaluations/`、`artifacts/stability/` | 原位保留作歷史執行紀錄；新 run 才使用專案內位置 |
| 原 PoC 封存 | 原位保留，不重新命名或當作新 run |

搬遷前的逐檔路徑、大小及 SHA-256 記在本機被忽略的 `artifacts/project-migration/source-inventory.json`；題目對照與修正在 `case-review.json`。已核對 View 契約搬遷前後的檔案與 catalog 指紋。GMS2 原 core 第一題問 `GN2300`，預期 filter 卻是 `ZX100`；新題庫把預期值修正為 `GN2300`。原檔未改寫。

## 執行與報告

```bash
uv run --locked cpea-eval --project gms2 --runs 1 --concurrency 1
uv run --locked cpea-eval --project gms2 --runs 3 --concurrency 1
```

指令固定使用真實模型。每次 run 產生 UTC 微秒時間加 Git 短 SHA 的 ID，輸出 `run.json`、私有 `calls.jsonl`／`results.jsonl`、`overview.md`、`summary.csv`、`model_summary.csv`、`category_summary.csv` 與逐題 Markdown。Git SHA 只涵蓋已追蹤程式；私有契約與題庫另外記內容指紋。`runs=1` 不提供重複執行穩定性結論。正式模型執行要求乾淨的 Git 工作目錄與有效 provider 設定；本次搬遷驗證使用離線測試，沒有宣稱實際模型通過率。

## 舊入口與回復

舊 `cpea-query-eval`、`cpea-governance-eval`、`evaluations.stability_runner` 仍可用於明確指定資料路徑的研究或診斷；不再自動選取已搬走的 reliability 題庫。專案評估的主要入口是 `cpea-eval`。舊全域產物保留，不能與新題庫、新設定下的通過率或延遲直接比較。

若需回復舊版程式，從 `artifacts/project-migration/legacy-integrations/` 還原舊 profile 工作路徑，並讓舊版部署設定重新指向該路徑；`artifacts/project-migration/source-inventory.json` 可驗證內容。回復只切換程式與設定，不重寫既有 run 或原 PoC 封存。正式部署前應另行備份私有 `projects/`、每專案 `.env` 與評估產物，因它們不會隨 Git checkout 或通用套件傳遞。
