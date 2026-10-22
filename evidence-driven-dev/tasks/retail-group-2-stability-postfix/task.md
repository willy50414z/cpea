---
{
  "schema_version": 1,
  "id": "retail-group-2-stability-postfix",
  "type": "research",
  "complexity": "moderate",
  "status": "CANCELLED",
  "phase": "CANCELLED",
  "owner": "main-agent",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "branch": "feat/progressive-view-retrieval",
  "worktree": "/home/willy/code/cpea",
  "openspec_change": null,
  "updated_at": "2026-10-21T04:01:49+00:00",
  "goal": "修復後group2固定30題各3次完整真實模型穩定性重測，原Oracle評分並比較原48/90",
  "problem": {
    "description": "使用者要求修復後穩定性測試，原group2為30題三次48/90；修復C僅6題混合節點6/6",
    "expected": "完成同一固定30題各3次完整真實模型查詢，忠實呈現正確率與一致性",
    "actual": "最終修復後的90次完整重測尚未執行",
    "evidence": [
      "../retail-test-group-2/final-report.md",
      "../fix-retail-group-2/final-report.md"
    ],
    "hypotheses": [
      {
        "id": "H-STABILITY",
        "claim": "固定來源、模型與測量契約可獲得可比的90次完整三次重測結果",
        "status": "UNCONFIRMED",
        "evidence": []
      }
    ]
  },
  "scope": [
    "evidence-driven-dev/tasks/retail-group-2-stability-postfix"
  ],
  "constraints": [
    "不改產品、題庫、Oracle、群組、契約或原結果",
    "真實生成，不使用回放、cache或自動HILP代選；每次空白隔離詞彙檔",
    "沿用原模型、digest、temperature0/seed42/context16000/output8192與PostgreSQL；不執行DB或正式核准",
    "逐一序列執行；provider錯誤保存後停止新呼叫，檢查後僅接續未做tuple，不重試失敗tuple；rate limit依account-switch處理"
  ],
  "acceptance": [
    {
      "id": "A1",
      "description": "固定30題×3共90個唯一tuple，每次完整真實生成，原輸入版本與模型不變",
      "status": "PENDING",
      "evidence": []
    },
    {
      "id": "A2",
      "description": "原Oracle逐筆重評，列出每題三次正確率、狀態/SQL一致性及原48/90比較",
      "status": "PENDING",
      "evidence": []
    },
    {
      "id": "A3",
      "description": "測量可追溯，保存所有失敗、calls、結果、成本與未驗證限制，不混入前序回放",
      "status": "PENDING",
      "evidence": []
    }
  ],
  "progress": [
    {
      "summary": "群組與原測量設定已讀取，準備離線及模型身分核對",
      "status": "IN_PROGRESS"
    }
  ],
  "agents": [],
  "experiments": [
    {
      "id": "EXP-001",
      "hypothesis_id": "H-STABILITY"
    }
  ],
  "decisions": [
    {
      "id": "DEC-001",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "依使用者要求完整重跑group2 30×3，不使用混合回放",
      "alternatives": [
        "只跑6題或14失敗題不足以測回歸，不採用"
      ],
      "reason": "使用者於修復後明確要求跑穩定性測試，沿用原完整群組與測量參數",
      "risks": "可能耗時數小時且仍有歧義/Oracle失敗；無DB、draft待核准",
      "revisit": "provider錯誤或版本改變時保存狀態並先診斷，不盲目重試",
      "references": [],
      "at": "2026-10-21T01:32:50+00:00"
    },
    {
      "id": "DEC-002",
      "source": "user",
      "question_id": "Q-001",
      "summary": "恢復測試，接續原程序且保留26個已完成tuple",
      "evidence": "本回合使用者明確訊息：繼續測試。恢復前已核對26筆原Oracle結果、資料/來源/模型digest不變；原runner socket有118534 bytes已收資料，優先保留在途回應，不重跑tuple。",
      "at": "2026-10-21T03:45:54+00:00"
    }
  ],
  "questions": [
    {
      "question_id": "Q-001",
      "source_agent": "main-agent",
      "question": "依使用者要求暫停，等待後續明確恢復指示",
      "context": "使用者：先暫停測試,並回報目前結果。已SIGSTOP原EDD與runner；26/90結果已封存，原Oracle於fresh subprocess逐筆核對通過（evidence/EV-20261021T033328-a40fca50.json），未自動重試或恢復。",
      "options": [],
      "recommendation": "維持使用者要求的暫停狀態",
      "impact": "保持暫停直到使用者要求恢復；恢復前核對在途請求、socket及版本，避免重複tuple。",
      "status": "ANSWERED",
      "answer": "恢復測試，接續原程序且保留26個已完成tuple",
      "answer_evidence": "本回合使用者明確訊息：繼續測試。恢復前已核對26筆原Oracle結果、資料/來源/模型digest不變；原runner socket有118534 bytes已收資料，優先保留在途回應，不重跑tuple。"
    }
  ],
  "blockers": [],
  "waiting": null,
  "paused_from": null,
  "checkpoint": {
    "last_completed": "本輪28/90（9通過19失敗）、237 calls，03:50:55 UTC因300秒ReadTimeout退出，失敗與證據已封存；目前ollama ps確認100% CPU",
    "current_action": "使用者要求停止；原PID皆不存在，未重啟測試或共享Ollama服務",
    "next_action": "不再接續；後續若需重測，先確認GPU與image/模型/參數，另立環境凍結的新測量，不將此中止測量當完整穩定性",
    "required_inputs": [],
    "unresolved_questions": []
  },
  "plan": {
    "solutions": [
      {
        "hypothesis": "H-STABILITY",
        "root_cause": "前輪修復只有混合節點驗證，尚無最終版完整三次測量",
        "scope": [
          "本Task記錄"
        ],
        "cost": "預計數小時真實模型查詢",
        "verification": "凍結雜湊、90唯一tuple、原Oracle逐筆重評、模型digest前後一致",
        "falsification": "重複tuple、回放混入、輸入或版本改變、原Oracle評分與紀錄不符",
        "rollback": "只新增私有產物，原測量與產品保持",
        "id": "S",
        "benefit": "完整30題三次，和原測量相同範圍",
        "complexity": "低",
        "risks": "仍可能存在原需求歧義/Oracle失敗；provider timeout需先診斷並保留，不重試既有tuple"
      },
      {
        "hypothesis": "H-STABILITY",
        "root_cause": "前輪修復只有混合節點驗證，尚無最終版完整三次測量",
        "scope": [
          "本Task記錄"
        ],
        "cost": "預計數小時真實模型查詢",
        "verification": "凍結雜湊、90唯一tuple、原Oracle逐筆重評、模型digest前後一致",
        "falsification": "重複tuple、回放混入、輸入或版本改變、原Oracle評分與紀錄不符",
        "rollback": "只新增私有產物，原測量與產品保持",
        "id": "M",
        "benefit": "只測原失敗題較省時，但無法檢查原通過題回歸，不採用",
        "complexity": "低",
        "risks": "仍可能存在原需求歧義/Oracle失敗；provider timeout需先診斷並保留，不重試既有tuple"
      }
    ],
    "selected_solution": "S",
    "success": "90tuple完整且可追溯，不以全部產品通過作為測量完整性的條件",
    "failure": "來源/Oracle/模型變更、重複或遺漏tuple、回放混入",
    "regression": [
      "原Oracle90筆重評",
      "原測量與輸入雜湊不變",
      "版本、模型與測試程序核對"
    ],
    "approval_required": false
  },
  "changes": {},
  "verification": {},
  "completion_summary": "",
  "history": [
    {
      "from": null,
      "to": "CREATED",
      "at": "2026-10-21T01:31:59+00:00",
      "reason": "初始化"
    },
    {
      "from": "CREATED",
      "to": "INVESTIGATING",
      "at": "2026-10-21T01:32:40+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "INVESTIGATING",
      "to": "PLANNING",
      "at": "2026-10-21T01:32:40+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "PLANNING",
      "to": "EXPERIMENTING",
      "at": "2026-10-21T01:32:50+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "EXPERIMENTING",
      "to": "IMPLEMENTING",
      "at": "2026-10-21T01:33:31+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "IMPLEMENTING",
      "to": "WAITING_USER",
      "at": "2026-10-21T03:34:00+00:00",
      "reason": "Q-001",
      "paused_from": "IMPLEMENTING"
    },
    {
      "from": "WAITING_USER",
      "to": "IMPLEMENTING",
      "at": "2026-10-21T03:45:54+00:00",
      "reason": "使用者已回答 Q-001",
      "paused_from": "IMPLEMENTING"
    },
    {
      "from": "IMPLEMENTING",
      "to": "CANCELLED",
      "at": "2026-10-21T04:01:49+00:00",
      "reason": "使用者明確要求停止測試；28次部分結果保留，Ollama image變動與目前CPU執行已記錄",
      "paused_from": null
    }
  ]
}
---
# 任務：retail-group-2-stability-postfix

