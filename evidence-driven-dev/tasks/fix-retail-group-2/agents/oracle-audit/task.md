---
{
  "parent_task": "fix-retail-group-2",
  "agent_id": "oracle-audit",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "唯讀分類group2的Oracle/需求歧義/環境問題，核對14失敗題原契約及題庫，不修改Oracle，不呼叫模型",
  "allowed_scope": [
    "projects/retail"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/oracle_audit",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "完成14題Oracle／契約唯讀調查及離線probe：6題確定產品行為Bug，2題列條件Bug兼粒度歧義，3題合理澄清，1題有2次環境逾時兼語意歧義，2題安全拒絕成功但raw mapping診斷FAIL。原Oracle與48/90均保留。",
    "evidence": [
      "agents/oracle-audit/task.md",
      "../../../projects/retail/evaluations/cases.jsonl",
      "../retail-test-group-2/.local/combined-group2-20261020/results.jsonl",
      "../retail-test-group-2/.local/combined-group2-20261020/calls.jsonl"
    ],
    "risks": [
      "合法SQL不保證題文唯一View；不得以14題都ready原target驗收。",
      "CUSTOMER S3-03回購與active、期間消費與lifetime存在語意差異。",
      "未執行模型、DB、SQL編譯或全395題回歸；產品根因程式位置由Main/source-audit核對。"
    ],
    "next_step": "Main讀取逐題證據後整合：保留原Oracle，分列safe reject與raw mapping；優先原call replay驗證6個確定Bug及2個guard症狀，保留含糊題澄清與反例回歸。",
    "diff_reference": "evidence-driven-dev/tasks/fix-retail-group-2/agents/oracle-audit/task.md（僅報告；無產品／tests／Oracle變更）"
  },
  "blockers": [],
  "question": null
}
---
# Oracle 與需求契約調查

## 範圍與結論

父任務fix-retail-group-2；oracle-audit唯讀基準SHA為`014cee1aff3abcfb51bbe5af6db0abd2ef060225`。已依EDD investigate閱讀父Task、舊Task/decisions/final-report、題庫與七View契約、原calls/results及原grader。未修改產品、tests、Oracle、契約、原測量或主Task；零模型呼叫、零DB執行。題庫為pending draft，validated不等於正式核准。

14題分類：6題確定產品行為Bug（ORDER S1-01/M3-01、CUSTOMER S2-02/H1-02、STORE_MONTHLY H3-01、INVENTORY H3-05）；2題列條件Bug兼有粒度歧義（DAILY M1-05/M3-05）；3題合理澄清、唯一View預期過強（PRODUCT S2-05/M3-04、DAILY S3-03）；1題有2次環境逾時兼回購語意問題（CUSTOMER S3-03）；2題安全拒絕成功但raw mapping診斷FAIL（兩邊界題）。**不能以14題都直接ready原指定View作成功標準。** 原48/90、42次FAIL全部保留，本報告不重評或替換Oracle。

## 可追溯來源

- [題庫](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl)：各節附實際行號、完整題文、預期。
- [原結果](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl)：各節附三次行號。結果call_ids可連回[原calls](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/calls.jsonl)。
- 契約：[sales_detail](/home/willy/code/cpea/projects/retail/views/demo_retail/v_sales_detail.yaml)、[order_summary](/home/willy/code/cpea/projects/retail/views/demo_retail/v_order_summary.yaml)、[daily_sales](/home/willy/code/cpea/projects/retail/views/demo_retail/v_daily_sales.yaml)、[product_monthly](/home/willy/code/cpea/projects/retail/views/demo_retail/v_product_monthly.yaml)、[customer_value](/home/willy/code/cpea/projects/retail/views/demo_retail/v_customer_value.yaml)、[store_monthly_kpi](/home/willy/code/cpea/projects/retail/views/demo_retail/v_store_monthly_kpi.yaml)、[inventory_status](/home/willy/code/cpea/projects/retail/views/demo_retail/v_inventory_status.yaml)。每節指出grain及具體欄位description依據。
- [原grader:21](/home/willy/code/cpea/evaluations/view_matching_grading.py:21)：normal取selected_mapping_index；non-normal取最後非空mapping、不篩outcome；非正常題SQL通過條件為supported=false且無SQL/plan。

## 實際離線Probe

`PYTHONPATH=src .venv/bin/python`唯讀腳本載入原case、YAML及原grader，未連模型或DB。結果：

