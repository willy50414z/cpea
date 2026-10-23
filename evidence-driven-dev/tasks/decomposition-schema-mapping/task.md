---
{
  "schema_version": 1,
  "id": "decomposition-schema-mapping",
  "type": "bugfix",
  "complexity": "moderate",
  "status": "COMPLETED",
  "phase": "COMPLETED",
  "owner": "main-agent",
  "base_git_sha": "095b6125623af5b9ade6914a6a83444e3d704b57",
  "branch": "feat/complex_req_test",
  "worktree": "/home/willy/code/cpea_terms",
  "openspec_change": null,
  "updated_at": "2026-10-23T06:55:37+00:00",
  "goal": "新增需求關鍵字逐 View 欄位證據對照與二次審核，據以產生 DecompositionDraft",
  "problem": {
    "description": "新增多來源需求詞到欄位證據 mapping 獨立入口",
    "expected": "需求抽取、逐 View 候選證據、全域審核及受核准來源限制的 DecompositionDraft",
    "actual": "既有流程一次 LLM 直接規劃，沒有 mapping 證據或二次審核",
    "evidence": [
      "src/cpea/workflows/task_decomposition/workflow.py",
      "相關四組基準 66 passed；使用者選獨立入口並同意 A"
    ],
    "hypotheses": [
      {
        "id": "H1",
        "claim": "新增獨立逐 View 比對與證據閉合審核，可在保留舊流程下提供可稽核 mapping",
        "status": "UNCONFIRMED"
      }
    ]
  },
  "scope": [
    "src/cpea/application/models/schema_mapping_decomposition.py",
    "src/cpea/application/services/schema_mapping_decomposition.py",
    "src/cpea/workflows/task_decomposition/",
    "tests/unit/test_schema_mapping_decomposition.py",
    "tests/schema_mapping_support.py",
    "docs/superpowers/"
  ],
  "constraints": [
    "保留原 workflow/service/validation/eval/tests 與使用者 prompt 修改",
    "不 commit/push、不呼叫真實模型或 DB",
    "UTF-8 無 BOM、保留換行"
  ],
  "acceptance": [
    {
      "id": "A1",
      "description": "原文spans、候選View每必要詞完整回覆、同欄同路徑引文真實",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261023T065342-b02c5d5b.json",
        "evidence/EV-20261023T065411-6e005928.json"
      ]
    },
    {
      "id": "A2",
      "description": "二次審核與Draft來源/操作allowlist、必要詞binding、期間/粒度/母體閉合",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261023T065342-b02c5d5b.json",
        "evidence/EV-20261023T065411-6e005928.json"
      ]
    },
    {
      "id": "A3",
      "description": "獨立service先檢索、C+3呼叫、錯誤早停與partial trace，舊66相關回歸及完整23既有失敗不變",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261023T065342-b02c5d5b.json",
        "evidence/EV-20261023T065411-6e005928.json"
      ]
    }
  ],
  "progress": [],
  "agents": [
    {
      "id": "mapping_research",
      "status": "DONE_WITH_CONCERNS",
      "report": "agents/mapping_research/task.md",
      "platform_id": "/root/mapping_research",
      "integrated": true,
      "disposition": "",
      "integrated_at": "2026-10-23T06:53:41+00:00"
    },
    {
      "id": "mapping_review",
      "status": "FAILED",
      "report": "agents/mapping_review/task.md",
      "platform_id": "/root/mapping_review",
      "integrated": true,
      "disposition": "原審查因模型capacity中止，已保存原輸出與not_quota_limit判讀；不當成成功，由fresh mapping_final_review接替完成全部驗收",
      "integrated_at": "2026-10-23T06:53:42+00:00"
    },
    {
      "id": "mapping_final_review",
      "status": "DONE_WITH_CONCERNS",
      "report": "agents/mapping_final_review/task.md",
      "platform_id": "/root/mapping_final_review",
      "integrated": true,
      "disposition": "",
      "integrated_at": "2026-10-23T06:53:42+00:00"
    }
  ],
  "experiments": [
    {
      "id": "EXP-001",
      "hypothesis_id": "H1"
    }
  ],
  "decisions": [
    {
      "id": "DEC-001",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "依使用者確認新增獨立入口，採 A 逐 View 需求候選證據與二次審核",
      "alternatives": [
        "B 完整逐詞逐欄矩陣",
        "替換原 task decomposition 預設流程"
      ],
      "reason": "使用者明確選擇獨立入口並於書面設計確認後回覆 A",
      "risks": "A 不保存全部拒絕組合；真實 LLM 語意仍需實測",
      "revisit": "使用者後續要求逐格拒絕稽核或整合既有預設流程時",
      "references": [
        "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
      ],
      "at": "2026-10-23T06:27:27+00:00"
    },
    {
      "id": "DEC-002",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "依使用者追加要求，在新入口最前端重用既有View檢索，再對候選執行A流程",
      "alternatives": [
        "繼續逐個比對完整catalog，不作前置篩選",
        "直接套用單View所有明列欄位交集"
      ],
      "reason": "使用者要求最前端View篩選以避免過多Views；研究者選擇僅移除檢索識別碼並補回原文明列來源，保留多來源能力",
      "risks": "soft top-k可能因ties或明列欄位owners增加；檢索召回與真實模型品質未實測",
      "revisit": "候選過多或實測發現缺少必要來源時",
      "references": [
        "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
      ],
      "at": "2026-10-23T06:44:43+00:00"
    }
  ],
  "questions": [],
  "blockers": [],
  "waiting": null,
  "paused_from": null,
  "checkpoint": {
    "last_completed": "173focused、獨立holdout/邊界/保護指紋/UTF8通過；完整773passed/23既有failed/1skipped，無新增失敗",
    "current_action": "Main已整合實作與fresh final review，EDD validate PASS",
    "next_action": "交付獨立入口與使用文件；真實模型語意與成本留待另行實測",
    "required_inputs": [],
    "unresolved_questions": []
  },
  "plan": {
    "solutions": [
      {
        "id": "A",
        "hypothesis": "H1",
        "root_cause": "現有 planner 缺少可稽核詞欄位證據鏈",
        "benefit": "逐 View 每詞候選與原文證據",
        "scope": "新增獨立入口，不改原流程",
        "complexity": "moderate",
        "cost": "V+3 次呼叫，稀疏候選輸出",
        "risks": "不保留每個拒絕組合；仍有語意漏判風險",
        "verification": "固定正反例、focused 與舊流程回歸",
        "falsification": "偽引文、遺漏詞或未核准欄位仍能 ready",
        "rollback": "不使用新入口即可保留原流程"
      },
      {
        "id": "B",
        "hypothesis": "H1",
        "root_cause": "現有 planner 缺少可稽核詞欄位證據鏈",
        "benefit": "完整需求乘欄位矩陣",
        "scope": "新增獨立入口，不改原流程",
        "complexity": "moderate",
        "cost": "依欄位分批再加3次，輸出成長較大",
        "risks": "較高成本與輸出超限風險，仍不證明語意正確",
        "verification": "固定正反例、focused 與舊流程回歸",
        "falsification": "偽引文、遺漏詞或未核准欄位仍能 ready",
        "rollback": "不使用新入口即可保留原流程"
      }
    ],
    "selected_solution": "A",
    "success": "新 focused 測試與原66項測試通過",
    "failure": "mapping證據或跨階段限制未閉合",
    "regression": [
      "新增三組schema_mapping測試",
      "原decomposition四組66項",
      "完整pytest比對23項既有失敗"
    ],
    "mvp": [
      "需求與候選驗證",
      "審核與Draft閉合",
      "獨立service完整流程"
    ],
    "approval_required": false,
    "approval_evidence": "使用者先選獨立入口，再回覆A，並補充continue",
    "document": "docs/superpowers/plans/2026-10-23-decomposition-schema-mapping.md"
  },
  "changes": {
    "scope": [
      "src/cpea/application/models/schema_mapping_decomposition.py",
      "src/cpea/application/services/schema_mapping_decomposition.py",
      "src/cpea/workflows/task_decomposition/mapping.py",
      "src/cpea/workflows/task_decomposition/mapping_models.py",
      "src/cpea/workflows/task_decomposition/mapping_prompts.py",
      "src/cpea/workflows/task_decomposition/mapping_retrieval.py",
      "src/cpea/workflows/task_decomposition/schema_mapping_workflow.py",
      "tests/schema_mapping_support.py",
      "tests/unit/test_schema_mapping_decomposition.py",
      "tests/unit/test_schema_mapping_retrieval.py",
      "tests/unit/test_schema_mapping_review.py",
      "tests/unit/test_schema_mapping_validation.py",
      "src/cpea/workflows/task_decomposition/README.md",
      "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md",
      "docs/superpowers/plans/2026-10-23-decomposition-schema-mapping.md"
    ],
    "revision": "095b6125623af5b9ade6914a6a83444e3d704b57",
    "diff_fingerprint": "aca4e956eca8f02c5b3977d2f0328b7dfeb119c4d16707f53898fd85ca9e1b46",
    "tests": [
      "evidence/EV-20261023T065342-b02c5d5b.json",
      "evidence/EV-20261023T065411-6e005928.json"
    ]
  },
  "verification": {
    "result": "PASS_WITH_WARNINGS",
    "reviewer": "mapping_final_review（fresh independent agent）與Main整合",
    "method": "獨立程式審查、fresh subprocess focused173、3holdout+5boundary、Main完整pytest與精確失敗集比較、保護指紋與UTF8核對",
    "verified_at": "2026-10-23T06:55:08.047975+00:00",
    "revision": "095b6125623af5b9ade6914a6a83444e3d704b57",
    "diff_fingerprint": "aca4e956eca8f02c5b3977d2f0328b7dfeb119c4d16707f53898fd85ca9e1b46",
    "tests": [
      "evidence/EV-20261023T065342-b02c5d5b.json"
    ],
    "regression": [
      "evidence/EV-20261023T065411-6e005928.json"
    ],
    "full_suite_evidence": "evidence/EV-20261023T065113-4d7bf5d2.json",
    "warnings": [
      "完整pytest仍有修改前同樣23 failed（773 passed、1 skipped），無新增失敗；多為私有Retail env/契約指紋與版本斷言",
      "soft cutoff可因ties與明列來源補回超額；隱含必要來源可能未召回"
    ],
    "unverified": [
      "真實LLM需求抽取/證據支持與審核語意品質、embedding/reranker召回品質及成本",
      "資料庫實際查詢與SQL生成不在此次入口範圍"
    ],
    "blocking_issues": []
  },
  "completion_summary": "已新增獨立SchemaMappingDecompositionService：前置View篩選→需求span抽取→逐候選View/欄位證據mapping→全文二次審核→受核准來源限制的DecompositionDraft與prepared requests。新107與原66項測試通過，完整suite僅23既有失敗；保留原prompt/既有流程，未commit/push或呼叫真實模型/DB。",
  "history": [
    {
      "from": null,
      "to": "CREATED",
      "at": "2026-10-23T06:17:09+00:00",
      "reason": "初始化"
    },
    {
      "from": "CREATED",
      "to": "INVESTIGATING",
      "at": "2026-10-23T06:18:55+00:00",
      "reason": "已核對單次規劃現況，獨立研究逐詞證據與跨階段驗證",
      "paused_from": null
    },
    {
      "from": "INVESTIGATING",
      "to": "PLANNING",
      "at": "2026-10-23T06:27:11+00:00",
      "reason": "需求與獨立入口方案 A 已核准，計畫與 TDD 實作進行中",
      "paused_from": null
    },
    {
      "from": "PLANNING",
      "to": "EXPERIMENTING",
      "at": "2026-10-23T06:29:35+00:00",
      "reason": "已核准 A，三步 TDD 計畫與最小驗證契約已保存",
      "paused_from": null
    },
    {
      "from": "EXPERIMENTING",
      "to": "IMPLEMENTING",
      "at": "2026-10-23T06:54:28+00:00",
      "reason": "支持實驗與最終focused/獨立驗證證據已保存，整合完成實作",
      "paused_from": null
    },
    {
      "from": "IMPLEMENTING",
      "to": "VERIFYING",
      "at": "2026-10-23T06:55:08+00:00",
      "reason": "同版本173focused與獨立驗證通過，完整suite23既有失敗集不變且Handoff已整合",
      "paused_from": null
    },
    {
      "from": "VERIFYING",
      "to": "COMPLETED",
      "at": "2026-10-23T06:55:37+00:00",
      "reason": "核准A與追加View篩選全部完成，驗收與Handoff整合通過；保留明示驗證限制",
      "paused_from": null
    }
  ]
}
---
# 任務：decomposition-schema-mapping

