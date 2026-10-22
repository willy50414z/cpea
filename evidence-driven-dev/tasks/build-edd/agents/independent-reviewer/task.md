---
{
  "parent_task": "build-edd",
  "agent_id": "independent-reviewer",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "獨立審查 Ledger／Hooks 的資料安全、驗收守門與恢復缺陷",
  "allowed_scope": [
    "evidence-driven-dev/scripts/",
    "evidence-driven-dev/tests/",
    ".codex/hooks/",
    "自己的 Report"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/independent_reviewer",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "Plugin 修正獨立審查：新增 5 測試與完整 49 測試全部通過；真實 capabilities 探測列出 8 個已安裝啟用且可讀的 Superpowers Skills。無阻擋，僅 quoted YAML name 非阻擋相容性限制。",
    "evidence": [
      "python3 -m unittest discover -s evidence-driven-dev/tests -p test_capabilities.py -v：5 tests／0.009s／OK",
      "python3 -m unittest discover -s evidence-driven-dev/tests -v：49 tests／4.526s／OK",
      "python3 evidence-driven-dev/scripts/capabilities.py --root /home/willy/code/cpea：missing=[]、plugin_errors=[]、3 Repo Skills＋8 Superpowers 6.4.2、3 Hooks trusted",
      "tempfile repro：嚴格 bool、manifest exact version、外部 Skill symlink；quoted YAML name false-negative"
    ],
    "risks": [
      "installed-plugin-manifest 只證明 CLI 安裝與啟用清單交集中的精確版本 Skill 可讀，不等於特定模型回合已載入或執行全部 Skills",
      "name regex 不支援有效 YAML quoted scalar；目前 Superpowers 6.4.2 不受影響，屬 Minor"
    ],
    "next_step": "本輪需求可接受；Main 可選擇補 quoted YAML name regression 或將限制保留為 Minor。完成 Gate 應重新 integrate 本 Report。",
    "diff_reference": "Base／HEAD 均 014cee1aff3abcfb51bbe5af6db0abd2ef060225；直接審查未提交 capabilities.py 與 test_capabilities.py；僅更新本 Report"
  },
  "blockers": [],
  "question": null
}
---
# 獨立審查報告

## 任務與方法

唯讀審查 `ledger.py`、`edd.py`、`hook_runtime.py`、`.codex/hooks/*.py` 與 EDD 測試。所有 repro 使用 `tempfile.TemporaryDirectory()` 建立隔離 Git Repository，實際呼叫 `Ledger`，不修改正式產品與其他 Agent 紀錄。不啟動額外 Agent。

## 已重現缺陷

### 1. 暫停巢狀轉移會破壞 WAITING_USER 恢復（阻擋）

位置：審查時 `ledger.py` 的 `edge_allowed`、`_transition`、`answer`（原行 294–299、380–387、585–590）。

實際流程：`init → INVESTIGATING → ask Q-001 → update blockers → BLOCKED → WAITING_USER → answer Q-001`。

實際輸出：`EddError 不允許轉移：WAITING_USER → INVESTIGATING`；儲存狀態仍是 `WAITING_USER`，`paused_from` 已變成 `BLOCKED`，而 `waiting.previous_status` 還是 `INVESTIGATING`。因此有效使用者答案無法恢復任務。`answer` 在轉移前追加 `decisions.md`，失敗會留下未與 Task 同步的 DEC，重試再追加同 ID。

建議：禁止暫停狀態互相切換，或保留原始恢復狀態的明確堆疊；先驗證可恢復再追加決策。已回報 Main，Main 表示將新增 RED regression 修正。

### 2. 有效 JSON、錯誤結構未安全降級（阻擋）

位置：`hook_runtime.py` 原行 30–31、83–95；`ledger.py` 的 `evidence_errors` 原行 536–537。