1. 12個normal expected_sql的select/filter/group/order欄位皆存在，聚合未列入disallowed：12/12 PASS。僅證明指定target的契約結構可行，未證明題文唯一，未執行SQL編譯或DB數值驗證。
2. 以原raw mapping及原case型別重播兩邊界grader，皆精確得到`('fail', 'pass', ['mapping_view', 'mapping_fields'])`。證實安全PASS與草稿FAIL可同時成立。
3. 純Python粒度反例：折扣明細60、60，明細>=100無資料但月列120符合；明細/日列100、200之MAX=200，月列300之MAX=300。
4. 契約反例：會員只有一張兩日前完成單，active=true卻不代表回購。

SHA256：

```text
cases.jsonl 4160a4b229483f9286f501d1504c08c2f4decbedcfd122812bacd884f1625cf9
view_matching_grading.py eded80bce4b948063784d0784c1e8de2bd6bc5edfc28be93b95837a3db33a1f5
原results.jsonl a03e654840fa04223b3dcf25ba6a1a3ad58bdd551d8ce7972ed2460a3ad69981
原calls.jsonl 8ceba4c4a427b3a3b972e61ed153bf9f2798be11ced2cd0ec7fecce976da9aed
```

## 逐題核對

以下建議驗收不替換原Oracle。精確程式根因交Main/source-audit核對，不把觀察症狀當已證實的程式根因。

### RETAIL-CUSTOMER_VALUE-S2-02

題文（[行7](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:7)）：幫我看每列的所在城市、累計花費，條件是最近下單日期 >= 2026-01-01。

原target：`demo_retail.v_customer_value`；三次狀態`ready、ready、ready`；結果行[13](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:13)、[14](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:14)、[15](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:15)。原預期：

```json
{"aggregations": {}, "filters": [{"column": "last_order_date", "operator": ">=", "value": "2026-01-01"}], "group_by": [], "having": [], "order_by": [], "select_columns": ["city", "lifetime_spend"]}
```

**確定產品行為Bug；唯一直接合法View為customer_value。** 原ready卻選sales_detail，將「最近下單日期」偷換order_date、「累計花費」偷換SUM(net_sales)，且依store_city分組，改了最近一單的篩選、累計範圍、城市對象與每列粒度。應ready原Oracle、不自動SUM/GROUP BY。反例：會員有較早與較晚訂單，應用全期lifetime_spend、再以last_order_date過濾，而非只累計2026年後交易。契約customer_value.city明示不是交易門市所在地；sales_detail.store_city明示不是會員居住城市。

### RETAIL-CUSTOMER_VALUE-S3-03

題文（[行13](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:13)）：我想看逐筆的最近90日有沒有再回來買、涵蓋期間實際花掉的錢，條件是會員叫什麼 LIKE 王%。

原target：`demo_retail.v_customer_value`；三次狀態`error、error、unsupported`；結果行[22](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:22)、[23](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:23)、[24](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:24)。原預期：

```json
{"aggregations": {}, "filters": [{"column": "customer_name", "operator": "LIKE", "value": "王%"}], "group_by": [], "having": [], "order_by": [], "select_columns": ["active_in_last_90d", "lifetime_spend"]}
```

**2次環境逾時＋1次語意歧義；不能全算映射Bug。** rep1 ReadTimeout約400558ms、rep2約300633ms，沒有generation。rep3第一個schema_match call `29a2da625dad4ce795098c5d8a5f0b3f`已產生完全符合原Oracle mapping，後續grain/meaning guard拒絕。「再回來買」可能指回購，active_in_last_90d只保證最近90日任一已完成單；「涵蓋期間實際花掉的錢」也未明示全期。「逐筆」可能是會員或交易。建議澄清近90日任一下單或回購、全期或期間消費；不可直接弱化guard。反例：首次購物兩日前完成者active=true，但未回購。既有S1-03寫「最近90日活躍狀態、累計折扣後消費金額」，S2-03寫「近90日是否有下單、累計花費」，與S3-03不保證語意等價。逾時保留、分列，勿重跑抹去原失敗。

### RETAIL-CUSTOMER_VALUE-H1-02

題文（[行32](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:32)）：依會員等級、城市、最近90日活躍狀態分組，顯示累計折扣後消費金額合計與已完成訂單筆數的單列最大值，限定最後訂單日期 >= 2026-01-01且會員名稱 LIKE 王%且平均每筆已完成訂單消費額 >= 100，依會員等級排序。

