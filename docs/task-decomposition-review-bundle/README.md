# CPEA 任務拆分補充審查包

本包補齊完整核心程式與引用資料。主文只引用本資料夾內存在的檔案，無超連結；程式、Prompt、YAML與原始結果採原bytes複製，不以函式摘錄代替完整檔案。本次沒有執行模型、測試或SQL，沒有改主線程式／Task／Oracle。完整清單與SHA256見 `bundle-manifest.json`。

## 1. 快照與資料夾配置

- UTC快照：2026-10-22T02:00:16.292101+00:00。
- Task：PLANNING；最近已結算：EDD loop 第22輪 capability_projection_semantics：PASS。
- 用量：本機29次／重試0次／雲端0次。
- 原Task完整bytes：`evidence/task.snapshot.txt`；進度、已結案輪次與請求狀態：`evidence/progress-snapshot.json`。

| 位置 | 內容 |
|---|---|
| `payload/src/cpea` | 完整產品原碼：workflow、schema、catalog、驗證及prepared生成 |
| `payload/evaluations` | 完整evaluation原碼、候選adapter、Prompt、fixtures與Oracle |
| `payload/tests` | 原測試完整原碼，這次未執行 |
| `payload/projects/retail` | View YAML、manifest、catalog、contract_review及原30題 |
| `external/codex` | 原controller及Ledger完整原碼 |
| `evidence` | Task／進度快照、已結案handoff索引 |

保留相對專案結構以追查imports。依賴宣告在 `payload/pyproject.toml` 與 `payload/uv.lock`。不附現行.env／認證／第三方安裝目錄；原碼中的原絕對controller路徑、歷史fingerprint不改寫。本包是審查快照，不宣稱解壓即能無設定啟動模型流程。

## 2. P0：完整Pipeline原碼、呼叫關係與驗證順序

### 2.1 三條不同路徑

| 路徑 | 完整入口 | 實際責任 |
|---|---|---|

| task_decomposition.py | `payload/src/cpea/application/services/task_decomposition.py` | 產品TaskDecompositionService.plan委派workflow |

| workflow.py | `payload/src/cpea/workflows/task_decomposition/workflow.py` | 產品load_contracts→plan_tasks→validate_plan→prepare_requests；單次完整draft規劃，不是三階段evaluation |

| managed_three_stage_runner.py | `payload/evaluations/managed_three_stage_runner.py` | 自然record_run／run_pipeline／replay：Recall＋七View Coverage＋Selection共九節點 |

| managed_capability_projection.py | `payload/evaluations/diagnostics/managed_capability_projection.py` | 第23輪固定上游Coverage隔離：五個獨立預固定首次POST；不能代替自然Recall或全管線 |


### 2.2 自然三階段的實際順序

```text
record_run(contract=候選module)
  → fingerprint及run metadata，先落盤INTERRUPTED
  → run_pipeline
      → recall：version→保存request→input容量→invoke→保存raw→strict parse→materialize_recall→normalized
      → 七View coverage各一次：messages／schema→invoke→parse→compile／materialize_coverage→原guards
      → selection：全部coverage＋typed schema→invoke→parse→materialize_selection
      → finish_selection→finish(guard=True)→validate_decomposition→guard_errors→prepare_requests
  → 保存response／停止原因／artifact hashes
```

HTTP邊界在managed runner同檔ManagedInvoke：body保存後只呼叫controller一次，不自動retry。controller完整檔 `external/codex/skills/edd-loop/scripts/loopctl.py`；Ledger完整檔 `external/codex/edd/scripts/ledger.py`。

### 2.3 最新候選的各層委派

| 完整檔案 | 責任 |
|---|---|

| `payload/evaluations/diagnostics/managed_capability_projection.py` | Coverage無損cards、有限scope AND診斷Oracle、五樣本身份／版本守門、outer receipt；非Coverage委派policy |

| `payload/evaluations/diagnostics/managed_policy_shape.py` | Selection政策與真nest檢查及通用suffix，其餘委派kind |

| `payload/evaluations/kind_mapping_managed_contract.py` | 依kind動態schema；compile只補確定role、不適用值與grain固定path |

| `payload/evaluations/own_responsibility_managed_contract.py` | 不改模型status／own_gap，程式根據同View明示依賴生成缺口 |

| `payload/evaluations/evidence_bound_managed_contract.py` | 索引Recall、typed必填Selection、assignment／exclusion refs與證據理由 |