## 目標

新增需求關鍵字逐 View 欄位證據對照與二次審核，據以產生 DecompositionDraft

## 問題定義（預期／實際／證據／未確認假設）

{
  "description": "新增多來源需求詞到欄位證據 mapping 獨立入口",
  "expected": "需求抽取、逐 View 候選證據、全域審核及受核准來源限制的 DecompositionDraft",
  "actual": "既有流程一次 LLM 直接規劃，沒有 mapping 證據或二次審核",
  "evidence": [
    "src/cpea/workflows/task_decomposition/workflow.py",
    "相關四組基準 66 passed；使用者選獨立入口並同意 A"
  ],
  "hypotheses": [
    {
      "id": "H1",
      "claim": "新增獨立逐 View 比對與證據閉合審核，可在保留舊流程下提供可稽核 mapping",
      "status": "UNCONFIRMED"
    }
  ]
}

## 範圍

- src/cpea/application/models/schema_mapping_decomposition.py
- src/cpea/application/services/schema_mapping_decomposition.py
- src/cpea/workflows/task_decomposition/
- tests/unit/test_schema_mapping_decomposition.py
- tests/schema_mapping_support.py
- docs/superpowers/

## 限制

[
  "保留原 workflow/service/validation/eval/tests 與使用者 prompt 修改",
  "不 commit/push、不呼叫真實模型或 DB",
  "UTF-8 無 BOM、保留換行"
]

