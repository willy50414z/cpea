---
{
  "schema_version": 1,
  "id": "retail-test-group-2",
  "type": "research",
  "complexity": "moderate",
  "status": "COMPLETED",
  "phase": "COMPLETED",
  "owner": "main-agent",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "branch": "feat/progressive-view-retrieval",
  "worktree": "/home/willy/code/cpea",
  "openspec_change": null,
  "updated_at": "2026-10-20T14:17:29+00:00",
  "goal": "固定14題為test group 1，抽取不重複30題test group 2，各3次真實模型穩定性測試並完整記錄成功與失敗",
  "problem": {
    "description": "目前14題未有固定group名稱；需額外30題各3次驗證當前v10的泛化與穩定性。",
    "expected": "固定group1原14題；group2新30題不重複、3次共90筆完整記錄，分開正確率/一致性/HILP/正式核准。",
    "actual": "已固定group1原14題與group2另30題；v10各3次合計90筆完成，48通過/42未符合原預期，16題三次全通過、14題三次全失敗。",
    "evidence": [
      "projects/retail/evaluations/test_groups/test_group_1.json",
      "projects/retail/evaluations/test_groups/test_group_2.json"
    ],
    "hypotheses": [
      {
        "id": "H-SAMPLE",
        "claim": "固定種子分層可得到不重疊且覆蓋七View、各難度的30題樣本",
        "status": "CONFIRMED",
        "evidence": [
          "evidence/EV-20261020T050600-34a5fb8c.json",
          "evidence/EV-20261020T141423-03800329.json"
        ]
      },
      {
        "id": "H-STABILITY",
        "claim": "目前v10對group2的正確率與三次一致性可由凍結90次測量，不能預設通過。",
        "status": "CONFIRMED",
        "evidence": [
          "evidence/EV-20261020T141420-2af1e9c8.json",
          "evidence/EV-20261020T141423-03800329.json",
          "evidence/EV-20261020T141613-15248dee.json"
        ]
      }
    ]
  },
  "scope": [
    "projects/retail/evaluations/test_groups",
    "evidence-driven-dev/tasks/retail-test-group-2"
  ],
  "constraints": [
    "不修改產品、prompt、契約、原Oracle或依輸出重抽；保留所有失敗。",
    "不自動代選HILP；不執行DB；保留正式pending狀態；遇provider/rate limit停止新呼叫，不自動重跑。",
    "原有dirty變更保留；group1不自動重跑。"
  ],
  "acceptance": [
    {
      "id": "A1",
      "description": "group1固定原14題、group2可重現抽30題且無重疊，留成員/題文/預期hash與來源歷史",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T050600-34a5fb8c.json",
        "evidence/EV-20261020T141423-03800329.json"
      ]
    },
    {
      "id": "A2",
      "description": "當前v10凍結執行group2各3次共90筆，全部成功/失敗與呼叫皆記錄，不把一致失敗算通過",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T092245-d11eb8ec.json",
        "evidence/EV-20261020T141420-2af1e9c8.json",
        "evidence/EV-20261020T141423-03800329.json"
      ]
    },
    {
      "id": "A3",
      "description": "產出每題3次正確率/狀態及SQL一致性、HILP狀態、正式核准狀態與限制，驗證版本及Oracle未變",
      "status": "PASS",
      "evidence": [
        "evidence/EV-20261020T141423-03800329.json",
        "evidence/EV-20261020T141613-15248dee.json"
      ]
    }
  ],
  "progress": [
    {
      "summary": "group1原14題與group2另30題已固定且無重疊，seed20261020可重現",
      "status": "DONE"
    },
    {
      "summary": "版本/原Oracle/設定/契約預檢通過，50項評分及專案回歸通過",
      "status": "DONE"
    },
    {
      "summary": "90筆測量及575次call完整保留，3個segment合併；2次逾時未重試",
      "status": "DONE"
    },
    {
      "summary": "Main核對全部原Oracle重評、版本與報告；48/90通過，風險與未驗證項目已揭露",
      "status": "DONE"
    }
  ],
  "agents": [],
  "experiments": [
    {
      "id": "EXP-001",
      "hypothesis_id": "H-SAMPLE"
    }
  ],
  "decisions": [
    {
      "id": "DEC-001",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "固定14題為group1、排除後以seed20261020分層抽30題為group2，各3次；凍結當前產品並保留所有失敗",
      "alternatives": [
        "均勻隨機30題但可能缺難度/安全覆蓋"
      ],
      "reason": "滿足額外不重疊樣本並覆蓋七View及各難度，不按模型輸出重抽。使用者已授權額外30題穩定性測試，沿用每題3次。",
      "risks": "新測試組仍來自已知395題，不能視為從未見過的盲測；本地模型需要數小時；無DB數值驗證。",
      "revisit": "服務錯誤停止新呼叫後依完整記錄處理；本輪完成後若要修復失敗另立任務，避免污染穩定性測量。",
      "references": [
        "evidence/EV-20261020T050600-34a5fb8c.json"
      ],
      "at": "2026-10-20T05:07:43+00:00"
    },
    {
      "id": "DEC-002",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "保留第22次ReadTimeout為失敗，檢查服務與指紋後只繼續原排程尚未執行的68次",
      "alternatives": [
        "重跑整輪或重試逾時tuple，會抹去原穩定性失敗",
        "放棄剩餘68次，無法完成使用者要求"
      ],
      "reason": "原run按規則停止；服務可連線且模型digest、source/settings/Oracle/sample未變；持續授權90次測量，接續不重試失敗且不改設定。",
      "risks": "provider逾時影響一題三次結果，報告單獨揭露；同來源多segment執行，不宣稱單次不中斷。",
      "revisit": "再次服務錯誤立即停止新呼叫並查明，不盲目重試，不改模型或timeout。",
      "references": [
        "evidence/EV-20261020T050649-113b0aec.json"
      ],
      "at": "2026-10-20T06:21:13+00:00"
    },
    {
      "id": "DEC-003",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "使用者明確選擇「等它結束」；等cpea_terms的decomposition工作釋出共享Ollama後，只接續67次未做測量",
      "alternatives": [
        "中斷另一輪測試，使用者未選擇且不執行"
      ],
      "reason": "使用者最新訊息「等它結束」，保留全部23筆與兩次服務逾時，避免共享推論互相影響。",
      "risks": "等待期間不送新的測試生成，總耗時較長；服務恢復後仍需核對model/source/Oracle。",
      "revisit": "另一輪程序結束或使用者改變優先順序後恢復；不自動重跑已做tuple。",
      "references": [
        "evidence/EV-20261020T062744-cb642387.json"
      ],
      "at": "2026-10-20T06:33:57+00:00"
    },
    {
      "id": "DEC-004",
      "status": "ACCEPTED",
      "source": "main-agent",
      "summary": "90次同版本測量完整，研究任務可完成；產品僅48/90符合原預期，不宣稱全部穩定或正式核准",
      "alternatives": [
        "依結果修改產品、Oracle或重試失敗，會污染本輪固定版本測量"
      ],
      "reason": "三個segment的90個唯一tuple及575次呼叫均完整，原Oracle重評及報告審核成功，產品與模型指紋一致；失敗42次原樣保留",
      "risks": "14題三次皆失敗；2次provider逾時；pending draft Oracle；無DB數值與盲測驗證；同Main以獨立程序驗證",
      "revisit": "未來修復需另立任務與新版本重測，不改寫本輪原始結果；group1其餘8題修復版仍未新增重跑",
      "references": [
        "evidence/EV-20261020T141423-03800329.json",
        "evidence/EV-20261020T141613-15248dee.json"
      ],
      "at": "2026-10-20T14:16:43+00:00"
    }
  ],
  "questions": [],
  "blockers": [],
  "waiting": null,
  "paused_from": null,
  "checkpoint": {
    "last_completed": "完成90個唯一tuple與575次calls；原Oracle重評、hash/版本/模型一致性、50項回歸及最終報告審核通過",
    "current_action": "Main已整合完整證據；驗收A1-A3皆PASS，verification=PASS_WITH_WARNINGS（產品48/90通過）",
    "next_action": "保存COMPLETED研究狀態並回報群組與結果；產品失敗、pending/noDB/2次逾時等限制保留，不另行修復或重跑",
    "required_inputs": [],
    "unresolved_questions": []
  },
  "plan": {
    "solutions": [
      {
        "id": "S",
        "hypothesis": "H-SAMPLE",
        "root_cause": "固定種子分層抽30題且平衡View",
        "benefit": "涵蓋七View與SQL/語意難度，保留6項拒絕/歧義/安全案例",
        "scope": [
          "projects/retail/evaluations/test_groups"
        ],
        "complexity": "低",
        "cost": "離線預檢與90次本地模型生成",
        "risks": "非母體隨機估計且非從未見過的盲測",
        "verification": "可重現樣本、不重疊、原Oracle/hash、90筆唯一結果與呼叫完整核對",
        "falsification": "樣本重疊/依結果重抽/遺失失敗/執行中改來源",
        "rollback": "保留原資料，只另存新群組與本次紀錄"
      },
      {
        "id": "M",
        "hypothesis": "H-SAMPLE",
        "root_cause": "從剩餘381題均勻隨機抽30題",
        "benefit": "最少抽樣邏輯",
        "scope": [
          "projects/retail/evaluations/test_groups"
        ],
        "complexity": "低",
        "cost": "離線預檢與90次本地模型生成",
        "risks": "可能缺View、難度或安全案例",
        "verification": "可重現樣本、不重疊、原Oracle/hash、90筆唯一結果與呼叫完整核對",
        "falsification": "樣本重疊/依結果重抽/遺失失敗/執行中改來源",
        "rollback": "保留原資料，只另存新群組與本次紀錄"
      }
    ],
    "selected_solution": "S",
    "success": "群組不重疊可重現、完整90筆同版本測量與報告；不是要求產品90筆皆正確。",
    "failure": "名單污染、版本改動、漏失結果或未揭露中斷/失敗。",
    "regression": [
      "群組預檢",
      "既有評分與專案評估測試",
      "最終產物完整性及不可變輸入核對"
    ],
    "approval_required": false
  },
  "changes": {
    "scope": [
      "projects/retail/evaluations/test_groups/test_group_1.json",
      "projects/retail/evaluations/test_groups/test_group_2.json",
      "projects/retail/evaluations/test_groups/README.md"
    ],
    "revision": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
    "diff_fingerprint": "1c843050fcd699b19aff6641c0045e9b6fd8a92d1ea2329be9d68acb4d490f7c",
    "tests": [
      "evidence/EV-20261020T050600-34a5fb8c.json",
      "evidence/EV-20261020T050650-028f8d0d.json",
      "evidence/EV-20261020T092245-d11eb8ec.json",
      "evidence/EV-20261020T141420-2af1e9c8.json",
      "evidence/EV-20261020T141423-03800329.json",
      "evidence/EV-20261020T141613-15248dee.json"
    ]
  },
  "verification": {
    "result": "PASS_WITH_WARNINGS",
    "reviewer": "Main Agent；既有Oracle於fresh subprocess重評，未另啟Reviewer Agent",
    "method": "原Oracle重評90筆、90個唯一(case_id,repetition)、575次call關聯、原始segment封存hash、抽樣重現、版本/模型/settings/catalog/prompt/dataset不變、最終報告核對；50項既有回歸通過。",
    "verified_at": "2026-10-20T14:17:12.971868+00:00",
    "revision": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
    "diff_fingerprint": "1c843050fcd699b19aff6641c0045e9b6fd8a92d1ea2329be9d68acb4d490f7c",
    "tests": [
      "evidence/EV-20261020T050600-34a5fb8c.json",
      "evidence/EV-20261020T092245-d11eb8ec.json",
      "evidence/EV-20261020T141420-2af1e9c8.json",
      "evidence/EV-20261020T141423-03800329.json",
      "evidence/EV-20261020T141613-15248dee.json"
    ],
    "regression": [
      "evidence/EV-20261020T050650-028f8d0d.json"
    ],
    "unverified": [
      "案例pending且為draft契約，屬探索性評估",
      "未執行DB或驗證實際數值",
      "30題來自已知395題，非從未見過的盲測",
      "本輪只測group2，沒有新增group1修復版執行",
      "曾遇provider逾時，中斷後只接續未做項目；逾時保留失敗且未重試",
      "Main依原Oracle於fresh subprocess重評，未另啟Reviewer Agent"
    ],
    "warnings": [
      "研究測量完整，不代表產品通過：48/90符合原預期，42次不符合；16題3/3，14題0/3。",
      "生成狀態29/30題一致；13題SQL皆相同，其中1題為一致錯誤View，不計正確。",
      "2次provider ReadTimeout保留失敗；共3個segment，無tuple重試；2次health診斷另計。",
      "正式狀態88次pending、2次逾時無結果；未核准正式通過。"
    ],
    "blocking_issues": []
  },
  "completion_summary": "group1固定原14題；group2另30題各3次共90筆已完成且版本/模型/樣本/Oracle未變。48/90符合原預期，16題3/3、14題0/3；狀態29/30一致，13題SQL一致但含1題錯View；2次逾時保留未重試。50項回歸與最終重評/完整性/報告審核通過。研究完成，非產品全通過；pending draft，無DB數值驗證，本輪未重跑group1。",
  "history": [
    {
      "from": null,
      "to": "CREATED",
      "at": "2026-10-20T05:04:08+00:00",
      "reason": "初始化"
    },
    {
      "from": "CREATED",
      "to": "INVESTIGATING",
      "at": "2026-10-20T05:04:08+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "INVESTIGATING",
      "to": "PLANNING",
      "at": "2026-10-20T05:06:25+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "PLANNING",
      "to": "EXPERIMENTING",
      "at": "2026-10-20T05:06:25+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "EXPERIMENTING",
      "to": "IMPLEMENTING",
      "at": "2026-10-20T05:06:49+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "IMPLEMENTING",
      "to": "VERIFYING",
      "at": "2026-10-20T05:07:43+00:00",
      "reason": "",
      "paused_from": null
    },
    {
      "from": "VERIFYING",
      "to": "COMPLETED",
      "at": "2026-10-20T14:17:29+00:00",
      "reason": "固定群組與90次測量研究完成；全部驗收有當前證據，Main已核對報告；產品48/90通過及未驗證範圍完整揭露",
      "paused_from": null
    }
  ]
}
---
# 任務：retail-test-group-2

