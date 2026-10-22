# 外部引擎固定版本研究與 Wren 技術探測

日期：2026-10-22。狀態：研究草稿，未獨立審核。此文件支援 R2-01／02／03，沒有完成 R1 比較、正式四情境 Pilot 或 ADG 選型。所有來源 SHA／檔案 hash 見 [來源索引](research-source-index.json)。

## 固定版本與能力觀察

| 候選 | 本次固定版本／授權觀察 | CPEA 適配與執行狀態 |
| --- | --- | --- |
| Wren Core | `wren-core-py 0.8.1`；WrenAI snapshot `7f94c7889bf83b936df9ab3079fbf2fd8110b4d5`；core 與 Python manifest 為 Apache-2.0 | 優先使用 `SessionContext(base64_mdl).transform_sql()`；本次只有 MDL／固定 SQL 的無 DB 編譯，不是自然語言生成。7/7 View 技術探測成功 |
| MetricFlow | `v0.213.0`，commit `4200f85c59b2bb334f0b0dea851b38d0b8198134`；此次 root 與 dbt-metricflow LICENSE 為 Apache-2.0 | 指標／維度／entity 的語意層候選；需要另建 semantic definitions。未安裝，未實測離線 compile／dbt adapter，也未驗 CPEA PostgreSQL／SQL Server |
| Cube | `v1.8.9`，commit `b4b2591791653a91eaf7b3a61a2eb8125bc2ae41`；root 預設 Apache-2.0，個別 package 可為 MIT；所讀 schema-compiler LICENSE 為 Apache-2.0 | 治理／模型／join 候選；需獨立服務與 schema adapter。未安裝，未測離線編譯、方言、telemetry 或權限整合 |
| LangChain | repository snapshot tag `langchain-core==1.6.13`，commit `bdf0f53ed0aec3c9ae371a549e1a4d2ee4e9f021`；所讀 core 與 classic LICENSE 為 MIT；此 snapshot 的 `libs/langchain` 實為 `langchain-classic 1.0.8` | 不把 core 版號當完整 SQL toolkit 版號。官方預設 SQL agent 會取 schema、執行與修復查詢，不適合直接進 R1-B；應研究固定 catalog 的單次生成薄封套，尚未實作或實測 |
| LlamaIndex | `v0.14.25`，commit `f12d46acab73f5b2243ef49c2f00101617b38ce4`；root LICENSE 為 MIT | `sql_only=True` 可略過結果執行，但 wrapper 的 SQLAlchemy schema reflection／table info 路徑仍須處理；不能僅開此旗標宣稱零 DB。未安裝或實測 |
| Vanna | `v2.0.2`，commit `365d0617c1a4567ffee1b19b40c27feb4206bfcf`；root LICENSE 為 MIT | 基本 SQL 生成與知識適配候選；未測固定 catalog、額外知識量、工具呼叫／重試關閉或 CPEA gate，不作產品接入 |
| SQLGlot | tag `v30.24.0`，commit `5d588c0f32d17a08191898638f67ff27bb0a13ff`；release API 無 latest release，改固定 tag；此輪未核對 LICENSE | 僅 AST／方言靜態工具候選，不能代替業務等價 oracle；未安裝 |