原target：`demo_retail.v_customer_value`；三次狀態`unsupported、unsupported、unsupported`；結果行[52](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:52)、[53](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:53)、[54](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:54)。原預期：

```json
{"aggregations": {"completed_order_count": "max", "lifetime_spend": "sum"}, "filters": [{"column": "last_order_date", "operator": ">=", "value": "2026-01-01"}, {"column": "customer_name", "operator": "LIKE", "value": "王%"}, {"column": "avg_order_value", "operator": ">=", "value": 100}], "group_by": ["membership_tier", "city", "active_in_last_90d"], "having": [], "order_by": ["membership_tier"], "select_columns": ["membership_tier", "city", "active_in_last_90d", "lifetime_spend", "completed_order_count"]}
```

**確定產品行為Bug；唯一完整合法View為customer_value。** 首次mapping錯把已預算avg_order_value>=100放入HAVING AVG(avg_order_value)，正確觸發契約disallowed_aggregations=[sum,avg]；repair遂宣告unsupported。題目普通「限定平均每筆已完成訂單消費額>=100」可在會員列WHERE過濾，再依等級/城市/active分組，未要求群組平均。應ready原Oracle、avg_order_value僅criteria，不移除AVG禁令。反例「群組平均客單價>=100」不得用AVG預算比率。H2-02/H3-02為相同Oracle變體。原call系統prompt已明示「欄位本身表示統計值不代表要再聚合」「有分組或指標不代表普通門檻變成having」。

### RETAIL-CUSTOMER_VALUE-B-02

題文（[行47](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:47)）：請從 demo_retail.v_customer_value 列出 快照日期。

原target：`demo_retail.v_customer_value`；三次狀態`unsupported、unsupported、unsupported`；結果行[76](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:76)、[77](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:77)、[78](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:78)。原預期：

```json
{"criteria": [], "fields": [], "group": [], "having": [], "ignored": [], "order": [], "table": null, "unsupported_reason": "指定 View 沒有 snapshot_date 欄位。"}
```

**安全拒絕符合契約；raw rejected mapping診斷仍失敗。** 指定customer_value但要求snapshot日期，無合法SQL；契約只有註冊日期/最近訂單日期。原Oracle table=null、fields=[]合理。實際raw mapping錯提registered_on，但兩日期options均same_concept=false，後續拒絕、最終unsupported、無SQL/plan。原grader對non-normal抓最後非空mapping而不看outcome，故評rejected草稿mapping_view/fields FAIL。安全已攔截，不能說錯SQL漏出；亦不能說mapping品質正確。建議保留原FAIL、另列SQL/safety PASS；產品宜明確說來源無快照欄，不暗示註冊日期可替代。改draft需泛化不存在欄位不猜相似欄位，不清空trace。既有DAILY-B-03/PRODUCT-B-02同型。

### RETAIL-DAILY_SALES-S3-03

題文（[行70](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:70)）：我想看逐筆的城市別、賺到的毛利，條件是折扣後進帳 >= 100。

原target：`demo_retail.v_daily_sales`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[19](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:19)、[20](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:20)、[21](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:21)。原預期：

```json
{"aggregations": {}, "filters": [{"column": "revenue", "operator": ">=", "value": 100}], "group_by": [], "having": [], "order_by": [], "select_columns": ["city", "gross_profit"]}
```

**需求歧義／daily唯一Oracle無足夠題文依據。** 「逐筆」沒有指明門市日列；sales_detail、order_summary可直接輸出城市、毛利及淨額條件，卻分別是品項列與訂單列。daily_sales為門市×日期，store_monthly_kpi則是門市×月份。原澄清的兩來源確實不同；daily被拒理由為日匯總不能保證逐筆明細，不能只因有欄位就強制daily。應先澄清逐筆指訂單、品項或日列，明示每日後才ready daily。契約各View.grain與金額欄description構成反例。

### RETAIL-DAILY_SALES-M1-05

題文（[行77](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:77)）：依門市識別碼分組，顯示折扣後銷售淨額合計與銷售件數的單列最大值，限定城市 = 臺北且已完成訂單筆數 >= 1且毛利總額 >= 100，依門市識別碼排序。

原target：`demo_retail.v_daily_sales`；三次狀態`unsupported、unsupported、unsupported`；結果行[25](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:25)、[26](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:26)、[27](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:27)。原預期：

