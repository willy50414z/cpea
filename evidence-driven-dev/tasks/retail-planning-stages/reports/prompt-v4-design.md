# 參考 text-to-sql 的 planner prompt／context 調整

使用者已明確要求參考現有 text-to-sql 篩選 View 流程並調整 prompt；模型沿用 Azure DeepSeek-V4.1-Flash，主 agent 實作。本次屬既有流程的有界修正，不新增多階段模型架構。

## 參考位置與適用邊界

- `src/cpea/workflows/text_to_sql/sql_generation.py::_retrieve_schema`：檢索與 budget 收納候選。
- 同檔 `_match_candidates`：逐候選完整 schema，限制合法 View／欄位，再驗證需求條件。
- 同檔 `candidate_schema`：透過 `CatalogContract.field_contract` 明列解析後 capabilities 與 aggregations，不把缺省設定誤認為不支援。
- `src/cpea/workflows/text_to_sql/prompts/match/v10.txt`：逐項需求到欄位的對應、資料粒度與口徑先核對，僅列出既有值不自行再聚合；不忽略必要條件、不對已合法欄位多餘澄清。

planner 需要多 View 聯合覆蓋需求，不能直接套用 text-to-sql 的「整題只允許一個 View」規則，或先以完整需求做單一 View 欄位交集，否則會排除必要來源。本次不引入新的檢索步驟；七個核准來源仍全部提供給模型，只在 prompt 中明確逐子需求核對候選能力。

## 具體變更

1. `_load` 使用 `catalog.field_contract` 提供每欄解析後能力，保留來源原有 description、grain、禁止規則及其他 View 設定；不改原 YAML 或 catalog。
2. prompt v4 重寫為子需求映射 → 單 View 查詢子句 → 母體整合；維持一次模型呼叫，沒有增加路由或補救生成。
3. 來源必須具備實際需要的條件與指標；其他來源的責任不強迫同一 View 單獨承接。已有旗標直接查詢，不重新要求定義；準備評估資料不多問決策門檻。
4. 明列逐筆／聚合的欄位角色、輸出角色覆蓋、必要欄位聯集、root／child grain 及 preparation 對齊鍵。日期、通路、零符合母體與缺值政策延續核准邊界。

新測試先在原版因缺少 aggregations 失敗（`EV-20261020T111933-4cfd06f8`），最小 context 修正後 workflow 八項測試通過（`EV-20261020T111942-61e745ba`）。重寫 prompt 後完整回歸 392 passed／1 skipped（缺私有 SQL Server profile），證據 `EV-20261020T112114-fdaf8a74`。

## 模型實驗預先固定

三十題成對比較：v3/raw 與 v4/resolved，每個版本每題一次；逐題輪替先後順序。共同使用 DeepSeek-V4.1-Flash、temperature=1、top_p=1、seed=42、context=16384、max_output_tokens=-1、timeout=300、SDK retries=0、JSON object。模型不看題號、oracle 或其他模型答案，不修改 grader／題庫。遇 provider 錯誤停止後續呼叫，不重試。

新版三十題的實際 context 計數為 13,831–13,866，低於目前 15,744 budget；不增加 context 設定。能力描述增加輸入 tokens，須列入成本比較。

成功標準：新版自動結構通過數高於同批原版，且 request ready 不下降；來源／欄位與已知語意盲點另列，不將單次分數當完整正確率。這是 prompt 與契約呈現的整體比較，不能分離歸因於兩者之一；本輪不加入第三個生成變因。舊的三階段失敗實驗保持原樣。
