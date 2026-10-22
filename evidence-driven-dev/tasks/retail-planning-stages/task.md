---
{
  "schema_version": 1,
  "id": "retail-planning-stages",
  "type": "research",
  "complexity": "moderate",
  "status": "COMPLETED",
  "phase": "COMPLETED",
  "owner": "main-agent",
  "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
  "branch": "feat/cross_view",
  "worktree": "/home/willy/code/cpea_terms",
  "openspec_change": null,
  "updated_at": "2026-10-20T11:46:10+00:00",
  "goal": "參考現有text-to-sql的候選View映射，調整單次planner prompt/context並用DeepSeek驗證；保留先前三階段研究負結果。",
  "problem": {
    "description": "依使用者最新授權參考text-to-sql候選View篩選，調整單次planner prompt並顯式提供解析後欄位能力。",
    "expected": "固定DeepSeek設定與既有30題契約，以成對小樣本比較原版、單次檢查清單、三階段規劃，保留失敗及成本。",
    "actual": "已依text-to-sql候選映射調整並實測v4/v5/v6。v4中止16筆另列；v5完整對照未達標。v6僅改system prompt，同批30題來源欄位25→26、自動結構15→16、ready18→16，未達預設門檻，恢復v3。全部136筆已保存回覆fresh重播一致，最終391pass/1skip，產品無差異。",
    "evidence": [
      "reports/prompt-view-matching-results.md",
      "reports/prompt-v6-audit.json",
      "reports/prompt-v6-review.json",
      "reports/prompt-final-verification.json"
    ],
    "hypotheses": [
      {
        "id": "HS1",
        "claim": "錯誤主要源於檢查順序不明；同一呼叫加入明確檢查步驟即可改善。",
        "status": "UNCONFIRMED",
        "observation": "本次B2/10低於A7/10，這個checklist版本無改善；不能由單次已見樣本推論所有提示策略。",
        "evidence": [
          "evidence/EV-20261020T094051-96dff029.json",
          "evidence/EV-20261020T094610-d7310696.json"
        ]
      },
      {
        "id": "HS2",
        "claim": "分成來源/需求、單View子任務、整合三階段，在相同檢查指引下優於單次規劃。",
        "status": "UNCONFIRMED",
        "observation": "EXP-001對本次固定原型為REFUTED；C2/10等於B2/10且有控制退步。不推論所有拆分策略。",
        "evidence": [
          "evidence/EV-20261020T094051-96dff029.json",
          "evidence/EV-20261020T094610-d7310696.json",
          "evidence/EV-20261020T094749-0284328a.json"
        ]
      },
      {
        "id": "HS3",
        "claim": "本次原型在21、24、26的route固定了錯誤final grain，integration沿用後仍被validator拒絕。",
        "status": "CONFIRMED",
        "evidence": [
          "evidence/EV-20261020T094051-96dff029.json",
          "evidence/EV-20261020T094610-d7310696.json",
          "reports/stages-analysis.json"
        ]
      },
      {
        "id": "HS4",
        "claim": "原始YAML未明示v3契約預設capabilities/aggregations，使planner與text-to-sql看見的欄位能力不同；解析後能力搭配逐子需求候選映射可降低來源及多餘澄清錯誤。",
        "status": "UNCONFIRMED"
      },
      {
        "id": "HS5",
        "claim": "v4將task專用unbound_inputs與頂層欄位並列，產生頂層extra_forbidden；明確schema層級有助避免此格式錯誤。",
        "status": "UNCONFIRMED",
        "evidence": [
          ".local/prompt-v4-20261020T112256Z/interruption.json"
        ]
      },
      {
        "id": "HS6",
        "claim": "維持原View上下文、僅小幅修訂來源映射與必要澄清，比大幅改寫更容易隔離prompt作用並降低回歸。",
        "status": "UNCONFIRMED"
      }
    ]
  },
  "scope": [
    "src/cpea/workflows/task_decomposition",
    "tests/unit/test_task_decomposition_workflow.py",
    "evidence-driven-dev/tasks/retail-planning-stages"
  ],
  "constraints": [
    "使用者最新明確授權參考text-to-sql的View篩選並調整prompt；主agent直接實作。",
    "本次僅Azure DeepSeek-V4.1-Flash，不呼叫GPT或Ollama，不生成/執行SQL或查DB。",
    "固定原30題、schema、View契約、grader；模型看不到oracle與GPT答案，原始結果與失敗不覆寫。",
    "任何context/能力呈現改動須經同批對照；未達標則撤回，不因程式測試通過就宣稱模型品質改善。",
    "temperature1/top_p1/seed42/context16384/max_tokens不限/timeout300/retries0；provider錯誤停止不重試。",
    "v4中止16筆完整回覆另列，一筆in-flight結果未知可能計費；不混進完整輪次分母。",
    "UTF-8無BOM、文件及使用者回覆繁體中文。"
  ],
  "acceptance": [
    {
      "id": "AP1",
      "description": "參考text-to-sql候選View映射、提供可審閱prompt候選與差異說明。",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T114501-a1bfa250.json"
      ],
      "scope_note": "候選已產出並實測；不表示已採用或模型全數正確。"
    },
    {
      "id": "AP2",
      "description": "原版與候選同批成對、固定設定/契約/題庫/原分，保留失敗、中止與未驗證項目。",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T114501-a1bfa250.json"
      ],
      "scope_note": "v4部分16、v5/v6各60筆完整保存，非三個完整輪次；一筆在途結果未知可能計費。"
    },
    {
      "id": "AP3",
      "description": "未達標不替換預設，恢復v3後全套測試及所有保存回覆fresh重播通過。",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T114501-a1bfa250.json",
        "evidence/EV-20261020T114258-46fc2ee0.json"
      ],
      "scope_note": "驗收實驗/恢復完整性；不宣稱候選品質PASS或已驗證SQL。"
    }
  ],
  "progress": [
    {
      "id": "P1",
      "status": "DONE",
      "description": "既有三階段研究負結果保留。"
    },
    {
      "id": "P2",
      "status": "DONE",
      "description": "盤點text-to-sql候選映射；raw/resolved能力差距red/green重現，v4/v5實驗保留，未達標撤回。"
    },
    {
      "id": "P3",
      "status": "DONE",
      "description": "v6小幅prompt-only同批30題完成；欄位及結構局部增一，ready降二，未採用。"
    },
    {
      "id": "P4",
      "status": "DONE",
      "description": "恢復v3，fresh136筆重播及391pass/1skip完成；候選/patch/報告交付。"
    }
  ],
  "agents": [],
  "experiments": [
    {
      "id": "EXP-001",
      "hypothesis_id": "HS2"
    },
    {
      "id": "EXP-002",
      "hypothesis_id": "HS4"
    },
    {
      "id": "EXP-003",
      "hypothesis_id": "HS4"
    },
    {
      "id": "EXP-004",
      "hypothesis_id": "HS5"
    },
    {
      "id": "EXP-005",
      "hypothesis_id": "HS6"
    }
  ],
  "decisions": [
    {
      "id": "DEC-001",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "本次DeepSeek三階段原型未改善，保留原產品流程；後續候選優先型別化中間契約與結構編譯，尚未宣稱有效",
      "alternatives": [
        "直接採用三階段原型：自動2/10、ready5/10、有控制退步",
        "維持原prompt流程，保存三arm實驗與失敗，先處理來源/欄位角色/粒度契約再另做比較",
        "繼續增加審查與模型修補：變因及成本更高，本次不擴張"
      ],
      "reason": "固定十題成對結果A7/10、B2/10、C2/10；三個表示差異另列，C仍不優於A且不符合C優於B/控制無退步條件",
      "risks": "小樣本單次且已見案例；grader等價盲點、來源覆蓋與母體語意仍需驗證，不能推論所有多階段策略皆無效",
      "revisit": "中間契約設計清楚且有新成對/重複及未參與調整案例支持時",
      "references": [
        "reports/results.md"
      ],
      "at": "2026-10-20T09:50:21+00:00"
    },
    {
      "id": "DEC-002",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "依text-to-sql候選映射完成v4/v5/v6 prompt調整與DeepSeek驗證；v5及v6未達預先門檻，保留候選與原分，恢復v3預設，不再追加調參",
      "alternatives": [
        "採用v5完整改寫及resolved context：來源欄位提高，但ready及結構大幅降低",
        "採用v6小幅prompt：欄位25→26、結構15→16，ready18→16",
        "保留v3預設，將候選/patch/全量回覆/結果交付供後續設計使用"
      ],
      "reason": "v6只改system prompt且human context相同，仍有實際格式/欄位/粒度回歸；局部提升不足以符合預先三項核心指標門檻。",
      "risks": "已見題庫單輪且模型結果波動；自動評分有等價與語意盲點；本次無SQL或DB驗證。",
      "revisit": "若後續有明確契約生成、受限修正或其他新假設，再以固定對照與新案例驗證，不沿用相同prompt反覆調參。",
      "references": [
        "reports/prompt-view-matching-results.md"
      ],
      "at": "2026-10-20T11:44:16+00:00"
    }
  ],
  "questions": [],
  "blockers": [],
  "waiting": null,
  "paused_from": null,
  "checkpoint": {
    "last_completed": "prompt候選與成對測試交付；v3預設恢復，136筆重播與391pass/1skip完成。",
    "current_action": "本輪任務完成，候選未達採用門檻；reports/prompt-view-matching-results.md",
    "next_action": "保留候選/patch/原始結果，等待使用者新指示；不自動重跑模型或繼續調參。",
    "required_inputs": [],
    "unresolved_questions": []
  },
  "plan": {
    "solutions": [
      {
        "id": "S",
        "hypothesis": "HS4",
        "root_cause": "原始契約未解析能力且來源映射範圍不清",
        "benefit": "維持一次呼叫並提供明確來源能力",
        "scope": "重寫prompt及load階段以catalog.field_contract取得能力",
        "complexity": "低",
        "cost": "每題一次",
        "risks": "上下文增加、模型波動",
        "verification": "契約context合成回歸與固定30題fresh成對",
        "falsification": "來源/澄清/粒度無改善或context超限",
        "rollback": "還原兩個planner檔案"
      },
      {
        "id": "M",
        "hypothesis": "HS4",
        "root_cause": "候選來源上下文負擔",
        "benefit": "縮小候選",
        "scope": "引入子需求檢索再生成",
        "complexity": "中",
        "cost": "檢索與可能新增模型節點",
        "risks": "完整跨View需求不能套用單View欄位交集；可能提前排除必要來源",
        "verification": "需要候選召回率新矩陣，本輪不實作",
        "falsification": "必要來源召回降低",
        "rollback": "保留全契約上下文"
      }
    ],
    "selected_solution": "保留v3預設；v6候選、patch及實驗證據交付",
    "success": "來源能力傳入與validator一致，合成禁止能力/不突變/budget回歸通過；固定三十題fresh成對比較揭露來源/欄位/ready/自動結構與退步，不更改oracle。",
    "failure": "能力欄位被省略/禁止規則遺失、context超額未拒絕或new策略較baseline退步；不宣稱全部正確。",
    "regression": [
      "新增契約context測試",
      "完整pytest",
      "30題DeepSeek原版與新版成對",
      "fresh離線重播"
    ],
    "approval_required": false,
    "authorization": "使用者明確要求參考text-to-sql篩選View流程並調整prompt；主agent直接實作，模型延續Azure DeepSeek。",
    "kind": "investigation_spike",
    "parent_task": "retail-task-decomposition",
    "mvp0": "離線比較已保存GPT/DeepSeek輸出",
    "mvp1": "固定十題三arm，無自動修復",
    "later": "C優於B且控制不退步才考慮擴大",
    "research_complete": true,
    "product_adoption": false,
    "ledger_note": "新一輪prompt/context修正有supported最小差距實驗並進IMPLEMENTING；模型候選未達標後還原產品，以fresh136筆重播及完整回歸驗收實驗與恢復完整性。",
    "prompt_v4_design": "reports/prompt-v4-design.md",
    "prompt_v4_run": ".local/prompt-v4-20261020T112256Z",
    "previous_stages_report": "reports/results.md",
    "prompt_version": "v3_restored",
    "prompt_v4_interruption": ".local/prompt-v4-20261020T112256Z/interruption.json",
    "current_protocol": "調查與使用者授權之prompt調整驗證完成；本輪不再追加模型呼叫或調參。",
    "prompt_v5_run": ".local/prompt-v5-20261020T112607Z",
    "prompt_v6_run": ".local/prompt-v6-20261020T113508Z",
    "next_stop": "v6未達預先核心指標門檻即回到原版，不再追加prompt調參"
  },
  "changes": {
    "scope": [
      "evidence-driven-dev/tasks/retail-planning-stages"
    ],
    "revision": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
    "diff_fingerprint": "aa41d10592dbead4910485bf28a61ea48d945514929dbccc513e0b4e93b18997",
    "tests": [
      "evidence/EV-20261020T114501-a1bfa250.json",
      "evidence/EV-20261020T114258-46fc2ee0.json"
    ],
    "product_source_changed": false,
    "candidate": "evidence-driven-dev/tasks/retail-planning-stages/.local/prompt-v6-candidate.py"
  },
  "verification": {
    "result": "PASS_WITH_WARNINGS",
    "reviewer": "main-agent",
    "method": "同一主agent使用既有oracle與fresh subprocess；恢復原版後重播136筆保存回覆，核對原始輸入、解析、validator、prepared payload及grader；完整pytest，非跨agent獨立驗收。",
    "verified_at": "2026-10-20T11:46:09.212968+00:00",
    "revision": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
    "diff_fingerprint": "aa41d10592dbead4910485bf28a61ea48d945514929dbccc513e0b4e93b18997",
    "tests": [
      "evidence/EV-20261020T114501-a1bfa250.json"
    ],
    "regression": [
      "evidence/EV-20261020T114258-46fc2ee0.json"
    ],
    "blocking_issues": [],
    "warnings": [
      "僅驗收調整與實驗完整性，候選未達採用門檻，已恢復v3。",
      "單輪已見案例、模型輸出波動；自動分數有等價與語意盲點。",
      "v4中止有一筆在途結果未知可能計費，未混入完整輪次。",
      "私有SQL Server profile缺少，一項測試略過。"
    ],
    "unverified": [
      "沒有SQL生成/執行、DB查詢、實際採購結論驗證。",
      "全題正式人工語意核准仍pending；未做外部holdout或多輪穩定性。"
    ]
  },
  "completion_summary": "已參考text-to-sql完成prompt調整候選與DeepSeek成對驗證。v6來源欄位25→26、自動結構15→16、ready18→16，未達預設門檻，產品恢復v3；v4/v5/v6全部136筆已保存回覆fresh重播一致，391pass/1skip；候選及完整報告可審閱，不再追加調參。",
  "history": [
    {
      "from": null,
      "to": "CREATED",
      "at": "2026-10-20T09:37:00+00:00",
      "reason": "初始化"
    },
    {
      "from": "CREATED",
      "to": "INVESTIGATING",
      "at": "2026-10-20T09:37:00+00:00",
      "reason": "原benchmark維持COMPLETED；另開後續研究並連結既有證據，保留原分數",
      "paused_from": null
    },
    {
      "from": "INVESTIGATING",
      "to": "PLANNING",
      "at": "2026-10-20T09:41:00+00:00",
      "reason": "完成根因分類；已固定DeepSeek十題三arm實驗方案與驗收條件",
      "paused_from": null
    },
    {
      "from": "PLANNING",
      "to": "EXPERIMENTING",
      "at": "2026-10-20T09:41:47+00:00",
      "reason": "候選方案與驗收欄位完整，執行已授權之調查性spike",
      "paused_from": null
    },
    {
      "from": "EXPERIMENTING",
      "to": "PLANNING",
      "at": "2026-10-20T09:52:13+00:00",
      "reason": "調查已完成；被測原型REFUTED，不進IMPLEMENTING。保存未實作後續候選，無待執行模型批次。",
      "paused_from": null
    },
    {
      "from": "PLANNING",
      "to": "EXPERIMENTING",
      "at": "2026-10-20T11:19:42+00:00",
      "reason": "使用者已授權prompt/context修正；先確認解析後能力缺失的最小重現，再驗證最小變更",
      "paused_from": null
    },
    {
      "from": "EXPERIMENTING",
      "to": "IMPLEMENTING",
      "at": "2026-10-20T11:20:34+00:00",
      "reason": "解析後欄位能力差距已red/green重現；依使用者授權進行prompt重寫及DeepSeek驗證",
      "paused_from": null
    },
    {
      "from": "IMPLEMENTING",
      "to": "VERIFYING",
      "at": "2026-10-20T11:46:09+00:00",
      "reason": "候選未達標已撤回，最終產品原版與136筆產物fresh驗證完成",
      "paused_from": null
    },
    {
      "from": "VERIFYING",
      "to": "COMPLETED",
      "at": "2026-10-20T11:46:10+00:00",
      "reason": "使用者授權prompt調整及比較完成；負結果與候選交付、產品恢復，驗收範圍為調整實驗完整性",
      "paused_from": null
    }
  ]
}
---
# 任務：retail-planning-stages

