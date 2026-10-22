# Ollama qwen3.8:27b 單輪 benchmark

固定版本：`bc09c67fc4078501599c37e4cdfecdee40af2ef8`。30 題全部完成，實際30次模型呼叫，provider失敗0、略過0；整輪耗時約 3.15 小時（3 小時 9 分鐘）。

## 三模型觀測結果

題庫、prompt v3、Human訊息中的response schema、View契約與grader相同；沒有為本地模型調整答案或補寫輸出。以下均為既有自動分數，不是完整語意正確率。

| 指標 | gpt-6-sol | DeepSeek-V4.1-Flash | Ollama qwen3.8:27b |
|---|---:|---:|---:|
| 完成題數 | 30/30 | 30/30 | 30/30 |
| 主要View任務配置命中 | 30/30 | 27/30 | 29/30 |
| 來源與必要欄位原評分 | 30/30 | 26/30 | 21/30 |
| Request結構就緒 | 30/30 | 22/30 | 11/30 |
| 完整結構自動檢查 | 30/30 | 18/30 | 7/30 |

主要View命中按任務配置比較，未列於oracle的合法替代也可能失分；欄位原評分不代表request可dispatch。三個模型各一個完整輪次，不是三輪穩定性測試；GPT第二輪部分17筆未混入30題對照。

## 欄位評分盲點

欄位原評分21/30中，01、03、05、19四題實際有使用欄位未列入required_columns，已被validator阻擋。既有grader日期alias寬鬆規則可能將這種漏列也算對，因此21/30不能解讀為21題欄位契約完整。本輪不回寫分數、不改grader；扣除這四個已確認漏判後，僅17題通過這項補充完整性檢查，仍不是全面語意保證。

## 錯誤分類

19題因invalid_plan無法準備request；另有4題ready但完整結構檢查未過（04、06、15、30）。下列validator原因按題數統計，彼此重疊：

- 12題漏列使用欄位；共16個任務出現此錯誤。
- 9題最終粒度夾帶不屬於anchor的維度。
- 9題細粒度來源缺少正確的nest／pivot／aggregate準備。
- 2題group_by與output_grain不一致。

04以月份條件聚合展開8／9月，與oracle的逐月列表示不同；須另驗證缺月份的NULL／零語意，不擅自加分。06改用門市KPI彙總區域毛利，替代來源可能需要審查，但其inner join確實可能刪除無銷售匹配的庫存區域。15同樣誤認inner join會保留未匹配庫存門市，是實際母體保留錯誤。30以唯一門市×日期列的attribute表達收入，與oracle的sum表示有等價判斷差異，原分保持不變。

自動通過也不等於完整語意核准，例如12的庫存彙總仍帶store_name單值attribute，但現有View契約的完整鍵是store_id/product_id，未證明store_id單獨決定名稱。跨日估值、額外度量、未匹配與零值、SQL可編譯性均不能由結構分數單獨保證。

## 本地設定與比較限制

- 使用專案本地設定：thinking=True、temperature=0、top_p=1、seed=42、context=16384、num_predict=-1。
- Ollama使用native JSON schema約束；Azure使用JSON object。Azure temperature=1，並非所有生成設定完全一致。
- 本地SDK逾時設900秒（原設定300秒），以容納本地排程與推論；未修改.env。
- 模型digest：`aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`，Q4_K_M，伺服器回報27.3B。
- 本地服務有既有工作共用，沒有停止其他工作；本輪平均每題約 377.7 秒，最短約 245.0 秒，最長約 699.7 秒，僅為本輪觀測。

## 驗證證據與範圍

- 真實本地單輪：`EV-20261020T061323-aa90f27b`，exit0、source_unchanged=true，harness SHA-256前後一致。
- Fresh離線稽核：`EV-20261020T092232-0cabb01a`，exit0；重播本地30筆並重新核對原雲端77筆。兩個雲端完整30題及本地30題的模型訊息逐題完全相同，原始回覆、驗證、prepared payload、grading與summary一致。
- 產品程式未修改，維持bc09c67；沿用同版本完整回歸391pass／1項缺私有SQL Server profile略過。本輪驗收由同一主agent使用既有獨立oracle與fresh subprocess執行，沒有冒稱另有獨立agent驗收。
- 原始產物：`projects/retail/artifacts/task_decomposition/20261020T061325410052Z-bc09c67f-ollama-0e14eb`；統計與雜湊：`ollama-audit.json`；重播腳本：`audit_ollama_round.py`。
- 本次不生成或執行SQL，不查DB，不驗證實際採購決策、資料值或日期一致性；逐題正式人工語意核准仍pending。

## 逐題結果

| 案例 | 欄位原分 | Request就緒 | 自動結構 | 驗證錯誤 |
|---|---|---|---|---|
| cross-view-01 | True | False | False | task_sales_sep2026: used column absent from required_columns |
| cross-view-02 | True | True | True | — |
| cross-view-03 | True | False | False | inv_current: aggregate grain differs from group_by；sales_sep_2026: used column absent from required_columns |
| cross-view-04 | True | True | False | — |
| cross-view-05 | True | False | False | sales_category: used column absent from required_columns |
| cross-view-06 | False | True | False | — |
| cross-view-07 | True | True | True | — |
| cross-view-08 | True | True | True | — |
| cross-view-09 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-10 | True | True | True | — |
| cross-view-11 | True | False | False | inv_stock: aggregate grain differs from group_by |
| cross-view-12 | True | True | True | — |
| cross-view-13 | False | False | False | kpi_sep: used column absent from required_columns |
| cross-view-14 | False | False | False | task_kpi: used column absent from required_columns |
| cross-view-15 | True | True | False | — |
| cross-view-16 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-17 | True | True | True | — |
| cross-view-18 | False | False | False | task_orders: used column absent from required_columns |
| cross-view-19 | True | False | False | sep2026_store_orders: used column absent from required_columns；final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-20 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-21 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-22 | False | False | False | customer_base: used column absent from required_columns；product_purchases: used column absent from required_columns；final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-23 | False | False | False | task_kpi: used column absent from required_columns；task_product: used column absent from required_columns；final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-24 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-25 | True | False | False | final output grain must come from the anchor grain；finer output grain requires an explicit preparation |
| cross-view-26 | False | False | False | orders_by_channel_2026_09: used column absent from required_columns |
| cross-view-27 | False | False | False | task_kpi: used column absent from required_columns；task_vip_online: used column absent from required_columns |
| cross-view-28 | False | False | False | task_product_profit: used column absent from required_columns；task_store_target: used column absent from required_columns |
| cross-view-29 | True | True | True | — |
| cross-view-30 | True | True | False | — |