Wren 的根目錄 license 按路徑區分，不能以套件品牌概括整個 repository；本次只使用 core wheel，沒有使用其他產品模組。[Wren 路徑授權](https://github.com/Canner/WrenAI/blob/7f94c7889bf83b936df9ab3079fbf2fd8110b4d5/LICENSE)、[Python package 版本與授權](https://github.com/Canner/WrenAI/blob/7f94c7889bf83b936df9ab3079fbf2fd8110b4d5/core/wren-core-py/pyproject.toml)。

MetricFlow 與 Cube 的授權觀察僅適用本次固定的來源；沒有核對所有 transitive dependency／NOTICE 或部署組合。[MetricFlow LICENSE](https://github.com/dbt-labs/metricflow/blob/4200f85c59b2bb334f0b0dea851b38d0b8198134/LICENSE)、[MetricFlow manifest](https://github.com/dbt-labs/metricflow/blob/4200f85c59b2bb334f0b0dea851b38d0b8198134/pyproject.toml)、[Cube LICENSE](https://github.com/cube-js/cube/blob/b4b2591791653a91eaf7b3a61a2eb8125bc2ae41/LICENSE)。

LangChain 官方 agent 流程明列 schema 查詢、DB 執行及錯誤修復；這是拒用其預設 DB agent 的依據，並非判定單次 SQL 生成封套不可行。[官方 SQL agent](https://docs.langchain.com/oss/python/langchain/sql-agent)、[固定 classic manifest](https://github.com/langchain-ai/langchain/blob/bdf0f53ed0aec3c9ae371a549e1a4d2ee4e9f021/libs/langchain/pyproject.toml)。

LlamaIndex 的生成旗標與 SQLDatabase 建構需要分別驗證，未以靜態閱讀冒充零 DB 實測。[固定 SQL retriever](https://github.com/run-llama/llama_index/blob/f12d46acab73f5b2243ef49c2f00101617b38ce4/llama-index-core/llama_index/core/indices/struct_store/sql_retriever.py)、[固定 SQL wrapper](https://github.com/run-llama/llama_index/blob/f12d46acab73f5b2243ef49c2f00101617b38ce4/llama-index-core/llama_index/core/utilities/sql_wrapper.py)、[Vanna LICENSE](https://github.com/vanna-ai/vanna/blob/365d0617c1a4567ffee1b19b40c27feb4206bfcf/LICENSE)、[SQLGlot 固定來源](https://github.com/tobymao/sqlglot/tree/5d588c0f32d17a08191898638f67ff27bb0a13ff)。

## Wren 的隔離技術探測

隔離環境 `.superpowers/sdd/task/wren-venv` 使用 Python 3.12.3，僅安裝 `wren-core-py==0.8.1` wheel，無額外 dependencies。Linux x86_64 wheel 的 PyPI 登錄 SHA-256 為 `781baa9188845451d39f295083e5e07172ec2a186b9fa71d7df861c1982b2f6b`；此值是登錄 metadata，不冒稱自行計算下載檔 hash。產品 `pyproject.toml`、`uv.lock` 與 `.venv` 未修改。

`evaluations/query_pipeline_wren_poc.py` 可在隔離 interpreter 直接執行，不依賴 CPEA 或其 evaluation dependencies。snapshot 由既有 `SchemaCatalog` 讀取；保留所有七 View 的完整原契約 sidecar，只把來源／欄名／技術型別轉成 MDL。

| 項目 | 實際結果／限制 |
| --- | --- |
| 七 View | inventory、sales detail、daily sales、customer value、order summary、product monthly、store monthly KPI 全部 SELECT 編譯成功，分母 7 |
| 呼叫 | 僅使用 MDL 初始化與 `transform_sql`；模型呼叫 0，DB API 呼叫 0；沒有提供 DB credentials |
| 網路 | `strace -f -e trace=network` 17 行，未觀察到 `connect`、AF_INET／AF_INET6 或 sendto。結論僅涵蓋這次初始化及七個編譯請求 |
| 自然語意 | 未測；輸入是固定 semantic request，不是自然語言、核准 Pilot、完整 QueryPlan 或產品 gate |
| 鍵與 Join | 不推定 primary key、cardinality、relationship；沒有 Join／fanout 實測 |
| 數值型別 | YAML `number` 無精確 storage type，暫映射 double；每欄列為技術假設，不宣稱 decimal／identifier 型別無損 |
| 業務政策 | grain、unit、日期 scope、禁用 aggregation、母體及缺值規則保存於 sidecar，這份 MDL 草稿尚未 enforce |
| 方言 | 未做 PostgreSQL／SQL Server 的正式成對驗證；Wren 回傳 SQL 不等於通過 CPEA 同方言 compiler／policy |
| 重現 | MDL／原契約、首次 request／SQL、環境、安裝 log、系統呼叫追蹤與 hash 在新的 private run 中；本次未執行引擎 SQL |

無 DB 編譯的程式路徑可由官方 wrapper 的 `transform_sql` 方法核對；該方法與其他 `query`／file registration API 分開。[固定實作](https://github.com/Canner/WrenAI/blob/7f94c7889bf83b936df9ab3079fbf2fd8110b4d5/core/wren-core-py/src/context.rs)、[固定使用方式](https://github.com/Canner/WrenAI/blob/7f94c7889bf83b936df9ab3079fbf2fd8110b4d5/core/wren-core-py/README.md)。

## 業務核准與知識缺口

Retail manifest 的 `approved` 只代表目前 loader 允許載入；profile 名仍為 `demo_retail_draft`，不由此推導獨立業務核准。原 12 題的 `review_state` 全為 pending。

七 View 雖有 grain keys 與欄位描述，此輪不把它們自動轉成引擎 Join 的唯一鍵／cardinality。待獨立確認：庫存快照與近 30 日相對日期、不同 View 的時間一致性、庫存 left 母體、KPI 背景重複、比率重算、NULL／零／無列，以及跨來源權限。轉換中的 provisional double 也須以真實但受控的 schema／fixture 核對。

上述問題未解前，四情境 Pilot 不宣稱通過；七 View SELECT 探測也不替代部分鍵、無關 identifier、日期／scope 與 unsupported 四情境。

## 成本與可行性

| 成本／能力 | 已有證據 | 尚缺證據 |
| --- | --- | --- |
| 安裝 | wheel 約 49.4 MiB；uv 顯示 preparation 8.24 秒；單一 package 隔離安裝成功 | 完整產品部署、telemetry、權限與授權組合 |
| 轉換 | 7/7 View 技術草稿與原契約 sidecar | 各項業務政策的 engine enforcement、Join／指標建模、實際人工工時 |
| 模型 | 本次 0 calls；token 用量未適用，記錄 null | 自然模型比較的品質、延遲、用量與 provider revision |
| 工程與維護 | 新增隔離探測程式，產品未接入 | 建模／修正／維護／升版工時均未量測，不能填 0 |
| 新 ERP | 沒有新 ERP 代表樣本 | 不提供已證明的新客戶導入成本；待代表樣本與人工知識清單 |
| 回退與相容 | 正式雙節點、API、gate 未改 | 若 ADG 建議 ADAPT／REPLACE，另提遷移、回退、相容與新增驗收計畫 |

可行性限於「此固定版本能把七 View 的技術 MDL 草稿編譯成 SQL，這次未觀察到網路連線」。業務等價、完整 Join、自然生成與實際結果仍未測，尚不能判定應 KEEP／ADAPT／REPLACE。R2 的獨立審查、R1 成對比較與 R3 的固定 DB fixture 都維持原依賴。
