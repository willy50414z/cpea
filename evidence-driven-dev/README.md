# Evidence-Driven Development（EDD）

先確認問題與證據，再執行能區分假設的最小實驗。任務狀態保存在檔案，可跨 Session 恢復；測試未執行不能宣稱成功。

## 安裝

需求：Python 3.10+、Git、已有至少一個 Commit。CLI 與測試僅使用標準函式庫；Codex 與 Superpowers 均為可選整合。

在其他專案複製 `.agents/skills/edd*`、`evidence-driven-dev/`（排除 tasks、archive、reports、.local）、`.codex/hooks/` 及經審查的 `.codex/hooks.json`，將根目錄 AGENTS.md 的 EDD 協定合併到既有規範，不覆蓋原規則。保留目錄相對位置；不要只安裝 Skills 而遺漏 CLI。`tasks/` 和 `archive/` 由 init／archive 建立。

```bash
python3 -m unittest discover -s evidence-driven-dev/tests -v
python3 evidence-driven-dev/scripts/capabilities.py
python3 evidence-driven-dev/scripts/edd.py --help
```

Codex 自動探索 Repo `.agents/skills`；若未顯示則重新啟動。Capabilities 合併實際 app-server skills/list 與 `codex plugin list --json`；Plugin Skills 另外核對已安裝且已啟用的精確版本、manifest 宣告路徑和可讀內容，標記 discovery=installed-plugin-manifest。不把 cache 存在當成已安裝，也不把 Plugin 安裝探索與 skills/list 混成同一來源；整個探測不發起模型回合。Superpowers 未安裝時先詢問使用者；同意後使用目前官方 Plugin 安裝方式，重新執行探索後才引用 Skill。缺少時用 EDD references 中的基本診斷／TDD／驗證流程，不能自稱第三方整合已通過。

## 使用

```text
$edd 幫我調查這個 Bug。
$edd 幫我評估三種架構方案，先建立最小實驗，不要直接修改正式程式。
$edd resume fix-view-retrieval
```

```bash
python3 evidence-driven-dev/scripts/edd.py init --id fix-view-retrieval --type bugfix --goal '修正檢索契約' --scope src/retrieval --complexity moderate
python3 evidence-driven-dev/scripts/edd.py status
python3 evidence-driven-dev/scripts/edd.py resume --id fix-view-retrieval
python3 evidence-driven-dev/scripts/edd.py transition --id fix-view-retrieval --to INVESTIGATING
python3 evidence-driven-dev/scripts/edd.py checkpoint --id fix-view-retrieval --last '觀察基準' --current '建立 Replay' --next '測試第一個失敗邊界'
python3 evidence-driven-dev/scripts/edd.py validate --id fix-view-retrieval
python3 evidence-driven-dev/scripts/edd.py archive --id fix-view-retrieval
```

`--root <repo>` 和 `--actor <id>` 放在子命令之前。所有文字檔 UTF-8 無 BOM；覆寫現存文件時保留 CRLF／LF。exit 0 表示命令成功／紀錄有效，1 表示驗證或測試失敗，2 表示輸入／操作錯誤。`validate` 的 PASS 僅代表 Ledger 結構與當前階段門檻，不代表產品驗收已完成；必須另看 Task status 與 verification.result。

## 架構與責任

| 元件 | 責任 |
|---|---|
| edd | 分類、主狀態、User Gate、協作、恢復 |
| edd-investigate | 根因假設、單節點 Replay、S/M/L、MVP |
| edd-verify | 獨立 Oracle、Regression、反過擬合與驗收 |
| scripts/ledger.py | Schema、狀態守門、檔案安全、證據與歸檔 |
| scripts/edd.py | 明確 CLI 操作；不從 Markdown 執行命令 |
| .codex/hooks | 無模型的協定 adapters；不跑測試、不修改主 Task |