## 驗收標準

[
  {
    "id": "A1",
    "description": "原文spans、候選View每必要詞完整回覆、同欄同路徑引文真實",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261023T065342-b02c5d5b.json",
      "evidence/EV-20261023T065411-6e005928.json"
    ]
  },
  {
    "id": "A2",
    "description": "二次審核與Draft來源/操作allowlist、必要詞binding、期間/粒度/母體閉合",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261023T065342-b02c5d5b.json",
      "evidence/EV-20261023T065411-6e005928.json"
    ]
  },
  {
    "id": "A3",
    "description": "獨立service先檢索、C+3呼叫、錯誤早停與partial trace，舊66相關回歸及完整23既有失敗不變",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261023T065342-b02c5d5b.json",
      "evidence/EV-20261023T065411-6e005928.json"
    ]
  }
]

## 工作進度

[]

## Subagent Registry

[
  {
    "id": "mapping_research",
    "status": "DONE_WITH_CONCERNS",
    "report": "agents/mapping_research/task.md",
    "platform_id": "/root/mapping_research",
    "integrated": true,
    "disposition": "",
    "integrated_at": "2026-10-23T06:53:41+00:00"
  },
  {
    "id": "mapping_review",
    "status": "FAILED",
    "report": "agents/mapping_review/task.md",
    "platform_id": "/root/mapping_review",
    "integrated": true,
    "disposition": "原審查因模型capacity中止，已保存原輸出與not_quota_limit判讀；不當成成功，由fresh mapping_final_review接替完成全部驗收",
    "integrated_at": "2026-10-23T06:53:42+00:00"
  },
  {
    "id": "mapping_final_review",
    "status": "DONE_WITH_CONCERNS",
    "report": "agents/mapping_final_review/task.md",
    "platform_id": "/root/mapping_final_review",
    "integrated": true,
    "disposition": "",
    "integrated_at": "2026-10-23T06:53:42+00:00"
  }
]

