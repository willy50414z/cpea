# 技術決策

尚未採納方案；不得以備用程式碼代替決策紀錄。

## DEC-001

```json
{
  "id": "DEC-001",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "採用標準庫 JSON-subset YAML 與單一 task.md 狀態來源",
  "alternatives": [
    "S：檔案＋標準庫",
    "M：外部狀態套件",
    "L：DB／Dashboard／排程"
  ],
  "reason": "18 項 MVP 與後續守門測試支持最小部署；使用者已明確要求 v1 範圍",
  "risks": "Machine Frontmatter 不接受完整 YAML 語法；合作 Writer 非 OS 安全邊界",
  "revisit": "跨大量任務出現實際查詢／競態需求",
  "references": [
    "EXP-001",
    "reports/environment.md"
  ],
  "at": "2026-10-19T15:21:31+00:00"
}
```

## DEC-002

```json
{
  "id": "DEC-002",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "延後 DB、Web Dashboard、大規模排程、逐工具 E2E 與自動重試",
  "alternatives": [
    "無資料庫",
    "無 Web 服務",
    "無閒置 Agents"
  ],
  "reason": "使用者 v1 明確排除；目前無支持新增架構的證據",
  "risks": "大型團隊規模尚未實測",
  "revisit": "檔案工作流出現可量測瓶頸後再研究",
  "references": [
    "reports/evaluation.md"
  ],
  "at": "2026-10-19T15:21:31+00:00"
}
```

## DEC-003

```json
{
  "id": "DEC-003",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "保留 Hook 信任審查與 Superpowers 降級",
  "alternatives": [
    "advisory Hook",
    "使用者 /hooks 信任後 enforce",
    "取得安裝同意後第三方整合"
  ],
  "reason": "Codex hooks/list 顯示 untrusted；目標八個 Superpowers Skills missing",
  "risks": "正式 Hook 事件及第三方行為未驗證",
  "revisit": "取得安裝決策與 Hook 信任後",
  "references": [
    "reports/skill-discovery.json"
  ],
  "at": "2026-10-19T15:21:31+00:00"
}
```

## DEC-004

```json
{
  "id": "DEC-004",
  "source": "user",
  "question_id": "Q-001",
  "summary": "已由使用者完成安裝 Superpowers 與 Hook 信任；不需要重新安裝",
  "evidence": "本回合使用者訊息：「都安裝好了」；codex plugin list installed/enabled 與 hooks/list trusted 實際確認",
  "at": "2026-10-19T15:57:46+00:00"
}
```

## DEC-005

```json
{
  "id": "DEC-005",
  "status": "ACCEPTED",
  "source": "main-agent",
  "summary": "安裝後合併 Repo 與 Plugin 能力來源；保留探索 provenance",
  "alternatives": [
    "只看 skills/list（已反證）",
    "把 cache 當安裝（拒絕）",
    "核對 installed/enabled、精確版本、manifest 與可讀 Skill（採納）"
  ],
  "reason": "實際 CLI 已安裝 Superpowers 6.4.2，但獨立 app-server skills/list 未提供其路徑；五項 RED/GREEN 與獨立審查支持修正",
  "risks": "目前只支援已驗證的未加引號 Skill name；Plugin inventory 與模型實際載入是不同證據",
  "revisit": "Codex API／Plugin cache schema 改變時重新探查",
  "references": [
    "reports/superpowers-integration.md",
    "reports/skill-discovery.json"
  ],
  "at": "2026-10-19T15:58:49+00:00"
}
```