| `payload/evaluations/referenced_view_coverage.py` | 真JSON pointer文字取證後交原Coverage guards |

| `payload/evaluations/three_stage_view_selection.py` | Recall／Coverage／Selection、同來源條件、母體／粒度與typed一致性 |

| `payload/evaluations/planning_mvp.py` | finish、保守唯一鍵、快照／百分比guard與prepared生成 |

| `payload/evaluations/managed_node_diagnostics.py` | 原隔離engine：prepare／_run／evaluate、raw保存、compile／materialize及固定Oracle |

| `payload/evaluations/diagnostics/managed_node_diagnostics_rebound.py` | 原fixture三方閉合來源、preflight、receipt及版本守門 |

| `payload/evaluations/diagnostics/managed_node_diagnostics_v2.py` | 保留的v2 adapter及歷史來源鏈 |


產品typed模型完整檔 `payload/src/cpea/application/models/decomposition.py`；validate_decomposition／prepare_requests在 `payload/src/cpea/workflows/task_decomposition/validation.py`。Catalog規則在 `payload/src/cpea/application/catalog_contract.py` 與 `payload/src/cpea/infrastructure/catalog/yaml_catalog.py`。Prompt完整原文在 `payload/evaluations/prompts`；policy／cards suffix在上述候選module內。

### 2.4 第23輪隔離測試的驗證順序

```text
projection.main
  → load_package／prepare五contexts
  → preflight：完整bindings、fixture／policy／新作者審者真closed PASS、audit
  → execution_guard：active node／ticket／round
  → settings及model identity→保存review／freeze
  → 每個固定sample再preflight／execution_guard
      → projection.record_sample先保存outer INTERRUPTED
      → base.record_sample／_run：保存request／body／upstream→input容量
          → guarded invoke→ManagedInvoke→controller POST→保存provider raw
          → 重核版本→base.evaluate
              → presence→strict parse→compile→原materialize／guards
              → 固定Oracle→保存legacy machine findings
      → 重核outer receipt／版本／授權／inner hashes
      → projection._outcome：只對精確scope AND差異另判，不吞其他錯誤
      → 保存outer PASS／FAIL，保留legacy verdict／raw
```

契約materialize／證據path檢查先於診斷Oracle；path錯誤時，不能用後面的matcher宣稱PASS。有限AND matcher屬隔離裁決，不會替模型修改輸出。

重複驗證確實存在：evidence-bound materialize_selection內部呼叫finish_selection；外層run_pipeline或隔離evaluate又呼叫一次。沒有第二次模型推理，但guard／prepared生成可能重複執行。原碼保留此實際順序，沒有為本包整理而合併。

## 3. P0：partial在最終規劃中的預期用途

### 3.1 已由現行程式確認的契約

**partial目前是保留有用能力分量及缺口的診斷狀態，不是可直接assignment的完整責任，也沒有多個partial自動合成supported的規劃器。**

| 用途 | 現行行為 | 直接依據 |
|---|---|---|

| 保留mapping | partial必須有非空合法mapping；不能因整題不完整就清空 | `payload/evaluations/own_responsibility_managed_contract.py`，materialize_coverage |

| 指派完整需求 | assignment只接受同來源status=supported | `payload/evaluations/evidence_bound_managed_contract.py`，materialize_selection |

| 最終typed規劃 | finish_selection再次要求supported及mapping／scope實際進task | `payload/evaluations/three_stage_view_selection.py`，finish_selection |

| child對齊鍵重用 | key擴充只取supported entries，不直接取partial grain的key | 同上finish_selection內mappings擴充 |

| 排除理由 | 未選來源的gap refs可以引用partial等非supported責任 | evidence-bound的exclusions分支 |

| 合成完整能力 | 沒有A、B兩個partial自動升級運算；每requirement仍需一個supported來源 | 上述兩個完整檔案 |

同一欄位若另有獨立supported需求，可由那項證據使用；這不等於partial自動升級。必要責任若所有候選都只有partial，不能因此ready，應保留缺口或澄清。

### 3.2 本題的具體用途

- daily有store_id，所以店×商品grain存在有用partial，但不代表完整商品級online淨額。
- revenue/sum可自身完整、只欠online及完整grain；缺口應分開，不能因此丟掉金額能力。
- product_monthly有商品淨額、order_summary有通路，不表示兩來源Join就能還原商品online營收。
- 本題成功計畫由inventory完成庫存／母體、sales_detail在同task完成月份＋online＋折扣／淨額，不靠多個partial合成。

