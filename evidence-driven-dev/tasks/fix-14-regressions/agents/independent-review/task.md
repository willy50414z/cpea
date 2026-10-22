---
{
  "parent_task": "fix-14-regressions",
  "agent_id": "independent-review",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "依EDD驗證規範獨立審查本次四個局部修正與負面回歸，特別檢查過擬合、操作誤綁、識別碼/證據驗證未被放寬；不改產品",
  "allowed_scope": [
    "src/cpea/workflows/text_to_sql",
    "tests/unit/test_mapping_preflight.py",
    "tests/unit/test_business_clarification.py",
    "docs/hilp_confirmation.md"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/independent_review",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "summary": "獨立審查 PASS_WITH_WARNINGS：4項重要/阻擋finding均由Main修正，最新版22獨立probe+117正式回歸共139 passed，無未處置blocking。",
    "next_step": "Main整合本Report與review-final.json/log，確認完整產品/EDD regression與真實模型焦點穩定性；DB未執行限制需保留。若src/tests再變更需重驗。",
    "evidence": [
      ".local/review-final.json",
      ".local/review-final.log",
      "agents/independent-review/task.md",
      ".local/review-red.json",
      ".local/review-alias-intrinsic-red.json",
      ".local/review-mapped-punctuation-red.json",
      ".local/review-mapped-punctuation-e2e-red.json"
    ],
    "verification_result": "PASS_WITH_WARNINGS",
    "revision": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
    "diff_fingerprint": "3e860a198c01c8d8dc1cf8c16f1e3b4c2a59566da7177b1db153c969fe651ac1",
    "verified_at": "2026-10-20T03:29:48.543958+00:00",
    "blocking_issues": [],
    "warnings": [
      "未呼叫真實LLM或DB；真實模型與完整產品/EDD回歸由Main驗證。",
      "原工作樹有使用者PG dirty變更，審查只限分派實作差異。"
    ],
    "findings_resolved": 4,
    "tests": {
      "passed": 139,
      "independent_probes": 22,
      "regression": 117
    },
    "blockers": []
  },
  "blockers": [],
  "question": null
}
---
# 獨立驗證報告

## 範圍與方法

審查 BASE/HEAD `014cee1aff3abcfb51bbe5af6db0abd2ef060225` 的本次映射、聚合驗證、必要詞彙候選篩選與有界語意修正差異。工作樹原有 PostgreSQL 與其他 dirty 變更不列入本次實作歸因。讀取父 Task、EDD verify 三份政策、實際 diff、正式測試及原始 42 次評估 report。審查由實作者以外 Agent 執行；使用 fresh subprocess、獨立 negative/holdout probe，未呼叫真 LLM 或 DB，未修改產品或正式 tests、Oracle。

實際使用 `.agents/skills/edd-verify/SKILL.md` 與已確認可讀的 Superpowers verification-before-completion；僅按自己執行的命令與讀到的退出碼回報。

## 發現與處置

1. **阻擋，已修正且最終版本重驗通過**：明確聚合的結尾標點白名單漏掉 ASCII 冒號、分號、括號與引號。`顯示訂單金額的單列最大值:` 可把 `count` 草稿送進一般語意整理，mock 模型返回合法 label/evidence 後得到 ready 與 `COUNT([order_amount])`，違反明確最大值。本次獨立 RED 包含完整 workflow 證據；Main 改為沿用完整 `PUNCTUATION`。
2. **重要，已修正且最終版本重驗通過**：approved alias `歷來最大值` 若 mapper text 含查詢 wrapper `列出歷來最大值`，原驗證將名稱自身的最大值誤認為運算，拒絕合法未聚合欄位。Main 加入名稱 wrapper 辨識。
3. **重要，已修正且最終版本重驗通過**：第一版 wrapper 修正直接 `_peel` 後比名稱，會剝除完整 approved alias 自帶的 grammar 字元。`按月合計`、`分組最大值`、`依約合計` 均在未聚合時誤報。需保留完整名稱命中且 wrapper 辨識不得剝除業務名稱。

4. **阻擋，已修正且最終版本重驗通過**：mapper text 自身含尾端標點時，intrinsic regex 對 raw text 使用 `$`，因此 `訂單金額的單列最大值:` 或帶句點的整段 mapper text 無法抓到 max。端到端與只含欄名的 text 比較，後者已正確拒絕，前者仍 ready + COUNT。Main 已收到 `.local/review-mapped-punctuation-e2e-red.json/log` 與 3 條純 assess RED。

## 反過擬合與安全審查

本次新增產品邏輯無 case ID、完整題文、Retail View 名或固定答案特判；操作詞彙為泛用語法，名稱取自既有 catalog。compare 的唯一證據、request/contract 一致性與共享詞彙不可強選條件未修改。label 的識別碼/SQL 拒絕、逐字 evidence、eligible columns、exact required terms 均保留或更嚴；負面測試僅將呼叫數 2 改 3 反映一次有界修正，拒絕狀態不變。本次未修改評估 Oracle。

獨立 partial-resolution probes 包含「不相容必要詞彙已有 proposal，另一必要詞彙漏給 proposal」。補齊第二個詞彙時第一個否定 proposal 保留；錯誤來源不進 matched，比較也不被呼叫；有其他可行來源時選正確來源，否則 unsupported。正式來源歧義、共享詞不得強選、stale/unoffered choice、概念/粒度/單位排除測試均實跑通過。

