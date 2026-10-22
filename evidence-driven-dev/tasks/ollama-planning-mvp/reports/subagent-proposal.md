# DeepSeek 先驗收、再轉移本地 Ollama 的規劃 MVP 提案

本文件是**未實作、未實測的研究建議**。本次僅唯讀檢查既有程式、契約與報告，未呼叫任何模型、Ollama、資料庫或 SQL，未修改產品、oracle 或既有結果。以下門檻與預算是預先提出的實驗規則，不能視為預測成績。

## 使用者順序與判斷

先讓 Azure DeepSeek-V4.1-Flash 在已審核的完整測試範圍內逐項正確，通過 DeepSeek Gate 後，才測本地 Ollama qwen3.8:27b。**DeepSeek 未通過，不呼叫 Ollama。**最終目標仍是本地模型獨立準備 requests；DeepSeek 是先驗證方法的實驗平台，不能在本地執行階段代答或修補。

## 最小改法

先保留一次模型規劃，以離線重播測試「可證明的欄位閉包＋更嚴格的語意拒絕」，再決定是否值得引入較短的語意骨架。暫不採用完整三階段 LLM 流程，也不優先導入候選 View 裁剪：既有 DeepSeek 與 Qwen 都有欄位角色、母體與粒度錯誤；Qwen 主要 View 任務配置 29/30 是後續轉移時的背景，不能代替 DeepSeek 的實驗證據。

欄位閉包只能救回已經表達正確語意、但漏填 `required_columns` 的任務；無法補上模型從未表達的期間、通路、母體或度量。若離線結果顯示它只能提高 ready、無法提高人工語意安全的可用率，就停止把它當主要解法，轉測語意骨架。最終目標仍是完整可提交的單 View requests，不能以「拒絕更多所以安全」取代可用率。

既有 DeepSeek 三階段 2/10 的結果，只否證該次實作在該次樣本優於對照，沒有否證所有拆分方式。尤其其路由階段把錯誤 final grain 固定後往下傳；新候選必須在昂貴下游生成前檢查母體契約，不能只增加呼叫次數。

## 三個可否證候選

| 候選，皆未實測 | 改動與假設 | 可否證觀察 | 成本與採用順序 |
|---|---|---|---|
| A：一次原規劃＋確定性閉包／拒絕 | 沿用 v3 與 `DecompositionDraft`，依已存在的型別欄位組裝必要欄位、檢查不安全輸出；假設部分錯誤只是重複填寫失配 | 原始語意錯誤不應被變成 ready；若語意安全可用率無提高，A 只能當護欄，不能宣稱解決規劃 | 離線零模型，正常每題仍一次；第一個最小試驗 |
| B：一次較短語意骨架＋程式編譯既有 draft | LLM 明列需求覆蓋、母體、來源任務、欄位角色、子集合形狀；程式導出重複欄位與 integration 結構；假設減少同一決策重填能改善一致性 | 與新鮮 v3 配對時，母體／粒度真錯不減，或既有成功控制退步，即不升級；正確骨架注入可編譯不等於模型會抽取 | 正常每題一次；A 上限不足才測，不先增加 LLM 階段 |
| C：語意路由→每來源任務→整合，邊界驗證＋一次有限修正 | 每一階段僅見必要契約且可拒絕上游矛盾；假設真正的認知負擔需要分開 | B 已能輸出正確骨架而來源任務持續失敗時才有價值；若仍早期錯誤鎖死、或成功控制退步，否證本版 C | 兩來源通常 4 次、三來源 5 次，另至多 1 次修正；DeepSeek 成本另測；378 秒／次只適用既有 Qwen 輪次，不能套用；暫不進第一輪 |

推薦先 A 的離線實驗，通過後把 A 留作所有候選共用護欄；若其可用率不足，再採 B 的單次語意骨架。C 是後備實驗，不是既定架構。A 與 B 必須用相同安全規則評估，否則較嚴格的拒絕會被誤算成模型退步或改善。

