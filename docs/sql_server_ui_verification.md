# SQL Server 單題介面驗證

驗證日期：2026-10-15。介面依使用者選擇改為 Gradio Blocks，外觀使用框架預設。

## 已完成的離線驗證

- Python 3.12，Gradio 6.30.0、SQLAlchemy 2.1.4、pymssql 2.4.4；137 項 pytest 通過，涵蓋既有 JSON API、CLI、graph factory、generation-only 與 executor 注入相容性。
- Fake engine／driver 驗證 datasource／View 拒絕、單次執行、有限 fetchmany、login_timeout／timeout、NullPool、Unicode／特殊字元 URL 與 SQL 百分比字元保留、各階段清理與並行隔離；測試沒有連接真實 DB。
- Application service 以空 history 生成一次，執行同一份核准 SQL，保留 attempts、row bounding 與 trace，不進行文字答案生成。
- 受控 ASGI send 證明 SQL body 先送出才開始 executor；實際 HTTP 用暫停中的 fake executor 證明客戶端可先讀到 SQL。
- 串流 API 測試成功、零列、unsupported、policy 拒絕、DB／timeout／編碼錯誤、malformed payload、固定錯誤、明確型別編碼與斷線後資源釋放。
- 真實 Chromium 驗證慢速 executor 先顯示 SQL、成功後保留 SQL、最新問題取代、零列、生成／DB／編碼錯誤、上限與裁切、HTML 純文字、Enter／Shift+Enter、中文組字、空白攔截、重複提交、375px 手機寬度、live region 與重新整理清空。
- 模擬 Gradio queue 網路失敗時顯示固定錯誤並恢復輸入；不重新提交查詢，框架的技術錯誤 toast 不顯示。
- Wheel／sdist 建置成功；在 checkout 外的新虛擬環境安裝 wheel，驗證首頁、JavaScript 資源、Gradio config 與未設定 DB 的 preflight。
- 分發檔包含 UI 模組與必要 JavaScript，不含私有 profile 或 `.env`。

## 真實 GMS2 驗證狀態

使用者已補齊連線字串與邏輯 datasource binding，profile 指向既有私有 GMS2 契約。此文件未複製連線字串、主機、database、帳號、問題、SQL 或真實 rows。

使用者指定改為 mssql+pymssql，已完成本地 `.env` 連線欄位格式轉換，保留既有連線目標與帳密；原 ODBC sudo 安裝腳本已移除。這台 Ubuntu 可直接載入 pymssql 與 wheel 內含的 FreeTDS，不需 ODBC。預設 TLS policy 維持加密、system CA 與 hostname 驗證。

初次握手受自簽憑證阻擋；不傳送帳密的 TDS／TLS probe 確認 DNS、TCP 與 SQL Server TDS 正常，系統 CA 驗證得到代碼 18。使用者明確表示這次以能連上為主，已在本機部署設定接受自簽憑證，仍要求加密；公開套件的預設憑證驗證保留。

真實連線 preflight 已成功，實際 database 與設定相符，三個核准 View 均具 SELECT 權限；未發現核准 View 的 INSERT／UPDATE／DELETE／ALTER／CONTROL 權限，也未具有 sysadmin／db_owner 角色。任務 7.1 已完成。

真實 DB 串流 smoke test 使用由私有 profile 與 compiler 預先核准的 generation fixture，透過實際 HTTP 收到 sql → result；核准 SQL 僅執行一次，回應欄位及數值編碼與 driver 原始結果相符。驗證過程未輸出或保存真實 SQL／rows，任務 7.2 已完成。

另以真實 Ollama 生成流程測試一個自然語言問法，於既有 schema_linking 驗證階段被拒絕，正確收到固定 error 終止事件且未執行 DB。因此上述成功 smoke test 證明 DB／串流流程，未宣稱該問法的 LLM SQL 生成已成功；生成品質需另外檢視。

網頁已啟動於本機 8000 port，首頁 HTTP 200，供使用者直接使用。

安裝與連線設定見 [README](../README.md#連接-sql-server)。確認 DB 連線可用後，應以明確選定 `.env` 啟動，確認核准 View 的 SELECT 權限，再驗證 SQL／結果先後順序及資料正確性；不得將真實資料或憑證加入此報告。