## 實驗

[
  {
    "id": "EXP-001",
    "hypothesis_id": "H1"
  }
]

## 決策

詳見 [decisions.md](decisions.md)。
[
  {
    "id": "DEC-001",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "依使用者確認新增獨立入口，採 A 逐 View 需求候選證據與二次審核",
    "alternatives": [
      "B 完整逐詞逐欄矩陣",
      "替換原 task decomposition 預設流程"
    ],
    "reason": "使用者明確選擇獨立入口並於書面設計確認後回覆 A",
    "risks": "A 不保存全部拒絕組合；真實 LLM 語意仍需實測",
    "revisit": "使用者後續要求逐格拒絕稽核或整合既有預設流程時",
    "references": [
      "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
    ],
    "at": "2026-10-23T06:27:27+00:00"
  },
  {
    "id": "DEC-002",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "依使用者追加要求，在新入口最前端重用既有View檢索，再對候選執行A流程",
    "alternatives": [
      "繼續逐個比對完整catalog，不作前置篩選",
      "直接套用單View所有明列欄位交集"
    ],
    "reason": "使用者要求最前端View篩選以避免過多Views；研究者選擇僅移除檢索識別碼並補回原文明列來源，保留多來源能力",
    "risks": "soft top-k可能因ties或明列欄位owners增加；檢索召回與真實模型品質未實測",
    "revisit": "候選過多或實測發現缺少必要來源時",
    "references": [
      "docs/superpowers/specs/2026-10-23-decomposition-schema-mapping-design.md"
    ],
    "at": "2026-10-23T06:44:43+00:00"
  }
]