Skill 不等於 Subagent。Trivial 可省略工作區，仍需可靠測試；Moderate／Complex 建立 Ledger，Complex 需驗收條件與獨立驗證。官方 API 與環境快照見 [environment.md](reports/environment.md)。

## 單一狀態來源與 Schema v1

`tasks/<id>/task.md` Frontmatter 是唯一機器狀態來源。採 **JSON-subset YAML 1.2**：`---` 之間是 JSON 物件，因此亦是有效 YAML，不接受任意 YAML 語法。正文由 CLI 產生方便閱讀；不可只改正文期待狀態變更。用 `update --data-file <UTF-8 JSON>` 更新開放欄位；狀態、歷史、Agent Registry、實驗 ID、問題與 DEC 由專用命令管理。範例完整 Schema 在 [task.md](templates/task.md)。

必要欄位：schema_version=1、id、type（bugfix／feature／architecture／research）、complexity（moderate／complex）、status、phase、owner=main-agent、base_git_sha、branch、worktree、openspec_change、updated_at、goal、problem、scope、constraints、acceptance、progress、agents、experiments、decisions、questions、blockers、waiting、paused_from、checkpoint、plan、changes、verification、completion_summary、history。機器驗證以 ledger.py 的 schema_errors／gate_errors 為準。

- problem：description、expected、actual、evidence[]、hypotheses[]；假設含 id、claim、status=UNCONFIRMED／CONFIRMED／REFUTED，CONFIRMED 需 evidence。
- checkpoint：last_completed、current_action、next_action、required_inputs[]、unresolved_questions[]。
- plan：solutions[]（id、hypothesis、root_cause、benefit、scope、complexity、cost、risks、verification、falsification、rollback）、selected_solution、success、failure、regression[]、approval_required、approval（User DEC ID）。Complex 的 MVP 計畫可額外放 mvp[]。
- acceptance[]：id、description、status=PENDING／PASS／FAIL、evidence[]；完成時每項都必須有當前實際證據。
- changes：scope[]、revision、diff_fingerprint、tests[]。
- verification：result=PASS／PASS_WITH_WARNINGS／FAIL／BLOCKED／NOT_VERIFIED、reviewer、method、verified_at、revision、diff_fingerprint、tests[]、regression[]、unverified[]、warnings[]、blocking_issues[]。
- experiments[] 僅保存 ID 與假設識別；執行結果在 experiments/EXP-NNN.md，不能另建相互衝突的狀態索引。

Main 是主 Task 唯一 Writer。鎖檔防合作程序競態；`--actor` 是工作協定，不能防惡意程序直接寫檔。多檔案更新中斷可能留下 Registry／Report 不一致，validate／resume 會揭露，Main 核對實際證據後修復，不能猜測成功。

## 狀態守門

```text
CREATED → INVESTIGATING → PLANNING → EXPERIMENTING → IMPLEMENTING → VERIFYING → COMPLETED → ARCHIVED
                   ↑          ↑                                      |
                   └──────────┴──────────────────────────────────────┘
```

- 調查需問題／Scope／Owner；規劃需預期／實際、觀察與假設。
- 實驗需方案比較、成功／失敗標準、最小實驗與必要 User Gate。
- 實作需支持實驗、選定方案與 Regression 計畫。
- 驗證需變更 Scope、Git Revision、Diff 指紋及實際測試。
- 完成需所有驗收、必要測試與 Regression、無 Blocker、Handoff 整合、DEC、風險揭露與摘要。
- 歸檔另需 final-report.md，同名目錄不覆蓋。完成後變更程式需回 VERIFYING。

活躍任務可 WAITING_USER／BLOCKED／CANCELLED。ask 保存原狀態、問題來源、影響與恢復條件；answer 記錄真實使用者訊息並恢復。BLOCKED 需 blockers 描述恢復條件。單次只聚焦一個重大 User Gate，不得將時間經過視為批准。

## 實驗與證據