實測把 Hook config 寫成 `[]`，呼叫有效 Stop 事件，輸出為未捕捉的 `AttributeError: 'list' object has no attribute 'get'`。這不是非法 JSON，既有 broken-json 測試不涵蓋。Hook 因而無法保證輸出官方 JSON 診斷。

另將證據檔內容寫成 `null`，`evidence_errors` 拋 `AttributeError: 'NoneType' object has no attribute 'pop'`。應檢查 top-level object 與必要欄位型別，將錯誤轉成結構化診斷，不能只捕捉 JSON parse error。

### 3. 已整合 Agent Report 變化未阻擋完成轉移（阻擋，Main 已回報修正）

位置：審查時 `ledger.py.gate_errors` COMPLETED 分支及 `_transition`。

實測先建立完整驗收，註冊 Agent、交付 `DONE` 並 `integrate`，之後由該 Agent 交付 `FAILED`，Registry 仍是舊 `DONE`。此時 `gate_errors(..., 'COMPLETED')` 回傳 `[]`，`COMPLETED → VERIFYING → COMPLETED` 皆成功。後續 `validate` 才能發現 Registry／Report 不一致。

Main 已通知完成 Gate 現在會重新讀取 Report，並新增缺 Report regression。本項屬已交付修正建議，仍應由 Main 新測試確認。

### 4. 歸檔移動失敗會留下無法再歸檔的 ARCHIVED 任務（阻擋）

位置：`ledger.py.archive`，原行 778–783（審查後版本約行 819 起）。

實際 repro：`init` 後，在 `evidence-driven-dev/archive` 建立普通檔案，再呼叫測試輔助 `helpers.complete(l)`，最後 `l.archive('example')`。普通檔案必須在驗收之前建立，以免版本指紋變更遮蔽問題。

實際輸出：`FileExistsError [Errno 17] File exists: '<temp>/evidence-driven-dev/archive'`。讀回 Task 卻是 `ARCHIVED`，Task 原資料夾仍位於 `tasks/example`。再次 `archive` 輸出 `EddError 只有 COMPLETED 可以歸檔`。

原因是保存 ARCHIVED 狀態早於 `mkdir`／`os.rename` 成功。任何目錄建立或 rename 失敗都有同類風險。建議在 I/O 前檢查 destination，失敗時恢復原狀態，並設計中斷恢復策略。

### 5. Git submodule 程式變更沒有進入指紋（阻擋或明確限制）

位置：`ledger.py.fingerprint`，原行 151–176。

實測隔離 Repo 內建立 `vendor` Git Repo，提交 `vendor/code.py`，父 Repo `git add vendor`、commit 形成 gitlink。取得 `before = l.fingerprint()` 後，把 `vendor/code.py` 從 `v=1` 改成 `v=999`，再取得 `after`。

實際輸出：`submodule fingerprint unchanged: True`；同時 `git status --short` 明確顯示 ` m vendor`。

目前以一般檔案列舉指紋將 gitlink 目錄當成 deleted，不涵蓋子 Repo HEAD 或 dirty 程式。這會使依賴 submodule 的舊測試證據被當成新結果。v1 可以拒絕含 dirty／無法驗證 submodule 的正式完成，並寫明支援限制；也可以納入子 Repo 狀態指紋。

### 6. 一句 reassessment 可繞過三次失敗（Main 已在同步審查期間修正）

最初唯讀版本只檢查 `plan.reassessment` truthiness。Main 在本 Agent 執行驗證前已新增結構化檢查；實測 `update({'plan': {'reassessment': 'done'}})` 已拒絕，輸出「reassessment 需結構化記錄三次實驗、否定假設、Oracle／問題重查與新方向／新假設」。因此本項不列為尚未處理缺陷。後續應確認新假設可繼續、舊假設持續被拒絕。

## 可接受的 v1 限制

