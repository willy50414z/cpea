---
{
  "parent_task": "fix-14-regressions",
  "agent_id": "mapping-audit",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "唯讀診斷 9 次 fields 缺分組欄位與聚合 COUNT/MAX 偏差；以原始評估 Replay 提出根因與泛用修正，不改 Oracle",
  "allowed_scope": [
    "src/cpea/workflows/text_to_sql",
    "evaluations",
    "tests"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/mapping_audit",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "已確認九次 group 維度漏列 fields 是 v10 草稿契約未 enforce；本地 append 正規化九筆全部 mapping/SQL pass。DAILY 原始六筆 COUNT/MAX 誤配全部可通過 assess hard validation，明確最大值被併入 uncertain business term，應於語意確認前拒絕並送既有同 View repair。",
    "next_step": "Main 實作 v10 group fields 正規化與明確聚合 suffix 的逐欄 hard validation；加入負面測試及原始回覆 replay，獨立處理 View 歧義。",
    "evidence": [
      "agents/mapping-audit/task.md",
      ".local/mapping-replay.py",
      ".local/mapping-replay.json",
      ".local/mapping-replay-output.txt"
    ],
    "risks": [
      "未執行真實 LLM 或 DB；尚無產品變更。",
      "原始案例 pending，View target 的 Oracle 不是已核准的業務事實。",
      "聚合擷取須保護已核准業務名稱、重複名詞與多指標操作的邊界。"
    ],
    "blockers": []
  },
  "blockers": [],
  "question": null
}
---
# Mapping 調查報告

## 任務與範圍

唯讀診斷原始 v10 14 題穩定性評估中的九次分組維度缺少 fields，以及 DAILY_SALES-M2-01 的 COUNT／MAX 偏差。讀取父 Task、決策、EDD investigate 與實際可讀的 Superpowers systematic-debugging。未修改產品、tests、Oracle、主 Task；未呼叫真實 LLM／DB。

版本 HEAD 為 `014cee1aff3abcfb51bbe5af6db0abd2ef060225`；工作樹啟動已有多個未提交檔案，因此本次證據針對目前工作樹，不把 HEAD 當作完整版本指紋。

## 輸入與可重現證據

原始目錄：`projects/retail/artifacts/evaluations/20261019T115951Z-qwen-v10-samples14-stability3`。

- `results.jsonl` 第 13–15、37–42 行：三題各三次，failure_reasons 僅 mapping_fields，SQL 通過。
- `calls.jsonl` 第 45、48、54、57、62、65 行：DAILY_SALES-M2-01 的 daily_sales／order_summary 原始 mapper 回覆，三次都把明確單列最大值轉為 count。
- 本地實驗：`.local/mapping-replay.py`、`.local/mapping-replay.json`、`.local/mapping-replay-output.txt`，執行命令 `.venv/bin/python evidence-driven-dev/tasks/fix-14-regressions/.local/mapping-replay.py`，最終 exit 0。JSON 保存兩個原始檔 SHA-256。
- 實驗準備中第一次漏填模型必填 having 而 exit 1；補齊空陣列後重跑。另第一次 grading 使用預設 MSSQL，產生 sql_compiled_structure；核對 rerun.py 與原 SQL 後改用原設定 PostgreSQL，九筆原始評分全部復現。兩者皆實驗設定修正，並非產品測試失敗或產品變更。

## 已確認發現

### F1：草稿欄位表示不一致，SQL 結果沒有少維度

`prompts/match/v10.txt:4` 明定 group 維度與指標皆須入 fields。九筆草稿卻只有兩個聚合指標，group 正確且完整：

| 案例 | 漏列於 fields 的 group 欄位 | 次數 |
|---|---|---:|
| INVENTORY_STATUS-H3-01 | region、category、stock_status | 3 |
| STORE_MONTHLY_KPI-H1-01 | sales_month、region、store_name | 3 |
| STORE_MONTHLY_KPI-M3-03 | city | 3 |

第一個偏差在 mapper 回傳草稿。伺服器沒有 enforce group 是 fields 子集；`sql_generation.py:454` 用 fields + group 建立 links，`_draft_plan:1161` 再將維度加到 SELECT，因此 SQL 補齊維度。grader 的 mapping_fields 比對精確欄位 multiset，SQL 獨立評分（`view_matching_grading.py:35–42`）。這是已明定的草稿契約未落實，不是資料查詢錯誤，也不是應改 Oracle 的證據。

可否證實驗：只在本地 Replay 把 group 中缺少的 column 以相同 text、aggregation=None append 至 fields，保留原 SQL／plan／其他 clauses；九筆均由 `(fail, pass, [mapping_fields])` 變成 `(pass, pass, [])`。若 append 導致 SQL／plan 改變或其他 grading 失敗，假設即不成立；本實驗未出現。

### F2：明確聚合操作被降級成待確認業務詞

原文為「成交訂單數的單列最大值」。daily_sales 輸出 text=成交訂單數、column=order_count、aggregation=count；order_summary 輸出同名 text、column=order_id、aggregation=count。六筆原始回覆經目前 `assess` Replay 全部 hard_errors=[]，未觸發同 View repair。

`semantics.py:153` 只覆蓋 typed aggregation 自己的詞；未知的最大值留在 uncovered。`:245` 將毗鄰 gap 合併到 use.term，得到「成交訂單數的單列最大值」，當作需要欄位語意確認的業務詞。`_resolve_clarifications:851` 明定不改 query clauses，故選項只能確認欄位，無法修正 count。這不是單純模型隨機誤差；模型誤解是輸入源，伺服器讓明確操作缺失經過語意確認而未 hard reject 是可重現的驗證缺口。

