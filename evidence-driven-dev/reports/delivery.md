# EDD v1 交付與驗證報告

## A．架構

三個 Repo Skills：edd 管理分類、Task Ledger、User Gate 與協作；edd-investigate 管理根因、S/M/L、MVP 與最小實驗；edd-verify 管理獨立 Oracle、Regression 與反過擬合。Skill 不等於 Subagent，Trivial 不建立完整工作區。

標準庫 CLI 與 ledger.py 共用唯一 Schema／轉移驗證。task.md Frontmatter 是權威狀態；正文是閱讀檢視。實驗檔不可覆蓋，Agent Report 分開保存；Hook adapters 不修改主 Task、不執行 Markdown 命令、不跑測試。執行資料與可重用 Skills 分離。

## B．新增與修改檔案

所有 EDD 檔案均為新增；既有 CPEA 未提交變更保留，未修改正式 Retrieval／SQL 演算法與既有 pyproject／uv.lock。完整逐檔清單見 [files.md](files.md)。

- AGENTS.md：保存使用者的編碼、語言與 quota 規則，加入 EDD。
- .agents/skills/：三個 SKILL.md 與 10 份 references。
- evidence-driven-dev/：config、README、五模板、CLI／Ledger／validator／capability probe／Hook runtime／asset checks、測試、離線 fixtures、可重跑評估結果、環境與交付報告。
- evidence-driven-dev/tasks/build-edd/：本次 Task、決策、實驗、三份真實 Subagent Report、測試 evidence；原始輸出在忽略的 .local。
- .codex/hooks.json 與三個 adapters。
- .github/workflows/edd.yml：EDD 範圍的標準庫測試、assets 與 portable Ledger 驗證；不取代產品 CI。

## C．安裝與啟用

本 Repo 已可直接使用 `$edd`。可攜安裝指令與相依條件見 [README](../README.md)。CLI 僅需要 Python 3.10+、Git 與初始 Commit；不新增 runtime dependencies。

```bash
python3 -m unittest discover -s evidence-driven-dev/tests -v
python3 evidence-driven-dev/scripts/check_assets.py
python3 evidence-driven-dev/scripts/capabilities.py
python3 evidence-driven-dev/scripts/edd.py status
```

Codex 自動探索 `.agents/skills`，必要時重啟。Hook 載入需要使用者在 Codex `/hooks` 審查與信任；此實作未修改 trust store 或繞過安全確認。config.yaml 預設 advisory；信任後可依需求使用 `hooks-mode --mode enforce`。使用者已完成 Superpowers 6.4.2 安裝；八個目標 Skills 已查證可用，未重裝。

## D．使用

```text
$edd 幫我調查這個 Bug。
$edd 幫我評估三種架構方案，先建立最小實驗，不要直接修改正式程式。
$edd resume fix-view-retrieval
```

主流程：init／resume → INVESTIGATING → PLANNING → EXPERIMENTING → IMPLEMENTING → VERIFYING → COMPLETED → archive。必要時 ask／answer 保存 WAITING_USER；Subagent 使用 agent／agent-map／handoff／integrate。`validate` 的 PASS 只是紀錄與階段門檻通過，不能代替產品完成驗收。

## E．實際驗證

| 範圍 | 實測結果 |
|---|---|
| Phase B MVP | 首批 12 測試，再完整 18 測試通過，之後才加入 Skills／Hooks |
| Skills 格式 | 三個 skill-creator quick_validate 均通過 |
| Codex Skills 載入 | 真實 app-server skills/list：edd／edd-investigate／edd-verify enabled=true、readable=true、errors=[] |
| Codex Hook 設定 | 真實 hooks/list：三事件均辨識，hook_errors=[]；trustStatus=trusted |
| EDD 最終契約 | 49 個標準庫測試（包含 Hook、恢復、三次失敗、Writer、Git Worktree／子 Repo、歸檔與安全守門） |
| 既有產品回歸 | `.venv/bin/python -m pytest tests/unit tests/contracts -q`：301 passed in 23.29s |
| 獨立 Reviewer | 五類實際 repro 已修正並複驗；指定範圍無剩餘具體阻擋 |
| 一般流程案例 | 33 個測試方法通過；原始 RED、Replay、三次 threshold 失敗均保留 |
| EDD 流程案例 | 28 個測試方法 + 8 個實作後才新增的 holdout assertions 通過；CLI 停止第四次同假設實驗 |
| 恢復與使用者等待 | 新 CLI subprocess 恢復 Checkpoint、模擬 WAITING_USER/answer、舊證據過期拒絕；真實使用者詢問 0、模擬事件 1 |
| 真實多 Agent | 兩位隔離評估者及一位 Reviewer，各自 Report，Main 已讀證據並整合；未平行共改正式程式 |