## 目標

固定14題為test group 1，抽取不重複30題test group 2，各3次真實模型穩定性測試並完整記錄成功與失敗

## 問題定義（預期／實際／證據／未確認假設）

{
  "description": "目前14題未有固定group名稱；需額外30題各3次驗證當前v10的泛化與穩定性。",
  "expected": "固定group1原14題；group2新30題不重複、3次共90筆完整記錄，分開正確率/一致性/HILP/正式核准。",
  "actual": "已固定group1原14題與group2另30題；v10各3次合計90筆完成，48通過/42未符合原預期，16題三次全通過、14題三次全失敗。",
  "evidence": [
    "projects/retail/evaluations/test_groups/test_group_1.json",
    "projects/retail/evaluations/test_groups/test_group_2.json"
  ],
  "hypotheses": [
    {
      "id": "H-SAMPLE",
      "claim": "固定種子分層可得到不重疊且覆蓋七View、各難度的30題樣本",
      "status": "CONFIRMED",
      "evidence": [
        "evidence/EV-20261020T050600-34a5fb8c.json",
        "evidence/EV-20261020T141423-03800329.json"
      ]
    },
    {
      "id": "H-STABILITY",
      "claim": "目前v10對group2的正確率與三次一致性可由凍結90次測量，不能預設通過。",
      "status": "CONFIRMED",
      "evidence": [
        "evidence/EV-20261020T141420-2af1e9c8.json",
        "evidence/EV-20261020T141423-03800329.json",
        "evidence/EV-20261020T141613-15248dee.json"
      ]
    }
  ]
}

