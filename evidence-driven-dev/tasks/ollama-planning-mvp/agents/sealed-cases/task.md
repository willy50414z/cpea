---
{
  "parent_task": "ollama-planning-mvp",
  "agent_id": "sealed-cases",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
  "assignment": "獨立撰寫MVP2十題與完整Gate八題封存控制；不讀模型回答、不修改產品",
  "allowed_scope": [
    "evidence-driven-dev/tasks/ollama-planning-mvp/agents/sealed-cases"
  ],
  "worktree": "/home/willy/code/cpea_terms",
  "platform_id": "/root/sealed_cases",
  "handoff": {
    "schema_version": 1,
    "author": "sealed-cases (/root/sealed_cases)",
    "created_at": "2026-10-20T12:50:41.859866+00:00",
    "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
    "contract_fingerprint": "e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc",
    "files": {
      "mvp2-cases.jsonl": {
        "sha256": "05911e0cca424156860522475140f00bc0e462b034945211c4bf6275b1b3f043",
        "count": 10,
        "ready_count": 7,
        "negative_count": 3,
        "visibility": "開發執行前獨立審核"
      },
      "gate-sealed.jsonl": {
        "sha256": "e9a2ed4d886708b06692ed45634afed7459ccefc8ab7afb979af72e8ea166f69",
        "count": 8,
        "ready_count": 6,
        "negative_count": 2,
        "visibility": "封存；實作／prompt／schema／rules 版本凍結後揭露"
      }
    },
    "design_constraints": [
      "作者未參與產品開發；未讀任何模型回答、raw 或 result",
      "MVP2 與 Gate 題目集合互斥且不與原 30 題題文相同",
      "MVP2 固定 7 正 3 負，七個 View 均涵蓋；至少四題由此獨立作者撰寫並在模型執行前封存",
      "Gate 固定 6 正 2 負，包含 source／母體最小反轉、空集合、快照日期與 child 形狀",
      "Gate 題文／oracle 不送入主 agent 訊息，版本凍結後才揭露；揭露後不再宣稱未見",
      "所有 review_status=pending；作者自檢不等於獨立語意核准，正式 Gate 先另行審核",
      "不要求跨不同盤點日期加總 stock_qty；合法同日聚合必須保留日期維度／child",
      "零模型、零網路、零 SQL／DB；不修改產品、原 oracle 或原結果"
    ],
    "verification": {
      "status": "PASS_AUTHOR_SELF_CHECK_ONLY",
      "verified_at": "2026-10-20T12:52:07.870075+00:00",
      "command": ".venv/bin/python，唯讀載入本地 catalog／case loader／DecompositionDraft／validate_decomposition／prepare_requests；逐欄比對 payload JSON，未呼叫模型 SDK、SQL 或 DB",
      "results": {
        "mvp2-cases.jsonl": {
          "case_schema": "PASS",
          "reference_plan_schema": "PASS",
          "catalog_and_validation": "PASS",
          "payload_exact_typed_content": "PASS",
          "utf8_no_bom_lf": "PASS",
          "sha256_verified": true
        },
        "gate-sealed.jsonl": {
          "case_schema": "PASS",
          "reference_plan_schema": "PASS",
          "catalog_and_validation": "PASS",
          "payload_exact_typed_content": "PASS",
          "utf8_no_bom_lf": "PASS",
          "sha256_verified": true
        }
      },
      "case_id_and_request_unique_against_original_30": true,
      "mvp2_source_coverage": 7,
      "oracle_review": "PENDING_INDEPENDENT_REVIEW",
      "initial_environment_issue": "系統 python3 缺少 pydantic；改用專案現有 .venv/bin/python，未安裝或改動依賴。",
      "model_calls": 0,
      "network_calls": 0,
      "sql_db_calls": 0
    },
    "contract_resources": {
      "projects/retail/manifest.yaml": "42684d67c86ed0329abd67c59f3c6af9f6a724311c918dbedd125133f17f6b49",
      "projects/retail/catalog.yaml": "380d48cf75ee3d0afae72f6b69abf764318badd6051f7080a7bfe9f582608666",
      "projects/retail/views/demo_retail/v_customer_value.yaml": "d3ef37ced4521ef46a65980f418088683c4aefa9f138802a6829f87fb531f2cc",
      "projects/retail/views/demo_retail/v_daily_sales.yaml": "e2402ebcebfa7e2bbf46b9e5c4319a32b9a0522883ba7182ba7ccc17ab030fd4",
      "projects/retail/views/demo_retail/v_inventory_status.yaml": "ed7c44ef1fca1b55f92454fbbcc2b3145acd6dea0a4ca17f46c2a08d90cb58b3",
      "projects/retail/views/demo_retail/v_order_summary.yaml": "fbe7eecd74125611e506cadec1a8ab975f6f7065c470a2d90b3f5fda88ae062c",
      "projects/retail/views/demo_retail/v_product_monthly.yaml": "619b4180f877d9628eb458dd3fc0a1348d8849132aea7bbd684ac46e69870079",
      "projects/retail/views/demo_retail/v_sales_detail.yaml": "c0381bd2ab84330dd24a6e138350065d4cc1a40c4856295f0ecfd9a359d5048f",
      "projects/retail/views/demo_retail/v_store_monthly_kpi.yaml": "ca167e431f2a7faa502378c8dc89cec3e65cf27a8fc375adb512f61dfd84e7eb"
    },
    "status": "DONE_WITH_CONCERNS",
    "summary": "獨立新增並封存 MVP2 十題（7正3負）與 Gate 八題（6正2負）；18 題 reference plan 與 prepared request 離線契約驗證通過。所有語意 oracle 維持 pending，需獨立審核。",
    "evidence": [
      "agents/sealed-cases/mvp2-cases.jsonl",
      "agents/sealed-cases/gate-sealed.jsonl",
      "agents/sealed-cases/manifest.json"
    ],
    "risks": [
      "作者自檢不代表獨立語意核准；全部 review_status=pending，不可據此宣告正式 Gate 通過。",
      "Gate 內容尚未交給主 Agent；凍結版本後揭露並由獨立 reviewer 審核，揭露後不可再宣稱未見。",
      "既有 validator 與 prepare_requests 通過僅代表本地結構與 request 準備，不代表語意完整或 SQL API 已接受。",
      "來源等價需逐題契約依據審核；不得因自動分不符就修改原 oracle 或放寬業務條件。"
    ],
    "next_step": "先獨立審核 MVP2；主 Agent 完成方法開發且凍結 prompt／schema／rules／catalog／harness 指紋後才揭露 Gate 並核准 oracle；固定版本各跑兩輪 38 題，兩輪 first-pass 均需 38/38，DeepSeek 通過前不呼叫 Ollama。",
    "diff_reference": {
      "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
      "scope": "evidence-driven-dev/tasks/ollama-planning-mvp/agents/sealed-cases",
      "new_artifacts": [
        "mvp2-cases.jsonl",
        "gate-sealed.jsonl",
        "manifest.json"
      ],
      "modified_artifacts": [
        "task.md"
      ],
      "product_and_original_oracle": "UNCHANGED"
    }
  },
  "blockers": [],
  "question": null
}
---
# 獨立案例封存任務

