
# Hybrid AI Inference & Evaluation Platform
## 技術學習與實作計畫

- 計畫週期：12 週
- 建議投入：每週 6～10 小時
- 專案定位：AI Platform / Infrastructure Engineering
- 職涯目標：Senior / Staff Software Engineer、Senior AI Platform Engineer
- 長期薪資目標：3～5 年內挑戰年薪 NT$200～300 萬
- 核心原則：學習可跨模型、跨平台重用的系統工程能力

---

# 一、專案總目標

## 1.1 核心目標

建立一套可同時評估地端與雲端 LLM 的推論平台，具備：

1. 統一模型呼叫與管理
2. 本地 GPU 推論效能分析
3. 多模型品質評估
4. 模型自動路由與 Fallback
5. 推論成本及資源監控
6. 系統可靠性與安全控制
7. 地端、雲端及混合架構比較
8. 自動化測試與部署
9. 可重現的實驗及架構決策報告

最終必須能回答：

> 針對特定 AI 工作負載，應該選擇哪個模型、哪種部署方式，才能在符合品質、安全和延遲要求的前提下，取得合理的總成本？

## 1.2 學習成果

完成後應具備：

- [ ] 理解 LLM 推論的主要效能瓶頸。
- [ ] 能部署及管理本地 LLM 推論服務。
- [ ] 能分析 GPU VRAM、KV Cache、Context 與併發關係。
- [ ] 能建立可重複執行的 LLM Evaluation。
- [ ] 能比較不同模型的品質、延遲及成本。
- [ ] 能實作地端與雲端模型路由策略。
- [ ] 能處理模型失敗、超時與資源不足。
- [ ] 能監控 AI 系統的品質、效能與資源。
- [ ] 能評估企業地端與雲端 AI 的 TCO。
- [ ] 能提出有數據支持的 AI 系統架構決策。

## 1.3 不列入本階段的項目

- [ ] 不自行訓練大型語言模型。
- [ ] 不自行開發通用 Agent Framework。
- [ ] 不重新開發完整的 LLM Gateway。
- [ ] 不自行實作 GPU Kernel。
- [ ] 不追求大型 GPU 叢集。
- [ ] 不以建立商業 SaaS 作為驗收條件。
- [ ] 不為了測試而優先升級硬體。

優先使用成熟工具，將開發時間投入評估、可靠性、架構及效能分析。

---

# 二、現有資源

## 2.1 硬體

| 項目 | 現有配置 |
|---|---|
| CPU | AMD Ryzen 7 5700X |
| GPU | AMD RX 7800 XT 16GB |
| RAM | DDR4 48GB |
| OS | Ubuntu 24.04 |
| 容器平台 | Docker |
| LLM Runtime | Ollama ROCm |

## 2.2 可利用的現有專案

| 專案 | 用途 |
|---|---|
| Text-to-SQL | 結構化推理、SQL 正確性驗證 |
| RAG / ERP Assistant | 資料檢索、Groundedness 評估 |
| Video Summarizer | 長內容、多模態分析、資訊擷取 |

以上專案作為 Evaluation Workload，不要求重新開發完整產品。

## 2.3 建議研究工具

| 領域 | 工具 |
|---|---|
| Model Serving | Ollama |
| 進階推論 | vLLM / llama.cpp，視 GPU 支援而定 |
| Model Gateway | LiteLLM |
| Evaluation | MLflow / 自訂確定性測試 |
| Observability | OpenTelemetry |
| Metrics | Prometheus |
| Dashboard | Grafana |
| 資料儲存 | PostgreSQL |
| 容器與部署 | Docker / Docker Compose |
| 雲端模型 | 選擇一至兩家模型 API 供應商 |

工具只是候選實作方案，學習重點是底層原理及可驗證的工程成果。

---

# 三、12 週學習計畫

# Phase 1：LLM Serving & Performance Engineering

**期間：Week 1～4**

**階段目標：**

理解 LLM 在本地 GPU 上的推論行為，建立可靠的效能測試基準。

## Week 1：建立測試基礎與統一推論介面

### 學習內容