## 目標

修復後group2固定30題各3次完整真實模型穩定性重測，原Oracle評分並比較原48/90

## 問題定義（預期／實際／證據／未確認假設）

{
  "description": "使用者要求修復後穩定性測試，原group2為30題三次48/90；修復C僅6題混合節點6/6",
  "expected": "完成同一固定30題各3次完整真實模型查詢，忠實呈現正確率與一致性",
  "actual": "最終修復後的90次完整重測尚未執行",
  "evidence": [
    "../retail-test-group-2/final-report.md",
    "../fix-retail-group-2/final-report.md"
  ],
  "hypotheses": [
    {
      "id": "H-STABILITY",
      "claim": "固定來源、模型與測量契約可獲得可比的90次完整三次重測結果",
      "status": "UNCONFIRMED",
      "evidence": []
    }
  ]
}

## 範圍

- evidence-driven-dev/tasks/retail-group-2-stability-postfix

## 限制

[
  "不改產品、題庫、Oracle、群組、契約或原結果",
  "真實生成，不使用回放、cache或自動HILP代選；每次空白隔離詞彙檔",
  "沿用原模型、digest、temperature0/seed42/context16000/output8192與PostgreSQL；不執行DB或正式核准",
  "逐一序列執行；provider錯誤保存後停止新呼叫，檢查後僅接續未做tuple，不重試失敗tuple；rate limit依account-switch處理"
]