## 責任與中間契約

候選 B 的中間契約應少於現行最終 JSON，且不用自由敘述取代可驗證欄位。建議只增加實驗型 `SemanticPlan`，編譯成既有 `DecompositionDraft`，不先改對外 response：

- `requirements`：穩定的本次需求 ID、使用者原文片段、種類、對應 task／欄位角色。原文片段必須確實存在，但片段存在不代表語意已正確覆蓋；覆蓋仍需獨立審核。
- `population`：anchor task、母體限制、根粒度、未匹配保留政策。原文「保留所有庫存商品」「包含未下單會員」應有明確對應，不只是 notes。
- `tasks`：來源、filters、metrics／conditional metrics、attributes、metadata collections、查詢粒度；每一個語意選擇附契約依據 ID 或需求 ID，不索取隱藏思考過程。
- `attachments`：parent／child task、兩側鍵、`scalar_context` 或 `collection`、集合剩餘維度及呈現 `nest`／`pivot`／`aggregate`；pivot 的封閉值集合須有使用者明示或核准契約證據。
- `unresolved`：缺期間、缺政策、來源不支援或契約無法證明。程式不得把 unresolved 編譯成 ready。

**LLM 責任**是理解原需求、選正確來源及欄位語意、判斷條件作用範圍、選母體與分析粒度、區分明細子集合與背景資料，以及判斷缺口。不能把這些責任以「規則自動修補」藏起來。程式可依核准契約確定欄位合法性、型別、能力、唯一鍵、期間值合法性、集合閉包、圖連通與輸出長度；程式不憑同名或詞頻發明業務同義。

| 項目 | 可安全導出，但仍須驗證 | 應拒絕／澄清的情況 |
|---|---|---|
| 必要欄位 | 所有已表達角色的聯集：filters、條件度量的條件與度量、一般 metrics、attributes、metadata、group/grain、兩側整合鍵、preparation keys；逐來源成員與 capability 驗證後穩定排序去重 | 發現不在來源的欄位不能刪掉掩蓋；無法從 request 知道漏掉哪個業務要求，不能因閉包完整就判定需求完整 |
| 分組 | 已明示 `aggregate` 的任務若只有一個權威 query grain，程式據此生成 group_by；既有 draft 的 group_by／grain 矛盾則拒絕 | 不能任選兩者之一；不能為配合驗證刪除月份、商品或分類維度 |
| 母體與整合方向 | 已明示保留 anchor、且依附關係相容時，編譯 anchor 為 left 側、preserve_task 為 anchor／對應父節點 | inner join 不能保留未匹配母體；不能只改成 left 就宣稱已理解母體；來源母體不明時回 needs_clarification |
| 唯一性 | 契約完整鍵扣除已證明固定的等值維度後，可證明某側至多一列；同月單點區間須經日期型別的正規化後才當固定值 | `store_id` 不自動決定 `store_name`；庫存契約完整鍵是 store×product，不能猜 FD；同名城市／鍵不能證明同義 |
| 細粒度附件 | 明示 collection 時，先按 child query grain 聚合，再依對齊鍵 nest；只生成已明示的 preparation | 子來源多出月份／分類／通路時，不能自動選 aggregate 丟資訊；未指定橫向或集合且會影響輸出語意時須澄清 |
| 背景值 | KPI 固定月份後，完整鍵可證明 store 唯一，能 many_to_one attach 到商品母體；背景度量保留其原粒度標籤 | 不能將重複出現在商品列的月目標加總；若月份未固定，也不能假設每店單筆 |
| 日期 | 契約要求的盤點日期保留為逐筆 attribute 或已明示彙總任務的完整 DISTINCT metadata 集合 | 日期集合不證明同日，不能繞過 stock_qty 禁止跨快照日期加總；要求同日而契約無法保證時澄清 |
| request | 以最終型別資料生成現行單 View payload、固定 instruction、history=[]，再重驗證與檢查 4000 字限制 | 不從自由文字解析回結構、不截斷超長內容、不為通過而刪條件；payload ready 不代表 SQL API 已接受 |