### 3.3 尚未核准的產品意圖與資料模型含義

現有Prompt、guard與測試一致採supported-only執行；但「partial未來是否參與可執行跨View合成」沒有已核准的實作契約。若預期用它補齊粒度、關聯後再篩選或跨來源計算，還需定義合成運算、鍵／基數、可重建性與母體證明，不能只改status。

對目前可由完整來源作答的題目，未選View的partial修正主要改善Coverage語意與排除理由，尚未證明會改變最終成功計畫。它會阻塞目前測試，是因驗收明確要求所有候選語意正確；這與最終計畫可否執行應分開評估。本文確認現行規則，不替需求方擅自核准新的partial用途。

完整正反測試：`payload/tests/unit/test_own_responsibility_managed_contract.py`、`payload/tests/unit/test_three_stage_view_selection.py`、`payload/tests/diagnostics/test_managed_capability_projection.py`。

## 4. P1：contract_review、manifest與權威來源

| 完整引用文件 | 權威範圍／限制 |
|---|---|

| `payload/projects/retail/manifest.yaml` | profile／版本／source_kind／catalog定位及draft狀態；不是業務語意自動核准 |

| `payload/projects/retail/catalog.yaml` | 七View與各YAML位置 |

| `payload/projects/retail/contract_review.md` | 既有唯讀DB metadata及View結構人工審核；記錄鍵及時間／聚合風險，部分文字可能仍為歷史敘述 |

| `payload/projects/retail/views/demo_retail` | loader實際消費的七份YAML原文 |

| `payload/evidence-driven-dev/tasks/ollama-planning-mvp/agents/oracle-audit/review-manifest.json` | 原30題strict sidecar核准與限制；不代表catalog正式核准或模型通過 |

| `evidence/oracle-audit.snapshot.txt` | 同次人工Oracle審核全文原bytes，以txt保存避免新增外部Markdown引用 |


核心矛盾：sales_detail YAML宣告(order_id,product_id)為鍵，人工審核卻指出同訂單可有多筆同商品明細、真正明細鍵未輸出。strict sidecar禁用此鍵做FD、raw唯一性、COUNT等價及額外維度退化；planning_mvp.source_keys對此View回空集合。不能由模型或普通schema檢查覆蓋這個已知例外。

stock_qty不可跨不同快照直接SUM；日期metadata集合不證同日；百分比／平均值跨粒度須重算；最後訂單日期不等於完整交易期間。manifest仍draft。本次未重新連DB核對所有歷史文字，也不修改YAML消除矛盾。

## 5. P1：第21輪之後的新結果與handoff

### 5.1 已結案離線進度，不當成自然通過

- 第21輪 capability_projection_contract：**PASS**；`payload/evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-capability-contract/handoff.json`。

  第21輪純離線能力投影契約完成：無損cards、有限同View scope AND及五固定lineage樣本；原kind全部守門與policy委派保留。81新focused＋228直接回歸實跑PASS，287檔完整finalfreeze及190工件live/frozen一致，fake9兩prepared及scope/typed首錯保持；source/receipt/interrupt/provenance/HTTP身分拒絕通過。6389舊檔不變、Task/control本worker不變，原20 FAIL/PASS/FAIL與15FAIL/18PASS保留。0POST/SQL/DB/commit/push。自然效果PENDING；Main核真FINAL/hash後finish，先fresh audit19–21再fresh delta核准，未准不得POST。

- 第22輪 capability_projection_semantics：**PASS**；`payload/evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-capability-semantics/handoff.json`。

  fresh capability_projection_semantics離線delta ACCEPT。原需求/20原raw/真View與原56rows逐項核對，無損cards不洩漏答案或刪會員自身限制；daily有用店鍵與依賴-only own=false、customer無關鍵與會員自身own=true、inventory完整責任均保持。有限AND只允同View明示已完整驗證supported filter完整群聯集；17真context、16多群子集合、7動態kind、15授權控制與1focused實跑通過。五輸入與16新增引用rows、全部新舊bindings及作者28閉合證據吻合；精確review在真open審者下於settings/model/network前拒絕，未造Task。原20仍FAIL/PASS/FAIL，原15FAIL/18PASS、38×2 Gate未過及root PENDING不變。0POST/SQL/DB，僅新本審核JSON/log；未重跑作者81/228或全frozen，核其正式log及audit。全部程序/proof已結束；Main核真FINAL及hash/check-evidence、finish本輪closed PASS後才准固定五自然coverage。