## 範圍

- projects/retail/evaluations/test_groups
- evidence-driven-dev/tasks/retail-test-group-2

## 限制

[
  "不修改產品、prompt、契約、原Oracle或依輸出重抽；保留所有失敗。",
  "不自動代選HILP；不執行DB；保留正式pending狀態；遇provider/rate limit停止新呼叫，不自動重跑。",
  "原有dirty變更保留；group1不自動重跑。"
]

## 驗收標準

[
  {
    "id": "A1",
    "description": "group1固定原14題、group2可重現抽30題且無重疊，留成員/題文/預期hash與來源歷史",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T050600-34a5fb8c.json",
      "evidence/EV-20261020T141423-03800329.json"
    ]
  },
  {
    "id": "A2",
    "description": "當前v10凍結執行group2各3次共90筆，全部成功/失敗與呼叫皆記錄，不把一致失敗算通過",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T092245-d11eb8ec.json",
      "evidence/EV-20261020T141420-2af1e9c8.json",
      "evidence/EV-20261020T141423-03800329.json"
    ]
  },
  {
    "id": "A3",
    "description": "產出每題3次正確率/狀態及SQL一致性、HILP狀態、正式核准狀態與限制，驗證版本及Oracle未變",
    "status": "PASS",
    "evidence": [
      "evidence/EV-20261020T141423-03800329.json",
      "evidence/EV-20261020T141613-15248dee.json"
    ]
  }
]