母體身份、根粒度、child 形狀及對齊鍵的業務含義不能單憑集合包含／交集導出；集合檢查只能驗證已明示的語意選擇是否與契約相容。

A 的閉包亦應計入 integration／preparation 鍵，並保留 before／after／導出證據；不能依自由文字 `task.request` 補欄位，現行 `prepare_requests` 實際使用的是型別內容。多餘 required_columns 要另報精確率／用途，不能讓「列出所有 schema 欄位」成為捷徑。

根粒度與 child query grain 必須分開：會員×商品購買明細是會員母體下的商品集合，最終根仍是會員；店×商品母體可附店級 KPI 背景；月別趨勢須保留每月值，不能加總成一個月值。這些選擇先由語意契約明示，再由程式檢查。語意不可由欄位交集決定。

## 候選 View 與單 View 交集陷阱

現行 decomposition 的 `_load` 載入所有核准 View，沒有候選檢索。既有 text-to-sql `_match_candidates` 逐一把單候選 schema 交給模型，並用該候選欄位 enum 約束 mapping；這適合已拆好的單 View 子需求，不能直接接整個跨 View 原需求。若把原需求輪流交給每個候選，模型可能只留下該 View 支援的欄位／條件而忽略其餘，產生「每個任務各自合法、原需求實際遺失」的交集假象。

若後續為縮短 context 導入檢索，必須採「先需求分面→每分面召回→候選聯集＋可接鍵檢查」，不是只取整句 top-1／top-4，也不是求所有來源欄位名稱交集。衡量每題 **全部必要來源同時在候選內**的召回，以及每需求分面能力覆蓋；只有某個 target View 命中不夠。通路條件必須召回含 sales_channel 的來源；月表沒該欄位時不可默默去掉條件。店／商品／會員鍵也應保留來源與語意 namespace。

本案只有七個 View，先全量保留是合理控制。MVP0 可測純 lexical 的候選排名，但不呼叫 embedding；未達 30 題必要來源集合召回 30/30（含已審核合法替代）及新對抗來源案例 100% 時，不啟用裁剪。無法確保召回時回退七個契約；若七個完整契約超 context，回傳 context budget error，不得無聲截斷。候選選取不能使用 oracle 作 runtime 提示；oracle 僅供離線評分。

## 分階段 MVP 與預先門檻

以下各階段必須先凍結 case split、模型設定、prompt／schema／catalog／harness 指紋與計分規則；每階段只允許一個候選版本，失敗先記錄原因，不在同一批題上無上限改 prompt。所有模型呼叫均屬未來工作，本次零呼叫。MVP0／1／2 與最終品質 Gate 均以 DeepSeek 為主；後段另列已通過 Gate 才可開始的 Ollama 轉移。

### MVP0：離線檢查可救上限與拒絕能力

**輸入**：以既有 DeepSeek 首輪 30 筆 raw draft 與後續失敗對照作主體，保留原 v3／契約／oracle／評分；Qwen 既有 30 筆僅作零呼叫的跨模型風險參考，GPT 既有輸出僅作對照，不把答案寫入 runtime 規則。先對現有 30 題逐題做獨立人工語意審核，處理 pending、等價來源與 oracle 爭議，再固定新反例預期。未核准前只能做診斷，不能作正式品質 Gate。

**輸出**：原結果、純閉包結果、閉包＋語意護欄結果三欄 sidecar；逐題分類為機械可救／真語意錯／等價待審／資訊不足；原 raw 與原分不回寫。對新護欄要記錄「證據足夠／證據不足」，不能冒稱從既有 draft 一定知道使用者母體。