## 驗收標準

[
  {
    "id": "A1",
    "description": "固定30題×3共90個唯一tuple，每次完整真實生成，原輸入版本與模型不變",
    "status": "PENDING",
    "evidence": []
  },
  {
    "id": "A2",
    "description": "原Oracle逐筆重評，列出每題三次正確率、狀態/SQL一致性及原48/90比較",
    "status": "PENDING",
    "evidence": []
  },
  {
    "id": "A3",
    "description": "測量可追溯，保存所有失敗、calls、結果、成本與未驗證限制，不混入前序回放",
    "status": "PENDING",
    "evidence": []
  }
]

## 工作進度

[
  {
    "summary": "群組與原測量設定已讀取，準備離線及模型身分核對",
    "status": "IN_PROGRESS"
  }
]

## Subagent Registry

[]

## 實驗

[
  {
    "id": "EXP-001",
    "hypothesis_id": "H-STABILITY"
  }
]

## 決策

詳見 [decisions.md](decisions.md)。
[
  {
    "id": "DEC-001",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "依使用者要求完整重跑group2 30×3，不使用混合回放",
    "alternatives": [
      "只跑6題或14失敗題不足以測回歸，不採用"
    ],
    "reason": "使用者於修復後明確要求跑穩定性測試，沿用原完整群組與測量參數",
    "risks": "可能耗時數小時且仍有歧義/Oracle失敗；無DB、draft待核准",
    "revisit": "provider錯誤或版本改變時保存狀態並先診斷，不盲目重試",
    "references": [],
    "at": "2026-10-21T01:32:50+00:00"
  },
  {
    "id": "DEC-002",
    "source": "user",
    "question_id": "Q-001",
    "summary": "恢復測試，接續原程序且保留26個已完成tuple",
    "evidence": "本回合使用者明確訊息：繼續測試。恢復前已核對26筆原Oracle結果、資料/來源/模型digest不變；原runner socket有118534 bytes已收資料，優先保留在途回應，不重跑tuple。",
    "at": "2026-10-21T03:45:54+00:00"
  }
]

## 待使用者回答問題

[
  {
    "question_id": "Q-001",
    "source_agent": "main-agent",
    "question": "依使用者要求暫停，等待後續明確恢復指示",
    "context": "使用者：先暫停測試,並回報目前結果。已SIGSTOP原EDD與runner；26/90結果已封存，原Oracle於fresh subprocess逐筆核對通過（evidence/EV-20261021T033328-a40fca50.json），未自動重試或恢復。",
    "options": [],
    "recommendation": "維持使用者要求的暫停狀態",
    "impact": "保持暫停直到使用者要求恢復；恢復前核對在途請求、socket及版本，避免重複tuple。",
    "status": "ANSWERED",
    "answer": "恢復測試，接續原程序且保留26個已完成tuple",
    "answer_evidence": "本回合使用者明確訊息：繼續測試。恢復前已核對26筆原Oracle結果、資料/來源/模型digest不變；原runner socket有118534 bytes已收資料，優先保留在途回應，不重跑tuple。"
  }
]

## 阻礙

[]

## Recovery Checkpoint

{
  "last_completed": "本輪28/90（9通過19失敗）、237 calls，03:50:55 UTC因300秒ReadTimeout退出，失敗與證據已封存；目前ollama ps確認100% CPU",
  "current_action": "使用者要求停止；原PID皆不存在，未重啟測試或共享Ollama服務",
  "next_action": "不再接續；後續若需重測，先確認GPU與image/模型/參數，另立環境凍結的新測量，不將此中止測量當完整穩定性",
  "required_inputs": [],
  "unresolved_questions": []
}

## 最終驗證

{}

## 完成摘要


