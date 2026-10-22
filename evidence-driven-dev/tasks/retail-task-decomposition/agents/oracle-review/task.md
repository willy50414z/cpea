---
{
  "parent_task": "retail-task-decomposition",
  "agent_id": "oracle-review",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "b16d117a2a3168a61c3cdbd889fc0e54ab079625",
  "assignment": "獨立只讀審查通路oracle、日期metadata及唯一鍵等價；不委派實作",
  "allowed_scope": [
    "projects/retail/evaluations",
    "projects/retail/views",
    "evaluations/decomposition_grading.py"
  ],
  "worktree": "/home/willy/code/cpea_terms",
  "platform_id": "/root/oracle_review",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "已獨立定位通路範圍、metadata歧義及縮減grain風險",
    "findings": [
      "通路26缺明確範圍",
      "日期集合不代表同日，不可規避時間禁止聚合",
      "actual/final均須來源鍵證明"
    ],
    "evidence": [
      "reports/oracle-independent-review.md"
    ],
    "recommendation": "依需求補oracle，不無條件接受conditional pivot；補metadata及grain正負例。",
    "risks": [
      "metadata 日期集合只保留來源時間，不證明可跨日加總；混合日期估值不得宣稱同日總額。",
      "conditional pivot 與分通路列對零符合／未匹配來源的處理尚不可無條件視為等價。",
      "本次只讀審查 View／欄位／request 計畫，未驗證 SQL、DB 列數與實際資料時間。"
    ],
    "next_step": "由主 agent 保留時間與缺值限制，補 oracle 通路條件及 metadata／grain 正負例，依候選實驗與 holdout 證據進行驗收。",
    "diff_reference": "無產品 diff；只讀審查基準 b16d117a2a3168a61c3cdbd889fc0e54ab079625；證據 reports/oracle-independent-review.md。"
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
