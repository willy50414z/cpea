---
{
  "parent_task": "fix-retail-group-2",
  "agent_id": "independent-review",
  "role": "subagent",
  "status": "DONE_WITH_CONCERNS",
  "base_git_sha": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
  "assignment": "獨立驗證產品修復及安全反例；只寫自己的報告，禁止修改正式程式",
  "allowed_scope": [
    "src/cpea/workflows/text_to_sql"
  ],
  "worktree": "/home/willy/code/cpea",
  "platform_id": "/root/independent_review",
  "handoff": {
    "status": "DONE_WITH_CONCERNS",
    "verification_result": "PASS_WITH_WARNINGS",
    "summary": "C fresh獨立產品驗證PASS_WITH_WARNINGS：477產品＋原26＋新17獨立probes共520 passed/exit0；本地EDD 48pass/1日期時區failure原樣保留，TZ=UTC同原碼重跑49/49 OK；C多反證正反例與B原compare逐字重播均符合預期，fingerprint與六檔hash前後一致，原Oracle/契約/測量未改。",
    "evidence": [
      "agents/independent-review/task.md",
      "agents/independent-review/.local/version-c-verification.json",
      "agents/independent-review/.local/version-c-pytest.log",
      "agents/independent-review/.local/version-c-edd.log",
      "agents/independent-review/.local/version-c-edd-utc.json",
      "agents/independent-review/.local/version-c-edd-utc.log",
      "agents/independent-review/.local/version-c-seals.json",
      "agents/independent-review/.local/version-c-task-only.diff",
      "agents/independent-review/.local/version-c-recorded-comparison-replay.json",
      "agents/independent-review/.local/probes.py",
      "agents/independent-review/.local/multiconflict_probes.py"
    ],
    "risks": [
      "EDD archive collision測試本地date.today與ledger UTC日期不一致，本地原run有1failure；已保存並依UTC契約重跑49/49，未修工具/測試",
      "比較quote/type/結構gate不證明reason語意邏輯，仍依模型判定，僅有界反例保證",
      "本agent無真模型或DB驗證，不能宣稱完整題庫或實際數據正確",
      "C hybrid沿用B前序，不是C完整live E2E；原需求/Oracle粒度歧義須保留"
    ],
    "next_step": "Main整合獨立報告、日期限制與C單節點Replay/hybrid證據，分列量測版本及必要驗收；產品再變更則重跑必要檢查。",
    "diff_reference": "Revision 014cee1aff3abcfb51bbe5af6db0abd2ef060225；Ledger fingerprint 42e793d060d4fbbc8b4e1a7d8ad7661b949ce2563c9030b188852398e18d418c；初始sealed快照到C增量 agents/independent-review/.local/version-c-task-only.diff；本agent僅修改自己task.md與.local。",
    "blockers": [],
    "revision": "014cee1aff3abcfb51bbe5af6db0abd2ef060225",
    "diff_fingerprint": "42e793d060d4fbbc8b4e1a7d8ad7661b949ce2563c9030b188852398e18d418c",
    "verified_at": "2026-10-20T16:07:16.244721+00:00"
  },
  "blockers": [],
  "question": null
}
---

# 版本 C 獨立驗證

**PASS_WITH_WARNINGS。** 477 個產品測試、原有 26 個獨立 probes、新增 17 個多重反證 probes，共 **520 passed**。版本 C 的比較 gate 已接受同一競爭來源的多項不同合法反證，所有新增負例維持澄清；本次產品變更範圍內無未處理 blocking issue。

EDD 原始本地時區 run 為 **48 通過／1 失敗**；保留原始失敗，再以 `TZ=UTC` fresh 重跑得到 **49／49 OK**。這是必須保留的時區限制，不能描述為所有原始檢查均通過。主 Task 驗收與完成仍由 Main 整合判斷。

## 方法與版本

由實作者之外的 agent，依 EDD verify 與已可讀的 Superpowers verification-before-completion 設計並執行 Negative／Boundary／Holdout／Metamorphic 與完整回歸。未修改產品、正式 tests、Oracle、EDD 工具或主 Task；未呼叫真實模型或 DB。

- Revision：`014cee1aff3abcfb51bbe5af6db0abd2ef060225`，版本 C 為此 HEAD 上的既有 dirty worktree 加本次修復。
- 驗證時間：2026-10-20 16:05:24 至 16:07:16 UTC。
- Ledger fingerprint 前後一致：`42e793d060d4fbbc8b4e1a7d8ad7661b949ce2563c9030b188852398e18d418c`。
- 兩產品檔、兩正式測試檔、兩組獨立 probes 共六個內容 SHA-256 前後一致；UTC 重跑指紋亦一致。
- 版本及命令／退出碼／輸出雜湊：[C 驗證紀錄](.local/version-c-verification.json)、[UTC EDD 紀錄](.local/version-c-edd-utc.json)。
- 初始 sealed 快照到 C 的產品增量見 [.local/version-c-task-only.diff](.local/version-c-task-only.diff)。未見 Test ID、完整題文特判、Oracle 修改、停用安全檢查或額外模型架構。

## 實際執行

| Fresh subprocess | 實際結果 | 證據 |
|---|---|---|
| pytest：`tests`＋原 `probes.py`＋新 `multiconflict_probes.py` | 520 passed，81.96 秒，exit 0 | [產品與獨立 probes log](.local/version-c-pytest.log) |
| 本地時區 EDD unittest | 49 tests，1 failure，exit 1 | [原始失敗 log](.local/version-c-edd.log) |
| 同原碼 EDD unittest，子程序環境僅設 `TZ=UTC` | 49 tests，OK，exit 0 | [UTC log](.local/version-c-edd-utc.log) |

