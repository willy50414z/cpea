---
{
  "parent_task": "decomposition-schema-mapping",
  "agent_id": "mapping_review",
  "role": "subagent",
  "status": "FAILED",
  "base_git_sha": "095b6125623af5b9ade6914a6a83444e3d704b57",
  "assignment": "獨立核心與整體程式審查、驗收與回歸核對",
  "allowed_scope": [
    "只讀新入口實作與測試，可執行focused與/tmp holdout，不改產品檔"
  ],
  "worktree": "/home/willy/code/cpea_terms",
  "platform_id": "/root/mapping_review",
  "handoff": {
    "status": "FAILED",
    "summary": "原核心與獨立入口已自行驗證 156 passed；三個草稿反例（局部期間條件、未限時關聯任務、最終遺失必要粒度）與 token counter 原始例外問題均已交實作者修正並重驗。另發現 retrieval literal 誤釘來源，已交修。retrieval 最終完整驗收因 capacity 中止；mapping_final_review 已接替完成 173 passed 與全鏈 PASS_WITH_WARNINGS，本代理不重複宣稱該接替驗證為自身證據。",
    "next_step": "Main 以明確 disposition 整合本代理已完成發現、capacity 中止狀態，以及 mapping_final_review 的最終驗收證據。",
    "evidence": [
      "/tmp/cpea_mapping_review_holdouts.py",
      "/tmp/cpea_mapping_review_core_fingerprints.json",
      "/tmp/cpea_mapping_review_final_fingerprints.json",
      "/tmp/cpea-schema-mapping-counter-red.txt",
      "/tmp/cpea-schema-mapping-focused-green.txt",
      "/tmp/cpea-schema-mapping-retrieval-integration-green.txt",
      "evidence-driven-dev/tasks/decomposition-schema-mapping/.local/reviewer-capacity.txt"
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
