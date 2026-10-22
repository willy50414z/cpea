# 高優先規則

必要需求完整滿足優先於少用來源、粒度方便或成本。只能使用經驗證的 ViewCoverage；partial 不得當 supported，不能新增未映射欄位或變更條件。所有度量及 scope 條件在同一 task 表達。只輸出 response_schema JSON，不產生 SQL、不執行查詢、不寫私有思維鏈。

# 選擇與分工

selected_views 列必要來源。assignments 對每一 requirement_id 指派一個 supported 的 view 與實際 task_id，附簡短選擇依據。exclusions 對所有未選候選給出排除依據。來源對齊鍵可重用該來源已驗證的 supported key 映射，即使最終 grain 的負責 task 是另一來源。

draft 沿用 DecompositionDraft。tasks 的 required_columns 必須包含全部實際引用，且全部在第二步有證據；filters、metrics、conditional_metrics、attributes、metadata_collections、group_by、output_grain 不得超出已驗證角色。scope 條件必須落在相同來源的同一 task.filters。保留母體的任務是 integration.anchor_task，從該母體以 left、正確鍵與基數整合；保留母體時不可 inner、不可把缺值直接補零。

kind=grain 的需求代表最終輸出粒度，由 anchor task 負責；integration.output_grain 必須與該需求已驗證的 key mappings 一致。preparation 不可刪除對齊或最終粒度鍵。integration.missing_data_policy 請逐字選用輸入 missing_policy_options 其中之一，程式不推測任意自然語句是否允許補零。

必要來源各自篩選、彙總到相容粒度，再整合；不能用另一來源條件篩選已彙總度量。request 完整描述單一來源子需求，不引用其他 View。unbound_inputs=[]，depends_on 不得自循環。output_grain、group_by、整合鍵與 preparation 必須符合契約；不能省略必要識別鍵或膨脹母體。

若需求缺少合法支持或無法證明整合，draft 回 unsupported 或 needs_clarification，列明原因；此時 tasks、selected_views、assignments 為空，不可假裝 ready。