```bash
python3 evidence-driven-dev/scripts/edd.py experiment --id fix-view-retrieval --hypothesis-id H1 --hypothesis '邊界映射遺漏' --success 'Replay 契約通過' --failure '輸出仍錯誤'
python3 evidence-driven-dev/scripts/edd.py run --id fix-view-retrieval --kind focused --timeout 60 -- python3 -m unittest discover -s evidence-driven-dev/tests -v
python3 evidence-driven-dev/scripts/edd.py conclude --id fix-view-retrieval --experiment-id EXP-001 --conclusion SUPPORTED --evidence evidence/EV-實際編號.json --interpretation '依輸出判斷，不能預填成功'
```

命令輸出 evidence path，供 update 中 tests／regression／acceptance 參照。`run` 不經 Shell；只執行明確 argv，不讀取 Task 內任意 Shell。逾時殺掉自己的程序群組、保存 exit=124。測試過程若原始碼改變則不能驗收。輸出在 `.local/`，Git 忽略；精簡 evidence JSON 保存輸出 hash、命令、版本、指紋、時間與退出碼。不要把秘密放在 argv 或 metadata，提交前審查脫敏摘要。

指紋包含 tracked／untracked 原始檔內容、可執行位、HEAD，排除 Ledger tasks／archive／reports／.local／鎖檔；保存證據不會使自身過期。證據 hash 能偵測意外改動，不能防有意偽造；CLI 不判斷測試 Oracle 的業務正確性。

每次盡量只改一個變數，保留 Baseline 與所有失敗。三次實質修正同假設 REFUTED 後，CLI 要求結構化 plan.reassessment（experiments、rejected_hypothesis、oracle_review、problem_review、new_direction、new_hypothesis_id）；Main 需整理三次 I/O、Diff、Oracle、否定假設和新方向，重大方向變更交 User Gate。不得只填一句文字繼續相同假設。

## 多 Agent 與 User Gate

```bash
python3 evidence-driven-dev/scripts/edd.py agent --id fix-view-retrieval --agent-id cause --assignment '唯讀研究根因' --scope src/retrieval
python3 evidence-driven-dev/scripts/edd.py --actor cause handoff --id fix-view-retrieval --agent-id cause --data-file /tmp/cause-handoff.json
python3 evidence-driven-dev/scripts/edd.py integrate --id fix-view-retrieval --agent-id cause
```

先建立獨立 Report，再實際 spawn；使用 `agent-map --id <task> --agent-id <id> --platform-id <實際平台ID>` 對應真實 platform_id。Main 讀證據後整合；BLOCKED／NEEDS_USER_DECISION 不當 DONE。問題由 Main ask／answer，真實答案回傳 Agent。平行實作使用隔離 Worktree；不能假設未提交檔案共享。詳見 [multi-agent.md](../.agents/skills/edd/references/multi-agent.md)。

## Hooks 啟用、信任與降級