## 目標

參考現有text-to-sql的候選View映射，調整單次planner prompt/context並用DeepSeek驗證；保留先前三階段研究負結果。

## 問題定義（預期／實際／證據／未確認假設）

{
  "description": "依使用者最新授權參考text-to-sql候選View篩選，調整單次planner prompt並顯式提供解析後欄位能力。",
  "expected": "固定DeepSeek設定與既有30題契約，以成對小樣本比較原版、單次檢查清單、三階段規劃，保留失敗及成本。",
  "actual": "已依text-to-sql候選映射調整並實測v4/v5/v6。v4中止16筆另列；v5完整對照未達標。v6僅改system prompt，同批30題來源欄位25→26、自動結構15→16、ready18→16，未達預設門檻，恢復v3。全部136筆已保存回覆fresh重播一致，最終391pass/1skip，產品無差異。",
  "evidence": [
    "reports/prompt-view-matching-results.md",
    "reports/prompt-v6-audit.json",
    "reports/prompt-v6-review.json",
    "reports/prompt-final-verification.json"
  ],
  "hypotheses": [
    {
      "id": "HS1",
      "claim": "錯誤主要源於檢查順序不明；同一呼叫加入明確檢查步驟即可改善。",
      "status": "UNCONFIRMED",
      "observation": "本次B2/10低於A7/10，這個checklist版本無改善；不能由單次已見樣本推論所有提示策略。",
      "evidence": [
        "evidence/EV-20261020T094051-96dff029.json",
        "evidence/EV-20261020T094610-d7310696.json"
      ]
    },
    {
      "id": "HS2",
      "claim": "分成來源/需求、單View子任務、整合三階段，在相同檢查指引下優於單次規劃。",
      "status": "UNCONFIRMED",
      "observation": "EXP-001對本次固定原型為REFUTED；C2/10等於B2/10且有控制退步。不推論所有拆分策略。",
      "evidence": [
        "evidence/EV-20261020T094051-96dff029.json",
        "evidence/EV-20261020T094610-d7310696.json",
        "evidence/EV-20261020T094749-0284328a.json"
      ]
    },
    {
      "id": "HS3",
      "claim": "本次原型在21、24、26的route固定了錯誤final grain，integration沿用後仍被validator拒絕。",
      "status": "CONFIRMED",
      "evidence": [
        "evidence/EV-20261020T094051-96dff029.json",
        "evidence/EV-20261020T094610-d7310696.json",
        "reports/stages-analysis.json"
      ]
    },
    {
      "id": "HS4",
      "claim": "原始YAML未明示v3契約預設capabilities/aggregations，使planner與text-to-sql看見的欄位能力不同；解析後能力搭配逐子需求候選映射可降低來源及多餘澄清錯誤。",
      "status": "UNCONFIRMED"
    },
    {
      "id": "HS5",
      "claim": "v4將task專用unbound_inputs與頂層欄位並列，產生頂層extra_forbidden；明確schema層級有助避免此格式錯誤。",
      "status": "UNCONFIRMED",
      "evidence": [
        ".local/prompt-v4-20261020T112256Z/interruption.json"
      ]
    },
    {
      "id": "HS6",
      "claim": "維持原View上下文、僅小幅修訂來源映射與必要澄清，比大幅改寫更容易隔離prompt作用並降低回歸。",
      "status": "UNCONFIRMED"
    }
  ]
}