```json
{"aggregations": {"revenue": "sum", "units_sold": "max"}, "filters": [{"column": "city", "operator": "=", "value": "臺北"}, {"column": "order_count", "operator": ">=", "value": 1}, {"column": "gross_profit", "operator": ">=", "value": 100}], "group_by": ["store_id"], "having": [], "order_by": ["store_id"], "select_columns": ["store_id", "revenue", "units_sold"]}
```

**列條件／聚合門檻拒絕Bug，兼有日/月粒度歧義。** 原trace先將order_count>=1、gross_profit>=100放HAVING，遭「未明示aggregate threshold；請用criteria」；repair後criteria又遭「aggregate threshold cannot be a WHERE criterion」。既有統計欄位不代表再聚合，GROUP BY也不使普通門檻變HAVING，合法列條件不應兩邊互斥拒絕。但daily與store_monthly有相同欄位，單列MAX(units_sold)尺度不同，題目沒明示每日。應修正子句一致性，保留明確聚合門檻防線；整題仍可澄清每日或每月，不能把直接daily ready作唯一成功。反例日列100、200的MAX=200，月列300的MAX=300。既有M2-05同樣沒明示日；M1-01明示依銷售日期分組。

### RETAIL-DAILY_SALES-M3-05

題文（[行87](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:87)）：整理報表時照門市的編號分組，顯示折扣後進帳合計與成交商品有幾件的單列最大值，限定城市別 = 臺北且完成了幾筆單 >= 1且賺到的毛利 >= 100，依門市的編號排序。

原target：`demo_retail.v_daily_sales`；三次狀態`unsupported、unsupported、unsupported`；結果行[46](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:46)、[47](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:47)、[48](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:48)。原預期：

```json
{"aggregations": {"revenue": "sum", "units_sold": "max"}, "filters": [{"column": "city", "operator": "=", "value": "臺北"}, {"column": "order_count", "operator": ">=", "value": 1}, {"column": "gross_profit", "operator": ">=", "value": 100}], "group_by": ["store_id"], "having": [], "order_by": ["store_id"], "select_columns": ["store_id", "revenue", "units_sold"]}
```

**列條件／聚合門檻Bug，兼有日/月粒度歧義。** 與M1-05同Oracle結構。原daily候選先未承接1/100，repair把完成單數及毛利門檻放HAVING又拒；其他來源有context budget limitation，不能據此推論daily無合法SQL。應以原call replay修列條件承接、保留明確合計門檻防線；整題可澄清日或月，明示每日才應ready原daily結構。M1-05/M2-05為既有其他表述，不能按詞「完成了幾筆單」硬改。日/月MAX反例同前。

### RETAIL-INVENTORY_STATUS-H3-05

題文（[行158](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:158)）：整理報表時照南北區域別、商品屬於哪一類、缺貨還是需要補貨分組，顯示這批庫存的成本值合計與依近30日銷量估算還能賣幾天的單列最大值，限定庫存是哪一天盤的 = 2026-10-14且賣的是哪種商品 LIKE 茶%且商品庫存代碼 LIKE SKU-%，依南北區域別排序。

原target：`demo_retail.v_inventory_status`；三次狀態`unsupported、unsupported、unsupported`；結果行[70](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:70)、[71](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:71)、[72](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:72)。原預期：

```json
{"aggregations": {"estimated_days_of_supply": "max", "inventory_cost_value": "sum"}, "filters": [{"column": "snapshot_date", "operator": "=", "value": "2026-10-14"}, {"column": "product_name", "operator": "LIKE", "value": "茶%"}, {"column": "sku", "operator": "LIKE", "value": "SKU-%"}], "group_by": ["region", "category", "stock_status"], "having": [], "order_by": ["region"], "select_columns": ["region", "category", "stock_status", "inventory_cost_value", "estimated_days_of_supply"]}
```

**確定產品行為Bug；唯一完整合法View為inventory_status。** 原有合法SUM成本與MAX可售天數及三個篩選，卻因「依近30日銷量估算」中的30兩次遭unmapped request literals:30。第二mapping嘗試ignored近30日也被拒，不應以丟文字修復。契約summary與estimated_days_of_supply.description已明示近30日、stock_qty×30/sold_qty_30d。應ready，30作為契約固有視窗，不新增WHERE或重算公式；必須依完整欄位語意承接。反例近60日估算／最近30日營收>=100不得套通用忽略數字。H1-05/H2-05同Oracle卻不含30，不能只測該兩變體。

### RETAIL-INVENTORY_STATUS-B-05

題文（[行163](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:163)）：請從 demo_retail.v_inventory_status 查詢即時更新的庫存可售金額。

