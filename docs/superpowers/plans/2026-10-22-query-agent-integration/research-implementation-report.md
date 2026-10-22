# 研究增補實作與獨立測試紀錄

日期：2026-10-22。使用者後續指示已授權本次實作。基準為 `f5c97f564d0c14b14612faef893ad923fa5a17db`，分支 `feat/tts_compare`，worktree `/home/willy/code/cpea_terms`；開始時乾淨。未提交或推送。

## 實作範圍與狀態

| 里程碑 | 本次交付 | 仍缺的驗收證據 |
| --- | --- | --- |
| S1-02-E1 | evaluation 專用四種契約、六項能力描述、三種候選身分、責任檢查、沿用 case registry 的安全輸入建立器 | 獨立責任／介面審查；A2／A3 原型在此 worktree 不存在，尚無候選差異驗收 |
| S1-06-E1 | 原 runner 追加 worktree／branch／lock／未知模型 revision；首次 Raw 即時保存；原生候選分支及逐節點 hash、固定分母、成本、停止行為 | 受核准真實研究候選的自然原件；實際 immutable model revision 尚未核實 |
| S1-07-E1 | 逐義務投影評分、完整合法替代配對、六層分開呈現、Mapping Recall／Precision、Oracle 誤收／誤拒統計、hash 綁定獨立核准檢查、Raw replay／response regrade／managed index 分流 | 獨立核准的語意規則與 mutation corpus；其他指標與原生 reference／integration／SQL validator 尚須逐候選接線，未觀測層不給 PASS |
| S1-08-BL | 確認原 12 題全部 `pending`；原三模式入口與核准 gate 保留 | S1-01 人工核准及固定模型；本次無自然模型呼叫，未取得 baseline |
| R1-00／A／B | manifest、固定輸入、局部候選責任限制、離線 runner／重現工具可獨立測試 | BL、候選實作與獨立核准的 Pilot／研究矩陣；未執行 A/B，不生成勝負報告 |
| R2-01 | 固定官方 commit／來源 hash／授權觀察矩陣，見 [外部研究](external-engine-research.md) | 業務義務與授權適配的獨立審查；其餘引擎的實際部署／方言未測 |
| R2-02 | 隔離 `wren-core-py==0.8.1`；七 View 無損 sidecar＋MDL 草稿；7/7 SELECT 編譯；系統網路呼叫追蹤 | 四情境 Pilot 的技術語意義務核准、自然組、反例與獨立語意審查；本次僅固定 semantic request 技術探測 |
| R2-03 | [可行性與成本缺口](external-engine-research.md#成本與可行性) | 人工建模／維護／新 ERP 實測與獨立審查；不以編譯成功推定業務可行 |
| ADG-01 | 證據缺口已列明，尚未選型 | R1-A／B 與 R2-03 完整報告及獨立審核；沒有替換產品服務 |
| R3-01／02／03 | 保留原前置依賴 | S2／S3 驗收、固定 fixture／oracle／DB 授權；本次未做 DB 或結果層比較 |

上述離線測試通過不等於研究里程碑全數驗收；原 S1-01、S1-08 與 S2～S6 狀態不變。

## 責任與可重用邊界

| 能力 | 產品既有邊界 | 研究介面與獨立驗證 |
| --- | --- | --- |
| Requirement Parsing | `TaskDecompositionService.plan` 的完整規劃輸出 | 可保存原生 requirement observation；逐義務投影另評，不能補造模型的 coverage |
| Capability Resolution | A0 沒有公開 Coverage／own_gap | `internal_coverage` 僅接受相符責任；缺 own_gap 保留未觀測 |
| Query Planning | `QueryPipelineService` 的 planner 注入 | 完整候選沿既有 factory；局部 Coverage 進原生 observation 分支，不偽造 decomposition |
| Single-View SQL | `generate_task_sql`、`TaskSQLInput`、原 compiler／policy gate | 原 SQL 模式獨立使用核准 Prepared Task；外部 SQL 尚未適配者不宣稱通過產品 gate |
| Semantic Validation | 原整份方案 grader 與產品 gate | 新 requirement grader 只讀投影；其他五層需各自證據，原 grader 分數保留 |
| Cross-View Integration | S1 僅保留及驗證 integration 計畫 | 靜態計畫與 S3／R3 結果分開；本次 `result_completeness=not_tested` |

產品程式沒有 import evaluation，未變更正式 API、schema、雙節點與依賴。

## 可分別執行的驗證

以下每一列可單獨執行，無須模型、DB、其他測試的產物或先後順序。

| 環節 | 命令 |
| --- | --- |
| 候選／輸入／能力契約 | `.venv/bin/python -m pytest tests/unit/test_query_pipeline_experiments.py -q` |
| 原生 Raw／解析／正規化／首錯／成本 | `.venv/bin/python -m pytest tests/integration/test_query_pipeline_native_runner.py -q` |
| 逐義務評分／合法替代／Oracle／獨立核准 | `.venv/bin/python -m pytest tests/unit/test_query_pipeline_research_grading.py -q` |
| 原雙節點 runner 與 response regrade 回歸 | `.venv/bin/python -m pytest tests/integration/test_query_pipeline_runner.py -q` |
| Planning 節點 | `.venv/bin/python -m pytest tests/unit/test_task_decomposition_workflow.py tests/integration/test_decomposition_runner.py -q` |
| SQL 節點與 gate | `.venv/bin/python -m pytest tests/unit/test_query_pipeline_task_sql.py tests/unit/test_query_pipeline_validation.py -q` |
| Wren 轉換與缺口記錄 | `.venv/bin/python -m pytest tests/unit/test_query_pipeline_wren_poc.py -q` |

新測試先觀察功能缺失失敗，再實作與重跑。測試涵蓋 provider／parse／normalize 中斷、剩餘試次 skipped、無自動重試、未知用量 null、離線 network／DB sentinel、Raw 先存、完整性竄改、程式漂移、原件唯讀、互斥合法替代與錯日期／錯母體／無關 identifier。`research_live` 路徑只以本地假 provider 驗證 instrumentation，沒有真的呼叫模型。

執行完整聚焦集合：

```bash
.venv/bin/python -m pytest tests/unit/test_query_pipeline_*.py \
  tests/integration/test_query_pipeline_runner.py \
  tests/integration/test_query_pipeline_native_runner.py \
  tests/unit/test_task_decomposition_contract.py \
  tests/unit/test_task_decomposition_workflow.py \
  tests/unit/test_decomposition_evaluation.py \
  tests/integration/test_decomposition_runner.py -q
```

本次最終聚焦回歸 **194 passed（11.95 秒，退出碼 0）**；七組獨立命令皆退出碼 0，依表順序為 13／17／9／18／13／40／3 passed。`git diff --check` 與相關文字檔 UTF-8 無 BOM 檢查通過。未執行全 repository 測試，亦未執行自然模型或 DB 驗收。

## 介面使用約束

- `evaluation_input()` 重用既有案例 hash、catalog 與核准檢查；自然模型只收到 `request/catalog`，隔離組追加核准的 `upstream`。案例識別碼、答案、審核與預期 SQL 不入模型 context。
- catalog 原始 fingerprint 與 JSON snapshot hash 分開保存，不能用 JSON hash 取代既有 YAML 指紋；執行前再驗證可變的巢狀 snapshot。
- `evaluate_strategy()` 一次記錄 manifest 中一個候選，`planned` 是該候選全體試次，`matrix_planned` 保留整張矩陣。其他候選分別執行；不挑選成功答案。
- 明確提供 `transport` 永遠為 `stub`。真實模型路徑須 `live=True`、settings 及綁定 `research_execution_hash()` 的獨立 preregistration review；只會建立受記錄的既有 model，不建立 DB agent。`research_live` 仍不能自行宣稱完整自然成功。
- parser／normalizer 為評估端受信任的純函式，須回傳可 JSON 序列化的原生值；不得自行查 DB、呼叫模型或重試。這是內部研究 API，離線測試的 sentinel 不等於對任意第三方程式提供 sandbox。
- `replay_strategy()` 重跑相同 parser／normalizer、核對來源與原件；沒有 Raw 的 provider 失敗不能宣稱重現。`regrade_strategy()` 只重評既有 normalized；既有 `replay_query_pipeline()` 的報告明標 `response_regrade`。managed 僅提供唯讀完整性索引，本 worktree 缺原 managed runner，沒有冒稱已執行 managed Raw replay。
- 原生 requirement 評分只驗核准投影。native schema、引用、integration 與 SQL 的專屬 validator 尚未提供時，各層維持 `NOT_OBSERVED`；不因欄位相等宣稱 compiler／policy／DB／回答正確。

## 指標與分母契約

| 指標 | 分子／分母與適用責任 |
| --- | --- |
| Requirement Coverage | satisfied 義務／全部預登錄義務；partial／missing／unsupported／clarification／unknown 分列；正向必要義務不可漏 |
| Mapping Recall／Precision | 正確映射／核准映射；正確映射／候選輸出映射；輸出未觀測時率為 null |
| Own Gap／Dependency | 正確 own gap／全部核准 own 標記；正確同 View scope／grain dependency／全部核准 dependency；無投影規則不評 |
| Source／Grain／Population | 各自正確的適用義務／各自全部預登錄適用義務，靜態與結果層分開 |
| SQL Contract／Join Safety | 通過獨立靜態 gate 的適用項／全部適用項；未適配產品 gate 不計產品 PASS |
| Unsupported／Clarification | 正確停下／應停案例，另列誤拒合法需求及錯誤放行；不能把一律拒絕算高成功率 |
| Oracle False Reject／Accept | 自動誤拒／有獨立合法標記案例；自動誤收／有獨立非法標記案例；爭議及未觀測另列，總 planned 保留 |
| Calls／Tokens／Latency | 逐節點與整體實測，未知 null；額外模型呼叫／轉換／知識工時另記，無自動重試 |

目前程式提供 requirement、mapping、Oracle 核心；表內其他項為待候選 validator 接入的分母契約，未宣稱全部指標已實測。語意規則變更與 mutation 標記仍須獨立核准。

## 證據與後續

- 基準聚焦測試 36 passed，退出碼 0；執行紀錄留 `.superpowers/sdd/task/`。
- Wren 安裝與編譯命令、退出碼、來源 hash、逐欄轉換、逐 View request／SQL、網路追蹤及完整性索引位於受 gitignore 保護的 `projects/retail/artifacts/query_pipeline/research-integration-e1/`。頂層 `run.json` 記錄全部證據 hash；隔離環境在 `.superpowers/sdd/task/wren-venv`。
- 公開來源版本與檔案 hash 見 [research-source-index.json](research-source-index.json)。獨立審查狀態為未審查，沒有代簽任何業務核准。
- 下一步為核准原 12 題面板、逐義務規則／Pilot／候選版本矩陣及技術語意義務，再取得 BL、執行 R1／R2 正式比較。ADG 與 R3 保持前置條件，不提前進入 S2 或 DB。