- LLM Inference 基本架構
- OpenAI-compatible API
- Prompt Tokens / Output Tokens
- Context Window
- Model Parameters
- Quantization
- 模型版本管理

### 必須完成事項

- [ ] 盤點目前 Ollama 模型與推論環境。
- [ ] 選定本地 8B 與 31B 量化模型作為主要測試對象。
- [ ] 確認不同模型的載入與記憶體限制。
- [ ] 建立統一模型呼叫介面。
- [ ] 統一模型輸入與輸出格式。
- [ ] 記錄模型版本與推論參數。
- [ ] 建立第一批固定測試資料。
- [ ] 建立實驗紀錄格式。

### 必要驗證

- [ ] 不同模型能透過相同介面執行任務。
- [ ] 每筆結果可追溯模型、版本及參數。
- [ ] 模型載入失敗或超時可正確回報。
- [ ] 測試流程可重複執行。

### 交付成果

- 統一模型測試介面
- 模型及環境清單
- Baseline Test Dataset

---

## Week 2：LLM 推論效能與記憶體管理

### 學習內容

- Prefill / Decode
- TTFT / TPOT
- Tokens per Second
- GPU VRAM
- KV Cache
- Context Length
- Model Quantization
- CPU / GPU Offloading

### 必須完成事項

- [ ] 理解模型權重與 KV Cache 的記憶體需求。
- [ ] 比較不同 num_ctx 的資源消耗。
- [ ] 比較不同量化模型的記憶體使用。
- [ ] 量測 TTFT、TPOT、Tokens/sec。
- [ ] 分析 GPU 與 CPU 混合推論的效能。
- [ ] 記錄模型載入及卸載時間。
- [ ] 分析不同 Prompt 長度的推論效能。

### 必要驗證

- [ ] 能解釋 VRAM 不足的主要原因。
- [ ] 能判斷效能瓶頸位於載入、Prefill 或 Decode。
- [ ] 能比較不同 Context 設定的效能。
- [ ] 能提出適合 16GB VRAM 的模型配置建議。

### 交付成果

- LLM Performance Benchmark
- VRAM / Context 分析報告
- 推論參數最佳化建議

---

## Week 3：併發與推論服務效能

### 學習內容

- Concurrent Requests
- Request Queue
- Continuous Batching
- Throughput
- P50 / P95 / P99 Latency
- Rate Limiting
- Backpressure
- Capacity Planning

### 必須完成事項

- [ ] 建立單使用者測試。
- [ ] 建立多使用者併發測試。
- [ ] 量測排隊時間。
- [ ] 量測不同併發數的吞吐量。
- [ ] 測試長短 Prompt 混合負載。
- [ ] 測試資源耗盡時的系統行為。
- [ ] 比較不同推論參數下的服務品質。

### 必要驗證

- [ ] 能指出系統效能明顯下降的負載區間。
- [ ] 能提供併發數與 P95 延遲的關係。
- [ ] 系統在過載時能安全回報失敗。
- [ ] 能提出單機 GPU 的容量規劃建議。

### 交付成果

- Concurrency Benchmark
- Capacity Planning Report
- 推論服務效能瓶頸分析

---

## Week 4：地端與雲端推論比較

### 學習內容

- Cloud LLM API
- Local vs Cloud Inference
- API Latency
- Token Pricing
- Model Capability Differences
- Hybrid AI Architecture

### 必須完成事項

- [ ] 串接至少一個雲端 LLM API。
- [ ] 建立地端與雲端相同的測試介面。
- [ ] 固定相同測試資料與輸出要求。
- [ ] 比較回答時間。
- [ ] 比較輸出品質。
- [ ] 比較模型失敗情況。
- [ ] 初步估算推論成本。
- [ ] 記錄不同模型的能力限制。

### 必要驗證

- [ ] 地端與雲端模型能使用相同測試集。
- [ ] 可以公平比較品質及延遲。
- [ ] 雲端 API 用量及費用可追蹤。
- [ ] 敏感資料不會未經授權送至雲端。

### Phase 1 驗收