**測試**：重播全部 30 題；至少 12 個不安全最小變異涵蓋未表達必要業務條件、非法來源欄位、漏通路、inner 刪母體、缺 nest、錯 final grain、任意 FD、非加性百分比、條件 count 誤變 filter、跨快照加總、缺月份值與缺值填零；至少 6 個已合法的等價／成功控制，另加僅漏列 required_columns、但所有語意已完整表達的安全閉包案例，後者應被確定性補齊而非一律拒絕。合成列見證只用記憶體資料，不產生或執行 SQL。

**成功門檻**：原重播 30/30 一致；閉包後所有 ready 的型別使用欄位覆蓋率 100%；12 個不安全變異全擋、6 個合法控制無新增錯誤；人工抽審所有「新 ready」零新增重大母體／條件／粒度錯。A 若救回至少 3 個完整語意安全案例，可進 MVP1；救不到 3 個但機械正確，僅保留為護欄，將 MVP1 改測 B。凡出現一個把不安全變異轉成 ready，立即停止升級。不得以 ready 增加取代此門檻。

**預算**：0 模型、0 token；離線工程／審核最多半天，單次重播預算 10 分鐘。這是工作預算，不是已測耗時。超時先縮小重播依賴，不載入模型 SDK 或 profile 密鑰。

### MVP1：單節點能力定位與六題成對試驗

**輸入**：六個預先固定的現有題型：02、07 為既有成功控制；09 為日序列子集合、14 為條件計數、16 為會員母體×通路、28 為三來源背景。選題依已知現象分層，屬開發集，不冒稱 holdout。

先對 B 做零模型的「人工核准骨架→編譯」節點測試；這只證明編譯器能力。若可編譯，再讓 DeepSeek 從原需求產生骨架；評估來源能力、需求覆蓋、母體與根粒度四項，不立即讓錯骨架往下跑。A 則在相同六題測 v3 raw→閉包／護欄。兩者各與 fresh v3 配對，**本階段只擇一候選**，最多 6×2=12 次呼叫，不同時做三 arm。

**輸出**：每題原需求→節點產物→編譯 draft→驗證→prepared requests 全鏈 evidence；分開報告單節點分數與端到端分數。正確骨架注入結果不得與自然抽取結果合併。

**成功門檻**：6 題中至少 5 題達語意安全 ready，或相對同場 v3 至少淨增 2 題且達 4/6；02、07 兩個控制皆不能出現真實語意退步；零不安全 ready；來源／母體／根粒度節點至少 5/6 正確。未達則停止該版，不以更多重跑挑最好答案；可回 MVP0 修改假設，產生新版本與新預先門檻。

**預算**：僅 DeepSeek，12 次上限；依既有 Azure 小實驗為秒級但不保證延遲，預留 15 分鐘整階段、每次 timeout 300 秒、SDK retries=0、序列執行。每次 token 預算見後節；先量測前兩題，延遲超預算則停止而不改門檻。每題超時直接記 censored failure，不立即重跑。B 若六個骨架仍主要錯在母體，不升級 C 讓錯誤固化。

### MVP2：十題端到端與有限修正

**輸入**：固定新十題，其中至少四題由未參與開發的人撰寫且執行前封存；涵蓋七來源、兩／三來源、店／商品／會員母體、月／日序列、通路、分類、日期 metadata。至少三題是應澄清／不支援的負例，如缺必要期間、要求未提供欄位、未指定同日策略卻要求跨快照件數總和。六題開發題不混入主分。

**流程與控制**：勝出候選與 fresh v3 各 10 次，順序逐題交替；若時間窗口不同則標記，不合併當公平延遲比較。至多四題各允許一次局部修正，共最多 24 次。修正只能針對可定位的違約，提供原需求、相關完整契約、已驗證中間契約與 error codes；修正後重新驗證所有不變量。不能改母體／期間／來源來消除錯誤，不能自行替換缺欄位來源；這類錯誤改回完整一次重新規劃仍算一次修正，須清空未核准下游結果。第二次失敗即停止該題，沒有遞迴反思或雲端代答。