## 工作進度

[
  {
    "summary": "group1原14題與group2另30題已固定且無重疊，seed20261020可重現",
    "status": "DONE"
  },
  {
    "summary": "版本/原Oracle/設定/契約預檢通過，50項評分及專案回歸通過",
    "status": "DONE"
  },
  {
    "summary": "90筆測量及575次call完整保留，3個segment合併；2次逾時未重試",
    "status": "DONE"
  },
  {
    "summary": "Main核對全部原Oracle重評、版本與報告；48/90通過，風險與未驗證項目已揭露",
    "status": "DONE"
  }
]

## Subagent Registry

[]

## 實驗

[
  {
    "id": "EXP-001",
    "hypothesis_id": "H-SAMPLE"
  }
]

## 決策

詳見 [decisions.md](decisions.md)。
[
  {
    "id": "DEC-001",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "固定14題為group1、排除後以seed20261020分層抽30題為group2，各3次；凍結當前產品並保留所有失敗",
    "alternatives": [
      "均勻隨機30題但可能缺難度/安全覆蓋"
    ],
    "reason": "滿足額外不重疊樣本並覆蓋七View及各難度，不按模型輸出重抽。使用者已授權額外30題穩定性測試，沿用每題3次。",
    "risks": "新測試組仍來自已知395題，不能視為從未見過的盲測；本地模型需要數小時；無DB數值驗證。",
    "revisit": "服務錯誤停止新呼叫後依完整記錄處理；本輪完成後若要修復失敗另立任務，避免污染穩定性測量。",
    "references": [
      "evidence/EV-20261020T050600-34a5fb8c.json"
    ],
    "at": "2026-10-20T05:07:43+00:00"
  },
  {
    "id": "DEC-002",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "保留第22次ReadTimeout為失敗，檢查服務與指紋後只繼續原排程尚未執行的68次",
    "alternatives": [
      "重跑整輪或重試逾時tuple，會抹去原穩定性失敗",
      "放棄剩餘68次，無法完成使用者要求"
    ],
    "reason": "原run按規則停止；服務可連線且模型digest、source/settings/Oracle/sample未變；持續授權90次測量，接續不重試失敗且不改設定。",
    "risks": "provider逾時影響一題三次結果，報告單獨揭露；同來源多segment執行，不宣稱單次不中斷。",
    "revisit": "再次服務錯誤立即停止新呼叫並查明，不盲目重試，不改模型或timeout。",
    "references": [
      "evidence/EV-20261020T050649-113b0aec.json"
    ],
    "at": "2026-10-20T06:21:13+00:00"
  },
  {
    "id": "DEC-003",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "使用者明確選擇「等它結束」；等cpea_terms的decomposition工作釋出共享Ollama後，只接續67次未做測量",
    "alternatives": [
      "中斷另一輪測試，使用者未選擇且不執行"
    ],
    "reason": "使用者最新訊息「等它結束」，保留全部23筆與兩次服務逾時，避免共享推論互相影響。",
    "risks": "等待期間不送新的測試生成，總耗時較長；服務恢復後仍需核對model/source/Oracle。",
    "revisit": "另一輪程序結束或使用者改變優先順序後恢復；不自動重跑已做tuple。",
    "references": [
      "evidence/EV-20261020T062744-cb642387.json"
    ],
    "at": "2026-10-20T06:33:57+00:00"
  },
  {
    "id": "DEC-004",
    "status": "ACCEPTED",
    "source": "main-agent",
    "summary": "90次同版本測量完整，研究任務可完成；產品僅48/90符合原預期，不宣稱全部穩定或正式核准",
    "alternatives": [
      "依結果修改產品、Oracle或重試失敗，會污染本輪固定版本測量"
    ],
    "reason": "三個segment的90個唯一tuple及575次呼叫均完整，原Oracle重評及報告審核成功，產品與模型指紋一致；失敗42次原樣保留",
    "risks": "14題三次皆失敗；2次provider逾時；pending draft Oracle；無DB數值與盲測驗證；同Main以獨立程序驗證",
    "revisit": "未來修復需另立任務與新版本重測，不改寫本輪原始結果；group1其餘8題修復版仍未新增重跑",
    "references": [
      "evidence/EV-20261020T141423-03800329.json",
      "evidence/EV-20261020T141613-15248dee.json"
    ],
    "at": "2026-10-20T14:16:43+00:00"
  }
]