- [ ] 完成至少兩種本地模型配置比較。
- [ ] 完成至少一種雲端模型比較。
- [ ] 具備 TTFT、TPOT、P95、吞吐量數據。
- [ ] 能說明主要硬體限制。
- [ ] 能提出初步地端／雲端選型建議。

---

# Phase 2：AI Evaluation & Model Routing

**期間：Week 5～8**

**階段目標：**

讓模型選擇依據可驗證的品質、成本、安全及延遲數據，而不是模型大小或主觀印象。

## Week 5：Evaluation Dataset 與品質指標

### 學習內容

- Golden Dataset
- Ground Truth
- Exact Match
- Semantic Evaluation
- Execution Accuracy
- Groundedness
- Precision / Recall
- Evaluation Bias

### 必須完成事項

- [ ] 建立固定版本的測試資料集。
- [ ] Text-to-SQL 至少 25 題。
- [ ] RAG 至少 20 題。
- [ ] 影片資訊擷取至少 15 題。
- [ ] 建立每個工作負載的評估標準。
- [ ] 建立標準答案或人工驗證依據。
- [ ] 區分客觀計算與主觀品質評分。
- [ ] 保留尚未用於調整模型的測試題目。

### 必要驗證

- [ ] 至少 60 個有效測試案例。
- [ ] 每個案例具備明確驗收方式。
- [ ] 評估結果可重複執行。
- [ ] 能區分模型錯誤與資料／工具錯誤。

### 交付成果

- Evaluation Dataset v1
- Evaluation Metrics Definition
- Golden Answer / Review Records

---

## Week 6：自動化模型評估與回歸測試

### 學習內容

- Evaluation Pipeline
- Deterministic Evaluation
- LLM-as-a-Judge
- Regression Testing
- Model Comparison
- Traceability

### 必須完成事項

- [ ] 自動化執行完整 Evaluation Dataset。
- [ ] 建立不同模型的結果比較。
- [ ] 建立 SQL 執行結果驗證。
- [ ] 建立 RAG 答案來源驗證。
- [ ] 建立資訊擷取完整性驗證。
- [ ] 對主觀內容建立人工覆核機制。
- [ ] 比較模型或 Prompt 更新前後的品質。
- [ ] 記錄失敗案例與原因。

### 必要驗證

- [ ] 不需要逐題人工執行測試。
- [ ] 每次評估都有完整實驗紀錄。
- [ ] 可以追溯模型版本與測試資料版本。
- [ ] 模型更新造成品質退步時能被辨識。
- [ ] 核心數值測試不只依賴 LLM Judge。

### 交付成果

- Automated Evaluation Pipeline
- Model Quality Comparison
- Regression Test Report

---

## Week 7：Model Gateway 與路由策略

### 學習內容

- Model Gateway
- Model Routing
- Rule-based Routing
- Quality-based Routing
- Latency-aware Routing
- Budget Control
- Fallback Strategy

### 必須完成事項

- [ ] 建立統一 Gateway。
- [ ] 能依工作負載選擇不同模型。
- [ ] 建立簡單的模型路由規則。
- [ ] 加入模型不可用時的處理策略。
- [ ] 加入模型呼叫次數及資源限制。
- [ ] 記錄每次路由決策。
- [ ] 比較固定模型與混合模型策略。
- [ ] 確認路由策略不違反資料政策。

### 必要驗證

- [ ] 不同工作負載可選擇指定模型。
- [ ] 模型不可用時不會無限制重試。
- [ ] 禁止外傳的資料不會被 Fallback 至雲端。
- [ ] 路由結果可以重現與解釋。
- [ ] 可以比較路由前後品質、延遲及成本。

### 交付成果

- Hybrid Model Router
- Routing Decision Log
- Routing Strategy Comparison

---

## Week 8：可靠性與安全治理

### 學習內容

- Circuit Breaker
- Retry / Timeout
- Graceful Degradation
- IAM / RBAC
- Data Classification
- PII Protection
- API Security
- Secrets Management
- Failure Recovery

### 必須完成事項

