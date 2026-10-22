---
{
  "parent_task": "fix-retail-group-2",
  "agent_id": "source-audit",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "唯讀調查View選擇及語意來源首個偏離契約的節點，提出通用修正與Replay，禁止產品修改及模型呼叫",
  "allowed_scope": [
    "src/cpea/workflows/text_to_sql"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/source_audit",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "已以原trace與離線probe定位新增聚合/分組未授權、比較quote過嚴、單片語exact捷徑及語意來源信任缺口；區分三項粒度歧義與CUSTOMER S3未定根因。 已追加版本A ORDER M3原call18–24稽核，支持v10比較指引保留統計單位及typed條件的最小實驗。",
    "evidence": [
      "agents/source-audit/task.md",
      "../retail-test-group-2/.local/combined-group2-20261020/calls.jsonl",
      "../retail-test-group-2/.local/combined-group2-20261020/results.jsonl"
    ],
    "risks": [
      "沒有產品修改或修復驗收",
      "三項粒度歧義不能只由題文唯一決定原Oracle View",
      "CUSTOMER S3 source false無理由且回購/活動不同，仍需Oracle/需求核對",
      "放寬比較quote若缺逐候選反證可能放行錯誤來源",
      "版本A follow-up支持prompt修正，但未執行B真實比較，尚不能宣稱改善；上游source錯配仍存在。"
    ],
    "next_step": "A維持凍結；Main於B以固定A前序輸出加通用統計單位prompt/typed條件證據，實測比較節點並做安全反例與整合驗證。",
    "diff_reference": "未修改產品/tests/Oracle；僅本agent task.md及handoff暫存JSON"
  },
  "blockers": [],
  "question": null
}
---
# View 選擇與語意來源唯讀調查

## 範圍與方法

依 EDD investigate 與已可讀的 Superpowers systematic-debugging 執行。基準 SHA `014cee1aff3abcfb51bbe5af6db0abd2ef060225`，本 agent 未修改產品、tests、Oracle、主 Task，未執行真實模型或 DB。讀取原 575 calls／90 results；以下深入證據採 repetition=3（CUSTOMER S3 唯一非逾時結果），不是新模型測量。行號為原 JSONL 的 1-based 行號。原 calls 路徑為 `evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/calls.jsonl`，results 同目錄。

## 已確認問題

1. **模型新增跨列計算仍可通過**。`semantics.py:33-66` 的 aggregation_errors 只驗證「有明確運算時是否一致」，沒有運算時 `operations=[]` 讓任何模型 aggregation 通過；也沒有對新增 group 反向驗證授權。原 mapper prompt 明定「列出 A、B」不可自行聚合/分組。ORDER S1 call 40、CUSTOMER S2 call 112 均違反此契約；`sql_generation.py:543-584` 的 source semantic gate 也接受模型宣稱 true，沒有攔下。這是比較節點之前的確定 Bug。
2. **比較器將語意證據錯當同字面比對**。`sql_generation.py:64-68` COMPARE_SYSTEM 要求原文與契約各自提供逐字 quote；但 `:714-719` 額外要求 request_evidence 本身逐字出現在唯一契約。語意正確但不同表達的 select 被無聲降為澄清。ORDER S1 call 45、ORDER M3 call 356、STORE H3 call 536 均觸發；DAILY S3 call 171 同樣觸發，但該題被模型選 sales_detail，不能把放行視為修復原 Oracle。
3. **單一小片語壓過整題且繞過比較**。`sql_generation.py:686-703` 只要任一 mapped request_text 長度>=4 在唯一 contract_texts 命中就選該 View，未要求它能反證其他完整條件或不同粒度。CUSTOMER S2 的「所在城市」命中 sales_detail 的「交易門市所在城市」；customer_value 的描述為「會員登記城市」，未逐字含「所在城市」，故錯選 sales_detail。此題沒有比較 call，不能歸咎比較模型選錯。此處 contract_texts 是 summary/grain/policy 及被映射欄位描述全文，也無正面/否定片語區分；否定引用是可構造風險，**不是此題實際命中位置**。
4. **真實引用與模型布林不保證業務相容**。`clarification.py:79-101` 會核對 quote 確實來自該欄描述，但 same_concept/grain_compatible 由模型提供。`sql_generation.py:909-944` 接受這些布林及 quote，無法阻止「MAX 訂單件數→MAX 明細件數」、「月目標→訂單金額」、「訂單數→訂單ID」。需處理完整業務對象/指標/條件，不可只以型別與可用 MAX 證明同義。

