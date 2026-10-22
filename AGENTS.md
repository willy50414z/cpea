# Repository Agent 規範

## 文字與語言

所有文字檔以 UTF-8 讀取、UTF-8 無 BOM 寫入，保留既有換行。Python I/O 明確指定 encoding="utf-8"。顯示亂碼時先檢查 viewer／terminal，不任意轉碼。Markdown 文件與使用者回覆使用繁體中文；程式碼、技術術語與既有英文註解可保留。

## 帳號與額度

遇 rate limit 不重跑。先保存 terminal output，透過 Python 判讀：

```bash
Q=~/.claude/skills/account-switch/bin/quota.py
python3 "$Q" inspect-terminal -t codex --file terminal-output.txt
python3 "$Q" handle-terminal '<profile>' --file terminal-output.txt
```

主要帳本 `~/.hasna/accounts/account-switch.json` 僅透過 Python JSON API 或 quota.py 讀寫，不使用 cat、sed、regex 或手動編輯。accounts usage 回 unknown，不能判斷額度。切換 Codex 帳號不得改 CODEX_HOME；使用 quota.py swap 就地更新 auth.json，live account 以 auth fingerprint 判斷。完整說明 `~/.claude/skills/account-switch/SKILL.md`。

