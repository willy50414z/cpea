---
{
  "parent_task": "wrenai-semantic-decomposition",
  "agent_id": "cpea_boundary",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "ab4c67a45fa7039379bcadd788af0ae83bb3630f",
  "assignment": "CPEA結構MDL、JSONL父client、workflow及service與focused測試",
  "allowed_scope": [
    "src/cpea,tests/unit/test_wrenai_schema_adapter.py,tests/unit/test_wrenai_protocol.py,tests/unit/test_wrenai_workflow.py,tests/integration/test_wrenai_worker.py"
  ],
  "worktree": "/home/willy/code/cpea-wrenai",
  "platform_id": "/root/cpea_boundary",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "完成父端結構 MDL／JSONL client／獨立 workflow/service；依 fresh review B-R1/B-R2 修正重複終態停用及 backpressure 外部取消，32 focused 與原獨立 probe 全部通過，等待 final reviewer 驗收。",
    "evidence": [
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/focused-tests.log",
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/review-fix-red-tests.log",
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/review-fix-red-probes.log",
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/review-fix-green-focused.log",
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/review-fix-green-probes.log",
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/.local/review-probe.py"
    ],
    "changes": [
      "真 retail 七 View／102 欄位投影；m_ 加 UTF-8 hex 可逆且拒重名；NUMERIC/VARCHAR/DATE/BOOLEAN；無假 primaryKey、無額外字典或 memory；完整原始 policy 深拷貝。",
      "manifest identity 納 catalog/adapter/upstream/patch/lock/embedding provider/model/dimension，非空 project_id 與 namespace。",
      "startup metadata/import root 驗證；accepted/running/terminal ID 關聯；terminal 恰一；late events 原始 IDs 落盤；stdout/stderr 並行 drain、bounded line/payload/queue、partial stdin write/flush、timeout/cancel grace/terminate/kill/reap、重新使用前回收。",
      "外部 cancel(run_id)；私有 0700/0600 raw/lifecycle artifacts，持久化時間/容量限制；固定 error-code allowlist，message 不外露；Oracle 頂層 keys 禁止傳送。",
      "父端唯一 DecompositionDraft JSON schema 傳入 worker，回傳 Draft 使用既有 validator 與 prepare_requests；non-ready/malformed 無 prepared；沒有 fallback。",
      "B-R1：送出下一個 run 前排空 pending 事件；重複 terminal 記固定 duplicate_terminal diagnostic，保留原 run 恰一 terminal，拒絕該次呼叫並 terminate/kill/reap 違規 worker。合法 late 非終態依舊封存原 ID；之後顯式新 run 使用新 PID，不自動重送。",
      "B-R2：_send 等待 stdin write/flush 時每 20ms 同步檢查該 run 取消旗標；取消進入既有 grace/terminate/kill/reap，回 worker_cancelled；沒有回覆則 run terminal=unknown_outcome，保留可能已送出的事實。"
    ],
    "tests": {
      "command": "PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_wrenai_schema_adapter.py tests/unit/test_wrenai_protocol.py tests/unit/test_wrenai_workflow.py tests/integration/test_wrenai_worker.py -q",
      "result": "32 passed in 2.91s",
      "exit_code": 0,
      "tdd": "各批先新增測試並觀察 missing-module／missing cancel API／oracle allowlist／noncanonical JSON／lifecycle/error-code 測試失敗，再實作並轉綠；首輪紅燈保留於平台工具輸出，final raw 在 focused-tests.log。；fresh review 修正先改 duplicate-terminal 錯誤預期、加入 default timeout=120 的 blocked-send cancel 測試，保存 2 failed / 1 passed，原 probe 兩項 FAIL；實作後 32 passed 且 probe 三項 PASS。"
    },
    "interfaces": {
      "service": "WrenAIDecompositionService(client,catalog).plan(request,*,run_id=None,case_id=None)",
      "workflow": "WrenAIDecompositionWorkflow(client,catalog).plan()/invoke()",
      "client": "WrenAIWorkerClient(command,*,expected_metadata,expected_import_root,artifact_root,timeout=120,cancel_grace=2,terminate_grace=2,max_line_bytes=4MiB,max_payload_bytes=2MiB,max_queue=128,env=None).plan(request=...,run_id=...,case_id=...,catalog_fingerprint=...,schema=...,response_schema=...)",
      "native_sync": "已與 native_worker 確認 import_sources 僅列 pinned checkout 原生 modules、共同 handshake metadata 及 case_id/error-code 契約。"
    },
    "risks": [
      "30 項父端測試中的 subprocess 是可控 Python worker fixture，只驗生命週期；不能據此宣稱 pinned WrenAI + Qdrant 自然整體已通過，該證據由 native_worker 提供並由 Main/fresh reviewer 整合。",
      "兩舊 flow 113 focused regression 依 Main 最新指示留到所有產品檔完成後統一執行。",
      "共用 .venv editable 仍指向 /home/willy/code/cpea_terms；本次全部有效驗證顯式 PYTHONPATH=src，後續測試亦須設定。",
      "真模型能力未驗證；正式題庫／真模型資源不在授權範圍。"
    ],
    "next_step": "Main 重新整合本 handoff 後，交 final fresh reviewer 重跑 focused 及原 review probe，並統一執行 native graph／兩舊 flow regression；無需變更已核准 spec。",
    "diff_reference": {
      "base_git_sha": "ab4c67a45fa7039379bcadd788af0ae83bb3630f",
      "files": [
        "src/cpea/application/services/wrenai_decomposition.py",
        "src/cpea/workflows/task_decomposition/wrenai_schema.py",
        "src/cpea/workflows/task_decomposition/wrenai_protocol.py",
        "src/cpea/workflows/task_decomposition/wrenai_client.py",
        "src/cpea/workflows/task_decomposition/wrenai_workflow.py",
        "tests/unit/test_wrenai_schema_adapter.py",
        "tests/unit/test_wrenai_protocol.py",
        "tests/unit/test_wrenai_workflow.py",
        "tests/integration/test_wrenai_worker.py"
      ],
      "sha256": {
        "src/cpea/application/services/wrenai_decomposition.py": "b6a6efb52f03632268b527f72f3ecfbe6d67881d89fbe2573c805f940267a3d7",
        "src/cpea/workflows/task_decomposition/wrenai_schema.py": "b9eed16b07057d56ef5fba3f8fe37b2b3ab11d44c0d0561d4640eec9e5099e20",
        "src/cpea/workflows/task_decomposition/wrenai_protocol.py": "8a9f709589bf8427458751426974fd67948962403b002c67abdb74ecf239e3a6",
        "src/cpea/workflows/task_decomposition/wrenai_client.py": "baa40e440fef2dafa2a0a98b964004e47e3b5c312ae3de95d7684e1a59856372",
        "src/cpea/workflows/task_decomposition/wrenai_workflow.py": "783977133be46ac63b7b7967cf73ed93f7b4911657f04cae7ab5c19efc654320",
        "tests/unit/test_wrenai_schema_adapter.py": "8b14f8830405b0986c36df2bda7afac4277494f89feb9e605845971c9760fdfb",
        "tests/unit/test_wrenai_protocol.py": "9ede6e37a86bb00ce288a6d4b054c866c6a8788a75d82c0a5c654228b53b81bf",
        "tests/unit/test_wrenai_workflow.py": "1bc5432c12286b15a3a1201c59fd8d4f88c8f10401da672e5b350924efc5b82a",
        "tests/integration/test_wrenai_worker.py": "01fdd621101188c47f5d188b058701a5bbe6bc0a113618cfc82ae43c4b1edb5d"
      },
      "commit": "未 commit／push"
    },
    "review_resolution": {
      "B-R1": {
        "red": "重複 terminal 後第二個 run 沒有拋錯且沿用 PID；已保存原反例。",
        "green": "拋 duplicate_terminal、第二 run states=[error]，舊 worker 已 reap；第三個顯式 run 成功且新 PID；合法 late running 仍保留原 IDs 並沿用健康 worker。"
      },
      "B-R2": {
        "red": "取消 accepted=true，仍等 1.613 秒回 worker_timeout；default120 測試 .5 秒未結束。",
        "green": "原 probe 取消後 .127 秒回 worker_cancelled、全部 pipe threads 結束且已 reap；新增 default timeout=120 的 regression 同樣 <.5 秒。"
      },
      "unchanged_teardown_probe": "timeout=.25 的 ignored-SIGTERM child 於 .407 秒完成 kill/reap，worker_timeout 正確保留。",
      "probe_integrity": {
        "source": "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/boundary_review/.local/probe.py",
        "executed_copy": "evidence-driven-dev/tasks/wrenai-semantic-decomposition/agents/cpea_boundary/.local/review-probe.py",
        "sha256": "ca3a0b12a693507c08adc6ba8cc3cd6e0793400416ccd3ccc58c949d7e91806d",
        "reviewer_files": "唯讀，未修改；執行同內容副本使 probe 的 temp artifacts 僅落自己目錄。"
      },
      "approval": "尚待 Main 安排 final fresh reviewer；本 handoff 只陳述修正與已執行證據。"
    }
  },
  "blockers": [],
  "question": null
}
---
# Subagent 任務

禁止修改主 task.md、其他 Agent 紀錄、驗收標準或擴大範圍。

## 任務

## 允許範圍

## 禁止事項

## 輸入

## 調查

## 假設

## 實驗

## 發現

## 變更檔案

## 待釐清問題

## Handoff
