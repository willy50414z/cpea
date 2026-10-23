---
{
  "parent_task": "wrenai-semantic-decomposition",
  "agent_id": "wrenai_research",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "ab4c67a45fa7039379bcadd788af0ae83bb3630f",
  "assignment": "獨立查證官方 WrenAI 架構與版本、既有契約相容性、方案與分階段驗收",
  "allowed_scope": [
    "唯讀產品與官方來源；僅寫 research.md"
  ],
  "worktree": "/home/willy/code/cpea-wrenai",
  "platform_id": "/root/wrenai_research",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "已查證 pinned WrenAI v1 與現行 main，完成真 upstream 為主的隔離 worker 方案與待核准設計；未實作／安裝／真模型呼叫。",
    "findings": [
      "推薦 legacy/v1 ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc，原生 DBSchema/TableDescription/IntentClassification/DbSchemaRetrieval + 原生 providers；唯一新增 Wren BasicPipeline DraftPlanning extension 輸出 DecompositionDraft。",
      "upstream numpy/tiktoken 與 CPEA 衝突，package-mode=false；worker 是依賴隔離而非混合語意規劃。",
      "原生 LLM/embedding retries=3 與 repo rate-limit 規則衝突，需窄政策 patch 並測 transport attempts=1；原生 intent parser fallback 不能當正常分類。",
      "既有 validator 只保結構，原需求 conditions/population coverage 須獨立 evaluator oracle，對新需求不承諾完整語意保證。",
      "六個 sample 欄位與 SUM 能力已對 raw YAML/本 checkout SchemaCatalog 核對；30既有case pending且兩casefile fingerprint與現catalog不符。"
    ],
    "evidence": [
      "evidence-driven-dev/tasks/wrenai-semantic-decomposition/research.md",
      "docs/superpowers/specs/2026-10-23-wrenai-semantic-decomposition-design.md",
      "https://github.com/Canner/WrenAI/tree/ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc/wren-ai-service",
      "https://github.com/Canner/WrenAI/blob/f618d8d9848c3d6b617859e575bd560d50bcc04e/sdk/wren-langchain/src/wren_langchain/_toolkit.py"
    ],
    "changes": [
      "新增 research.md",
      "新增待核准設計；ownership 由 Main 後續明確擴充"
    ],
    "verification": {
      "official_refs": "git ls-remote + GitHub commit/raw source read",
      "sample_contracts": "七View raw YAML及正確PYTHONPATH SchemaCatalog讀取PASS",
      "encoding": "兩文件 UTF-8 無 BOM",
      "product_tests": "未重跑；Main 已提供本checkout focused 113 passed證據",
      "live_model_calls": 0
    },
    "blockers": [],
    "concerns": [
      "v1版本/結構MDL設計待使用者核准",
      "真測試LLM及embedding模型、Qdrant、總預算未指定，費用unknown",
      "既有oracle pending及fingerprint drift不可冒稱正式通過"
    ],
    "next_step": "Main 整合 builder check，將具體設計交使用者核准；核准後進 writing-plans，再按授權執行離線可行性及真實smoke。不得把研究交接完成誤稱產品實作完成。"
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
