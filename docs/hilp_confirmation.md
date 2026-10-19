# 欄位確認與來源詞彙對應

## 使用方式

網頁一次處理一個完整問題。輸入框在底部，本題訊息、業務語意選項、SQL 與結果在中間顯示；詞彙摘要整合在可捲動的聊天內容，不使用固定高度的獨立視窗。新問題與重新整理都不還原上一題。SQL 在獨立程式碼區塊顯示；一般選項、進度與摘要不含 View 名稱、column 名稱或內部紀錄識別碼，其他技術資訊由開發者 JSON／SSE API 與伺服器流程保留。

輸入框下方的 project 選單提供 `gms2`、`retail`，預設選 `gms2`。每題使用所選 project 的 `.env`、View 契約與獨立詞彙檔；執行中或等待 HILP 時無法切換。等待時按「新問題」會取消原題，再開放選擇其他 project。

資料來源識別碼自動使用 project 目錄名稱，不需另填 `CPEA_DATASOURCE_ID`；SQL 執行與詞彙紀錄使用相同識別碼。舊詞彙檔若仍使用其他來源識別碼，需先確認屬於同一 project／資料來源，再更新 scope；不自動接受任意 scope 不符的檔案。

每題進度保留安全的資料集名稱：「GMS2 業務資料」或「零售示範資料」，讓使用者確認本題使用哪份資料。無法承接問題時，訊息指出目前選擇的資料集，還原原題並開放 Project 選擇；不以通用錯誤要求使用者盲目改寫，也不自動跨專案搜尋或查詢。未知或格式不符的 project 資訊不會原樣傳到畫面。

所選 project 尚未配置 executor 或 datasource 時，首頁顯示「目前僅能產生查詢，尚未連接資料庫」，繼續完成生成、HILP 與詞彙保存，完成後標示「本次未執行查詢」。有 executor 的 project 才會在生成後查詢資料庫。本題方式在送題時固定，避免確認過程中因設定變更而意外開始查詢。執行型 JSON／SSE API 仍維持資料庫依賴檢查。

## 逐步流程摘要

助理訊息會在步驟發生時累積顯示固定的業務文字；模型尚未完成時即可顯示已開始比對，確認後接續更新。例如：

```text
正在尋找相關資料。
正在比對問題與資料內容。
正在確認詞彙含義。
有詞彙需要你確認。
```

瀏覽器使用允許清單將流程事件轉成固定文字，不直接序列化事件內容；未知事件不顯示。詞彙摘要分別標示「自動採用」、「本次確認」或「沿用確認」，只顯示業務含義。結果欄位以安全的業務描述顯示，無法取得描述時使用「結果 1」等標題。開發者 API 的獨立 `term_mapping_reasoning` 與技術追蹤仍保留。事件限定本題與目前瀏覽器工作階段；新問題會清空。

畫面會跟隨最新進度；往上捲動閱讀時會停止自動捲動，回到底部後繼續跟隨。這些即時步驟提供給網頁對話框，既有 JSON／SSE API 的回應格式維持原樣。

助理訊息內只為真正有歧義的詞彙顯示未預選的 radio。每項最多三個業務含義，加上「都不符合，重新描述」，合計最多四項，不補入無關欄位湊數。選完所有必要項目後，按「確認並記住，繼續」。任一項選「都不符合」再按「修改問題」，即可還原原題供編輯，不必填完其餘項目；已選的其他項目也不保存，不執行查詢。取消本題是獨立按鈕。確認不會新增稅額公式，也不代表已驗證該金額的發票或含稅業務保證。

排除不相關或不合法候選後，只有一個業務含義的詞彙直接採用，同時更新該詞彙在欄位、條件、分組與排序中的所有用途，再驗證整題。自動採用只保留本題依據，不寫入人工確認詞彙檔；已有不同人工對應時仍需明確確認。混合唯一候選與多個候選的問題，只詢問仍有歧義的詞彙。

## 候選篩選與提問時機

優先使用同一次 MATCH 回覆的 `clarifications`。若伺服器判定有詞彙需要確認，但模型漏給選項或選項證據、標籤不合法，會列出實際待確認詞彙及用途合法的欄位，對同一候選來源補一次批次語意整理，不逐詞呼叫模型，也不重新映射查詢。每個候選包含 `column`、簡短繁體中文 `label`、逐字引用自身欄位說明的 `evidence_quote`，以及 `same_concept`、`grain_compatible`。模型負責按完整問題與契約判斷業務概念及粒度，不能因公式提及成本便把毛利當成本，也不能把訂單條件換成月度統計。

補整理會獨立核對來源是否能保留整題統計對象與條件；若粒度不符，排除當前來源並繼續檢查其餘檢索候選，不重試同一個不相容來源。候選用盡才回報無法承接。模型輸出格式的 required 欄位明確包含查詢子句與選項結構，避免受約束生成器只回傳少數必填欄位；Pydantic 讀取舊草稿的預設值仍保留。