**輸出與評分**：分別報 first-pass 安全 ready、repair 後安全 ready、正確澄清／拒絕、可支持題的錯誤拒絕、無效 JSON／timeout、呼叫與 token；修正後的分數不掩蓋初次失敗。

**升級門檻**：10 題最終語意結果至少 9/10，包含全部負例正確拒絕／澄清；可支持正例的安全 ready 至少 6/7（若正例數改變須先重定門檻）；相對 fresh v3 淨增至少 2 題、零重大語意控制退步、零不安全 ready。無修正 first-pass 至少 8/10，否則修正依賴過大不升級。最多 2/10 題實際消耗修正才符合成本門檻；預留四次是觀測上限，不是合格修正率。

**預算**：僅 DeepSeek，20 次主呼叫＋至多四次修正，共 24 次、階段 wall-clock 上限 20 分鐘；沿用 MVP1 的實測 token／耗時分布估計，不能拿 Qwen 378 秒計算。達上限就凍結為不完整實驗，不能把未跑題視作通過。每題正常一次，最壞兩次；尚不測 C。

### 最終 DeepSeek Gate：完整 30 題與未見需求全部正確

**輸入**：先完成人工語意核准的原 30 題，加獨立封存的 8 題新 holdout。新題至少 2 題為正確澄清／拒絕、至少 2 題為 source／母體最小反轉，涵蓋空集合、快照／日期及子集合形狀。未見題不可在 MVP2 用過；一旦揭露就不能再稱未見。凍結版本完整執行兩輪，每輪 38 題，順序輪替；兩輪不得中途調 prompt、schema 或規則。

**輸出**：原 grader 成績、新 sidecar 語意分、first-pass／修正後分數、全部 raw／payload／token／elapsed 與兩輪差異分列。全部 38 題需逐項檢查來源與能力、欄位角色及用途、條件與期間、根／子粒度、母體與基數、缺值／零、日期限制、整合準備、payload 完整性。正確拒絕／澄清屬負例成功，不能要求負例 ready。

**完全正確的操作定義**：兩輪均 38/38 的上述語意檢查通過，30 題應 ready 的原需求全部有完整 prepared requests，負例全部正確拒絕／澄清，零待審等價、零未決 oracle、零必要條件遺失、零不安全 ready；first-pass 亦須兩輪各 38/38，不靠這輪臨時人工修改或補答案。核心語意兩輪一致，合法表現形式可不同。這只是固定測試範圍內的完整正確，不宣稱任意自然語言均正確。

27/30、grader 30/30、單輪 30/30、僅 ready 或修正後才全對，均**不通過本 Gate**。任何一題失敗即停留 DeepSeek，保留結果，回開發集定位第一個失敗節點；改版後使用新封存控制重新驗收，避免 holdout 洩漏。三次實質修正仍無進展時停止同假設調參，重新審查責任分工或需求／oracle，不進 Ollama。

**預算**：DeepSeek 76 次上限，整階段 wall-clock 60 分鐘上限，token 預算 76×預先固定單次上限；不自動修正重跑挑最好答案。依 MVP2 實測數據重估可否在此時間內完成，超時記不完整而不降低 Gate。未來若採預設可修正流程，必須先另定 Gate 並揭露首次正確率，本提案先驗收無修正主路徑。

### 通過後才執行的 Ollama 轉移與最終驗收

**凍結交接**：DeepSeek 驗收的 SemanticPlan／既有 draft schema、編譯器、閉包、語意護欄、catalog、prompt 內容、案例及審核結果全部以指紋交接。只允許必要的 provider adapter、JSON schema 綁定與生成設定適配；列出 Azure JSON object 與 Ollama native schema、temperature、thinking、context、timeout 差異。不能把 DeepSeek 推理或答案塞入 Qwen context，也不能因 Qwen 失敗悄悄修改已核准契約／oracle。