## 逐案例首個偏離點與分類

| 案例 | 原始 call 證據 | 首個偏離／判定 |
|---|---|---|
| ORDER_SUMMARY-S1-01 | calls:38 `16d71691fc424add99916eb7714b50e8` 正確 order_summary；40 `636cdf2199b846a89981056d9aa77896` 在「列出訂單成立月份、訂單折扣後總金額」新增 SUM(net_sales)+GROUP order_month；41 `cee895acf40c426aa576f70495a9dc01` 誤說 source_compatible=true；45 `c98786b2884a4eb6a86a710d8ea7625f` 正確選 order_summary 卻被字面 gate 擋下；results:6 | 首偏為 call40 自增聚合，確定 Bug；比較過嚴是後續放大因素。拒絕錯候選應留下唯一正確候選，不需放寬比較。 |
| PRODUCT_MONTHLY-S2-05 | calls:135 `a02c5bfad96b412897354195bb55ff8d` sales_detail 同欄位同操作；141 `25058a0946494d7292837d29fc0d5047` product_monthly 同欄位同操作；144 `83804d4d393245c0820bb378a15d33e9` 明確 clarify；results:18 | 題文只有「每列、店名、實際銷售額、折讓金額」，未指月度/商品粒度。明細折讓>=100 與商品月彙總折讓>=100 不等價。現有證據無法證明唯一 product_monthly；需求歧義，澄清合理。不得為通過原 Oracle 硬選。 |
| DAILY_SALES-S3-03 | calls:164 `6fdb87dd30b34e859599285e7a2256be` sales_detail；168 `322c13e1addf47b19dbabbc896cc4f70` daily_sales 因「逐筆」拒絕；169 `b31b19c7e4c549c1a6ff144327f15134` order_summary；171 `519ced35d76b455bb8ede6989767dd93` select sales_detail；results:21 | 題文「逐筆、城市別、毛利、折扣後進帳」未明示日/門市。若逐筆代表交易，daily 拒絕合理；若代表 View 每列，則對「逐筆」過度推論。原 Oracle daily 無法只由題文唯一決定。保留歧義，不把比較 gate 放寬後的 sales_detail 算修復。 |
| PRODUCT_MONTHLY-M3-04 | calls:324 `e1cc5c22d2cb4aa18cd9a4079519a353` product_monthly；328 `930edabe96e049d8929abd3327fa61cd` sales_detail；332 `6ca79011837247ec99e72451f51e7f86` clarify；results:42 | 按城市分組、商品/SKU/門市篩選，兩 View 均能 SUM 折讓，但 MAX 明細折前金額不等 MAX 商品門市月份折前金額。題文未指定基礎列粒度；需求歧義，澄清合理。 |
| ORDER_SUMMARY-M3-01 | calls:350 `1affde9f6a4540a79af0d63d22ef0889` 正確 total_quantity；352 `af9723dc83334cb39c196ca9489f2ccd` 將「每張單買了幾件的單列最大值」變成 MAX(quantity)；353 `d1161e5e9eac45e59d1b9cf41e1a943d` source true；356 `6d464b55c47d4a4a8b523928cac63f8f` 正確select被擋；results:45 | 首偏為 call352 業務粒度錯配，確定 Bug。SUM net_sales 跨明細在此範圍可能等價，但 MAX 明細quantity不能代替 MAX 訂單總件數，無法用多個正確欄位掩蓋此錯誤。 |
| STORE_MONTHLY_KPI-H3-01 | calls:527 `796e51aef5e5412bbd4d9e5acaef5f80` 正確 store_monthly；532 `5fd45ff360784badbcc5a6ef5b821d48` 將「這個月預定要達到的金額」映 order_amount、完成單數映 order_id/MAX；533 `f79e380fdeeb4bc0948b15022f797a08` 誤說 true；536 `e477999bced6436bb8a177056d3f35ce` 正確select被擋；results:69 | 首偏為 call532 指標/條件錯配，確定 Bug。月目標不是實績，更不是訂單實績；訂單ID最大值不是單數最大值。剔除此候選後不應再問 View。 |
| CUSTOMER_VALUE-S2-02 | calls:109 `05c65e83ca374897bacf553bed963b32` 正確 customer_value；112 `5f2a48d321c84ccdb55c337487308263` 新增SUM+GROUP且last_order_date語義替成order_date；113 `387ba823b91b41b3b822c9ed411402ba` source true；results:15錯選sales_detail | 首偏call112，確定 Bug。最終錯選由 exact_matches 小片語捷徑造成；「最近下單日期」應是會員最後一筆，不是所有 2026年後明細。先阻新增跨列操作足以移除此實際錯候選，但仍應回歸同樣錯配以免無聚合變體溜過。 |
| CUSTOMER_VALUE-S3-03 | calls:178 `29a2da625dad4ce795098c5d8a5f0b3f` 正確映 active_in_last_90d/lifetime_spend/customer_name；179 `95ba0e67559f41f4b05bb97f3b9e3acd` source_compatible=false，三詞options=[]；results:24 unsupported | 首個變更決策在call179，不是 retrieval/編譯。`_validate_resolution:911-912` 對false立刻return None，沒有理由或逐詞證據可稽核。「逐筆」被展開進完整詞「我想看逐筆的最近90日有沒有再回來買」，可能誘發交易粒度解讀；但「再回來買」也可能要求回購，契約 active 僅表示最近90日有完成訂單，不保證回購。因此 source拒絕根因尚未可確定；需要規格/Oracle語意核對與source理由證據，不能強迫true。前兩次 ReadTimeout 是獨立環境事件，不能用此邏輯修復宣稱消除。 |