## 實際命令與證據

- 首次命令誤包含不存在的 `tests/unit/test_hilp_confirmation.py`，exit 4、no tests ran；立即改用實際存在的套件，未將此誤作驗證成功。
- `.venv/bin/python -m pytest -q tests/unit/test_mapping_preflight.py tests/unit/test_business_clarification.py tests/unit/test_semantic_resolution.py tests/unit/test_semantic_confirmation.py tests/unit/test_clarification_workflow.py tests/integration/test_hilp_workflow.py`：88 passed。
- `.venv/bin/python evidence-driven-dev/tasks/fix-14-regressions/.local/review_runner.py red .venv/bin/python -m pytest -q evidence-driven-dev/tasks/fix-14-regressions/.local/review_probes.py`：6 failed、5 passed；before/after 相同，詳 `.local/review-red.json` 與 `.local/review-red.log`。
- 同 runner `green` 加上上述六份正式測試：116 passed，13.75 秒，before/after 相同，詳 `.local/review-green.json` 與 `.local/review-green.log`。
- 同 runner `alias-intrinsic-red ... -k complete_approved_names`：3 failed、11 deselected；before/after 相同，詳 `.local/review-alias-intrinsic-red.json` 與 `.local/review-alias-intrinsic-red.log`。

`.local/review_runner.py` 每次保存 argv、exit code、時間、HEAD、完整 EDD diff fingerprint、六個範圍檔案 SHA256 與輸出 SHA256。`.local/review_probes.py` 是獨立設計的測試；此階段最後一次新增測試沒有修改產品。

## 限制與後續

本報告只驗證離線產品行為；真實模型焦點穩定性、完整產品/EDD regression 與 DB 數值不由本 reviewer 宣稱通過。四項 finding 已由 Main 修正且在本 reviewer 最新 fresh subprocess 重驗通過；最終證據如下。後續產品變更仍需重驗，不得以此證據覆蓋不同版本。

新增獨立 probe 另驗證 column identifier mapper text + alias fallback 無法繞過 workflow，1 passed；雖紀錄名稱為 `review-identifier-fallback-red`，實際 exit 0 與完整內容是 PASS，不列為 finding。最新自建 22 cases 納入完整名稱/查詢前綴、mapper text 尾標點、必要詞彙 partial resolution、操作標點與兩組端到端 guard。

## 最終驗證

結果：**PASS_WITH_WARNINGS**。本次實作範圍無未處置 blocking issue；發現的兩類錯誤聚合放行與兩類合法別名誤拒皆已修正。Main 以完整 approved name 為錨點核對外圍 QUERY_WRAPPER，保留名稱本體；聚合辨識共用完整標點並去除 mapper text 的外圍語法。未放寬語意 label、證據、來源或 View compare。

命令：

```bash
.venv/bin/python evidence-driven-dev/tasks/fix-14-regressions/.local/review_runner.py final .venv/bin/python -m pytest -q evidence-driven-dev/tasks/fix-14-regressions/.local/review_probes.py tests/unit/test_mapping_preflight.py tests/unit/test_business_clarification.py tests/unit/test_semantic_resolution.py tests/unit/test_semantic_confirmation.py tests/unit/test_clarification_workflow.py tests/integration/test_hilp_workflow.py
```

實際輸出 **139 passed in 13.74s**（22 條獨立 probe、117 條正式回歸），exit 0。runner subprocess 總耗時 15.12 秒，開始/結束版本與範圍檔案雜湊完全相同。最終報告寫入前再次核對當前全工作樹 fingerprint 與驗證結束值相同。

驗證時間：`2026-10-20T03:29:48.543958+00:00`；HEAD：`014cee1aff3abcfb51bbe5af6db0abd2ef060225`；diff fingerprint：`3e860a198c01c8d8dc1cf8c16f1e3b4c2a59566da7177b1db153c969fe651ac1`。

輸出 SHA256：`54677ff82cb1e66036d9d92d82d13a13dde903eeba435a033cb51000c6f7809c`；機器紀錄 `.local/review-final.json`，完整輸出 `.local/review-final.log`。

| 範圍檔案 | SHA256 |
|---|---|
| `src/cpea/workflows/text_to_sql/semantics.py` | `3f309970c4289815ecd128a098b4f63ae5b0c8213bfdd012a1f2a78d5a1d4d73` |
| `src/cpea/workflows/text_to_sql/clarification.py` | `3213a319f304a58838bca76af5d69ae20967e9b96d4639329512c8efcc626abf` |
| `src/cpea/workflows/text_to_sql/sql_generation.py` | `df95d35f514fc944b6008bdc960882fe8b543101d06f270ce71423ccfe33f407` |
| `tests/unit/test_mapping_preflight.py` | `230aeee347fa29fc74fb88619bc0d4545d29194b32927e00f20b3d96bc52be72` |
| `tests/unit/test_business_clarification.py` | `31499ef219e9472be1753b75bbdd5166e833c049f44664d29be44f9de7084f04` |
| `docs/hilp_confirmation.md` | `dd1cc89e76a2a67c19316ab0e6806eabba4a91816dd59d41cb2e0af839f84716` |

警告與未驗證：本 reviewer 未執行真實模型穩定性或 DB；完整產品與 EDD 全套由 Main 負責。不得把本次離線 PASS 擴張為 A3 或 DB 數值已驗證。原工作樹含既有 PG dirty 變更，審查僅覆蓋明確分派差異。
