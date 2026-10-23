# 最終獨立審查

結論：**PASS_WITH_WARNINGS**。未發現本需求範圍內可重現且需阻擋交付的 Critical／Important 問題。

- 審查者：fresh agent `mapping_final_review`，與實作者及前次 reviewer 不同；只讀產品與測試，未派子代理。
- 方法：閱讀已核准設計、計畫、Task／DEC／EXP、實際新增程式與測試；fresh subprocess 執行 focused、前次 holdout 及自行補充邊界檢查。
- 驗證時間：2026-10-23T06:51:47.212535+00:00
- Git revision：`095b6125623af5b9ade6914a6a83444e3d704b57`（未提交的新檔另以下方指紋識別）。
- 產品及新測試內容指紋：`bd7c4dafb78997d2453213b76292da6b3129d5f87a332504c47f78f34b983c57`，由排序的相對路徑→SHA-256 JSON 再取 SHA-256。
- Blocking issues：無。本紀錄不代替 Main 的完整套件／EDD transition。

## 已執行驗證

```bash
.venv/bin/python -m pytest -q tests/unit/test_schema_mapping_validation.py tests/unit/test_schema_mapping_review.py tests/unit/test_schema_mapping_decomposition.py tests/unit/test_schema_mapping_retrieval.py tests/unit/test_task_decomposition_workflow.py tests/unit/test_task_decomposition_contract.py tests/unit/test_decomposition_evaluation.py tests/integration/test_decomposition_runner.py
```

結果：**173 passed in 10.88s**，exit 0。包含原四組 66 項回歸與新增 107 項。

```bash
.venv/bin/python /tmp/cpea_mapping_review_holdouts.py
```

結果：exit 0，`accepted_invalid_drafts=0`。局部 conditional 期間不能掩護全期間指標、額外未限時 task、最終輸出移除必要 store grain 三反例皆拒絕。

```bash
.venv/bin/python /tmp/cpea_mapping_final_boundaries.py
```

結果：exit 0，`boundary_checks=5; protected_baseline_matches=3`。自行檢查精確相鄰浮點分數不視為 ties、重複 View 取最佳分數、限定欄位與 IN literal 混合釘選、conditional metric 缺上界拒絕，以及 prohibited metric 同樣涵蓋 conditional metric。`prompt.py`、`prompt.md` 與全部 tracked diff 和 protected baseline 雜湊一致。

## 審查接點

- `mapping_retrieval.py:13`：重用既有排名、soft cutoff/ties、明列來源補回、未知 View／非有限分數拒絕；`mapping_retrieval.py:40` 排除比較及 IN literal 的來源釘選。
- `schema_mapping_workflow.py:90`：先檢索再抽取；失敗／空候選不呼叫 LLM，正常候選 C+3 次；完整原文傳至後續所有階段。
- `mapping.py:121`：全域審核僅採納已存在候選，必要需求與約束閉合；`mapping.py:224` 檢查條件作用範圍，`mapping.py:253` 對照草稿 allowlist／binding／最終粒度／母體。
- `schema_mapping_workflow.py:43`：每階段 context 預算與 token counter／provider／解析錯誤早停，原始 provider 錯誤只留呼叫者控制 observer。
- workflow `README.md` 已更新候選 C+3、retrieval trace 與召回限制；原流程與舊測試未改。

## 警告與未驗證

- 未連線真實 LLM、embedding、reranker 或 DB；語意抽取、引文是否真正支持需求、模型成本及檢索品質未驗證。
- 稀疏候選 A 不保留全拒絕矩陣；檢索排除來源未逐詞比對，隱含來源可能漏召回，ties／同名欄位補回也可能超過 soft limit。這些限制已在核准設計與 README 揭露。
- 本 reviewer 未跑全套，Main 負責新版本完整套件；已知原基準為 23 failed／666 passed／1 skipped，不把舊失敗當作已修復。

## 內容雜湊

```json
{
  "src/cpea/application/models/schema_mapping_decomposition.py": "2e3116564d1531130aba01cc8322470bb2cfcc5a2b8eb9dab5f91b20a367d5c5",
  "src/cpea/application/services/schema_mapping_decomposition.py": "a1640030438ad65bd834f4a2bde8c18affb79b9e80199062fbc59c239a8201ed",
  "src/cpea/workflows/task_decomposition/mapping.py": "2b4e24cf8ab0d2eda26d9cb8ab679737085a7bbf950970c3ca3387da087cd700",
  "src/cpea/workflows/task_decomposition/mapping_models.py": "5cabdc668f3ec22ca293800021a860b595e1bd61be3c0e9fc4c252fd65143acd",
  "src/cpea/workflows/task_decomposition/mapping_prompts.py": "48101eafd77508a6796446fffa326c30086cf78f2127909cd451e21a84fbf34f",
  "src/cpea/workflows/task_decomposition/mapping_retrieval.py": "a230dbd9e6a243b08338531b3d00d10201527b0f12278778095dd76331b81dce",
  "src/cpea/workflows/task_decomposition/schema_mapping_workflow.py": "6c4432f4173e5d1292ade30ebca9bc32927cc5a71e09f0d742441c2361d25f42",
  "tests/schema_mapping_support.py": "abe84a229e8cd5c5b2c721659425af236bb2e1c366d55a6ed0b8dc070912a734",
  "tests/unit/test_schema_mapping_decomposition.py": "e37768947bbbec93c54ab6c08435debeef0eaefd0b9ae997c7e72cc8d4e8084c",
  "tests/unit/test_schema_mapping_retrieval.py": "7746c597c9ad3b18394958ad618cca4d57006d204334d820102af3b75b570237",
  "tests/unit/test_schema_mapping_review.py": "8e2e93d4040767ae323af28da7fbd3289d6d44d0b6ae1f9d5ad6076913c334fe",
  "tests/unit/test_schema_mapping_validation.py": "bd056b0b0f1078bb2e3ff3e9f1ebf7e5cdd39aff8c4662e917e86234c882fd2c"
}
```