## 離線最小實驗（已實際執行）

使用 `.venv/bin/python`，載入 SchemaCatalog(allow_drafts=True)、原 repetition3 的 matched candidate links，以 `SimpleNamespace._invoke_model` 回放原 comparison JSON，直接呼叫 `_compare_valid_candidates`，沒有網路或模型。結果：

| 案例 | winner | clarification | stub比較呼叫 |
|---|---|---|---:|
| ORDER S1 | null | true | 1（原模型select order） |
| CUSTOMER S2 | sales_detail | false | 0 |
| PRODUCT S2 | null | true | 1（原模型clarify） |
| DAILY S3 | null | true | 1（原模型select sales_detail） |
| PRODUCT M3 | null | true | 1（原模型clarify） |
| ORDER M3 | null | true | 1（原模型select order） |
| STORE H3 | null | true | 1（原模型select store_monthly） |

第二個 probe 將原 mapping_attempts 載為 SQLClauseMappingV3，呼叫 aggregation_errors。ORDER S1 sales_detail 的 SUM+GROUP、CUSTOMER S2 sales_detail 的 SUM+GROUP **均回 []**；ORDER M3 的 MAX(quantity)、STORE H3 MAX(order_id) 亦回 []。後兩者運算語法雖正確，業務概念仍錯，證明新增聚合檢查不能單獨解決所有 source 問題。

以上是現有版本失敗機制 Replay，不是修復驗收；沒有產品修復或新 E2E PASS 宣稱。