**本地小試**：前述 6 題分層開發控制，以凍結方案對 fresh v3 作 6×2 配對，最多 12 次，按既有 378 秒估約 76 分鐘，120 分鐘停止；每次 timeout 900 秒、retries=0、序列執行。凍結方案須 6/6 語意安全、兩個原成功控制不退步，才擴大；未達回方法研究，但不改舊 Gate 冒稱已通過。此階段所有輸出均由本地模型獨立產生。

**本地完整驗收**：凍結方案採相同 30＋8 題完整兩輪，共 76 次；每輪均須首次結果 38/38 逐項語意通過、負例全部正確，兩輪核心語意一致，不能用修正後結果替代。按既有每題約 378 秒估算，每輪 38 次約 239 分鐘、兩輪約 479 分鐘；拆兩個窗口排程，每輪 300 分鐘停止、總計 600 分鐘停止，並依共享服務實測延遲調整後續排程。達時間上限記為不完整，不能降低驗收門檻。本輪僅設計，不執行。原題已見，不把轉移階段沿用的 8 題稱為 Qwen 全新未見；如需檢查 Qwen 的真正未見泛化，再另封存至少 4 題、4 次、約 25 分鐘、40 分鐘停止且另列分數。四題全通過也只是有限證據。

**回退**：Qwen 轉移不合格時保持現行產品 v3／既有版本與安全拒絕，回報失敗範圍；不得退回 DeepSeek 在線代答。只有語法／provider 綁定差異可在固定語意方案下修 adapter 並重新驗證；若需語意規則變更，先回 DeepSeek Gate。最終 38 題全對仍不等同 SQL API 已實際接受，當前禁用 SQL／DB 範圍只能聲稱「單 View requests 已備妥」。

## 模型變因與預算治理

DeepSeek 階段保留既有 Azure 實驗的 temperature=1、top_p=1、seed=42、context_window=16384、JSON object 與 timeout=300 秒作同場 v3 控制；後續調設定另立 arm。既有 DeepSeek 實驗的 A／B／C 累計模型呼叫耗時分別為 91.8／70.1／130.8 秒，合計 57 次、292.7 秒；130.8 秒僅屬 C 的 37 次呼叫。這只能作秒級觀測依據，不能當服務保證。第一個主樣本 12 次、後續 24 次、最終 76 次均先檢查時間與 token 帳本再升級，禁止任何 Ollama 探測性呼叫。

基準每題約 378 秒來自共享服務，既有範圍約 245–700 秒；不能當隔離效能常數。全程單一併發，不停其他使用者工作；記錄 request 起訖、Ollama 回傳的 load／prompt eval／eval duration、prompt／completion tokens（若介面提供）、timeout、服務負載資訊與缺測欄位，將排隊和生成時間盡量分開。每階段達 wall-clock 上限停止，不以共享服務延遲歸因模型退步。

只有通過 DeepSeek Gate 後的本地階段，才先固定已知 model digest／Q4_K_M、thinking=true、temperature=0、top_p=1、seed=42、context=16384、native schema，保持 v3 同場控制。`num_predict=-1` 沒有 token 硬上限；以 watchdog 與呼叫／時間上限作第一個試驗預算。未量測 thinking token 與 final JSON 分布前，不任意把輸出截至很小導致無效 JSON再歸因方法失敗。

MVP0 分開用 DeepSeek／Qwen 原 usage 統計 input／output 中位數、p95、最大值；若既有 Ollama usage 對 thinking 計數不明須直接標記。新候選每次 input+output reserve+safety 必須 ≤16384，例如候選輸入不超過 8192、輸出預留 7168、安全 1024，**此數字是待 preflight 驗證的上限配置，不是已知能容納所有契約**。超出則減少重複 schema／冗餘文字，保留完整必要契約；不能截斷契約。每階段預先設總 generated-token 預算為呼叫上限×7168，含 thinking 的實際口徑須先核對；基準未限制輸出時另報實際值，不假稱受此上限控制。