## 範圍

- src/cpea/workflows/task_decomposition
- tests/unit/test_task_decomposition_workflow.py
- evidence-driven-dev/tasks/retail-planning-stages

## 限制

[
  "使用者最新明確授權參考text-to-sql的View篩選並調整prompt；主agent直接實作。",
  "本次僅Azure DeepSeek-V4.1-Flash，不呼叫GPT或Ollama，不生成/執行SQL或查DB。",
  "固定原30題、schema、View契約、grader；模型看不到oracle與GPT答案，原始結果與失敗不覆寫。",
  "任何context/能力呈現改動須經同批對照；未達標則撤回，不因程式測試通過就宣稱模型品質改善。",
  "temperature1/top_p1/seed42/context16384/max_tokens不限/timeout300/retries0；provider錯誤停止不重試。",
  "v4中止16筆完整回覆另列，一筆in-flight結果未知可能計費；不混進完整輪次分母。",
  "UTF-8無BOM、文件及使用者回覆繁體中文。"
]

## 驗收標準

[
  {
    "id": "AP1",
    "description": "參考text-to-sql候選View映射、提供可審閱prompt候選與差異說明。",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T114501-a1bfa250.json"
    ],
    "scope_note": "候選已產出並實測；不表示已採用或模型全數正確。"
  },
  {
    "id": "AP2",
    "description": "原版與候選同批成對、固定設定/契約/題庫/原分，保留失敗、中止與未驗證項目。",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T114501-a1bfa250.json"
    ],
    "scope_note": "v4部分16、v5/v6各60筆完整保存，非三個完整輪次；一筆在途結果未知可能計費。"
  },
  {
    "id": "AP3",
    "description": "未達標不替換預設，恢復v3後全套測試及所有保存回覆fresh重播通過。",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T114501-a1bfa250.json",
      "evidence/EV-20261020T114258-46fc2ee0.json"
    ],
    "scope_note": "驗收實驗/恢復完整性；不宣稱候選品質PASS或已驗證SQL。"
  }
]

