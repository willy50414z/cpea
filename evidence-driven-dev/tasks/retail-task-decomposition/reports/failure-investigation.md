# 未通過案例調查

基準：b16d117 重驗原始 Azure 90 次回覆（來源 bf626de），保留原始產物，不重跑 SQL／DB。

30 個未通過題次涉及 12 題：22 次粒度、11 次欄位、2 次條件、1 次度量差異（重疊）。

已定位的第一個偏離點：prompt 將快照日期寫成可保留，但題庫視為必要；未限制附帶名稱成為分組；未區分分通路列與 pivot。評分器最終 output_ok 未使用子任務已有的來源唯一鍵等價證明。通路26的 oracle 缺少使用者指定的線上／實體範圍，待獨立契約審查。

競爭假設：H3 prompt歧義造成漏時間metadata及過度分組；H4 grader對已證明冗餘維度誤判；H5 通路26 oracle 缺少明確篩選或等價表示。

先作合成反例 RED/GREEN；再對預先固定 12 個失敗案例及 4 個原已通過案例做一次候選 prompt 實驗。其餘14題留作新prompt holdout，最後乾淨固定revision對全30題各三次真實呼叫。不得將答案或題號送模型，禁止降低安全驗證或將不成立的FD視為等價。

S：只改grader，無法修正漏欄位；M：修正通用prompt、來源鍵可證明的grader及獨立確認的oracle，先驗證；L：擴充schema／自動反覆模型修復，僅M被否證後考慮。選M，不增加模型重試。

## 最小實驗結果

EXP-002：metadata 新表示及最小grain政策，固定16題真實Azure呼叫全部通過；範圍為12題曾失敗需求及4題既有通過控制。產物 `20261020T053202971735Z-b16d117a-0c8707`，EDD `EV-20261020T053201-dad24c77`，source_unchanged=true。模型只見request、七View契約與schema。

唯一鍵整合正例最初1 failed/17 passed，再GREEN18 passed；metadata欄位新增前4 failed/17 passed；獨立review新增的final非法維度及metadata重複角色最初4 failed/43 passed，再修正。最終target 66 passed（含舊測試），不是以移除反例使其通過。

獨立審查另確認14題stock_qty只供條件，原oracle裸attributes不當，保留required_columns並移除attribute，沒有放寬度量或條件。只讀review補齊final欄位來源、縮減grain需準備或來源唯一鍵、metadata-only明確分組、型別/measure/select能力及重複角色限制。

基準用相同新版grader/修正oracle重評仍保留舊原始回覆；新prompt必須以fresh實測驗證，不以離線重評聲稱模型改進。

## V2 回歸與第二次最小修正

74ef295 原訂90題次，完成23題次後主動停止：cross-view-16未指定通路集合卻自行IN限縮。保留EV-20261020T053833-015705f6及未完成run，不充作完整benchmark。SIGTERM時有1次in-flight結果未知，可能已計費；recorded23不是保證全部計費呼叫數。

v3僅明示範圍來自使用者；未指定集合則保留全通路。oracle不變。以16全通路及26明確雙通路各三次對照；24/25/27/29仍保留最終holdout。
