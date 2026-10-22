# S1 能力與面板

版本：`s1-capabilities-v1`。所有案例均為**待人工核准**；不得將此文件視為人工驗收。Ollama `qwen3.8:27b` 僅作連通 smoke，正式三輪評估依使用者指示留待分階段調校。

| 類別 | S1 行為 | 面板 |
| --- | --- | --- |
| 單來源原始列 | 支援，保留來源鍵與核准輸出 | `raw_inventory` |
| 一般聚合 | 支援 catalog 允許的 aggregation／group | `sales_aggregate` |
| 日期與業務 AND 條件 | 完整保留 operator／value | `date_channel_and` |
| 獨立跨 View 任務 | 依序產出 SQL；不執行整合 | `independent_views` |
| 同 View 的獨立任務 | 依 task 分別產出 SQL | `same_view_tasks` |
| 可證明等價 | 僅 AND 順序、IN 集合順序、`!=`／`<>` | `equivalent_in_order` |
| 業務歧義 | 保留 `needs_clarification` | `ambiguous` |
| 無來源能力 | 保留 `unsupported`，不生成 SQL | `missing_capability` |
| 條件聚合 | 整批 `unsupported` | `conditional_metric` |
| 完整 DISTINCT metadata 集合 | 整批 `unsupported` | `metadata_collection` |
| dependency／unbound input | 整批 `unsupported` | `dependent_input` |
| NULL／boolean／無法忠實表示的值 | 整批 `unsupported` | `null_filter` 及單元 mutation |
| 排序、HAVING、業務 limit | 無上游表示；下游擅加即 `semantic_drift` | 單元 mutation |
| NOT IN 與非有限數值 | compiler 無完整承接；整批拒絕 | 單元 mutation |

面板位於 `tests/fixtures/query_pipeline/cases.json` 與 `projects/retail/evaluations/query_pipeline_cases.jsonl`，各 12 題。六題正向均通過既有規劃 validator；每題有原文、必要需求、完整候選方案、預期狀態、能力與契約指紋。六題負向／pending 的正確停止不代表已支援該能力。

核准須由人工檢查原文、catalog、所有 task 與 integration，填入 `review_state=approved`、`reviewer`、`reviewed_at`、`reviewed_case_sha256` 與 `reviewed_contract_fingerprint`。修改必要需求或核准方案後，須更新 `case_sha256` 並重新核准。核准輸入與自然輸出的人工語意審查分開；後者以回應指紋對應 `output_reviews`，不能用核准輸入代替。

新基準與機器可讀矩陣：`projects/retail/artifacts/query_pipeline/20261022-baseline/`。該目錄受 Git ignore 保護，未加入版本控制。
