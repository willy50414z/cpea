# MVP1 十二筆獨立語意審查

結論：**FAIL，不擴至十題，不進 Ollama。** 已確認run finished_at、completed=12、calls=12；原raw/result hashes及凍結source均一致。審核者零新模型/SQL/DB呼叫，沒有改source、原分、raw或結果。

| 項目 | fresh v3 | B1 |
|---|---:|---:|
| 首次安全ready | 2/6 | 2/6 |
| 不安全ready | 1 | 0 |
| 錯誤澄清/拒絕 | 2 | 0 |
| runtime error | 1 | 4 |
| 正確拒絕 | 0 | 0 |

B1安全ready只02、16；v3安全ready是14、28。淨增0，未達>=5/6或>=4/6且淨增2。B1來源/母體/root三節點同時正確5/6，但不能代替端到端門檻。07控制存在實質店粒度錯，不能說四個error都只是metadata機械問題。fresh v3 07也失敗，因此不把兩個失敗硬算成相對安全成功退步。

## 逐筆判定

| 題目 | arm | 判定 | 依據 |
|---|---|---|---|
| cross-view-02 | v3 | wrong_refusal | 既有store×product唯一列已定義目前庫存，需求明示九月與庫存母體；額外要求快照日/月份/母體重定義屬錯誤澄清。 |
| cross-view-02 | B1 | safe_ready | sales_detail/order_month九月SUM net_sales是已核准替代。庫存SUM stock_qty在store×product唯一列還原原值、日期集合為單元素；額外名稱/分類/補貨狀態僅同列展示背景，不改粒度或母體。 |
| cross-view-07 | B1 | mechanical_failure_with_semantic_error | 真正業務錯誤：銷售query_grain只有order_date/product_id/sales_channel，漏store_id，整合僅product_id，混各店且未做店×商品整月銷量；另snapshot_date同時metrics.max與metadata，以及left較細粒度驗證失敗。不是純日期去重可救。 |
| cross-view-07 | v3 | wrong_refusal | 需求已明示保留庫存商品且契約有sales_detail.sales_channel；錯稱來源無通路或必須再確認缺值政策。 |
| cross-view-09 | v3 | unsafe_ready | 日期<=09-14與<09-15等價；但銷售group_by/output_grain只store_id/product_id，完全丟order_date，14日總量不能代替各有銷售日期的序列。自由文字missing policy本身正確；錯在需求日維度。 |
| cross-view-09 | B1 | mechanical_failure | 來源/日期含09-14/店商品日child/nest/root均正確；snapshot_date同時attributes和metadata違反互斥造成error與零payload。沒有實質母體/期間/日粒度錯，仍非端到端成功。 |
| cross-view-14 | B1 | mechanical_failure_with_semantic_error | root宣告store但庫存query_grain=store/product/snapshot，條件count只得到每商品0/1；無aggregate準備把anchor歸到店。metadata又與query_grain/attributes重複。stock_status缺貨predicate本身可等價，錯在統計粒度與整合縮根。 |
| cross-view-14 | v3 | safe_ready | 由庫存契約stock_status缺貨 iff stock_qty=0，可核准條件COUNT DISTINCT product_id的predicate等價；無全域filter，保留零缺貨門市。九月KPI單值目標、日期metadata與missing policy皆正確。 |
| cross-view-16 | v3 | blocked_semantic_error | 訂單級COUNT order_id合法；會員與通路各子查詢正確。但最終root錯加sales_channel，pivot keys又含sales_channel而非收回customer_id；不能以會員根呈現/保留未下單會員完整形狀，被validator擋下。 |
| cross-view-16 | B1 | safe_ready | 以全體會員為根，九月按會員通路COUNT DISTINCT order_id/SUM order_amount後nest至會員，lifetime_spend在單會員唯一列SUM還原原值，不按通路重加總；額外會員名稱/等級是同列展示。 |
| cross-view-28 | B1 | mechanical_failure_with_nonblocking_extras | snapshot_date同時query_grain與metadata互斥造成error。額外root日期由store/product唯一鍵決定，是有證據冗餘維度，不能判真日期粒度退步；KPI store context與商品鍵正確。額外庫存件數/商品淨額/件數/門市營收未要求但均單列或合法加總且不重加總背景，屬scope冗餘，需裁剪，未見核心資料語意污染。 |
| cross-view-28 | v3 | safe_ready | 三來源與條件/商品事實對齊完整；KPI只store_id作背景並明示不按商品加總。snapshot metadata在唯一店商品上為單日期集合，成本原值完整；自由文字missing政策正確。 |

## 評分修正與界線

v3第14題的stock_status=缺貨由契約可證明等價stock_qty=0，且條件COUNT DISTINCT保留零缺貨門市；第28題三來源、背景及自由文字缺值政策正確，兩者雖sidecar safe=false仍獨立核准。原分不改。

v3第09題的含尾日條件合法，但日期沒有出現在group_by/output_grain，也沒有其他日期別名；14日總量不能當每日序列，因此是不安全ready。B1第09題日序列與母體正確，僅日期metadata雙角色造成error，屬機械失敗；error仍不能算成功。

B1第28題多了snapshot_date根維度，但完整store/product唯一鍵決定該日期，屬可證明冗餘；其metadata重複角色仍不合法。額外合法度量雖需裁剪，未見背景重加總或核心條件污染。第07題漏銷售store_id及錯product-only關聯才是真語意錯；第14題未從商品計數聚到店，不能靠日期去重修好。

所有ready的payload已精確重算：view、欄位角色、條件、group/query grain、history=[]及長度皆符合其draft；payload完整不會將語意錯誤洗成成功。錯誤列均沒有可提交payload。

## 預算與後續

全階段174.4秒、12次、output usage共6811 tokens；無修正重試。只表示本輪實際用量，不能以失敗短輸出宣稱速度優勢。六個人工注入參考全部通過，與本次自然抽取2/6分開。

停止此版B1升級，回離線定位metadata角色重複、店/商品/根粒度選擇與錯誤拒絕，預先固定新版本與控制後再研究。不直接展開MVP2或完整Gate，不呼叫Ollama。