精確最終命令、輸出摘要與 EV 參照另保存於本任務 final-report.md／evidence。完整比較與限制見 [evaluation.md](evaluation.md)。測試已執行，不把文件產生當成產品效果證據。

### 實際失敗與修復

- 初次 RED 因 Ledger 尚未存在而匯入失敗，之後建立核心。
- 完整歸檔測試發現 lock 檔使證據假性過期，排除執行紀錄後修正。
- 額外守門測試重現六個缺口：缺 Report 完成、清空 Scope 完成、巢狀 Schema、單句 reassessment 繞過、未回答問題整合、Worktree 不一致未揭露；先 RED 後修正。
- Reviewer 實際重現暫停鏈恢復失敗／孤兒 DEC、錯誤 JSON 型別崩潰、Agent Report 不一致、Archive I/O 後狀態錯誤、Git 子 Repo 指紋遺漏；已補測試與修正。
- 補上歸檔恰好中斷的明確診斷與安全續行，不重複歷史。
- EDD 評估 harness 一次換行轉義造成 SyntaxError，保留失敗後修正命令，未修改 Oracle。

### 明確未驗證

Superpowers 6.4.2 八個目標 Skills 均可讀，當前模型 Skill 目錄已提供；適用的 debugging／TDD／review／verification 已實際引用。能力探測器原只看 skills/list 造成誤報，已補五項測試與修正。Hooks 的 Script／協定／設定已測，使用者已信任，三種真實 Codex lifecycle 事件均完成；巢狀 CLI 子代理被 bwrap 限制，未完成該次正向 Handoff，實際阻塞與安全降級已保存。未真的終止目前 Codex Session 或觸發 Context Compact，只驗證檔案與 fresh subprocess 恢復。未執行會依賴外部服務的完整 CPEA Integration／LLM／資料庫 Benchmark；產品 Unit／Contract 已通過。新增 GitHub Actions workflow 在本機執行相同命令，但未推送遠端 CI。

## F．剩餘風險與任務狀態

本次 Task 已 COMPLETED，結果 PASS_WITH_WARNINGS。使用者安裝與 Hook 信任已實際查證；Q-001 已 ANSWERED。三種 Hook 已收到真實 completed 事件。巢狀 CLI 子代理因 bwrap 受阻未能自行保存 Handoff，由 Main 依實際訊息保存 BLOCKED 並明確處置，沒有假稱 DONE。一般 collaboration Agent 正向交接已另行實測，Report 映射與守門亦有自動測試。

三個離線案例兩組都找對根因，不能推論 EDD 準確率優於一般流程。沒有 Token／貨幣成本數據，不宣稱節省成本。機器證據 hash 可偵測意外改動，不能防惡意 Agent 偽造；actor 與鎖是合作協定，不是 OS 身分隔離。

多檔案寫入不具資料庫交易；中斷後 validate／resume 揭露衝突，Main 核對修復。正式 Benchmark 要固定乾淨 Git Revision；本回合保留既有未提交變更，採 Git SHA＋Diff 指紋，不能稱為正式效能 Benchmark。複製到新環境需重新探測 Codex 協定與外部設定。

## G．延後功能

DB Task Storage、Web Dashboard、大規模排程、分散式佇列、閒置 Agents、逐工具完整 E2E、自動重試、LLM Hook 判定均未實作。僅在檔案工作流出現可量測瓶頸或新增明確需求時重新評估；DEC 已保存理由與啟用條件。小 Bug 不強制 OpenSpec；本次不改既有正式規格與正式產品架構。

## 安裝後複驗補充

目前 Superpowers 版本 6.4.2；八個目標 Skills 可用，missing=[]、plugin_errors=[]。三 EDD Hooks trusted，且在真實 Codex 回合收到 SessionStart、SubagentStop、Stop 的 completed 通知。完整證據見 [superpowers-integration.md](superpowers-integration.md) 與 [live-hooks.json](live-hooks.json)。完整 EDD suite 現為 49 項；獨立 Reviewer 無阻擋。

Plugin 安裝與可讀性探索保留 installed-plugin-manifest 來源，不與獨立 app-server skills/list 混淆。Parser 的 quoted YAML name 支援仍屬 Minor 限制，對目前 6.4.2 無影響。核心 Skills 不複製第三方全文，未為形式而強迫重新啟動已完成的設計流程。