## 待使用者回答問題

[]

## 阻礙

[]

## Recovery Checkpoint

{
  "last_completed": "173focused、獨立holdout/邊界/保護指紋/UTF8通過；完整773passed/23既有failed/1skipped，無新增失敗",
  "current_action": "Main已整合實作與fresh final review，EDD validate PASS",
  "next_action": "交付獨立入口與使用文件；真實模型語意與成本留待另行實測",
  "required_inputs": [],
  "unresolved_questions": []
}

## 最終驗證

{
  "result": "PASS_WITH_WARNINGS",
  "reviewer": "mapping_final_review（fresh independent agent）與Main整合",
  "method": "獨立程式審查、fresh subprocess focused173、3holdout+5boundary、Main完整pytest與精確失敗集比較、保護指紋與UTF8核對",
  "verified_at": "2026-10-23T06:55:08.047975+00:00",
  "revision": "095b6125623af5b9ade6914a6a83444e3d704b57",
  "diff_fingerprint": "aca4e956eca8f02c5b3977d2f0328b7dfeb119c4d16707f53898fd85ca9e1b46",
  "tests": [
    "evidence/EV-20261023T065342-b02c5d5b.json"
  ],
  "regression": [
    "evidence/EV-20261023T065411-6e005928.json"
  ],
  "full_suite_evidence": "evidence/EV-20261023T065113-4d7bf5d2.json",
  "warnings": [
    "完整pytest仍有修改前同樣23 failed（773 passed、1 skipped），無新增失敗；多為私有Retail env/契約指紋與版本斷言",
    "soft cutoff可因ties與明列來源補回超額；隱含必要來源可能未召回"
  ],
  "unverified": [
    "真實LLM需求抽取/證據支持與審核語意品質、embedding/reranker召回品質及成本",
    "資料庫實際查詢與SQL生成不在此次入口範圍"
  ],
  "blocking_issues": []
}

## 完成摘要

已新增獨立SchemaMappingDecompositionService：前置View篩選→需求span抽取→逐候選View/欄位證據mapping→全文二次審核→受核准來源限制的DecompositionDraft與prepared requests。新107與原66項測試通過，完整suite僅23既有失敗；保留原prompt/既有流程，未commit/push或呼叫真實模型/DB。
