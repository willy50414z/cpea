# Superpowers 安裝後整合複驗

使用者實際回覆：「都安裝好了」。不重新安裝、不更改 CODEX_HOME、不修改 Hook 信任資料。

## 實際安裝與可載入性

`codex plugin list --json`：superpowers@openai-curated-remote，version=6.4.2，installed=true，enabled=true。manifest 為 `.codex-plugin/plugin.json`，宣告 `./skills/`。八個目標 Skills 的實際絕對路徑、版本、Frontmatter 與內容 sha256 見 [skill-discovery.json](skill-discovery.json)，均 readable=true；當前對話 Skill 目錄亦確實列出這八個 `superpowers:` Skills。

三個 EDD Hooks 的真實 hooks/list 結果均為 enabled=true、trustStatus=trusted，無 hook_errors。不把「已信任」當作「事件已觸發」，真實生命周期結果另見 live-hooks.json。

## 實際流程引用

本輪已讀取並使用 using-superpowers、systematic-debugging、test-driven-development、verification-before-completion、requesting-code-review；獨立 Reviewer 亦載入 review／verification Skill。用這些既有流程診斷能力探測器、補 RED 測試、最小修正、GREEN 與獨立審查。第三方 Skill 全文沒有複製進 Repo。

其餘 brainstorming／writing-plans／subagent-driven-development／dispatching-parallel-agents 依適用任務引用；本次沒有為完成形式而重新執行原已批准的設計流程。安裝與可讀證據不等同所有 Skill 在所有情境下的行為品質證明。

## 根因與修正

症狀：使用者安裝後，EDD 仍報八 Skills missing。

根因：舊 capabilities 只採 app-server skills/list，而新的獨立 app-server 不回報當前宿主 Plugin 的安裝 Skill 路徑。CLI Plugin 安裝清單與本回合的實際 Skill 目錄均證明 Plugin 已安裝。

修正：保留 Repo 探索，加上 CLI 的 installed／enabled 清單、精確版本與 manifest 所宣告之 Skills 根目錄；不得單看 cache，也不改成選「最新」cache 版本。每項標記 installed-plugin-manifest，與 skills/list 區別來源。無法讀取／版本錯誤／越界均清楚診斷，缺少時仍可降級。

新增五項契約測試涵蓋正常安裝、disabled／cache-only、錯誤版本、宣告路徑越界與錯誤 JSON 型別。原先測試因缺少 Plugin 探索而失敗，修正後五項通過；獨立 Reviewer 實跑完整 49 項通過且無阻擋。Minor：現行 parser 僅支援已知套件的未加引號 name scalar；其他有效 YAML 形式目前會明確診斷，不能宣稱支援任意第三方 Frontmatter。