## 工作進度

[
  {
    "id": "P1",
    "status": "DONE",
    "description": "既有三階段研究負結果保留。"
  },
  {
    "id": "P2",
    "status": "DONE",
    "description": "盤點text-to-sql候選映射；raw/resolved能力差距red/green重現，v4/v5實驗保留，未達標撤回。"
  },
  {
    "id": "P3",
    "status": "DONE",
    "description": "v6小幅prompt-only同批30題完成；欄位及結構局部增一，ready降二，未採用。"
  },
  {
    "id": "P4",
    "status": "DONE",
    "description": "恢復v3，fresh136筆重播及391pass/1skip完成；候選/patch/報告交付。"
  }
]

## Subagent Registry

[]

## 實驗

[
  {
    "id": "EXP-001",
    "hypothesis_id": "HS2"
  },
  {
    "id": "EXP-002",
    "hypothesis_id": "HS4"
  },
  {
    "id": "EXP-003",
    "hypothesis_id": "HS4"
  },
  {
    "id": "EXP-004",
    "hypothesis_id": "HS5"
  },
  {
    "id": "EXP-005",
    "hypothesis_id": "HS6"
  }
]

## 決策

詳見 [decisions.md](decisions.md)。
[
  {
    "id": "DEC-001",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "本次DeepSeek三階段原型未改善，保留原產品流程；後續候選優先型別化中間契約與結構編譯，尚未宣稱有效",
    "alternatives": [
      "直接採用三階段原型：自動2/10、ready5/10、有控制退步",
      "維持原prompt流程，保存三arm實驗與失敗，先處理來源/欄位角色/粒度契約再另做比較",
      "繼續增加審查與模型修補：變因及成本更高，本次不擴張"
    ],
    "reason": "固定十題成對結果A7/10、B2/10、C2/10；三個表示差異另列，C仍不優於A且不符合C優於B/控制無退步條件",
    "risks": "小樣本單次且已見案例；grader等價盲點、來源覆蓋與母體語意仍需驗證，不能推論所有多階段策略皆無效",
    "revisit": "中間契約設計清楚且有新成對/重複及未參與調整案例支持時",
    "references": [
      "reports/results.md"
    ],
    "at": "2026-10-20T09:50:21+00:00"
  },
  {
    "id": "DEC-002",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "依text-to-sql候選映射完成v4/v5/v6 prompt調整與DeepSeek驗證；v5及v6未達預先門檻，保留候選與原分，恢復v3預設，不再追加調參",
    "alternatives": [
      "採用v5完整改寫及resolved context：來源欄位提高，但ready及結構大幅降低",
      "採用v6小幅prompt：欄位25→26、結構15→16，ready18→16",
      "保留v3預設，將候選/patch/全量回覆/結果交付供後續設計使用"
    ],
    "reason": "v6只改system prompt且human context相同，仍有實際格式/欄位/粒度回歸；局部提升不足以符合預先三項核心指標門檻。",
    "risks": "已見題庫單輪且模型結果波動；自動評分有等價與語意盲點；本次無SQL或DB驗證。",
    "revisit": "若後續有明確契約生成、受限修正或其他新假設，再以固定對照與新案例驗證，不沿用相同prompt反覆調參。",
    "references": [
      "reports/prompt-view-matching-results.md"
    ],
    "at": "2026-10-20T11:44:16+00:00"
  }
]

