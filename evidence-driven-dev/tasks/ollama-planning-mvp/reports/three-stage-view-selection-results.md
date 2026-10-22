# 三階段 View 選擇實作與驗證結果

**結果：候選已實作，尚未通過第11題診斷；端到端語意 NOT_VERIFIED。** 產品 v3 預設保留，主 Task 回到 PLANNING。未進六題、十題、完整38題或 Ollama。

## 交付與離線驗證

- 新增 evaluation 專用 Requirement／ViewCoverage／SelectionResult，驗證原文、來源、欄位角色、聚合、契約 JSON pointer、同來源 scope、需求分工與整合。
- 部分映射保留；不完整支持不得冒充完整支持，最終任務不能新增第二步未驗證能力。
- 三份 Markdown prompts、序列 runner、context／calls／token／wall budget、raw／usage／版本指紋與離線 replay 已建立。模型建構前檢查預算，provider 不重試。
- **42 focused tests、含既有 decomposition 共135 passed**；[回歸證據](../evidence/EV-20261021T015608-374f69fc.json)。離線合法控制可準備兩份 request，但不算自然生成成功。
- [獨立審查](three-stage-independent-review.md)初版發現最終粒度、缺值政策及兩個重播缺陷；主 agent 以 RED→GREEN 修正。修正版以測試驗證，未宣稱經 reviewer 再次核准。

## 第11題首次診斷與續接

原需求、完整七來源、oracle hash 均沿用已核准資料。temperature=1、top_p=1、seed=42、每次最多4096 output tokens、context32768、safety1024、timeout300秒、SDK retries=0。不提供較強模型答案或 oracle 給 runtime。

| 實驗 | 真實新增呼叫 | 結果 |
|---|---:|---|
| EXP-009／v1 | 2 | 需求整理成功；customer View 的合法 `/grain/keys/0` 被本次檢查器誤拒。這是程式缺陷，不是模型語意失敗。 |
| EXP-010／v1.1 | 2 | 先重用前兩筆原 raw，再首次呼叫 daily、inventory。inventory 引文路徑指向 `/grain/keys` 陣列、quote 卻為 `store_id`／`product_id` 字串，不符合 schema 的字串路徑契約，停止。 |

原版 bug 以七個索引正／反例修正。續接前已核對 prompt、schema、catalog、case 與前兩節點 messages 完全相同，未重做模型答案、未改 raw／首次停止結果。新 runner 明記 cached_raw／live；**不是固定版本全流程首次通過**。[首次實驗](../evidence/EV-20261021T015032-3de25115.json)、[續接實驗](../evidence/EV-20261021T015637-436c6855.json)。

兩次實驗合計 **4 次不同節點的 provider 呼叫**，實際 input 13419、output 5550 tokens，執行時間合計約47.72秒；續接計數含2筆cache，不能把兩份run的總usage相加重複計費。Azure部署價格未能核實，美元成本未知；預先限制為合計9次、150000 input tokens、36864 output reserve、3000秒。

## 節點判讀與停止依據

| 節點 | 已觀察結果 | 能力界線 |
|---|---|---|
| 需求／召回 | 10項需求、七來源全部保留；金額綁定期間與通路 scope | 引文及ID合法不代表需求語意完整 |
| 逐View映射 | customer、daily完整通過結構檢查；inventory為第3個映射，因契約引用不合法被拒 | 尚未測到後續四來源，不能宣稱已正確排除月表或選中銷售明細 |
| 最終選擇／分工 | 未執行，prepared requests=0 | 原自動分及嚴格端到端語意分均無可評的最終產物，不能填成PASS或以ready數替代 |

inventory 的欄位名稱本身存在；錯誤是引用路徑與引文型別不匹配，不能說成虛構欄位。正確可引用 `/grain/keys/0` 的字串，或 `/grain/description` 的原文。程式沒有自動修改模型路徑來換取通過。

另外，需求整理把「目前庫存」建為 filter；inventory 回覆僅能以 `snapshot_date IS NOT NULL` 部分表達，並要求額外日期依據。與現有 oracle 保留快照日期、直接取目前庫存的設計有差異；這是下一輪可研究的語意界線，尚無最終產物可判定其整合結果。recall 也沒有單獨的 grain／metadata 類需求，最終粒度與資料時間仍須獨立語意驗收。

EXP-009／010的效果假設均為 **INCONCLUSIVE**；執行門檻未通過，但沒有證據否證所有三階段方法。按照預定停止規則，本輪不再調prompt、修正引用後續跑或擴題。

## 證據重播與限制

- v1改版前已重播兩筆 raw 並還原首次停止：[原版重播](../evidence/EV-20261021T015206-fb32d89a.json)。原v1程式另存 `.local/three-stage-v1-sources/`。
- v1.1 fresh subprocess 重播四個邏輯節點（含兩筆cache），還原 inventory 相同錯誤：[續接重播](../evidence/EV-20261021T015749-2e677d74.json)。
- [離線稽核程式](verify_three_stage_evidence.py)核對artifact集合/hash、原版程式hash、兩筆raw重驗、cache原文/usage、schema／prompt／catalog／case一致及產品檔案未變：[稽核證據](../evidence/EV-20261021T015828-e8216b14.json)、[機器摘要](three-stage-view-selection-results.json)。沒有重播造成的額外provider呼叫。
- 敏感raw在Task `.local/three-stage-20261021T015033Z-466574/`及`.local/three-stage-20261021T015638Z-2e0352/`，檔案權限600、目錄700且Git忽略。未產生／執行SQL、未查DB、未提交或推送。
- 本候選仍有保守介面限制：grain類需求代表最終粒度；保留母體僅支援由anchor直接left連出；缺值政策需使用明列canonical選項。一般多粒度、多跳整合及自然語句等價尚未驗證。

後續若繼續，先離線釐清「目前庫存」的需求角色、資料時間與引用契約，再建立新版本及EXP。封存題不參與調整，完整DeepSeek與Ollama兩輪各38/38門檻不變。
