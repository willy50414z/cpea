# WrenAI 原生離線 Worker

此目錄載入完整官方 WrenAI `ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc`（AI service 0.29.3），實際執行 `DBSchema`、`TableDescription`、`IntentClassification`、`DbSchemaRetrieval`。唯一新增語意節點為 `BasicPipeline`／Hamilton／Haystack 的 `DraftPlanning`；Draft JSON schema 由 CPEA 父端傳入，沒有複製其模型。

目前交付與驗證範圍為**離線 fake transport／錄製回應 replay**。沒有呼叫真模型、連業務 DB、產生 SQL 或證明語意品質。`NativeWrenAIPlanner` 要求顯式注入 completion／embedding transport；CLI 僅提供錄製 replay，並封鎖非 loopback 網路。後續真模型資源、價格與正式題庫仍須另外提供。

## 可重現環境

需要 Linux x86_64、Git、Python 3.12、uv，以及既有 CPEA `.venv`（測試用它讀真正 retail catalog／Draft schema）。已驗證 uv 0.11.21、Python 3.12.3、Poetry 2.1.4、Qdrant 1.15.4。執行：

```bash
python3 integrations/wrenai/bootstrap.py
env -u PYTHONPATH LANGFUSE_ENABLED=false HAYSTACK_TELEMETRY_ENABLED=false \
  integrations/wrenai/.runtime/env/bin/python integrations/wrenai/environment_probe.py
umask 077
integrations/wrenai/.runtime/env/bin/python -m pytest -q \
  -c integrations/wrenai/pytest.ini integrations/wrenai/tests
```

Bootstrap 保留完整 upstream checkout，使用原 lock `--only main --no-root`，前後檢查 SHA-256 `092fed1a63f08594e1f9eff3c8c6564d50f31d9be760dc2914c31ffe026a5e25`。工具與 runtime 分別位於 `.runtime/tools`、`.runtime/env`，不更動 CPEA `.venv`。上游 lock 的原始副本為 `upstream.poetry.lock`；授權原文為 `UPSTREAM-LICENSE`（AGPL-3.0）。上游來源、lock、必要 import 於每次握手／規劃重新核對；來源修改、切換 commit 或額外 upstream 檔案都拒絕執行。

測試直接透過父端 adapter 讀 `projects/retail` 的七個 View／102 欄，不依賴未追蹤 schema fixture。Qdrant binary 從固定版本官方 release 下載並核對 SHA-256；測試、worker 與 replay 各自建立私有 localhost instance，結束時 terminate／kill／reap，工作目錄與儲存均在 `.runtime`。不依賴或操作共享 Qdrant。

## 啟動與重播

完整 graph 測試會保存 `.runtime/test-recording-*/runs/*/`。選擇含 `response.json` 的成功 run，以下 `RUN_DIR` 為該絕對路徑：

```bash
integrations/wrenai/.runtime/env/bin/python integrations/wrenai/worker.py --recording "$RUN_DIR"
```

Worker stdout 僅有 JSONL 協定，upstream logging 走 stderr。父端傳 `protocol_version=1` 的 `plan`；事件依序為 `accepted`、`running`、唯一終態 `result/error/cancelled/unknown_outcome`，包含 request/run/case IDs。同時僅接受一 run；取消排空 transport 後才終結。單一 payload 上限 2 MiB、line 上限 4 MiB；父端負責 timeout grace、terminate／kill／reap 與雙 pipe drain。

直接重新執行真 graph：

```bash
cd integrations/wrenai/.runtime/upstream/wren-ai-service
PYTHONPATH=/absolute/repo/integrations/wrenai \
  /absolute/repo/integrations/wrenai/.runtime/env/bin/python \
  -m native_worker.replay "$RUN_DIR"
```

Replay 核對來源、lock、patch、Python、model、tokenizer、完整 configuration、原始輸入、schema、索引 snapshot 與逐 transport request fingerprint。冷索引重做原生 indexing；熱索引先從包含 embeddings 的私有 snapshot 回復，再執行原生 intent／retrieval／Draft。`--allow-drift` 會明標允許漂移，仍不改寫 request fingerprint。

## 隔離、觀測與限制

六種原生 dataset 全部經 namespace provider 映名，`recreate_index` 固定 false；project ID 不為空。generation 使用程序檔鎖與 atomic `building→ready/failed` manifest，兩種索引的 count／content digest 全部一致才可讀；損毀或半成品重建本流程索引。

窄政策 seam 保留原生 provider，僅解開 pinned backoff、固定 LiteLLM／SDK retries=0、禁止 fallback／streaming、單一 transport 串行、穩定文件 ID。原始 completion／每個 embedding batch 在 finish check／JSON extraction 前落盤；失敗停止後續 batch，取消留下結果不明狀態。raw 選欄在 renderer 前拒絕 unknown／empty／duplicate；三個 LLM 節點以實際 system/user/response schema 加 output reserve／safety 檢查預算，禁止截斷輸入。

所有 raw request／response、解析結果／錯誤、usage、貨幣未知狀態與 replay artifact 都在 Git 忽略的 `.runtime`，目錄 0700、檔案 0600；不含 credentials／auth headers。`ledger.json` 對帳每個 sent attempt；沒有可靠價格時 money amount 為 null、cost_complete=false，不以零冒充免費。runtime token counter 是明示的保守 tiktoken 估算，provider usage 另列；未驗證其他模型 tokenizer 的實際誤差。

完整測試包含真 Qdrant namespace／不同 dimension／共享 sentinel、雙索引失敗與鎖、raw selection／budget／single attempt、取消／唯一終態、冷／熱 replay，以及真 worker→父端 validate／prepare 的 ready 結果。只有 fake transport 成功不構成真模型正確性、recall 或成本保證。
