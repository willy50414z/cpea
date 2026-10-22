# 分階段規劃調查與預先固定的實驗

承接已完成的 retail-task-decomposition；本次只使用 Azure DeepSeek-V4.1-Flash，主 agent 執行，不使用 Ollama。屬調查性 spike，實驗程式不接入產品。

## 觀察事實與問題定位

GPT calls.jsonl 只有最終 response、messages、usage、elapsed_ms 等欄位，沒有 reasoning trace。參考的是可觀察的最終決策與整合說明，不能當成 GPT 的內部推理順序。原 GPT 完整首輪 30/30；DeepSeek 自動結構 18/30，來源欄位 26/30、request ready 22/30。

原工作流程 load_contracts → plan_tasks → validate_plan → prepare_requests 中，只有 plan_tasks 呼叫一次模型；圖上有四節點不代表已拆開模型規劃任務。第一個偏離可能出現在模型 JSON 的來源、單 View 任務或 integration；validator 是偵測點。

- 來源能力錯配：11、29 以無通路欄位的月彙總來源聲稱完成通路篩選。
- 單 View 契約：10、16 的 metadata/group_by 粒度不一致；26 用 order_count 輸出別名當作來源欄位，且漏明示通路條件。
- 母體語意：14 先以缺貨 filter 刪除零缺貨門市，不能僅靠欄位驗證發現。
- 整合：22、24 的子集合粒度與 preparation keys 不一致。
- 不必要澄清：21 已有 active_in_last_90d，卻要求重定義該欄位或不在需求中的時間概念。
- Oracle 差異：04 分開月份、06 月區間、17 月末日期表示；保留原分，不能把自動未過全視為模型錯。

已確認的是具體輸出違約；一次責任太多導致錯誤仍是假設。模型能力、提示清楚程度、較多 token 預算與隨機性都是競爭解釋。

## 方案與 MVP

S：維持一次模型呼叫，以明確檢查步驟區分來源、子任務與整合；成本小，但仍一次完成所有責任。

M：需求／來源路由 → 各 View 子任務 → integration；中間有契約檢查，後段不得改寫已固定欄位與粒度。平均每題至少四次呼叫；前階段錯誤會被傳播或提前拒絕。

L：另加獨立語意審查、結構編譯與受限修正；變因與成本大，暫不測。

MVP 0：離線對照既有 GPT 與 DeepSeek 最終輸出。

MVP 1：十題三個 arm 成對比較，不改產品；A 原版、B 同次呼叫加檢查步驟、C 使用與 B 相同規則分三階段。C 各 View 分別呼叫，單節點契約失敗即停止該題，不自動修補或重試。

後續條件：C 自動結構分數高於 B，且原成功控制不退步，才值得擴大；不符合就回研究，不能因比舊基準好便宣稱拆分有效。

## 預先固定的實驗方法

題號順序：02、07、18（三個原成功控制）、11、14、16、21、24、26、29（七個診斷題）。這些是既有已見案例，不是新 holdout。每題三 arm 順序輪替 ABC／BCA／CAB，以降低固定排程順序差異。

模型一律 DeepSeek-V4.1-Flash，temperature=1、top_p=1、seed=42、context_window=16384、max_output_tokens=-1、timeout=300、SDK retries=0、JSON object。保留所有 raw final JSON、輸入與 usage；provider 錯誤立即停止整場，不重跑。無 GPT／Ollama／SQL／DB 呼叫。

模型看不到題號、expected_tasks、oracle 或 GPT 答案。共同 checklist 只包含通用契約規則；不把測試題答案作 few-shot。C schema 與上下文範圍因階段不同而改變，屬整體策略比較；即使改善，也不能隔離歸因為呼叫次數本身。

原始 grader 與 validator 不修改；ready 只是結構通過。另檢查來源是否支持條件、零符合母體、明示通路、彙總角色與 join 保留。小樣本僅單次觀測，不估計統計顯著或全 30 題正確率。