對照實驗：正確 max 不論 text 是短名詞或含完整 suffix 均可通過；單純「列出已完成訂單筆數」aggregation=None 通過。另以已核准完整名稱測試 count + 最大值時可能已有 uncovered hard error；原始非逐字語意別名則被併入 uncertain，說明目前錯誤是否被拒絕取決於 span／alias 形狀，並不是可靠的操作一致性檢查。

### 真 Bug 與 Oracle／需求歧義邊界

- F1 違反 v10 明文契約，但原 SQL 沒少欄位。不得把 mapping fail 描述成 SQL 功能失敗。
- F2 不依賴 expected_match，即可由原文的明確最大值與實際 count 證明偏差。
- 原始案例均 review_status=pending；僅因 expected target=daily_sales 不能證明另一來源必定錯。原文未明定篩選資料應為每訂單或門市每日總量，View 澄清是否合理由 view-audit／Main 處理。聚合驗證修補不能據此保證 DAILY 三次端到端全過。

## 建議最小泛用方案

### S：v10 草稿正規化 + 明確操作 hard validation（建議）

1. 僅對合法選定單一 View、原 fields 非空的 v10 草稿，依 group 順序 append 缺少的 column，text 原樣且 aggregation=None。以 column 判斷是否存在，保留原 fields 順序、聚合與 terms index；不覆寫既有聚合欄位、不補 criteria/order。不把原本拒絕的 table=null／fields=[] 草稿變成可用。讓 trace、clause_mapping 與後續編譯使用同一正規化結果。這與既有 fields+group SQL 建構一致。
2. 在業務詞確認前，比對每個 fields／having 的明確聚合 syntax 與 typed aggregation；不符時 hard error 進既有同 View repair。只拒絕，不直接把 count 改成 max。修補後仍須正常契約／grain／能力驗證。

操作擷取建議：優先處理逐字 item.text 的所有 occurrence；檢查 text 自身結尾及緊接其後、同一子句內的明確運算 suffix。候選詞最長優先（單列最大值優先於最大值；count_distinct 優先於 count）；可容忍空白與連接「的」，不可跨逗號、指標連接詞或其他欄位。保留匹配區間，避免只從完整 request 搜到 MAX 就綁給每個 field。重複名詞有多個不同操作時保守報不一致或歧義，不能取第一個任意匹配。已核准完整名稱內的「筆數」「平均」「最高」不能自動當成跨列操作，尤其不得以筆數推定 count。若採較廣泛的 AGGREGATIONS 字典，必須先界定業務名稱與外部 suffix 邊界；初期至少對帶明確「單列最大值／單列最小值」的 suffix 保證 fail closed。

### M：缺少 group fields 一律送 repair

能維持原始模型輸出的 trace 意義，但增加模型呼叫與延遲，且 deterministic 可修的結構仍有模型不遵循風險。除非產品明確要求 MappingAttempt 永遠逐字保留原始草稿，否則不優於 S。現有原始 calls 已可保留模型輸出稽核。

### L：引入完整 request AST／操作 evidence schema

可全面處理聚合、group、order 關聯，但超出本次最小修復。若後續出現錯配操作／重複欄位多聚合等一般案例，再升級。

## Main 實作應加入的負面測試

| 類別 | 輸入／草稿 | 必須維持 |
|---|---|---|
| fields 正規化 | 多個 group 漏列、已有部分維度 | 只補缺少 column，無重複，保留順序與 null |
| fields 正規化 | 既有 group 欄位帶聚合 | 不覆寫成 null，仍被 dimension aggregation guard 拒絕 |
| fields 正規化 | filter-only／order-only 欄位 | 不新增至 fields |
| fields 正規化 | table=null 或 fields=[] 的拒絕草稿 | 不被補成可查詢草稿 |
| 聚合 | A合計與B的單列最大值；B=count／null | B hard error；A 的 SUM 不得替 B 提供證據 |
| 聚合 | A合計與B的單列最大值；A=max／B=sum | 逐欄都檢查，不能以全句出現 SUM/MAX 放行 |
| 聚合 | 正確 B=max，text 只給 B 或完整 suffix | 皆通過，syntax 不保存進 business term |
| 聚合 | 列出已完成訂單筆數，aggregation=None | 通過，不自動 count |
| 聚合 | 已核准名稱本身含「平均」「最高」「最大值」 | 無外部操作時不誤判 |
| 聚合 | 相同 B 出現於兩個不同位置，分別 max／min | 不任取第一個 occurrence；不跨欄或跨子句取證 |
| 聚合 | max 不在該欄能力內 | 仍由 catalog 拒絕，不因 request 明確而放行 |
| 聚合 | 第一草稿錯 count、同 View repair 給 max | 恰走既有有限 repair，仍驗證所有 clauses |

## 風險與未驗證

本次完成的是根因及局部方案 Replay。沒有產品實作、正式新增 tests、真實模型重測或 DB 執行，不能宣稱產品修復或模型穩定性改善。九筆正規化只驗證語義等價與原 Oracle grading，尚須 Main 加入產品流程測試。聚合 extraction 提案尚未實作，對自然語言語法覆蓋與已核准業務名稱保護須以負面測試界定。Main 需保存當前 dirty 工作樹正式版本指紋，避免把 Replay 與之後實作混淆。

## 變更檔案

僅本 Report 與 `.local/mapping-replay.py`、`.local/mapping-replay.json`、`.local/mapping-replay-output.txt`、`.local/mapping-handoff.json`。

## Handoff

請 Main 整合 F1／F2，依 S 方案正式實作並新增產品與負面測試；以原始回覆作離線 Replay，並獨立處理 View／Oracle 歧義。