已使用 EDD 的子 Agent Handoff 流程；只寫本 Agent 專屬目錄。

## 工作範圍

獨立建立 MVP2 十題與 Gate 八題，補足來源、欄位角色、條件、根與子粒度、母體、準備形狀、缺值政策及 request 不變量的語意 oracle。未讀取模型回答／raw／result，未修改產品、原 oracle 或任何既有結果。

## 已完成

- `mvp2-cases.jsonl`：10 題，7 正、3 負，涵蓋七個來源。供正式執行前獨立審核。
- `gate-sealed.jsonl`：8 題，6 正、2 負。未向主 Agent 傳送題文或答案；僅回報數量、檔案路徑及 SHA256。
- `manifest.json`：作者、建立時間、設計限制、檔案與契約 SHA256、離線驗證結果及 Handoff。

## 驗證

18 題通過原 case loader、catalog 欄位／聚合檢查、DecompositionDraft 型別、validate_decomposition 與 prepare_requests。逐項比對 prepared payload 的型別欄位，所有條件／度量／metadata／粒度完整，負例不輸出 prepared requests，UTF-8 無 BOM、LF。原 30 題與新 18 題的 ID／題文皆不重複；MVP2 七來源覆蓋。

初次系統 python3 缺少 pydantic，隨後改用現有 `.venv/bin/python` 完成驗證，沒有安裝或修改依賴。零模型、零網路、零 SQL／DB。

## 限制與交接

全部 review_status 維持 pending；作者自檢不是獨立語意核准，不代表模型或 SQL API 已通過。Gate 需待 prompt、schema、規則、catalog、harness 指紋凍結後才揭露並獨立核准；揭露後不得再稱未見。未對主 Task 或其他 Agent 檔案寫入。