先執行 Hook 測試，再放置設定。官方來源：[Hooks](https://learn.chatgpt.com/docs/hooks)。`.codex/hooks.json` 由 Codex 載入，但必須由使用者在 `/hooks` 審查與信任；EDD 不修改信任資料、不繞過權限。初始 config.yaml hooks_mode=advisory，只警告；改為 enforce 可對明確完成但缺少證據續行一次。使用 `python3 evidence-driven-dev/scripts/edd.py hooks-mode --mode enforce` 更新（不會授予 Hook 信任）。

SessionStart 將 Task／Checkpoint／待答問題加入 additionalContext。多任務要求明確 ID 或 `bind --session-id <實際 session_id>`；SubagentStop 使用 Registry.platform_id=event.agent_id，不解析不穩定 transcript，也不猜 Report。Stop 以 `[EDD-COMPLETE:<id>]` 明確完成標記觸發，狀態轉移本身另有強制驗收；一般聊天與中間報告不阻擋。WAITING_USER／BLOCKED 可正常回覆；重入 stop_hook_active=true 不再阻擋。無對應、格式錯誤或缺能力會警告且安全降級；不會自動執行測試。

## OpenSpec、CI 與故障排除

重大功能／架構需要正式規格時連結 openspec_change，相對路徑雙向參照；不重複規格，小 Bug 不強制 Change。既有 OpenSpec 與使用者規則優先。

CI 僅對 EDD 範圍變更跑標準庫測試、UTF-8／連結／Skill 契約與 Ledger validate；不在每次修改跑產品完整 E2E。產品測試保持既有命令。可在 pre-commit 加快篩選的 formatting／lint／靜態檢查，Repo 目前無既有 formatter，第一版不另加入 dependency。

- 重複 ID：選新 ID，包含 Archive 的識別碼均不可重用。
- 多個 Active Task：明確指定 ID／bind，不預設最新任務。
- .edd.lock 遺留：確認 PID 與 writer 均已停止，再手動移除；不要自動搶鎖。
- 證據過期：核對 Git 與工作樹，重新執行必要測試；不能修改 hash 騙過驗證。
- COMPLETED 但證據缺少：resume 會回 errors，Main 回 VERIFYING；不得直接信任完成狀態。
- Plugin 已安裝卻顯示缺 Skill：先看安裝清單、enabled、版本與 plugin_errors；獨立 app-server 的 skills/list 可能只列 Repo／User Skills，不能單憑它判定 Plugin 未安裝。
- Superpowers 確實缺少：走自身基本流程，揭露第三方整合 NOT_VERIFIED。
- Hook 不執行：核對 features.hooks、專案信任與 `/hooks`；不使用 bypass 旗標。
- Subagent 中斷／Worktree 失效：讀 Report／Base SHA，確認檔案／Commit 實際存在，再決定恢復或重新派遣。

測試結果、失敗、未驗證能力與評估限制將保存於 reports/；不得因檔案產生成功就宣稱 EDD 提高根因準確率。

## 可攜驗證與歸檔中斷

`validate --portable` 用於 CI 或跨機器檢查歷史紀錄的 Schema、狀態、內部證據版本一致性，刻意不將原始工作樹當作目前 Checkout。它不能作為正式完成的證據；transition COMPLETED、Stop、resume 仍會檢查當前版本。歸檔保存完成當時的證據，無需因後續其他任務變更而重測。

歸檔遇一般 I/O 錯誤會回復原狀態；若程序恰於寫入 ARCHIVED 與移動之間被終止，resume 會明確指出歸檔中斷，核對目標後重新執行 archive 可完成移動且不重複歷史。

## 跨專案複製指令

以下指令只建立新安裝；目標已存在時會拒絕覆蓋。Hook 設定仍需審查，AGENTS.md 請手動合併原規則。

```bash
EDD_TARGET=/absolute/path/to/another-repository python3 - <<'PY_INSTALL'
import os
from pathlib import Path
import shutil
source = Path.cwd()
target = Path(os.environ['EDD_TARGET']).resolve()
for name in ('edd', 'edd-investigate', 'edd-verify'):
    shutil.copytree(source / '.agents/skills' / name, target / '.agents/skills' / name)
shutil.copytree(source / 'evidence-driven-dev', target / 'evidence-driven-dev',
                ignore=shutil.ignore_patterns('tasks', 'archive', 'reports', '.local', '__pycache__', '*.pyc', '.edd.lock'))
shutil.copytree(source / '.codex/hooks', target / '.codex/hooks')
with (target / '.codex/hooks.json').open('x', encoding='utf-8') as output:
    output.write((source / '.codex/hooks.json').read_text(encoding='utf-8'))
PY_INSTALL
```

完整交付與測試結果見 [delivery.md](reports/delivery.md)；受控案例比較見 [evaluation.md](reports/evaluation.md)。複製到新專案時 reports 會被排除，README 的報告連結應改為來源 Repository 的對應網址。