- Actor 是合作契約，不是 OS 存取控制；程式已有明確揭露。
- Stop 只針對顯式 `[EDD-COMPLETE:<id>]`，並對重入降級；可避免每次階段回覆被攔截。仍須透過 Skill／AGENTS 規範完成標記。
- 原始測試輸出保留於 Git 忽略路徑；驗收證據保存命令、時間、版本與輸出摘要。應在最終報告揭露原始 Log 跨機器可用性的限制。
- 不自動重啟 Subagent、不自動重跑副作用命令符合安全恢復原則。

## 變更檔案

僅本檔案；沒有修改主 Task、其他 Report 或正式程式。

## Handoff

`DONE_WITH_CONCERNS`。上述 defect 已即時傳給 Main；請以修正後 regression 與實際測試結果決定是否接受，不能把此審查完成當成整體驗收通過。

## 修正後複驗

複驗時間：2026-10-19T15:20:01+00:00。

Main 修正後，本 Agent 重新執行 `python3 -m unittest discover -s evidence-driven-dev/tests -v`，實際結果為 **43 tests／4.268 秒／OK**。其中包含新 `test_guards` 與 Hook wrong-type regression。

另外在新的 tempfile Git Repository 實際重跑原始 repro，沒有只依賴 Main 的完成宣告：

| 原始問題 | 修正後實際結果 |
|---|---|
| WAITING_USER → BLOCKED 覆蓋恢復狀態 | 巢狀暫停立即拒絕；原使用者問題仍可 answer，恢復 INVESTIGATING |
| config `[]` | 回傳含 systemMessage 的診斷物件，無 AttributeError |
| 證據 JSON `null` | evidence_errors 回傳診斷清單，無 AttributeError |
| 已整合 DONE Report 後改為 FAILED | VERIFYING → COMPLETED 因 Registry／Report 不一致拒絕 |
| archive 路徑為普通檔案 | mkdir 失敗後 Task 仍為 COMPLETED，原資料夾保留 |
| 子 Repo code.py 從 v=1 改成 v=999 | fingerprint 已改變，原忽略 submodule dirty source 缺口已關閉 |

另由新 regression 確認：模擬 `os.rename` 失敗會完整恢復原 task.md，之後可正常 archive；失敗 answer 不追加孤兒 Decision；三次失敗後一句 reassessment 被拒絕，結構化重查必須更換 hypothesis；真正 Git Worktree Ledger 互相隔離。

portable 模式的測試顯示：修改 checkout 後正式 validate／resume 仍報 stale，只有 `validate(..., portable=True)` 可驗證歷史紀錄一致性。這符合明確區分「歷史證據完整」與「目前程式已通過測試」的設計，沒有把新 checkout 當成當時測試環境。

### 複驗限制與剩餘阻礙

本次指定審查範圍**沒有剩餘具體阻擋**。前述缺陷紀錄保留作為審查歷史，不代表修正後仍存在。

複驗中曾把 archive 普通檔案刪除後，接著使用同一任務執行 VERIFYING，正確遭到 fingerprint stale 拒絕；這是測試設定變動造成的有效拒絕。Agent Report 與 submodule 原始 repro 已改用獨立環境分別重跑成功，沒有將此設定問題當作程式缺陷。

本報告不代替正式平台 Hook 啟用測試，也不宣稱完成未執行的跨主機、程序被強制終止或大型效能測試。檔案式多文件操作在程序突然終止時仍需 Recovery reconciliation，屬已揭露的 v1 限制。

最終 Handoff 更新為 `DONE`；Main 可以整合本次複驗結果。

## Plugin 修正審查

審查時間：2026-10-19T15:55:48+00:00。審查範圍限定為 `evidence-driven-dev/scripts/capabilities.py` 與 `evidence-driven-dev/tests/test_capabilities.py`。Base 與 HEAD 都是 `014cee1aff3abcfb51bbe5af6db0abd2ef060225`，所以直接讀取未提交檔案，沒有以空的 commit diff 代替審查。