## 通用方案與安全邊界

### S：先擋未授權新增操作（建議立即採用）

在 assess/結構preflight 對跨列 aggregation、group 建立反向授權：無明確分組或跨列計算要求的列出/每列查詢，不接受模型新增SUM/GROUP；現成「累計金額／總件數／訂單總額」可直接select，不把統計名稱當再次聚合授權。與既有明確操作綁定共用 parsed operation evidence，避免全句任何地方有「合計」就授權所有欄位。先 rejection/repair 同View一次；保留原語義，不自動將整個錯草稿改成可用欄位來掩蓋source錯配。

安全反例：明確「依月份分組顯示銷售額合計」仍通過；「列出累計消費金額」不可SUM；「各店銷售額合計」可能省略「分組」但有真實跨列授權，需受支持或保守澄清，不能全句未含分組二字就拒絕；count/count_distinct/min/max也應涵蓋，不只修SUM。

### M：逐候選完整業務語意與反證

對來源保留每個完整業務詞、所屬子句、操作、原文quote、column描述quote，模型需說明統計對象/時間/單位/粒度是否相容，source_compatible=false也必須提供拒絕理由/衝突證據。正向quote只證明引用存在，不能證明兩個概念相等。對現成來源在相同物件/條件下可直接取值的需求，禁止用另物件欄位加聚合重建後聲稱同義。特別驗證目標vs實績、單數vs識別碼、訂單總件數vs明細件數、最後日期vs任意日期、會員城市vs交易門市城市。

比較 select 可保留「request原文逐字quote + contract原文逐字quote」兩項基本驗證，並要求**逐一反證每個競爭候選**：哪一個完整需求、哪項候選契約的正/負證據及哪種衝突。取消要求兩quote同字面的同時，不可只相信任意合法quote或model preference。若反證缺失、任一競爭候選仍合理或概念無法驗證，維持澄清。這需要結構化 comparison schema 與獨立語意驗證，範圍大於S；若本輪先做S，應保留比較保守行為。

### L：契約提供語意型別

若M的模型布林仍頻繁錯，把 object/measure/period/grain/filter_scope 作為核准契約型別，經人工核對後支持 deterministic compatibility。不能從測試ID/題文自動寫死口徑，也不能為這30題補 alias 後宣稱泛化；需獨立holdout與負例。

## 建議 Replay 與 Regression

- 單節點：原ORDER S1/CUSTOMER S2錯mapping→拒絕新增操作；正確mapping→通過；原exact_matches「所在城市」不可單獨壓過最後日期/累計花費。
- 單節點：ORDER M3錯quantity/STORE H3錯order_id及order_amount各自一個錯誤就足以拒絕，不得因其餘詞正確而PASS。
- 比較：原ORDER S1/M3/STORE H3 select JSON可驗證保守gate；新增反證schema時以語意同義但不同quote為正例，以「逐筆金額」及兩個MAX粒度可成立為負例。否定描述「不是會員居住城市」不可產生對會員城市的精確支持。
- Integration：使用原calls的完整有序stub回放，保留Oracle；因候選被拒會少呼叫，stub應以prompt用途/View/repair和實際載荷對應，不以固定call序號硬餵錯response。
- 需求歧義題 PRODUCT S2、PRODUCT M3、DAILY S3 保留原Oracle分數及另列語意判讀；不能把安全澄清強行改成唯一View。CUSTOMER S3需補source拒絕理由及活動/回購的語意負例。
- 安全反例：訂單總件數最大值≠明細件數最大值；月商品金額最大值≠逐筆交易最大值；門市目標≠實收；會員最後訂單日期≠每筆訂單日期；最近90日有訂單≠最近90日再購。
- 修復後跑既有 test_clarification_workflow、semantic_resolution、mapping_preflight、MATCH v10實作相關tests；真實模型驗證需主Agent另行排程並保存全新測量，不覆寫原575 calls/90 results。