## 多重反證變更的獨立核對

新增 [multiconflict_probes.py](.local/multiconflict_probes.py) 共 17 項，獨立使用三個不同統計口徑的合成來源，不使用 retail 題目 ID：

- 四個正例：兩／三個候選，每個競爭來源各有 primary witness 與另一完整片語反證；再反轉候選與反證順序，選擇保持一致。
- 十三個負例：合法 primary witness 混入不存在的契約 quote、未知來源、winner 自我反證、共同 quote、重複 `(view, request_evidence)`、空 reason、偏好 reason、未知 conflict_type、題文外片語、題文內但未映射片語、單一競爭來源缺 primary witness、缺該競爭來源所有證據，以及同一 pair 換 quote／reason。全部保留澄清。
- 以版本 B 原 call `485c5d2693224c17808c92d87dcb0ec1` 的模型 response 與原候選 mapped evidence，逐字重播版本 C gate。原兩項合法反證分別指出訂單識別碼不等於訂單筆數、實績金額不等於月目標；實際選出 `demo_retail.v_store_monthly_kpi`，無 clarification。這是離線單節點重播，沒有模型或 DB 呼叫，見 [原回應重播紀錄](.local/version-c-recorded-comparison-replay.json)。

## F1–F6 的既有反例修後核對


| 發現 | 版本 A／早期修復的實際失敗 | 版本 B 核對 |
|---|---|---|
| F1：統計業務名稱授權跨列計算 | 「列出區域、核准總和／部門合計」允許自增 SUM／GROUP BY，產生錯誤 SQL | 逐欄要求明確 operation evidence，拒絕自增計算；另以未見名稱「例行彙總額」驗證。明確合計／SUM／MAX 仍被辨識。 |
| F2：無關或共同引用被當競爭反證 | 日／月粒度未指定時，以共同城市名稱及無根據 reason 仍可選 monthly | 分開測共同引用與不相干 request phrase，兩者均保留澄清；正常不同措辭的預算／實績正反例及缺漏／捏造反證正式測試通過。 |
| F3：逐列未知欄位 crash | schema 已有錯誤後仍執行 row gate，field_contract 拋未捕捉 ValueError | 逐列與一般分組的未知 selected column、未知 HAVING 欄位均安全拒絕，沒有 SQL 或例外。 |
| F4：字串 literal 誤當聚合 | LIKE 平均%／合計%／總和% 及 IN 同詞值，被誤認為 aggregate threshold | LIKE／IN 的普通與統計字詞 literal 六組均 ready，保留原 typed filter value；真正聚合門檻仍不能放 WHERE。 |
| F5：名稱內「各」授權 GROUP-only | 「列出各類狀態」自增 GROUP BY，錯誤折疊列 | 無明確分組時拒絕；相同欄名明示分組時 ready。正式測試另覆蓋「分組標籤／彙總分類／匯總狀態」。 |
| F6：原 H1 平均業務同義詞仍被硬當 AVG | 實際 retail avg_order_value 契約下，「平均每筆已完成訂單消費額 >= 100」被誤認新增 AVG | 同義普通門檻不再由 guard 硬拒，仍交 semantic 判定；逐字契約名稱亦非新聚合；明確平均值／單列最大值 suffix 與 AVG(...) 仍是聚合，原 disallowed_aggregations 保留。 |

失敗證據未覆寫：[F1](.local/first-probes.json)、[F3](.local/unknown-red.json)、[F4](.local/f4-string-literal.json)、[F5](.local/f5-intrinsic-group-word.json)、[F6](.local/f6-average-paraphrase.json)。版本 A 最後一次獨立 probes 為 7 failed／19 passed，見 [red log](.local/f6-red.log)；相同 26 probes 已包含於版本 B 的 502 passed。


## 封存與反過擬合檢查

初始 seals 共 241 筆，239 筆內容未變，僅 `semantics.py` 與 `sql_generation.py` 兩授權產品檔改變。原題庫 cases、grader、575 calls、90 results 均與原封存 SHA-256 相符，沒有改原 Oracle、契約或原測量。核對結果與本次增量 diff 雜湊見 [.local/version-c-seals.json](.local/version-c-seals.json)。版本 B 的先前驗證報告另保存在 [.local/version-b-report.md](.local/version-b-report.md)。

## 警告與未驗證

1. **EDD 日期測試存在時區假設。** `test_lifecycle.py:27` 以本地 `datetime.date.today()` 建立 archive collision；`ledger.py:851` 以 UTC 日期選 archive 路徑。此 run 台北已為 2026-10-21，UTC 仍為 2026-10-20，測試未建立實際目的地 collision，故沒有得到預期 EddError。原失敗保留，僅依 Main 指示在 UTC 契約環境重跑，沒有修改工具／測試。
2. 比較器的引用真實性、需求片語與 conflict_type 不等於語意 reason 的邏輯證明，最終語意差異仍由模型判斷；已驗證的是列明的有界正反例。
3. 本 agent 未執行模型或 DB，未驗證完整題庫的模型穩定性、SQL 實際資料值、provider 可用性或新模型成本。
4. Main 的 B／C hybrid 使用前一版本的前序回應，不能稱為 C 完整 live E2E。本報告未把 hybrid、B 量測或離線全綠當 C live PASS。
5. 原調查已分類的需求／Oracle 粒度歧義仍須保留，不能以所有題目 ready 原指定 View 當成功標準。

## 交接

獨立結論為 **PASS_WITH_WARNINGS**，產品變更 blocking_issues 為空。Main 應整合本報告、日期測試限制與各版本的 live／hybrid 證據，再決定主任務必要驗收與狀態。產品或測試再次變更時，需依新的 fingerprint 重跑必要檢查。
