---
{
  "parent_task": "wrenai-semantic-decomposition",
  "agent_id": "evaluator",
  "role": "subagent",
  "status": "DONE",
  "base_git_sha": "ab4c67a45fa7039379bcadd788af0ae83bb3630f",
  "assignment": "依整合規格實作題庫載入、node oracle mutation、真graph重播及零模型評估runner",
  "allowed_scope": [
    "evaluations/wrenai_cases.py,evaluations/wrenai_oracles.py,evaluations/wrenai_replay.py,evaluations/wrenai_runner.py,tests/unit/test_wrenai_node_oracles.py,tests/unit/test_wrenai_replay.py,tests/integration/test_wrenai_evaluation.py"
  ],
  "worktree": "/home/willy/code/cpea-wrenai",
  "platform_id": "/root/evaluator",
  "handoff": {
    "status": "DONE",
    "summary": "已完成evaluator-only核准題庫載入、node/semantic不變量、private artifacts、零模型regrade、真native graph replay與離線CLI；最終固定patch的63項測試全通過，無skip。",
    "evidence": {
      "focused_command": "env PYTHONPATH=/home/willy/code/cpea-wrenai/src WRENAI_OFFLINE_RECORDING=/home/willy/code/cpea-wrenai/integrations/wrenai/.runtime/test-recording-8d2b6eea2ecd4498991639a757c083b3/runs/300a607946a88880ad74dcdee3faa6342684e0aaaec9400a243b97afae2f41db .venv/bin/python -m pytest tests/unit/test_wrenai_node_oracles.py tests/unit/test_wrenai_replay.py tests/integration/test_wrenai_evaluation.py -q",
      "focused_result": "63 passed in 16.70s; exit_code=0; zero skips",
      "red_logs": [
        "/tmp/wrenai-evaluator-red.log",
        "/tmp/wrenai-replay-red.log",
        "/tmp/wrenai-evaluator-request-red.log",
        "/tmp/wrenai-evaluator-intent-red.log",
        "/tmp/wrenai-evaluator-policy-red.log",
        "/tmp/wrenai-evaluator-status-red.log",
        "/tmp/wrenai-evaluator-resolver-red.log",
        "/tmp/wrenai-evaluator-offline-red.log",
        "/tmp/wrenai-evaluator-oracle-red.log",
        "/tmp/wrenai-evaluator-review-red.log",
        "/tmp/wrenai-evaluator-allow-drift-red.log",
        "/tmp/wrenai-evaluator-preparation-red.log",
        "/tmp/wrenai-evaluator-ledger-red.log"
      ],
      "independent_holdout": "D獨立7個policy反例/合法等價句已通過，agents/final_verifier/.local/oracle-holdout-pre-freeze.log",
      "native_regrade": "固定customer_id獨立synthetic oracle：intent/raw_selection/rendered_columns各自PASS；pricing unknown維持cost_complete=false/spend=null。",
      "focused_log": "/tmp/wrenai-evaluator-final-green.log",
      "native_recording": "/home/willy/code/cpea-wrenai/integrations/wrenai/.runtime/test-recording-8d2b6eea2ecd4498991639a757c083b3/runs/300a607946a88880ad74dcdee3faa6342684e0aaaec9400a243b97afae2f41db",
      "native_patch_sha": "a326aee5256928ba52b5dfc3b789bcaa93be3603a43dd35268ead844fe3a7f50",
      "native_replay": "錄製completion及document/query embedding+匹配snapshot，重跑真pinned workergraph/new localQdrant，產生新run_dir且Draft與原始輸出一致，全部calls精確消耗；loopback-only由native seam執行。",
      "final_review_red_log": "/tmp/wrenai-evaluator-final-review-red.log",
      "file_sha256": {
        "evaluations/wrenai_cases.py": "93bfa165fcfc30258d02776bf72e9cc8fb34ed45e39e1a299d49b4e2a048c426",
        "evaluations/wrenai_oracles.py": "06aa31b8a0b85565f3098c0251ff47e1a1031c38f35849df27c74ea0f33064b3",
        "evaluations/wrenai_replay.py": "050c05c53a24b7d02f2b50401e547b7f5725aeabb45df34cff9baa7c0e491088",
        "evaluations/wrenai_runner.py": "a426a01978dc42a428030451b3da02f54b19460eabd41c7f30a5a80fe98ce718",
        "tests/unit/test_wrenai_node_oracles.py": "57d563984873a0359cc16187205980a2e551500284c8edfb73493499f4691503",
        "tests/unit/test_wrenai_replay.py": "23b261caf53809da16b2ee17f9684a5040a4d86eb6a90d5d4d095e3fe6999d96",
        "tests/integration/test_wrenai_evaluation.py": "295a5546005da21313fc1a773d3faccdb0bef81333d675dfaaa6687682e4eb2c"
      }
    },
    "risks": [
      "正式題庫由使用者另備，本次只有標示fake的transport fixtures；不證明真模型語意品質、實際費用或latency。",
      "null policy採有界中英行為條款語法；未知句子保守FAIL，額外等價政策可由核准oracle明列；自由notes/reasoning不做文字精確比對。",
      "完整CPEA regression由Main/D的統一driver驗證，本agent未重跑先前113baseline；沒有真模型/SQL/業務DB呼叫，沒有commit/push。"
    ],
    "next_step": "Main/獨立驗證者執行唯一統一驗收driver與舊focused regression；C產品已freeze，不再修改。",
    "diff_reference": [
      "evaluations/wrenai_cases.py",
      "evaluations/wrenai_oracles.py",
      "evaluations/wrenai_replay.py",
      "evaluations/wrenai_runner.py",
      "tests/unit/test_wrenai_node_oracles.py",
      "tests/unit/test_wrenai_replay.py",
      "tests/integration/test_wrenai_evaluation.py"
    ],
    "changes": [
      "13項required runtime identity（含configuration_sha256），drift預設拒絕；allow_drift強制exact_reproduction=false。",
      "native raw node artifacts優先於response.nodes，防舊快照掩蓋retrieval drift。",
      "ready相容舊loader/grader，strict extra measure/conditional measure/source filters/background preparation/anchor/preserve/cardinality/null invariants；prepared payload須與既有prepare結果一致。",
      "nonready案例不套ready tasks/integration；Oracle keys不入model_input或recorded graph input。",
      "每call attempt/fingerprint/run/case與完整ledger對帳；unknown費用不填零；private artifact目錄0700/檔0600，CLI只輸出allowlist摘要。"
    ]
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