上述handoff直接引用的必要證據與第19–21輪audit已複製，沒有重跑其測試。

### 5.2 只附已完成的新自然樣本

#### 第23輪／COV-ISO-v1-01

- request ID：b2bca399f95d43b5a93e901ba5e237ce；HTTP 200；單樣本outer **FAIL**。
- 完成UTC：2026-10-22T01:47:41.746244+00:00；整輪已結案：false。
- 完整樣本：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01`；outer裁決：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01.outer.json`。

- node-body.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01/node-body.json`。

- node-provider-response.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01/node-provider-response.json`。

- node-parsed.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01/node-parsed.json`。

- node-compiled.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01/node-compiled.json`。

- node-error.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-01/node-error.json`。


原停止原因：

```json
{
  "error_type": "ValueError",
  "error": "contract reference must point to nonempty text: /columns/sales_date"
}
```

原raw部分觀測欄位，非整份語意核准：

```json
{
  "GRN-001": {
    "status": "partial",
    "own_gap": true,
    "mappings": [
      {
        "column": "store_id"
      }
    ]
  },
  "FILT-001": {
    "status": "supported",
    "own_gap": false,
    "mappings": [
      {
        "column": "sales_date",
        "operator": ">=",
        "value": "2026-09-01"
      },
      {
        "column": "sales_date",
        "operator": "<=",
        "value": "2026-09-30"
      }
    ],
    "contract_path": "/columns/sales_date"
  },
  "MET-003": {
    "status": "partial",
    "own_gap": false,
    "mappings": [
      {
        "column": "revenue",
        "aggregation": "sum",
        "conditions": []
      }
    ],
    "contract_path": "/columns/revenue"
  }
}
```

當次完整凍結來源：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/frozen`；用它判讀此版本，不以未來新碼覆蓋失敗。

#### 第23輪／COV-ISO-v1-02

- request ID：b5a046baca9c498fbd4502d607f9a98c；HTTP 200；單樣本outer **PASS**。
- 完成UTC：2026-10-22T01:52:23.550682+00:00；整輪已結案：false。
- 完整樣本：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02`；outer裁決：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02.outer.json`。

- node-body.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02/node-body.json`。

- node-provider-response.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02/node-provider-response.json`。

- node-parsed.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02/node-parsed.json`。

- node-compiled.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02/node-compiled.json`。

- semantic-review.json：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/COV-ISO-v1-02/semantic-review.json`。


原停止原因：

```json
null
```

原raw部分觀測欄位，非整份語意核准：

```json
{}
```

當次完整凍結來源：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-capability-projection-1-20261022T014118Z-68828b/frozen`；用它判讀此版本，不以未來新碼覆蓋失敗。

第一個daily新樣本原raw保留store_id partial／own=true、revenue partial／own=false，但contract_path指到欄位物件，contract_text要求非空文字節點，故在materialize先拒絕。這只是兩個先前分類欄位出現預期值，不等於整份Coverage、五樣本或自然全Pipeline通過。

其他單樣本outer PASS也只是機器／contract裁決，仍須完整語意核對及整輪結案。未結案時沒有正式最終handoff；本包未把進行中工作者檔案冒充handoff。其餘inflight及快照邊界見 `evidence/progress-snapshot.json`。

### 5.3 歷史對照及交接索引

原第20輪三樣本FAIL／PASS／FAIL：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-isolation-v2-rebind-1-20261022T000748Z-82acde`。原第18輪Selection PASS：`payload/evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-policy-shape-1-20261021T231146Z-570327`。已結案worker handoff清單：`evidence/closed-handoffs.json`。歷史對照不覆蓋新結果。

## 6. 完整性與界線

- 主文引用路徑均在本資料夾存在，程式與資料原bytes不變，SHA256可核對manifest。
- payload/src/cpea及payload/evaluations的本地絕對Python imports已做靜態檔案閉合檢查，缺失0；沒有執行imports、Pipeline、測試或模型。
- Task／handoff／raw內歷史原路徑保持作來源資料；主文使用包內路徑，不要求回原工作站取得本文引用檔案。
- 本包是審查材料，不是全部歷史實驗的環境備份；包含完整核心與本文所有引用，不包含憑證或未完成活動檔案。
- 歷史38題Gate與root尚未通過；離線PASS、單樣本機器裁決、整輪語意驗收與自然端到端分開標示。