程式檢查候選存在、證據確實出自該欄位、語意與粒度判斷為真、標籤無資料庫識別資訊、型別與單位相容，以及所有出現位置的操作能力。每項候選會先代回完整草稿，檢查篩選、聚合、分組與排序能否成立；使用者確認後仍須通過原有編譯與唯讀 SQL 驗證。重複欄位或無法區分的重複標籤不形成選項。

明確指定且存在、合法的欄位，以及核准名稱或有效的既有確認，不重問。欄位描述中的否定按子句檢查，例如「訂單成立日期（曆日），不含時間」可以明示支持「訂單成立日期」，但「不是會員居住城市」不能支持「會員居住城市」；仍須保留完整問題詞彙的所有限定。

確實無相關候選、模型要求補充口徑，或合法候選仍超過三個時，回傳 `code=clarification_rephrase`，訊息指出實際需要補充的原文詞彙，網頁保留原題供修改，不任意取前三項。系統未能產生有效選項時回傳 `status=error`、`code=clarification_generation_failed`，不將模型格式或證據錯誤當成使用者問題不清楚。明確不存在的底線識別碼不能改配其他欄位。完整詞彙、篩選值及粒度不符不能透過人工確認放行。

網頁的待確認資料只包含隨機 ID、業務詞彙、固定原因、業務選項及重新描述標記；實際 View／column 對應留在伺服器 checkpoint。語意及粒度判斷仍依賴模型理解契約，逐字證據與程式檢查不能證明自然語言語意必然正確，需以實際題組持續驗證。

確認完成後，下一題遇到相同完整詞彙、來源與契約時可直接沿用。回應中的獨立 `term_mapping_reasoning` 陣列提供詞彙、View、column、業務描述、紀錄 ID、確認時間、來源與固定依據說明；人工來源為 `confirmed_this_request` 或 `reused_confirmation`。唯一候選自動採用的來源為 `automatically_resolved`，紀錄 ID 與確認時間為 null。這是可查證的欄位對應依據，不是模型內部推理。

## 部署與儲存

- 使用 **一個 application worker**。LangGraph checkpoint 僅在記憶體，重啟後舊確認失效。
- 等待確認預設 15 分鐘，最多 1,000 個活躍工作；過期或容量滿時明確回報。成功、取消、失敗與到期會清除完整 checkpoint，去重標記只留隨機 ID、狀態與期限。
- 預設寫入選定 profile 的 `terms_mapping.json`。可透過可信設定 `CPEA_TERMS_MAPPING_PATH` 指定其他可寫路徑；相對路徑以選定 env file 所在目錄解析。API 不接受儲存路徑。
- 同部署的 profile／datasource scope 共用字典，不是個人字典。沒有 datasource 時記為 null，之後綁定來源需要重新確認。
- JSON 採 UTF-8 無 BOM，保留既有 LF／CRLF。保存前會重讀、檢查 scope／revision、合併並行更新，再以同目錄暫存檔原子替換。同詞在同 View 改到不同欄位，必須另一次明確取代確認。
- 檔案不存在表示空字典；毀損、schema／scope 不符不當成空檔，不自動覆寫。保存失敗時 `status=error`、`sql=null`，不執行 DB、不自動重試。
- 手動編輯 JSON 前先停止服務。預設詞彙檔已排除於 Git 與發佈產物；自訂檔名請自行放在受保護、未追蹤的資料路徑。
- 只保存詞彙對應，不保存整段問題、訊息、SQL、rows 或瀏覽器 session ID。不使用瀏覽器儲存還原問答。當題畫面可保留到新問題或重新整理。

JSON 根層有 `schema_version=1`、`revision`、`scope`、`mappings`。每筆包含 `id`、`term`、`normalized_term`、`view`、`column`、`view_contract_fingerprint`、`status`、`relation`、`confirmed_at` 與 `confirmed_by`。未知確認者為 null。正規化僅去除前後空白、統一 ASCII 大小寫，保留稅別、單據種類等修飾。

## JSON API

| 初始入口 | 確認入口 | 成功行為 |
|---|---|---|
| `POST /api/assistant/sql` | `POST /api/assistant/sql/confirm` | 只生成 SQL |
| `POST /api/assistant/query` | `POST /api/assistant/query/confirm` | 執行一次並合成答案 |
| `POST /api/assistant/query/stream` | `POST /api/assistant/query/confirm/stream` | 新串流先送 SQL，再執行並送結果 |

初始 JSON API 的 history 只接受缺省或空陣列；非空回 422 `history_not_supported`。串流初始入口僅接受 request，其他鍵被拒絕。依賴上一題補條件的追問，需要改成完整問題重新提交。

