# WrenAI 獨立研究交接

日期：2026-10-23。研究者為 fresh-context agent；依 EDD investigate 與 brainstorming 執行只讀調查，未實作、安裝、讀 secrets 或呼叫真模型。

## 結論與問題分類

這是新功能／介面適配工作，不是既有 flow 的 bug。使用者已選「先以真實 WrenAI 為主，測量後才考慮混合」，因此推薦直接執行 pinned legacy/v1 pipeline，不推薦在 LangGraph 模仿 WrenAI。需求存在一個不可省略的邊界：upstream 沒有 CPEA 的 `DecompositionDraft`，需要明確的新 Draft 輸出 extension；把 schema retrieval 結果冒稱 Draft 不成立。

具體可 review 設計：[設計草案](../../../docs/superpowers/specs/2026-10-23-wrenai-semantic-decomposition-design.md)。狀態待使用者核准。

## 已查證來源

以下均為官方原始碼；`git ls-remote` 與 GitHub commit API 核對 SHA。2026-10-23 查證：

| 證據 | 已確認事實 |
| --- | --- |
| [v1 pyproject](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/pyproject.toml) | branch legacy/v1 = `ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc`；service 0.29.3；package-mode=false；AGPL-3.0；Python 3.12；Haystack==2.7.0、Hamilton ^1.69；numpy ^1.26.4、tiktoken ^0.12 |
| [BasicPipeline](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/core/pipeline.py) | BasicPipeline 持有 Haystack Pipeline／Hamilton AsyncDriver；實際研究的 intent／retrieval／indexing 類別皆使用 AsyncDriver |
| [provider 介面](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/core/provider.py) | LLMProvider.get_generator、EmbedderProvider.get_text/document_embedder、DocumentStoreProvider.get_store/get_retriever 可注入與錄製 |
| [DBSchema](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/db_schema.py) | MDLValidator→DDLChunker→document embedder→clean→writer；TABLE_SCHEMA 文件分模型與欄位批次 |
| [TableDescription](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/table_description.py) | TABLE_DESCRIPTION 文件包含名稱、description、欄位名清單，無額外 LLM 語意生成 |
| [MDLValidator](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/indexing/__init__.py) | JSON 缺少 models/views/relationships/metrics 時補空；不要求業務詞典才能索引 |
| [IntentClassification](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/generation/intent_classification.py) | 自行 embedding／schema retrieval 後分類 TEXT_TO_SQL／GENERAL／MISLEADING_QUERY／USER_GUIDE；不是細粒度需求抽取器；post_process 解析失敗會 fallback TEXT_TO_SQL |
| [DbSchemaRetrieval](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/pipelines/retrieval/db_schema_retrieval.py) | query embedding→表說明檢索→schema文件→DDL→可選 LLM 欄位裁剪；run(query,tables,project_id,histories,enable_column_pruning)；回 retrieval_results 等旗標，非 Draft |
| [原生 LLM provider](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/providers/llm/litellm.py)／[embedder](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/providers/embedder/litellm.py) | APIError 內建 backoff max_tries=3/max_time=60；需窄 policy patch 才符合本 repo rate limit 不重跑規則 |
| [trace_cost](https://github.com/Canner/WrenAI/blob/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service/src/utils.py#L164) | decorator 將 model、usage、fallback flag 交 Langfuse；沒有本地 oracle、費率版本或完整 replay 契約 |
| [現行 main 架構](https://github.com/Canner/WrenAI/blob/f618d8d9848c3d6b617859e575bd560d50bcc04e/docs/core/reference/architecture.md) | main = `f618d8d9848c3d6b617859e575bd560d50bcc04e`，已轉 agent-native CLI/core；模型生成由 agent orchestration 負責 |
| [現行 toolkit](https://github.com/Canner/WrenAI/blob/f618d8d9848c3d6b617859e575bd560d50bcc04e/sdk/wren-langchain/src/wren_langchain/_toolkit.py)／[版本](https://github.com/Canner/WrenAI/blob/f618d8d9848c3d6b617859e575bd560d50bcc04e/sdk/wren-langchain/pyproject.toml) | wren-langchain 0.2.3；需 target/mdl.json；無 memory 只提供 SQL query/dry_plan/dry_run，不能直接滿足本次 pre-SQL 語意 flow |

## 本地可重用契約與限制

- `DecompositionDraft`／PlanningTask／IntegrationPlan 已能承載單／多 View、filter、conditional metric、metadata collection、grain、母體、prepare；本需求不必改其介面。
- `validate_decomposition`／`prepare_requests` 為兩條流程共用 deterministic 邊界，重用可保持後續 SQL generation 契約。`QueryPipelineService(planner,generator)` 已可注入新 `.plan()` service。
- `CatalogProvider`／`SchemaCatalog` 提供核准 View、欄位、型別與 field_contract；不必查 live DB 或新增 business dictionary。複合 source grain 不可縮成假 primary key。
- 舊單 call flow 與 schema-mapping flow 的 observer 可借其事件欄位習慣，但不能直接滿足 node oracle／replay／費率 provenance。
- `evaluations/decomposition_cases.py` 與 grading 可重用必要欄位 recall／precision、可接受替代 task、filters、聚合、grain、integration 的等價規則。現有 scorer 的 `semantic_review_required=True` 不能當完成人工語意驗收。
- 30 題 decomposition case 全部 pending；需求多採業務中文詞，不是本階段明確 identifier 基準。兩個 casefile fingerprint 均 `e5e5a5…`；本 checkout 強制 PYTHONPATH 實測 catalog fingerprint=`f448fd223570b38ab5cd4002a5afc31b60002422cd47549868c64cbf2c87c430`，有 drift，不能原樣載入就當正式 benchmark。
- `query_pipeline_runner.py` 已有 private artifacts、來源 fingerprint、離線重新評分與 provider recording，可重用設計與小型工具；現有 replay 是輸出重評，不等同逐 node provider replay。
- Main 回報正確 checkout 的 focused baseline 113 passed，證據 `evidence/EV-20261023T074047-2f43a752.json`；研究者未重跑完整 baseline。先前 editable import 指向別的 checkout 結果不能引用為本分支證據。

## 合理候選與推薦

| 方案 | 假設／收益 | 範圍、成本與風險 | 可否證測試／回退 |
| --- | --- | --- | --- |
| A：pinned v1 isolated worker，原生 indexing＋intent＋retrieval＋Wren BasicPipeline Draft extension（推薦） | 真實 Wren schema linking 能在 exact identifiers 上選齊來源／欄位；三個 LLM node 可定位失敗 | 獨立 venv 與 Qdrant；schema MDL adapter；窄 retry policy patch；Draft extension 不可省。LLM／embedding 貨幣費用 unknown | 先真實 imports／chunker offline，再自然 smoke；retrieval漏欄、母體／grain誤判則假設失敗。新 service opt-in，停用即回既有 flow，不改它們 |
| B：同程序載入 pinned v1 原始碼，調整 dependency family 後原生 pipeline＋同一 Draft extension | 可減少 worker 通訊與部署維護 | upstream 不是穩定 SDK；numpy/tiktoken 已衝突；必須升級／維護 upstream 依賴並擴大舊流程回歸，會增加本次風險與範圍 | 若能在獨立 lock proof 下同時滿足依賴並跑全部回歸才成立；否則回 A，不能強灌本專案環境 |
| C：現行 main wren-langchain toolkit | 現行 SDK 安裝與 LangGraph 整合較方便 | 在不採 memory、不生成 SQL 的本任務邊界缺少實際可用語意原語；將規劃搬回 CPEA agent 才可做，與使用者先以 WrenAI 為主的動機不合 | 本次排除。將來若 upstream 提供 standalone pre-SQL retrieval／planning API，再重新評估 |

推薦 A 的 isolation 只是處理依賴衝突，不是 WrenAI＋CPEA 兩套語意 planner 混合。唯一新生成節點以 Wren 原生執行框架補上 CPEA-specific Draft 輸出；既有 validator 是交接安全契約，不參與替代語意選源。

## Node → Parent → E2E 驗收契約

1. schema adapter 生成衍生 MDL（models＋原欄位／型別，空 relationships/views/metrics），執行 upstream 索引兩類文件；seven-view round trip、名稱碰撞、型別與 fake-PK 檢查。返回整個 worker 測 index manifest／重用／隔離，不只測 leaf serializer。
2. intent 原始分類、schema retrieval 欄位選取、DraftPlanning 各有固定輸入 oracle、原始 req/res、解析物件、模型 metadata、transport call ID、elapsed、tokens、費用及其 unknown 狀態。每個 oracle 是業務不變量／合法替代集合，不是強模型答案或自由文字理由精確相等。
3. 錄製 provider 可 isolated replay 每節點與整圖，regrade 只改評分；兩者都零付費。自然 end-to-end 不得注入 gold retrieval 蓋過失敗。
4. 父節點用自然 intent→retrieval→Draft 輸出，經既有 validate/prepare；evaluator 再對獨立 oracle 核對關鍵欄位、條件、時間、母體、integration keys/grain 全保留才 PASS。既有 validator 不讀原 request，只保證結構契約，不能證明任意需求語意 coverage。非 ready 不可暴露 prepared requests。
5. 舊兩條 flow focused regression＋後續 SQL boundary adapter test，證明可交接 Draft；本階段不執行 SQL，不能宣稱數值答案正確。

實際 call 記錄包括所有 LLM 及 embedding batch，unknown usage／價格不能填 0；source、schema、prompt、model、catalog、index 與 oracle 均有版本。upstream 自動 retry 必須停用並測試 transport attempt=1，不能只把 runner metadata 改成零。

## 首批 sample 機械核對

使用 `.venv/bin/python`、UTF-8 yaml，及 `env PYTHONPATH=/home/willy/code/cpea-wrenai/src` 強制本 checkout 載入 `SchemaCatalog`。

- customer：customer_id／registered_on／lifetime_spend 全存在；grain=[customer_id]。
- sales detail：store_id／product_id／order_date／quantity 全存在；quantity SUM 可用；原始粒度 keys=null，不能聲稱原列唯一。
- inventory：store_id／product_id／stock_qty／snapshot_date 全存在；grain=[store_id,product_id]。
- monthly product：store_id／product_id／sales_month／units_sold 全存在；grain=[store_id,sales_month,product_id]。
- store KPI：store_id／sales_month／target_amount 全存在；grain=[store_id,sales_month]。
- missing_metric_xyz 在全部七個 View 都不存在；city 在多個 View 存在，會員城市與門市城市不能靠同字選定母體。

## 分階段資源與停止／重判

- phase 1 離線真實 upstream imports／index chunking／retry／worker protocol，無付費；只驗可嵌入。
- phase 2 node fixture＋provider replay＋自然整圖 fixture＋舊流程回歸；只驗契約與可除錯，未證真模型能力。
- phase 3 建議六題每題一次，最多18 LLM attempts＋embedding，需明確模型、embedding／Qdrant與總預算；真實 smoke 才驗 schema linking／Draft 語意能力。
- phase 4 同輸入比較三條 flow，擴及 conditional metrics／metadata dates／三來源背景。失敗回獨立研究判斷是 upstream能力、oracle、契約adapter或資源問題，再決定混合。
- rate limit／provider error 先保存證據，按 repo quota 規範處理，不能自動 retry；若原生 import 不可用或依賴鎖不可建立，先停在可行性 gate，不能默默本地重寫 pipeline。

## 待使用者決定／阻礙

1. 設計核准包含：採 legacy/v1 pinned 實作，以及自動產生的結構性 MDL 不屬禁止的業務詞典。
2. 真實測試前需 LLM provider／model、embedding model／dimension、Qdrant endpoint 與總呼叫／費用預算。當前費用 unknown，研究沒有已核准真模型額度。
3. oracle 輸出仍需人工核准；既有 case fingerprint drift 必須獨立審視，不能把 pending 舊題目改 fingerprint 後自稱 approved。

未改產品、既有測試或現有題庫；本交接僅新增 research.md 與待核准設計。

Builder 邊界釐清：upstream intent 經 utils.sql 傳遞 import src.core.engine，允許 module／型別 import，但 worker 不實例化或呼叫 Engine、不連 DB；設計已修正。完整需求語意 coverage 由測例 evaluator oracle 驗收，不冒稱 runtime 既有 validator 可證明，也未新增混合 planner。
