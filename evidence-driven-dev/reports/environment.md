# 環境調查（Phase A）

調查日期：2026-10-19；所有結論以實際命令與官方文件交叉檢查。

| 項目 | 結果 |
|---|---|
| Codex | codex-cli 0.163.0 |
| Skills | Repo `.agents/skills`；使用者 `~/.agents/skills`；系統 `/etc/codex/skills`；本機另有 `~/.codex/skills` 的相容安裝 |
| Subagent | 本回合可呼叫 collaboration 工具；`codex features list`：multi_agent=true |
| Hooks | hooks=true；支援 SessionStart、SubagentStop、Stop；stdin JSON；stdout JSON |
| Superpowers | 原始 Skills 目錄與 Plugin cache 未找到；已詢問安裝意願；目前降級 |
| OpenSpec | CLI 1.4.1；已有 openspec/specs 與多個進行中的 changes |
| AGENTS.md | Repo 未有檔案；本回合使用者提供編碼、語言、quota 規範 |
| Git | feat/progressive-view-retrieval；HEAD 014cee1aff3abcfb51bbe5af6db0abd2ef060225；4 個 Worktrees |
| 未提交變更 | 已有多個業務程式、測試、文件與 dependency 變更；EDD 不覆蓋 |
| Python | 專案 3.12；.venv 有 pytest 9.1.1、PyYAML 6.0.3 |
| 測試 | pytest tests/（unit / contracts / integration）；README 指令 uv run --locked --group dev --all-extras pytest |
| Lint / Formatting / CI | 未找到既有設定或 .github workflows；不另改既有 pyproject / uv.lock |

可重用：Codex 原生 Skills 探索、Subagents、Hooks、Git Worktrees、OpenSpec、pytest。
需實作：檔案式 Ledger、Schema、轉移守門、實驗與驗證證據、明確 Agent 對應、恢復、三個 EDD Skills、安全 Hook adapters。

官方依據：

- [Skills 探索與 Frontmatter](https://learn.chatgpt.com/docs/build-skills)：Repo 向上探索 `.agents/skills`，支援 symlink；變更會自動偵測。
- [Hooks](https://learn.chatgpt.com/docs/hooks)：Repo `.codex/hooks.json`；需要使用者審查與信任；Stop/SubagentStop 以 decision=block 請求續行，重入旗標 stop_hook_active；不修改信任資料。
- [Superpowers](https://github.com/obra/superpowers)：目前官方建議 Codex Plugin marketplace；只引用可實際探索並讀取的 Skill。
- [OpenSpec](https://github.com/Fission-AI/OpenSpec)：沿用既有變更機制；EDD 保存執行證據而非複製規格。

本報告是安裝時快照。移植或升級 Codex 後需重新探查；不能將目前能力當成跨版本保證。

## 安裝後複查（2026-10-19）

使用者回覆「都安裝好了」後，實際 `codex plugin list --json` 確認 Superpowers 6.4.2 installed=true、enabled=true；精確版本 cache manifest 宣告 `./skills/`，八個目標 Skills 均可讀取，當前對話 Skill 目錄亦包含 `superpowers:` 名稱。三 EDD Hooks 已 trusted／enabled。

獨立 app-server 的 skills/list 仍只列出 Repo Skills，不能單憑此清單判定 Plugin 未安裝。EDD capabilities 已修正為合併安裝清單、精確版本 manifest 與可讀路徑，保留 discovery provenance；missing=[]、plugin_errors=[]。初次調查的 missing 是當時環境快照，不代表目前狀態。