## 風險與下一步

新增操作gate若以粗糙全句keyword判斷會誤拒合法省略式分組；單純放寬比較quote會把DAILY S3模型誤解直接放行；只修比較無法消除首個source錯配；source false缺理由讓CUSTOMER S3無法判定是合理拒絕或模型誤解。本報告未作DB數值/新模型驗證，原Oracle仍draft pending。

next_step：Main優先實作S並以原trace Replay確認ORDER S1/CUSTOMER S2唯一候選；再決定M是否需要本輪實作，先用ORDER M3與STORE H3最小錯配負例確認語意gate能拒絕。與oracle-audit交叉核對三題粒度歧義及CUSTOMER S3活動/回購口徑。若無通用安全判準，保留澄清並在報告列未解決範圍。

## 讀取指紋

```json
{
  "evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/calls.jsonl": "8ceba4c4a427b3a3b972e61ed153bf9f2798be11ced2cd0ec7fecce976da9aed",
  "evidence-driven-dev/tasks/retail-test-group-2/.local/combined-group2-20261020/results.jsonl": "a03e654840fa04223b3dcf25ba6a1a3ad58bdd551d8ce7972ed2460a3ad69981",
  "src/cpea/workflows/text_to_sql/sql_generation.py": "df95d35f514fc944b6008bdc960882fe8b543101d06f270ce71423ccfe33f407",
  "src/cpea/workflows/text_to_sql/semantics.py": "3f309970c4289815ecd128a098b4f63ae5b0c8213bfdd012a1f2a78d5a1d4d73",
  "src/cpea/workflows/text_to_sql/clarification.py": "3213a319f304a58838bca76af5d69ae20967e9b96d4639329512c8efcc626abf"
}
```

## Follow-up：版本 A 的 ORDER M3 真實比較節點

本節只讀 `evidence-driven-dev/tasks/fix-retail-group-2/.local/live-focus-20261020/{calls.jsonl,results.jsonl}`。版本 A 仍在執行，未改產品、Oracle、prompt 或任何執行中設定；沒有呼叫模型或 DB。以下為 A 的 results 第 3 筆及 calls 第 17–24 筆，不覆寫前述基準證據。

### 已確認的新證據

- call18 `0cb10859be1c400aa2a7794cfe384fa5`：order_summary 正確提供 SUM(order_amount)、MAX(total_quantity)、GROUP(order_month)。契約 total_quantity 描述是「此訂單全部明細的商品銷售件數加總；單位件。」（`projects/retail/views/demo_retail/v_order_summary.yaml:64`）。
- call20 `bb434053f2ec404ebecd15d4ef20507a`：sales_detail 用 MAX(quantity)，仍只 GROUP(order_month)，沒有依訂單先加總；quantity 契約為「本筆明細銷售件數；僅含已完成訂單，可依商品、門市、期間加總。」（`v_sales_detail.yaml:77`）。
- call21 `1c010bdefcb4499787a79a3d17a30bae`：source_compatible=true，仍未發現統計單位錯配。
- call24 `5c33338b50934d3792d8357fcb8f3a69`：compare回 clarify，詢問「每張單買了幾件的單列最大值」是單一商品最高件數，還是訂單全部商品件數總和。這兩者並非原文都合理的同義解讀：原文已用「每張單」指定內層實體；外層「單列最大值」綁定每張單的件數。把錯候選提供的明細粒度轉成新選項，是由來源能力製造的假歧義。
- call24實際候選payload有 request_text/role/aggregation/description/grain，但未提供結構化 operator/value，也沒有 column。條件雖可在request_text重讀，擴增operator/value可讓比較模型直接檢查完整 typed 條件是否保留，並使後續稽核不依賴重新解析人話。

