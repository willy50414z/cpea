---
{
  "parent_task": "ollama-planning-mvp",
  "agent_id": "oracle-audit",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
  "assignment": "依提案獨立審核30題oracle、契約與評分盲點，不呼叫模型或修改原oracle",
  "allowed_scope": [
    "evidence-driven-dev/tasks/ollama-planning-mvp/agents/oracle-audit"
  ],
  "worktree": "/home/willy/code/cpea_terms",
  "platform_id": "/root/oracle_audit",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "原30題canonical oracle已限保守profile核准；MVP0歷史輸出另逐題審核為18安全完整/9真語意錯/3機械錯。MVP1十二筆完成後獨立審核B1與fresh v3均安全ready2/6，B1淨增0，未達門檻，不擴十題、不進Ollama。",
    "evidence": [
      "agents/oracle-audit/review-manifest.json",
      "agents/oracle-audit/oracle-audit.md",
      "agents/oracle-audit/grader-witnesses.json",
      "agents/oracle-audit/mvp0-b1-review.json",
      "agents/oracle-audit/mvp0-b1-review.md",
      "agents/oracle-audit/mvp1-semantic-review.json",
      "agents/oracle-audit/mvp1-semantic-review.md",
      "agents/oracle-audit/baseline-semantic-review.json",
      "agents/oracle-audit/baseline-semantic-review.md",
      "agents/oracle-audit/final-review-verification.json"
    ],
    "risks": [
      "原grader18/30與獨立安全18/30數字巧合：05/08/25自動過但不安全，04/06/17自動未過但核准等價；原14全域缺貨filter亦為不安全ready。",
      "MVP0 runtime拒絕7/12不等於oracle拒12/12；原15/19有主鍵JOIN證據的store_name FD被typed guard誤拒。",
      "MVP1 B1第07有真店粒度/整合鍵錯，14根聚合錯；09主要metadata雙角色機械error；28日期有FD冗餘但metadata角色不合法。不能把四個error都歸為純機械問題。",
      "MVP1 v3第09丟日維度是不安全ready；第14條件stock_status缺貨有契約等價、第28完整背景缺值政策正確，兩者獨立核准但原分不改。",
      "B1六個人工注入6/6僅編譯節點成功，不是自然抽取成績。完整Gate未執行、未達成；原oracle pending不回寫。"
    ],
    "next_step": "主agent整合本handoff與兩份逐題語意報告後，保留PLANNING/未達Gate。停止本B1升級，回離線研究分開處理語意選擇與結構角色一致性，先預定新版本及控制，不直接擴十題或呼叫Ollama。",
    "diff_reference": {
      "base_git_sha": "bc09c67fc4078501599c37e4cdfecdee40af2ef8",
      "scope": "evidence-driven-dev/tasks/ollama-planning-mvp/agents/oracle-audit",
      "product_changes_by_reviewer": false,
      "original_oracle_or_result_changes": false,
      "model_calls_by_reviewer": 0,
      "sql_db_calls_by_reviewer": 0
    },
    "blockers": []
  },
  "blockers": [],
  "question": null
}
---
# 獨立 Oracle 審核

採用 EDD 獨立驗證流程。已先讀父 Task、Checkpoint、MVP0/Gate、原30題與七View契約，核對HEAD及原JSONL狀態。審核者與主agent離線實作者為不同agent。

## 範圍及結果

- 依嚴格sidecar profile核准原30題canonical參考語意及題庫明列替代；原JSONL仍30 pending，沒有回寫追分。
- 每題含來源、欄位角色、條件、根/child粒度、母體、快照、零/缺值及整合形狀，並關聯case/catalog指紋。
- v_sales_detail複合唯一鍵與既有contract_review矛盾，以保守profile禁用該鍵的FD/count等價推導；明確COUNT DISTINCT與不依鍵的SUM可核准。
- metadata日期集合不解除跨日SUM(stock_qty)限制。原30題聚合庫存只有成本總額或條件商品計數，無此canonical矛盾。
- fresh subprocess重現六個grader盲點：五個錯誤變異仍automated_pass，一個不實COUNT等價task metrics仍true。另有一個合法基線。
- 無模型/網路/SQL/DB呼叫；未改產品、契約、oracle或其他agent紀錄。

## 交付

- [完整審核](oracle-audit.md)
- [逐題核准manifest](review-manifest.json)
- [離線grader見證](grader-witnesses.json)
- [報告驗證](artifact-verification.json)

## 限制與下一步

核准僅適用嚴格profile與已凍結指紋；未列新等價仍待審。原catalog為draft，不因此正式啟用。主agent須實際整合manifest並讓sidecar執行所有限制；現行grader單獨不具充分語意驗收力。模型新方案NOT_VERIFIED，完整Gate尚未執行，不可進Ollama。

## MVP0／MVP1 後續獨立審核

- [MVP0/B1離線審查](mvp0-b1-review.md)：兩個false-pass修正後重驗，允許六題研究，非完整Gate核准。
- [MVP1十二筆語意審查](mvp1-semantic-review.md)：B1安全ready2/6、fresh v3安全ready2/6，淨增0；B1不安全ready0、v3不安全ready1；B1來源/母體/root同時正確5/6，仍FAIL，不擴十題。
- [原30題逐題分類](baseline-semantic-review.md)：18安全完整、9真語意錯、3機械錯，0等價待審/資訊不足；原22ready中4不安全。
- [審核驗證](final-review-verification.json)：全部原分/raw/result保持，12筆raw/response/payload重播一致，沒有新增模型/SQL/DB呼叫或讀取Gate封存題文。

下一步：主agent整合後停止本版B1升級，回MVP0定位語意選擇與metadata角色一致性；不以本輪修後結果洗白首次成績，不進MVP2或Ollama。主Task不由本agent完成或改狀態。