## 待使用者回答問題

[]

## 阻礙

[]

## Recovery Checkpoint

{
  "last_completed": "prompt候選與成對測試交付；v3預設恢復，136筆重播與391pass/1skip完成。",
  "current_action": "本輪任務完成，候選未達採用門檻；reports/prompt-view-matching-results.md",
  "next_action": "保留候選/patch/原始結果，等待使用者新指示；不自動重跑模型或繼續調參。",
  "required_inputs": [],
  "unresolved_questions": []
}

## 最終驗證

{
  "result": "PASS_WITH_WARNINGS",
  "reviewer": "main-agent",
  "method": "同一主agent使用既有oracle與fresh subprocess；恢復原版後重播136筆保存回覆，核對原始輸入、解析、validator、prepared payload及grader；完整pytest，非跨agent獨立驗收。",
  "verified_at": "2026-10-20T11:46:09.212968+00:00",
  "revision": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
  "diff_fingerprint": "aa41d10592dbead4910485bf28a61ea48d945514929dbccc513e0b4e93b18997",
  "tests": [
    "evidence/EV-20261020T114501-a1bfa250.json"
  ],
  "regression": [
    "evidence/EV-20261020T114258-46fc2ee0.json"
  ],
  "blocking_issues": [],
  "warnings": [
    "僅驗收調整與實驗完整性，候選未達採用門檻，已恢復v3。",
    "單輪已見案例、模型輸出波動；自動分數有等價與語意盲點。",
    "v4中止有一筆在途結果未知可能計費，未混入完整輪次。",
    "私有SQL Server profile缺少，一項測試略過。"
  ],
  "unverified": [
    "沒有SQL生成/執行、DB查詢、實際採購結論驗證。",
    "全題正式人工語意核准仍pending；未做外部holdout或多輪穩定性。"
  ]
}

## 完成摘要

已參考text-to-sql完成prompt調整候選與DeepSeek成對驗證。v6來源欄位25→26、自動結構15→16、ready18→16，未達預設門檻，產品恢復v3；v4/v5/v6全部136筆已保存回覆fresh重播一致，391pass/1skip；候選及完整報告可審閱，不再追加調參。