- [ ] 建立模型超時處理。
- [ ] 建立模型不可用時的安全失敗機制。
- [ ] 建立 API 權限控制。
- [ ] 限制不同使用者的模型使用權限。
- [ ] 設定敏感資料的推論政策。
- [ ] 防止機密資料寫入不受控的 Log。
- [ ] 建立故障事件紀錄。
- [ ] 測試模型輸出不符合格式的情況。
- [ ] 測試資料政策與路由政策衝突的情況。

### 必要驗證

- [ ] 模型服務失效時系統不會無限制重試。
- [ ] 未授權使用者無法呼叫受限制的服務。
- [ ] 敏感資料不可透過 Fallback 洩漏。
- [ ] 錯誤與故障可以追溯。
- [ ] 所有設定的高風險安全案例通過。

### Phase 2 驗收

- [ ] 可自動化評估至少三種模型配置。
- [ ] 可比較品質、延遲與成本。
- [ ] 完成模型路由策略。
- [ ] 完成安全 Fallback。
- [ ] 建立可執行的 Regression Test。
- [ ] 能用測試數據說明混合架構的優缺點。

---

# Phase 3：Observability、Cost & Production Architecture

**期間：Week 9～12**

**階段目標：**

將實驗平台提升為具備企業級工程設計與架構評估能力的作品。

## Week 9：Observability

### 學習內容

- OpenTelemetry
- Metrics / Logs / Traces
- Prometheus
- Grafana
- SLI / SLO
- Alerting
- Model Quality Monitoring

### 必須完成事項

- [ ] 建立推論服務 Metrics。
- [ ] 監控請求量、延遲、錯誤率。
- [ ] 監控 Token Usage。
- [ ] 監控 GPU、CPU、RAM、VRAM。
- [ ] 建立跨 Gateway 與模型服務的 Trace。
- [ ] 建立服務健康 Dashboard。
- [ ] 加入基本告警。
- [ ] 顯示模型評估結果與版本資訊。

### 必要驗證

- [ ] 能定位主要延遲來源。
- [ ] 能追蹤模型呼叫失敗原因。
- [ ] 能觀察 GPU 資源瓶頸。
- [ ] 模型不可用時能產生告警。
- [ ] Dashboard 可以支援實際效能分析。

### 交付成果

- AI Platform Monitoring Dashboard
- Trace / Metrics Report
- Reliability Dashboard

---

## Week 10：成本最佳化與 TCO

### 學習內容

- Inference Cost Modeling
- Cost per Successful Task
- GPU TCO
- Cloud Token Pricing
- Capacity Utilization
- Cost / Quality Trade-off
- Break-even Analysis

### 必須完成事項

- [ ] 建立地端硬體成本估算。
- [ ] 計入電力、攤提及維運成本。
- [ ] 建立雲端模型費用統計。
- [ ] 比較不同模型的單次成功任務成本。
- [ ] 分析不同流量下的成本變化。
- [ ] 建立本地與雲端成本交叉點分析。
- [ ] 評估不同模型路由策略的經濟性。
- [ ] 提出成本最佳化建議。

### 必要驗證

- [ ] 可以估算每千次成功任務的成本。
- [ ] 地端成本不會被錯誤視為零。
- [ ] 成本分析包含模型失敗及重試。
- [ ] 可以提供不同負載情境的 TCO。
- [ ] 能說明在什麼條件下雲端或地端較划算。

### 交付成果

- AI Inference Cost Model
- Cloud vs On-prem TCO Report
- Model Selection Recommendation

---

## Week 11：Production-oriented Architecture

### 學習內容

- Container Deployment
- CI/CD
- Configuration Management
- Infrastructure as Code 基礎
- Rollback
- Resource Isolation
- High Availability 基礎
- Kubernetes 架構概念
- Cloud IAM / Network 基礎

### 必須完成事項

- [ ] 建立可重現的部署方式。
- [ ] 建立模型與平台設定版本管理。
- [ ] 建立自動化測試流程。
- [ ] 新版本部署前執行 Regression Test。
- [ ] 建立回復上一版本的流程。
- [ ] 建立模型不可用時的服務降級策略。
- [ ] 完成基本安全設定檢查。
- [ ] 說明單機架構擴充至多節點時的限制。

### 必要驗證