原target：`demo_retail.v_inventory_status`；三次狀態`unsupported、unsupported、unsupported`；結果行[85](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:85)、[86](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:86)、[87](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:87)。原預期：

```json
{"criteria": [], "fields": [], "group": [], "having": [], "ignored": [], "order": [], "table": null, "unsupported_reason": "契約沒有即時庫存可售金額語意。"}
```

**安全拒絕符合契約；raw rejected mapping診斷仍失敗。** 題目要即時庫存可售金額，契約inventory_cost_value明示成本估值、不是預估銷售額；snapshot也不保證即時，故無完整合法SQL。原Oracle空mapping合理。raw草稿錯提成本欄位但same_concept=false，後續guard拒絕，最終unsupported無SQL/plan；原grader仍取rejected草稿造成mapping FAIL。應保持拒絕或澄清口徑/更新頻率，不輸出成本冒充銷售估值。保留原FAIL、另列安全PASS，勿按題號清空草稿。DAILY-B-05/PRODUCT-B-05有同型題；此View有相似金額欄更需反例。

### RETAIL-ORDER_SUMMARY-S1-01

題文（[行170](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:170)）：列出訂單成立月份、訂單折扣後總金額，條件是訂單成立日期 >= 2026-07-01。

原target：`demo_retail.v_order_summary`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[4](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:4)、[5](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:5)、[6](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:6)。原預期：

```json
{"aggregations": {}, "filters": [{"column": "order_date", "operator": ">=", "value": "2026-07-01"}], "group_by": [], "having": [], "order_by": [], "select_columns": ["order_month", "order_amount"]}
```

**確定產品行為Bug；唯一直接合法View為order_summary。** 題目「訂單折扣後總金額」要求整單order_amount；sales_detail.net_sales僅為商品明細額。原兩候選澄清接受了錯粒度來源。應ready原Oracle且不增加GROUP BY。反例：一張訂單有兩個品項，任一品項net_sales都不代表整單總額。同組SALES_DETAIL-S1-01有「折扣後銷售金額」但無「訂單…總金額」且已通過；不可抹除此差異。契約：order_summary.grain及order_amount；sales_detail.grain、order_id重複及net_sales。

### RETAIL-ORDER_SUMMARY-M3-01

題文（[行195](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:195)）：整理報表時照訂單落在哪個月分組，顯示每張訂單折扣後的錢合計與每張單買了幾件的單列最大值，限定訂單發生的那一天 >= 2026-07-01且哪一家店 LIKE 中山%且會員叫什麼 LIKE 王%，依訂單落在哪個月排序。

原target：`demo_retail.v_order_summary`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[43](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:43)、[44](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:44)、[45](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:45)。原預期：

```json
{"aggregations": {"order_amount": "sum", "total_quantity": "max"}, "filters": [{"column": "order_date", "operator": ">=", "value": "2026-07-01"}, {"column": "store_name", "operator": "LIKE", "value": "中山%"}, {"column": "customer_name", "operator": "LIKE", "value": "王%"}], "group_by": ["order_month"], "having": [], "order_by": ["order_month"], "select_columns": ["order_month", "order_amount", "total_quantity"]}
```

**確定產品行為Bug；唯一直接合法View為order_summary。** 每張訂單折扣後金額、每張單買幾件的單列MAX，明示整單粒度；order_amount/total_quantity可承接。sales_detail.net_sales/quantity是品項級，不能代表整單件數MAX。應ready原Oracle，SUM(order_amount)、MAX(total_quantity)且保留三列條件。反例：一張訂單有品項件數2與3，整單5不能由MAX(quantity)=3替代。同組ORDER_SUMMARY-M2-03已ready。契約sales_detail.grain=(order_id,product_id)，order_summary.grain=(order_id)。

### RETAIL-PRODUCT_MONTHLY-S2-05

題文（[行235](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:235)）：幫我看每列的店名、實際銷售額，條件是折讓金額 >= 100。

原target：`demo_retail.v_product_monthly`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[16](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:16)、[17](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:17)、[18](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:18)。原預期：

```json
{"aggregations": {}, "filters": [{"column": "discount_amount", "operator": ">=", "value": 100}], "group_by": [], "having": [], "order_by": [], "select_columns": ["store_name", "net_sales"]}
```

