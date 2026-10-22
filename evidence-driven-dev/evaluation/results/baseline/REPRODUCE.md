# 基準對照實驗重現

此暫存 Repo 與正式專案隔離，未使用 EDD Skills 或 EDD Ledger 管理三個案例。

## 修正後驗證

```bash
python3 -m unittest -v tests holdout_tests
```

## 原始失敗測試

`baseline/cases.py` 是 Base SHA 的原始檔案。以下命令將它放在 import 路徑最前方，完全不覆寫修正後檔案。

```bash
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('tests.py',run_name='__main__')" BoundsTests
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('tests.py',run_name='__main__')" RetrievalTests
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('tests.py',run_name='__main__')" RoutingTests
```

## 單節點 Replay 與最小實驗

```bash
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('replay.py',run_name='__main__')"
```

## 三次失敗重現

三個命令都應以 exit 1 失敗；這些是預期的反證，並非修正後測試。

```bash
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('threshold_trials.py',run_name='__main__')" 0.3
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('threshold_trials.py',run_name='__main__')" 0.6
python3 -c "import sys,runpy; sys.path.insert(0,'baseline'); runpy.run_path('threshold_trials.py',run_name='__main__')" 0.9
```

修改可用 `git diff -- cases.py` 或 `changes.diff` 檢視。`measurement.json` 記錄時間與未量測的 Token。測試輸出保留在 `red-*.txt`、`green-*.txt`、`threshold-*-failure.txt`、`replay-output.txt`、`all-tests-output.txt`。