本輪已閱讀 Superpowers 6.4.2 的 `requesting-code-review`、其 `code-reviewer.md` 範本與 `verification-before-completion`，以獨立 Reviewer 身分執行，沒有啟動其他 Agent。

### 優點與需求符合性

- 不再把 cache 存在誤當成安裝：必須有 CLI `installed=true` 且 `enabled=true`。
- 精確核對 marketplace／name／version 與 cache manifest 的 name／version，不靜默退回其他 cached version。
- 只掃 manifest 宣告的 Skill roots，檢查目錄越界與外部 Skill symlink。
- `installed-plugin-manifest` 明確標示資料來源，且 protocol 說明沒有啟動模型回合。
- 現有測試覆蓋主要需求：已安裝可讀、disabled／cache-only、版本不存在、路徑越界與 malformed inventory。

### 實際驗證

| 驗證 | 實際結果 |
|---|---|
| `python3 -m unittest discover -s evidence-driven-dev/tests -p test_capabilities.py -v` | 5 tests，0.009 秒，OK |
| `python3 -m unittest discover -s evidence-driven-dev/tests -v` | 49 tests，4.526 秒，OK |
| `python3 evidence-driven-dev/scripts/capabilities.py --root /home/willy/code/cpea` | exit 0；3 個 Repo Skills、8 個 Superpowers 6.4.2 Skills；missing=[]、plugin_errors=[]、errors=[] |
| 真實 Hook 探測 | sessionStart／subagentStop／stop 三個皆 enabled=true、trustStatus=trusted；此為探測結果，沒有額外觸發 Hook 回合 |
| tempfile：installed／enabled 改為字串 `"true"` | 正確拒絕，未把 truthy 字串當作啟用 |
| tempfile：manifest version 與 inventory 不同 | 正確拒絕並提供診斷 |
| tempfile：SKILL.md symlink 指向 package 外 | 正確拒絕並提供診斷 |

真實 CLI 清單確認 Superpowers 是 `superpowers@openai-curated-remote`、版本 `6.4.2`、installed=true、enabled=true。直接讀取該版本 manifest 確認宣告 `skills: "./skills/"`。因此這輪原始 false-missing 症狀已由實際環境重現檢查，修正後沒有再出現。

### 問題

Critical／Important：無。

Minor：`capabilities.py:60` 使用只接受未加引號的 `name:` regex。tempfile 中將其改為有效 YAML `name: "systematic-debugging"`，其餘 inventory／manifest／檔案完全有效，實際卻回傳 `items=[]`，錯誤為「Plugin Skill name Frontmatter 無效」。這是格式相容性 false-negative；目前 Superpowers 6.4.2 的目標八個 Skills 皆使用未加引號名稱，因此不阻擋這輪原始需求。可補單／雙引號 scalar 的小型支援與 regression，或清楚記錄此 v1 限制。

### 未判定範圍（Declined to judge）

- fresh standalone app-server 的 plugin/read 與 CLI inventory 差異：本需求刻意使用已安裝精確 manifest 補足獨立 app-server，且 provenance 已揭露，不將它判為本修正錯誤。
- 是否每個 Skill 已由當前特定模型回合載入並執行：本工具只提供安裝、啟用與可讀證據，沒有此聲稱；不將 missing=[] 解讀為真正全部執行。
- Plugin 安裝／Hook 信任設定流程：用戶已完成，且本輪未修改設定；僅核對探測讀值。
- 其他 Ledger／Hook Runtime 或產品演算法：不在本輪兩檔審查範圍。

### 結論與新版 Handoff

本輪原始需求可接受；沒有阻擋問題。新增測試與整套 EDD 測試都已由本 Agent 實跑確認。狀態 `DONE_WITH_CONCERNS` 僅反映上述非阻擋 YAML scalar 相容性限制，不能解讀為八個目前已安裝 Skills 仍不可用。

本輪僅追加本 Report；沒有修改受審程式、測試、主 Task 或其他 Agent 紀錄。
