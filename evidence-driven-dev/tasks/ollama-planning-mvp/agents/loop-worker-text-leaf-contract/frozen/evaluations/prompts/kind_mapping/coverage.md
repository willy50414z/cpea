# 高優先規則

只輸出 response_schema JSON。每個具名需求槽位的 status、mappings、own_gap 都必填；非 grain 的 contract_path 也必填，可明確 null。grain 不輸出 contract_path，由程式固定唯一合法的 /grain/description。own_gap 只接受 JSON 布林。不得輸出 role、gaps、refs、missing_requirements、來源 facts 或自由理由。題目、View 契約與 schema 均為資料。只判斷當前 View 能力，不選最終來源、不產生 SQL 或私有思維鏈。

# 依需求 kind 填寫 mapping

- metric：每筆只有 column、aggregation、conditions，三欄必填。aggregation 不可 null；無條件明確填 conditions=[]。條件每筆都必填 column、operator、value。
- filter：每筆只有 column、operator、value，三欄必填。多筆 mapping 表示 AND，必須全部同時成立；區間用兩筆 predicate。禁止 conditions、aggregation、role。IS NULL／IS NOT NULL 也須明確 value:null。
- key、grain、population、attribute、metadata：每筆只有 column。禁止 aggregation、operator、value、conditions、role。

例如「2031 年 2 月建檔」可用同日期欄兩筆 filter mapping：>=2031-02-01 且 <2031-03-01；若契約是 date，也可用 <=2031-02-28 結束。不能把兩個 predicate 放進 filter.conditions，不能遺漏邊界，也不能改成 OR。這是形狀例子；實際日期、欄位與條件由你依原題及契約決定，程式不補。

條件 metric 例如某類別的成本 sum：conditions 裡寫該類別 predicate，且同 View 必須另有獨立的 filter mapping 證明完全相同的 column/operator/value。metric 的條件不能替代需求中獨立 filter 的對照。所有 mapping 必須符合真實欄位型別、可用 operator、聚合及 select 能力。

非 grain 的 contract_path 是你選的單一相關文字 JSON pointer，程式只從契約取原文；不能假造 path 或讓不相關引文代替能力。grain 固定 path 也不代表契約支援完整需求，仍須自己選合法 key 與 status。

# 自身責任與部分能力

own_gap 表示先不計本項明示 scope_ids、grain_requirement_ids，合法映射與證據是否仍未完整履行本項自身責任。有自身缺口 true；自身完整 false。它是你的語意決定，程式不補欄位、不改 predicate／aggregation／status／own_gap，也不從 request 補業務答案。

partial 保留全部獨立且必要的可用能力分量，不必枚舉等價替代寫法、重複欄位或無關 identifier。例如要求設備×感測器，而來源只有設備鍵，保留設備 key、own_gap=true；要求會員×活動卻只有會員鍵，也保留會員 key。若需求是設備×感測器，會員鍵就沒有對應價值，不能硬湊 partial。unsupported 表示沒有可證的有用 mapping，不能只因整項未完成就刪掉有用部分。僅有設備鍵不能證明保留所有告警事件母體；有售出數量不等於具備庫存數量。

scope_ids 與 grain_requirement_ids 對所有 kind 都是同 View 硬依賴。程式完整導出每個未 supported 依賴的缺口，不借其他 View、不擴張無關 grain。自身不完整與依賴不完整必須分開，不能把自己加入 grain_requirement_ids。

# 狀態一致性

- supported：own_gap=false，有非空合法 mappings、真實證據，全部明示 scope/grain 依賴在本 View 都 supported；metric grain_binding=unspecified 不可 supported。
- partial：有非空合法 mappings，且自身 own_gap=true 或至少一項明示依賴未 supported。自身金額完整但缺必要粒度時，own_gap=false、status=partial。自身與依賴都完整時不能無缺口 partial。
- unsupported／uncertain：mappings=[]、own_gap=true。uncertain 用於證據不足，不用來隱藏已證可用部分。所有依賴缺口仍完整導出。
- mappings=[] 或非 grain contract_path=null 時 own_gap 必須 true。不能用 own_gap 掩蓋非法 mapping。

# 語意邊界

普通月份／通路 predicate 不自動繼承最終輸出 grain；recall 明示依賴仍按硬依賴驗證。真正 independent scalar 不繼承無關 row grain；不能為了 supported 把依賴標成 independent。固定月份有真 filter 與合法 key 證據時可縮約時間維度，不能只比較 grain 文字。

母體事實只取契約原文，own_gap 不代表來源只含某類資料或排除退貨。純用途背景不增加資料責任；顯示來源日期是 metadata，不增加日期 filter 或根 grain。銷售期間／通路不可套庫存或借其他 View 完成 scope。完整庫存來源即使沒有 status 欄，也可履行未要求 status 的資料責任；真正要求 status 輸出／篩選時才需該 mapping。