- [ ] 平台可以從文件重新部署。
- [ ] 設定錯誤時能安全停止。
- [ ] 模型更新失敗時可以回復。
- [ ] 部署後可以自動執行健康檢查。
- [ ] 完成正式環境架構風險清單。

### 交付成果

- Deployment Guide
- Architecture Diagram
- CI/CD & Regression Process
- Production Readiness Checklist

---

## Week 12：完整驗收與作品集整理

### 必須完成事項

- [ ] 重跑完整 Evaluation Dataset。
- [ ] 重跑效能與併發測試。
- [ ] 比較地端、雲端及混合模型策略。
- [ ] 完成品質與成本比較。
- [ ] 完成安全及可靠性驗證。
- [ ] 完成系統架構圖。
- [ ] 完成技術決策紀錄。
- [ ] 完成已知限制與改善計畫。
- [ ] 製作可展示的 Dashboard。
- [ ] 撰寫專案 README。
- [ ] 整理履歷可使用的技術成果。

### 最終必要驗證

- [ ] 至少 60 題可重複執行的 Evaluation。
- [ ] 至少三種模型配置可比較。
- [ ] 有完整品質、延遲、吞吐量及成本數據。
- [ ] 有地端／雲端／混合策略比較。
- [ ] 有模型 Fallback 和安全測試。
- [ ] 有 Metrics、Logs、Traces。
- [ ] 有可重現的部署流程。
- [ ] 有 TCO 與容量規劃報告。
- [ ] 所有架構結論都有實驗依據。

---

# 四、核心能力驗收清單

## 4.1 LLM Serving

- [ ] 理解 Prefill / Decode。
- [ ] 理解 KV Cache 與 VRAM。
- [ ] 理解 Context 對效能的影響。
- [ ] 能進行推論 Benchmark。
- [ ] 能進行併發與容量分析。
- [ ] 能提出推論參數最佳化建議。

## 4.2 AI Evaluation

- [ ] 能建立 Golden Dataset。
- [ ] 能定義不同任務的品質指標。
- [ ] 能自動化執行評估。
- [ ] 能建立模型回歸測試。
- [ ] 能進行人工與自動化混合驗證。
- [ ] 能分析模型錯誤類型。

## 4.3 Hybrid AI Architecture

- [ ] 能統一地端與雲端模型呼叫。
- [ ] 能建立模型路由規則。
- [ ] 能根據安全政策限制模型使用。
- [ ] 能處理模型不可用與超時。
- [ ] 能比較混合部署的實際效益。

## 4.4 Reliability & Observability

- [ ] 能追蹤完整推論流程。
- [ ] 能監測延遲、錯誤與資源使用。
- [ ] 能建立告警。
- [ ] 能處理服務降級。
- [ ] 能執行版本回歸測試。
- [ ] 能分析故障原因。

## 4.5 Cost & Capacity

- [ ] 能估算本地 GPU TCO。
- [ ] 能估算雲端 API 成本。
- [ ] 能比較每次成功任務成本。
- [ ] 能提出模型與硬體選型建議。
- [ ] 能根據負載量評估容量需求。

---

# 五、學習優先順序

## P0：必須掌握

1. LLM Serving 基本原理
2. TTFT / TPOT / Throughput / Latency
3. GPU VRAM / KV Cache / Context
4. Evaluation Dataset
5. Regression Testing
6. Model Gateway
7. Model Routing
8. AI Reliability
9. Cost per Successful Task

## P1：建議深化

1. OpenTelemetry
2. Prometheus / Grafana
3. Kubernetes
4. Cloud IAM / Networking
5. Hybrid AI Architecture
6. AI Security / Governance
7. Advanced Model Serving
8. Capacity Planning

## P2：未來視職涯方向決定

1. CUDA / HIP
2. Triton
3. GPU Kernel Optimization
4. Distributed Inference
5. Tensor Parallelism
6. Pipeline Parallelism
7. Large-scale GPU Scheduling
8. Multi-node AI Infrastructure

原則：

完成 P0 並取得可驗證的工程成果後，再決定是否投入 P1 / P2。

---

# 六、專案最終交付物

建議保存以下文件作為技術作品集。