僅在 DeepSeek Gate 已通過、Ollama 品質方法固定後，才用額外明列預算的四題成對試驗（8 次、約 50 分鐘、70 分鐘停止）比較 thinking true／false；這四題需涵蓋困難與成功控制。同一試驗保持 context 與輸出限制不變。context=8192 與去除重複 schema 是另一個變因，不與 thinking 一起改。若品質未過門檻，不用速度提升為其辯護。無法取得 8192 完整內容預算時跳過縮 context。一次小試無法保證新設定一般化。

所有預算逐階段依既有授權排程，不自動跑完整合計；本次授權只設計，沒有任何實驗已執行。rate limit 不重跑，依既有 account-switch 規則先保存並結構化判讀 terminal output；auth／network／unknown 不當成 quota，也不冒充模型品質錯誤。

## 語意驗收與評分盲點

評分至少保留四個互不替代的層次：來源召回／選擇、契約合法、prepared payload ready、需求語意正確。現行 grader 的 columns 是 required 子集而非精確集合，日期 alias 有已知漏判；metrics／conditional_metrics／metadata 多為包含檢查，額外錯誤度量或欄位角色仍可能過。integration 自動分不等同核對所有 preparation 的可執行語意、基數、缺值政策、母體保留；現行 validator 的圖可達也不會證明 inner 保留未匹配母體。

因此必須另設嚴格 sidecar：需求片段覆蓋、每個欄位用途、母體集合、根／子粒度、條件作用來源、FD 證據、快照安全、零／缺值、背景度量不重加總、明示 preparation 是否足夠。日期 alias 的正規化須經型別與期間等價證據，不能以「同軸任一欄位存在」寬鬆補過 required_columns 缺口。

採至少六個合成資料見證比較預期語意：有庫存無銷售、有會員無訂單、零缺貨門市、雙月缺一月、同店多商品共享 KPI、不同盤點日庫存。nest/pivot 與條件聚合的零／缺值差異要加入空集合和未匹配列。對文字 plan，見證只證明參考語意與 invariant，不能證明未執行的 preparation 或未呼叫的 text-to-sql API 實際相容。

不修改原 oracle 追分；新等價方案另附契約依據與反例邊界，待獨立審核後報「已核准等價」或「待審」。全部舊分繼續保留。既有 391 測試通過不證明新方案安全；未來實作後須跑對應契約／編譯／護欄測試與現有回歸，但本報告未執行這些測試。

## 已閱讀的依據

- `reports/background-brief.md`：主 agent 的任務背景摘要。
- `src/cpea/application/models/decomposition.py`：現行型別契約與只有 ready 可暴露 requests 的限制。
- `src/cpea/workflows/task_decomposition/{workflow,prompt,validation}.py`：一次 LLM、全量契約、v3、驗證與確定性 payload 生成。
- `src/cpea/workflows/text_to_sql/sql_generation.py` 的 `_match_candidates`：單候選 schema／enum／局部修正；本次僅讀程式，未啟動 workflow。
- `evaluations/decomposition_grading.py`、`evaluations/retail_view_retrieval.py`、`projects/retail/evaluations/task_decomposition_matrix.md`：評分與召回邊界。
- `projects/retail/views/demo_retail/v_inventory_status.yaml`、`v_store_monthly_kpi.yaml`：唯一鍵、日期、禁止加總的具體限制。
- `evidence-driven-dev/tasks/retail-task-decomposition/reports/ollama-results.md`、`evidence-driven-dev/tasks/retail-planning-stages/reports/results.md`：既有觀測及其限制。

本文件所有新方案、門檻、預算配置與預期效益均未實測，不能預先保證 30/30。
