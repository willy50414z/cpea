目標：先讓 Azure DeepSeek-V4.1-Flash 正確完成 retail 跨 View 拆分及單 View text-to-sql request準備；通過完整驗收後，才用同門檻測本地 Ollama qwen3.8:27b。不生成SQL、不查DB。
現況：七個核准 View、30 題跨來源 benchmark。流程為載入全部契約與 schema→一次 LLM 同時選來源、組 tasks/integration→程式驗證→準備 requests；沒有候選檢索或自動修復，預設已恢復 prompt v3。
基準：GPT 的欄位/ready/自動結構為30/30/30；DeepSeek首輪26/22/18；Qwen為21/11/7，View配置29/30。Qwen欄位21題含四個漏判，不能當完整正確率。19題invalid_plan，錯誤題數重疊：12題漏列使用欄位、9題最終粒度偏離母體、9題缺nest/pivot/aggregate、2題分組不一致；另有inner join誤刪母體。不是單純資料庫缺欄位。
已試：DeepSeek十題原版/加檢查步驟/三階段規劃，自動通過7/2/2；早期錯誤被固定傳遞。完整改寫prompt及明列全部欄位能力，欄位23→27，但ready21→15、結構16→9；小幅候選映射prompt同批30題欄位25→26、ready18→16、結構15→16，均未採用；這些改版尚未測Qwen。
Qwen本地30題耗時約3小時9分，thinking=true、temperature=0、top_p=1、seed=42、context=16384、num_predict=-1、SDK timeout=900秒、Q4_K_M，使用native JSON schema；服務有其他工作共用，延遲不是隔離測試，與Azure生成設定不同。
限制：原分、原始回覆及失敗已保存；grader有日期alias漏判與等價表示盲點，ready不保證語意安全，人工語意核准仍pending。391測試通過、1項略過。請先離線重播再小樣本測試，明確分配模型與程式責任；每階段明列輸入輸出、指標、成功/失敗門檻、呼叫與時間預算、回退方式，先以DeepSeek驗收30題及未見案例的來源、欄位、條件、粒度、母體、缺值與payload，不能只看自動分數；通過後才測Ollama。