## 待使用者回答問題

[]

## 阻礙

[]

## Recovery Checkpoint

{
  "last_completed": "完成90個唯一tuple與575次calls；原Oracle重評、hash/版本/模型一致性、50項回歸及最終報告審核通過",
  "current_action": "Main已整合完整證據；驗收A1-A3皆PASS，verification=PASS_WITH_WARNINGS（產品48/90通過）",
  "next_action": "保存COMPLETED研究狀態並回報群組與結果；產品失敗、pending/noDB/2次逾時等限制保留，不另行修復或重跑",
  "required_inputs": [],
  "unresolved_questions": []
}

## 最終驗證

{
  "result": "PASS_WITH_WARNINGS",
  "reviewer": "Main Agent；既有Oracle於fresh subprocess重評，未另啟Reviewer Agent",
  "method": "原Oracle重評90筆、90個唯一(case_id,repetition)、575次call關聯、原始segment封存hash、抽樣重現、版本/模型/settings/catalog/prompt/dataset不變、最終報告核對；50項既有回歸通過。",
  "verified_at": "2026-10-20T14:17:12.971868+00:00",
  "revision": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "diff_fingerprint": "1c843050fcd699b19aff6641c0045e9b6fd8a92d1ea2329be9d68acb4d490f7c",
  "tests": [
    "evidence/EV-20261020T050600-34a5fb8c.json",
    "evidence/EV-20261020T092245-d11eb8ec.json",
    "evidence/EV-20261020T141420-2af1e9c8.json",
    "evidence/EV-20261020T141423-03800329.json",
    "evidence/EV-20261020T141613-15248dee.json"
  ],
  "regression": [
    "evidence/EV-20261020T050650-028f8d0d.json"
  ],
  "unverified": [
    "案例pending且為draft契約，屬探索性評估",
    "未執行DB或驗證實際數值",
    "30題來自已知395題，非從未見過的盲測",
    "本輪只測group2，沒有新增group1修復版執行",
    "曾遇provider逾時，中斷後只接續未做項目；逾時保留失敗且未重試",
    "Main依原Oracle於fresh subprocess重評，未另啟Reviewer Agent"
  ],
  "warnings": [
    "研究測量完整，不代表產品通過：48/90符合原預期，42次不符合；16題3/3，14題0/3。",
    "生成狀態29/30題一致；13題SQL皆相同，其中1題為一致錯誤View，不計正確。",
    "2次provider ReadTimeout保留失敗；共3個segment，無tuple重試；2次health診斷另計。",
    "正式狀態88次pending、2次逾時無結果；未核准正式通過。"
  ],
  "blocking_issues": []
}

## 完成摘要

group1固定原14題；group2另30題各3次共90筆已完成且版本/模型/樣本/Oracle未變。48/90符合原預期，16題3/3、14題0/3；狀態29/30一致，13題SQL一致但含1題錯View；2次逾時保留未重試。50項回歸與最終重評/完整性/報告審核通過。研究完成，非產品全通過；pending draft，無DB數值驗證，本輪未重跑group1。