| 文件 | 內容 |
|---|---|
| README.md | 專案目標、功能及使用方式 |
| architecture.md | 系統架構、元件及設計取捨 |
| serving-benchmark.md | 推論效能測試 |
| concurrency-report.md | 併發、延遲及容量分析 |
| evaluation-report.md | 模型品質與回歸測試 |
| routing-report.md | 模型路由策略與成效 |
| reliability-report.md | 故障與安全測試 |
| cost-analysis.md | TCO 與成功任務成本 |
| production-readiness.md | 正式環境準備度 |
| technical-decisions.md | 技術決策與替代方案比較 |

---

# 七、職涯成果定位

## 7.1 目標職務

主要：

- Senior Backend / Platform Engineer
- Senior AI Platform Engineer
- AI Infrastructure Engineer

延伸：

- AI Reliability Engineer
- ML Infrastructure Engineer
- AI Platform Architect
- Staff Software Engineer

不預設 AI 職稱一定比同級軟體工程師高薪。

## 7.2 履歷應能展示的能力

- LLM Inference Performance Engineering
- Hybrid Cloud / On-prem AI Architecture
- AI Model Evaluation
- Model Routing & Gateway
- Observability & Reliability
- GPU Capacity Planning
- AI Cost Optimization
- Secure AI Infrastructure
- Production-oriented AI System Design

## 7.3 履歷成果必須量化

至少提供：

- [ ] 不同模型的品質差異。
- [ ] 不同模型的 P95 延遲。
- [ ] 本地 GPU 最大實測負載。
- [ ] 模型路由前後的品質與成本差異。
- [ ] 回歸測試覆蓋範圍。
- [ ] 故障處理與安全測試結果。
- [ ] 不同負載下的地端／雲端成本比較。

不應只列出使用過的工具名稱。

---

# 八、12 週完成後的決策

## 情境 A：平台實驗成功，AI 職缺也有薪資優勢

下一階段：

- 深入 Kubernetes / Cloud Architecture。
- 研究 vLLM / Advanced Serving。
- 挑戰 Senior AI Platform / Infrastructure 職缺。

## 情境 B：平台實驗成功，但 AI 職缺沒有明顯薪資優勢

下一階段：

- 保留 AI Platform 作為第二專長。
- 繼續以 Senior / Staff Software Engineer 為主線。
- 加強 Distributed Systems、Cloud、System Design。

## 情境 C：地端模型成本或效能不具優勢

下一階段：

- 分析適合使用 Cloud API 的工作負載。
- 強化 Evaluation、Gateway、Reliability 技術。
- 不為了地端部署而投入額外硬體成本。

## 情境 D：現成平台已涵蓋大部分功能

下一階段：

- 停止重複開發底層功能。
- 專注系統整合、效能、治理及架構決策。
- 以降低 TCO 或提高可靠性作為技術成果。

---

# 九、最終 Definition of Done

本計畫完成的標準不是「成功架設多個模型」，而是：

- [ ] 能部署與操作本地及雲端 AI 推論服務。
- [ ] 能建立可靠的模型品質評估。
- [ ] 能量測 LLM Serving 效能及資源。
- [ ] 能驗證模型路由策略。
- [ ] 能處理推論服務錯誤與故障。
- [ ] 能管控敏感資料與模型使用權限。
- [ ] 能分析推論總成本與容量需求。
- [ ] 能用實驗數據支持模型選型。
- [ ] 能提出企業可採用的 Hybrid AI 架構。
- [ ] 能完整說明系統限制及技術取捨。
- [ ] 能將成果用於資深工程師／架構師面試。

## 最終目標

成為具備以下整合能力的資深軟體工程師：

**Backend Engineering + AI Inference + Evaluation + Reliability + Infrastructure Architecture**

不以精通特定模型或 Agent Framework 作為核心競爭力，而是具備設計、部署、驗證與最佳化 AI 系統的能力。

長期目標仍是：

**Senior / Staff Software Engineer with AI Platform Engineering Expertise**

在不放棄原有軟體工程優勢的前提下，建立未來 3～5 年可持續累積的 AI 基礎設施與架構能力。