用兩張訂單明細 `[[3,4],[5]]` 實際執行小型純Python算術反例：`max(map(sum, orders))=7`，`max(q for order in orders for q in order)=5`。不涉及DB或案例ID；證明將每實體的明細總和取MAX，不能替換為所有明細值取MAX。比較模型也不能假想錯候選已有按訂單SUM的查詢層：原 mapping 並不存在此層，且目前單一QueryPlan不支援任意巢狀聚合。

### 最小通用修正判斷

**Main提出的比較prompt修正合理，屬修正候選狀態與判斷契約；但仍是假設，未有新真實比較結果，不能預宣稱修復成功。**

建議 v10 比較指引清楚表述：

> 候選僅通過查詢結構、欄位能力及SQL安全檢查，尚未證明業務語意等價。逐一核對每個完整需求的業務對象、指標統計單位、時間口徑、聚合所作用的基礎量及所有條件。保留需求已指定的每個實體單位；在分組後對「每實體的明細總和」取MAX/MIN/AVG，不能替換成直接對明細值取同一聚合。既有欄位已代表每實體總量時，直接以該欄位作為外層聚合的輸入；不得假設另一候選已完成草稿中不存在的中間加總。某候選違反原文已指定口徑時，將它列為具體反證，不要求使用者在原有需求與此錯誤口徑間選擇。只有原文確實未指定且兩個以上方案仍完整承接全部需求，才澄清。

上述規則以一般實體/明細/聚合為單位，不引用案例ID、不補專用詞彙/alias、不預設某View應勝出。它能涵蓋每單總件數、每客戶累計值、每門市月總額等同類結構。

候選mapped_fields建議補 `operator`、`value`（使用原 SchemaLink 內容，含 list/number/date 字串型別，不用重新解讀原文）；保留既有 role/aggregation/description/grain。可另保留 `column` 作內部稽核，但不要求暴露給使用者。prompt須核對 WHERE/HAVING 所篩對象及階段，不因值相同或欄位型別相同就當等價；單列金額>=100不等於分組後總額>=100；IN/LIKE、邊界包含性及值也不可更換。

### 必須保留的反例與驗收

- 原文只寫「件數最大值」、未指訂單/明細且兩口徑皆合理，應保留澄清；不可一律偏好較粗粒度或名稱有total的欄位。
- 原文明確要求「單一商品明細最高件數」，明細MAX是正確來源，不能因出現訂單維度就自動改用訂單總件數。
- 同一基礎口徑下的可加總指標，SUM跨明細與SUM跨預彙總有時相等；不能把所有跨粒度方案一律判錯。仍需核對預彙總範圍、重複、WHERE條件與缺列行為。
- 不允許比較模型以任意真實quote作反證：選定來源及所有競爭來源仍要各有對應完整需求quote及契約quote，衝突須指出統計單位/指標/條件差異；不能只說另一View比較不適合。
- 條件正例：原 `order_date >= 2026-07-01`、`store_name LIKE 中山%`、`customer_name LIKE 王%` 必須全部保留；反例各自改成 `>`、`=`、其他值或錯誤聚合階段，均不可被視為等價。
- 版本B用凍結A前序輸出，只替換比較prompt及candidate evidence，以同一schema/gate真實呼叫比較節點，是合適的單變數實驗。需記錄B輸入完整payload、prompt差異、model/options/digest、輸出與具體反證；不能因離線手寫select已通過gate就宣稱真實模型改善。隨後執行整合Replay並核對新的真實模型變化。

next_step：A繼續凍結至原定其餘題結束；Main將此prompt/evidence修正納入B的獨立最小實驗。先驗證B真實比較能選唯一完整承接來源，且上述缺少統計單位/明細單位明確指定的反例保持正確，才整合。此修正降低假澄清，不能取代上游semantic source的修復。

call24單筆排序鍵JSON UTF-8 SHA256：`157288c15c7edf913dd01ebf4a02c4e7f98bb9cfd496e4bef3d278c6720c295d`。整份A calls仍在追加，未將當下檔案hash當最終seal。
