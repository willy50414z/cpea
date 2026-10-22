# 高優先規則

僅根據本次單一 View 契約逐項映射，保留合法部分支持。不得捏造欄位、能力、引文、通路、日期或來源母體；無能力就明列缺口。度量與其 scope_ids 條件必須由同一來源支持，不能借另一來源替既有彙總度量補篩選。只輸出 response_schema JSON，不產生 SQL，不寫私有思維鏈。

# 單一來源映射

每個 requirement_id 都要有且只有一筆 entries，status 為 supported／partial／unsupported／uncertain。supported 必須有 mappings、contract_evidence、空 missing_requirements，且所有 scope_ids 在本 View 都 supported；否則保留可用映射並標 partial。unsupported／uncertain 的 mappings 為空。非 supported 必須說明 missing_requirements。

grain 逐字填契約 grain.description；keys 逐一填完整契約 grain.keys，不能換成希望的輸出粒度。population 描述本來源真實母體，contract_evidence 引用其 summary 或 grain.description。

每個 mapping 的 column 必須存在，role 對應需求 kind；grain／population 項目使用 key 映射對齊識別鍵。source_quote 是其 requirement.quote 中的逐字片段。contract_evidence 必填本欄位 /columns/欄位名稱/description 的 JSON pointer 與該處逐字引文，可另加其他契約引文；entries 自身也要附相關契約證據。路徑相對本 View 契約，不含 View 名稱。

metric 填合法 aggregation，其餘角色 aggregation=null。filter 填 operator 與型別正確 value；其他角色 operator=null、value=null。conditions 通常為 []，只有條件度量可用，條件欄位也須有獨立 filter 映射。key 為識別／分組鍵；attribute 為顯示屬性；metadata 為日期或字串來源資訊集合。不得把 filter 當成屬性，或把資料日期當額外分組維度。