生成回應的 `status` 為 `ready`、`needs_confirmation`、`unsupported`、`cancelled` 或 `error`。只有 ready 的 supported 為 true 且有 SQL；待確認、取消或拒絕都不執行 DB。JSON query 成功維持 `AssistantQueryResponse`，等待或無法承接則回 `SQLGenerationResponse`。

待確認的 `clarification` 包含 `confirmation_id`、`expires_at`、`kind` 與 `items`。每個 item 有完整詞彙、原因、View、item ID，以及包含 option ID、column 與描述的合法選項。client 只能回傳 server 核發的 ID，不可傳 SQL、任意欄位、另一個 View 或修改原問題。

確認格式（ID 必須取自前一次回應）：

```json
{
  "confirmation_id": "SERVER_CONFIRMATION_ID",
  "action": "confirm",
  "decisions": [
    {"item_id": "SERVER_ITEM_ID", "option_id": "SERVER_OPTION_ID"}
  ]
}
```

取消不需 decisions：

```json
{"confirmation_id": "SERVER_CONFIRMATION_ID", "action": "cancel"}
```

重新描述使用 `action=rephrase`，同樣不得包含 decisions。伺服器清除本次等待且不保存詞彙，以 `status=cancelled`、`code=clarification_rephrase` 回覆；網頁進入可編輯狀態並還原原題。原確認 ID 隨即失效。

取代確認使用相同格式，`kind=replace_mapping`。server 綁定原有紀錄 ID 與新目標；若目標再被其他題改變，就重新發選項，不沿用過期授權。

缺項或非法選項為 422 且保留等待；已處理或處理中為 409；過期、重啟或契約失效為 410。ID 綁定呼叫模式；SQL 確認 ID 不能拿到 query 入口執行。網頁另綁定其短期 session。

SSE 待確認時只有 `clarification` 終止事件，不送 SQL；恢復後才是 `sql → result`，或 `sql → error`。取消為 `cancelled`，拒絕為 `unsupported`。`sql` 事件包含 `term_mapping_reasoning`；ASGI 完成 SQL frame 傳送前不啟動 DB。

## 斷線與新問題

確認或取消送出後若斷線，網頁顯示「無法確認處理結果；舊請求可能仍完成」，停用舊按鈕，不自動重送。使用者可明確按「放棄等待，開始新問題」，換掉當題 UI 版本與 gate；原 server 工作仍依原生命週期結束，舊 callback 不得覆蓋新題。已送出的同步 DB 與已明確同意的 JSON 保存不保證撤回。

等待時按「新問題」會先取消原題；若 server 已在處理，維持原題處理中。此流程沒有查詢歷史或遺失結果的恢復功能。

## CLI

互動終端在同一程序逐組選擇編號；0 或「都不符合」停止。非互動終端遇到待確認時輸出結構化回應並以 **exit 4** 結束，不支援另開 CLI 程序恢復記憶體 checkpoint。compact 與 verbose 輸出都保留獨立對應依據。

## 驗證與限制

```bash
uv sync --locked --group dev --all-extras
uv run --locked --all-extras pytest
uv build
uv run --locked cpea-eval --project retail --prompt-version v10 --runs 3 --concurrency 1
```

真實評估需另外提供私有 profile、模型設定與已核准題組。HILP 案例使用 `case_kind=hilp`，指定初始狀態、完整待確認詞彙、明確選項腳本、最終欄位與是否驗證下次沿用；不讓模型替使用者決定。新題需按當前契約與 case fingerprint 人工審核後才正式採計。每個案例／每次重複使用隔離的 temporary JSON，不能污染部署字典。

保留 v1–v9 prompt/schema 供離線比較，預設為獨立 v10。舊 Retail 題庫產生器固定 v6，不會自動改寫既有 ground truth。`--prompt-version` 只選評估 prompt，不能繞過正式流程的確認關卡；歷史 v6 成績需連同當時 commit、題目與契約指紋一起比較。

v10 優先產出欄位與查詢子句映射，`terms`、`syntax_spans` 可留空，由程式從原文獨立檢查；若模型提供區間，仍須通過逐字驗證，不接受猜測位置。待確認詞彙會移除該用途已明示的聚合、比較值及排序語法，例如「預估淨額的單列最大值」保留「預估淨額」，而含稅、發票等業務限定詞仍須保留。普通列門檻即使搭配分組也必須使用 WHERE；HILP 不會放行錯誤的 HAVING。

這是保守的證據與原文字元覆蓋檢查，不能證明已完整解析所有自然語言關係。沒有證據的新同義詞可能需要首次確認；多指標修飾等剩餘風險仍須透過題組檢查。JSON 整檔讀寫成本隨記錄數增加；目前未支援大型字典索引、多程序寫入、SSO 或個人詞彙權限。