**需求歧義／唯一View Oracle過度指定；原澄清合理。** 題文沒提月份，只寫每列；sales_detail與product_monthly均有store_name/net_sales/discount_amount，均有結構合法SQL，條件作用卻不等價。應澄清訂單商品明細或門市×月份×商品，不代選、不生成SQL；明確選月表後才應符合原Oracle。反例同店同商品同月兩個明細折扣60、60：明細>=100無資料，月列120則符合。契約兩View.grain與discount_amount.description直接可追。不得以題號、較少欄位或排名選定月表。

### RETAIL-PRODUCT_MONTHLY-M3-04

題文（[行254](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:254)）：整理報表時照城市別分組，顯示讓掉多少錢合計與還沒扣折扣時的金額的單列最大值，限定賣的是哪種商品 LIKE 茶%且商品庫存代碼 LIKE SKU-%且門市的編號 IN 1、2、3，依城市別排序。

原target：`demo_retail.v_product_monthly`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[40](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:40)、[41](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:41)、[42](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:42)。原預期：

```json
{"aggregations": {"discount_amount": "sum", "gross_sales": "max"}, "filters": [{"column": "product_name", "operator": "LIKE", "value": "茶%"}, {"column": "sku", "operator": "LIKE", "value": "SKU-%"}, {"column": "store_id", "operator": "IN", "value": [1, 2, 3]}], "group_by": ["city"], "having": [], "order_by": ["city"], "select_columns": ["city", "discount_amount", "gross_sales"]}
```

**需求歧義／唯一View Oracle過度指定；原澄清合理。** 無月度限定，兩View均有商品、SKU、store_id、折扣額、折扣前額及門市城市（city/store_city）。SUM可能在覆蓋相同時等價，單列MAX(gross_sales)卻分別為商品月列或交易品項列。應澄清單列粒度、不代選、不生成SQL。反例同商品兩筆折扣前額100、200，明細MAX=200，商品月列MAX=300；沒有日期條件也不消除此差異。契約兩View.gross_sales及grain。

### RETAIL-STORE_MONTHLY_KPI-H3-01

題文（[行379](/home/willy/code/cpea/projects/retail/evaluations/cases.jsonl:379)）：整理報表時照業績落在哪個月、南北區域別、哪一家店分組，顯示折扣後進帳合計與完成了幾筆單的單列最大值，限定門市的編號 IN 1、2、3且這個月預定要達到的金額 >= 100且成交商品有幾件 >= 1，依業績落在哪個月排序。

原target：`demo_retail.v_store_monthly_kpi`；三次狀態`needs_clarification、needs_clarification、needs_clarification`；結果行[67](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:67)、[68](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:68)、[69](/home/willy/code/cpea/evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl:69)。原預期：

```json
{"aggregations": {"order_count": "max", "revenue": "sum"}, "filters": [{"column": "store_id", "operator": "IN", "value": [1, 2, 3]}, {"column": "target_amount", "operator": ">=", "value": 100}, {"column": "units_sold", "operator": ">=", "value": 1}], "group_by": ["sales_month", "region", "store_name"], "having": [], "order_by": ["sales_month"], "select_columns": ["sales_month", "region", "store_name", "revenue", "order_count"]}
```

**確定產品行為Bug；唯一完整合法View為store_monthly_kpi。** 「業績落在哪個月」「這個月預定要達到的金額」明示月度及營收目標target_amount。原另一matched候選order_summary偷換為order_amount，且將完成單數MAX改成MAX(order_id)，導致不必要澄清；daily還把月份當sales_date、目標當revenue（已遭拒）。應ready原Oracle，保留target_amount列條件。反例識別碼1000不代表1000筆訂單；實際金額亦非營收目標。契約target_amount、order_summary.order_id role=identifier及grain。

## 方案與交接

小方案僅分類，不修產品，能避免把合理澄清視作錯誤，但無法修6題確定Bug及2題guard症狀。建議中方案：先用原response replay修錯粒度候選、預計算欄位列條件判定與契約固有時間窗承接；保留多合法來源澄清及所有原FAIL。大方案是新建正式語意／多粒度Oracle，需另立決策與新版本，不能覆蓋本次原Oracle或48/90。

驗收分列原Oracle mapping/SQL、正常語意行為、safe reject及provider可用性。不得為衝原分數讓含糊題無條件ready；不得移除AVG禁令、忽略所有數字、清空rejected trace或按題號放行。明確日/月及整單/明細的變體與反例應列回歸。

未驗證：SQL編譯與實際DB值、修復後模型穩定性、395題泛化、provider逾時根因。此報告只完成Oracle／契約分類與所列最小離線Probe。
