## ADDED Requirements

### Requirement: 同服務的單頁問答入口

系統 SHALL 由 FastAPI 在 `/` 掛載 Gradio Blocks，提供使用體驗類似 ChatGPT 的單頁介面，包含中央最新問題／答案區與底部問題輸入框。UI 模組 MUST 隨公開套件打包，框架靜態資源由 Gradio 依賴提供，使用者不需另行執行前端服務。

#### Scenario: 安裝套件後開啟首頁

- **WHEN** 在 checkout 外安裝 wheel 並啟動 HTTP app
- **THEN** Gradio 首頁及框架 CSS／JavaScript 可正常載入並提供輸入與結果區

### Requirement: 僅保留最新問題與答案

頁面 SHALL 僅在頁面及 Gradio 暫存工作階段的記憶體保存最新問題、SQL、結果或錯誤。每次有效提交 MUST 立即取代上一題內容並清除上一題 SQL／結果，送出獨立 request。頁面 MUST NOT 保存問答到 DB、localStorage、sessionStorage 或 checkpoint；重新整理 MUST 清空問答狀態。

#### Scenario: 提交下一題

- **WHEN** 使用者已有結果並送出下一題
- **THEN** 畫面立即只顯示新問題及處理中狀態，且請求不包含 history

#### Scenario: 重新整理

- **WHEN** 使用者重新整理已有問答的頁面
- **THEN** 問題、SQL 與答案清空，且不存在問答持久化資料

### Requirement: 分段顯示 SQL 與資料

頁面 SHALL 在 generator 提供 SQL 階段時立即呈現 SQL 與查詢中狀態，不能等待 result 才顯示 SQL；收到結果階段後 SHALL 顯示 columns／rows 表格並結束處理中狀態。空 rows SHALL 顯示「查無資料」。達 row_limit 或 rows_truncated 為真時 SHALL 顯示對應限制提示。SQL 與資料 SHALL 保持可閱讀且支援橫向捲動。

#### Scenario: DB 尚未完成

- **WHEN** SQL 階段已抵達且結果階段尚未抵達
- **THEN** 使用者可看到本次 SQL 與查詢中狀態，尚無本次結果表格

#### Scenario: 成功或零列結果

- **WHEN** 收到有效結果階段
- **THEN** 頁面顯示本次資料表格或查無資料文字，重新啟用輸入送出

### Requirement: 固定錯誤畫面

頁面在生成／DB／結果編碼失敗、非成功 HTTP、網路中斷、格式錯誤或未完成的 Gradio 傳輸時 MUST 僅以「執行錯誤請再試一次」作為錯誤訊息，並 MUST 停止處理中狀態、恢復送出能力且不自動重試。已收到的本次問題與 SQL SHALL 保留，結果區 SHALL 顯示錯誤而不殘留上一題資料。

#### Scenario: 生成階段失敗

- **WHEN** 尚未取得 SQL 階段就失敗
- **THEN** 頁面保留本次問題，顯示固定錯誤文字，不顯示 SQL 或舊資料

#### Scenario: DB 或傳輸失敗

- **WHEN** 已顯示 SQL 後查詢失敗
- **THEN** 頁面保留本次 SQL，顯示固定錯誤文字，且不宣稱查詢成功

### Requirement: 正確串流解析與輸入互動

頁面 MUST 透過 Gradio 傳輸分段更新 Unicode 內容；MUST 停用問題的 Markdown 解譯並先 HTML escape，並以 Code／純文字資料表呈現 SQL、欄名與資料。頁面 SHALL 拒絕空白輸入、處理中停用重複送出、使用 Gradio 元件與少量 JavaScript 提供 Enter 送出與 Shift+Enter 換行，且 MUST 在中文輸入法 composition 中避免誤送出。同工作階段處理中的請求 MUST 阻擋重複提交，避免較舊結果覆蓋最新請求。介面 SHALL 支援手機寬度與可存取的處理狀態。

#### Scenario: 跨 chunk 中文更新

- **WHEN** Gradio 傳輸中文 SQL 與結果
- **THEN** 頁面正確重組並呈現文字，不漏更新或誤報完成

#### Scenario: 文字中的 HTML

- **WHEN** 問題或資料包含 HTML 標籤與 script 字串
- **THEN** 頁面以文字呈現，不執行 HTML 或 JavaScript

#### Scenario: 重複提交與中文輸入

- **WHEN** 請求處理中重複操作送出，或中文 composition 中按 Enter
- **THEN** 頁面不多送請求，且輸入法按鍵不誤觸提交
