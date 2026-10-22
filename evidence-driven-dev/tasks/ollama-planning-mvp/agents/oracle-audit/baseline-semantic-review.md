# MVP0 原 30 題獨立語意分類

此處只審歷史首輪原始response，不與MVP1新十二筆混分。原raw、原分與JSONL pending未修改；新模型/SQL/DB呼叫為0。

結果：**18題安全完整、9題真語意錯、3題機械錯、0題等價待審、0題資訊不足**。原自動分亦18/30只是數字巧合：05/08/25自動過但不安全，04/06/17自動未過但獨立核准安全。原22個ready中有4個不安全ready（另含14），不能當完整驗收通過。

| 題目 | 分類 | 最早錯誤節點／核准依據 |
|---|---|---|
| cross-view-01 | 安全完整 | 庫存stock_qty原值與單列日期集合，九月units_sold按店商品彙總，left保庫存；缺值政策正確。 |
| cross-view-02 | 安全完整 | 店商品唯一列SUM stock_qty等價原值，九月net_sales、鍵、日期及缺值皆完整，無跨日聚合。 |
| cross-view-03 | 安全完整 | 店商品唯一列SUM成本等價原值，九月SUM毛利非毛利率；日期及庫存母體完整。 |
| cross-view-04 | 安全完整 | 獨立核准等價：八月與九月拆兩個固定月份request，各以店商品對齊並明示不同月份欄位，保存缺月缺值，無加總庫存。三tasks不能被機械長度比較誤判。 |
| cross-view-05 | 真語意錯 | 額外SUM(stock_qty)按store/category聚合且未固定或分組snapshot_date，契約可能混不同商品盤點日；日期metadata不能解除跨日限制。成本與淨額本身正確。 |
| cross-view-06 | 安全完整 | 獨立核准sales_month[09-01,10-01)等價=09-01，因契約保證月份第一天；兩側region成本/毛利、日期揭露與母體正確。 |
| cross-view-07 | 安全完整 | online與九月order_month、SUM quantity、庫存店商品母體完整；SKU/名稱/分類/警戒/狀態是同列補貨展示背景，未改條件或度量口徑。 |
| cross-view-08 | 真語意錯 | stock_qty只在required_columns而沒有attributes/metrics輸出，實際prepared body只要求stock_status，缺目前庫存件數。 |
| cross-view-09 | 安全完整 | 銷售order_date逐日與含09-14條件完整，nest保每日與件數對應、庫存只一次。額外inventory_cost_value是店商品單列估值背景，不跨日或擴大母體；屬可核准低影響冗餘。 |
| cross-view-10 | 機械錯 | inventory metadata集合存在但group_by空、output_grain店商品，validator報聚合粒度不一致；VIP/九月/店商品、根及角色已表達，無新增商業決策缺口。 |
| cross-view-11 | 真語意錯 | 選product_monthly卻要求online，來源無sales_channel；向使用者提議接受全通路不符已支援需求。ready又有clarification是額外結構矛盾，應選sales_detail。 |
| cross-view-12 | 安全完整 | 庫存成本按店SUM及日期集合；九月單店KPI唯一列SUM revenue/target還原原值，母體與缺值正確。 |
| cross-view-13 | 安全完整 | 庫存成本總額與單店九月達標率attribute正確，不SUM/AVG百分比，零目標NULL未改。 |
| cross-view-14 | 真語意錯 | 庫存全域filters已stock_qty=0，零缺貨門市被查詢排除；即使conditional_metrics再次同條件且notes承諾保全部門市也無法恢復。count與distinct在inventory店商品唯一列可等價，錯不在count命名。 |
| cross-view-15 | 安全完整 | 庫存成本按店SUM，毛利率/客單價取單店九月原值；額外store_name可由stores.store_id主鍵及inventory主鍵JOIN證據確立FD，非猜同名，guard此處屬保守FP。 |
| cross-view-16 | 機械錯 | 會員group_by=[customer_id,city]而output=[customer_id]，city由customer_id唯一決定，MAX lifetime_spend單列等價原值；子通路pivot明示保所有來源通路、不預設封閉域，核心語意保留，但型別驗證error。 |
| cross-view-17 | 安全完整 | registered_on為date，<=08-31等價<09-01；九月online及訂單級COUNT order_id等價DISTINCT有真order_id主鍵，保八月註冊無線上訂單會員。 |
| cross-view-18 | 安全完整 | 會員city/active旗標原值，九月in_store訂單級COUNT合法；<=09-30等價<10-01，包含未下單會員。 |
| cross-view-19 | 安全完整 | 會員city/累計消費與按會員×交易店金額nest完整；額外store_name由stores.store_id主鍵且order_summary store_id來自該門市表可證FD，合法展示標籤，guard為保守FP。 |
| cross-view-20 | 安全完整 | 九月按會員商品SUM quantity後nest至會員，會員city/累計消費只一次，含未下單會員，無零值臆填。 |
| cross-view-21 | 真語意錯 | 錯誤要求使用者重定義View既有active_in_last_90d基準、訂單/付款月份；需求只取既有旗標及九月分類淨額，有足夠契約可規劃。needs_clarification不算正確拒絕。 |
| cross-view-22 | 機械錯 | 會員/台北市city/九月online/product度量及會員root均正確，但nest.keys填customer+product而edge收集到customer，描述卻已明示會員下商品集合，局部結構不一致，沒有prepared payload。 |
| cross-view-23 | 安全完整 | 九月KPI店母體，商品units/netSales子集合依store nest，目標單值只一次；店名/商品ID展示合法。 |
| cross-view-24 | 真語意錯 | 需要KPI門市為根附分類子集合，實際final grain=store/category且nest keys=store/category，與門市母體及notes矛盾；不是已正確表達的root，validator擋下。 |
| cross-view-25 | 真語意錯 | target_amount只required未置attributes/metrics，prepared request只選store_name；核心月目標缺失，雖原grader過仍不安全ready。 |
| cross-view-26 | 真語意錯 | 自創不存在order_count作count度量，不能閉包補欄或猜改名；另未限制online/in_store且聲稱保所有來源通路，域非封閉不能當等價。 |
| cross-view-27 | 安全完整 | KPI九月店母體、VIP及online同時只篩訂單；SUM order_amount按店，缺值及背景語意完整。 |
| cross-view-28 | 安全完整 | 三來源商品事實店商品鍵，KPI僅store背景且明示不按商品加總；額外stock_qty在唯一店商品上SUM不跨日，revenue是同月店背景且有明示用途，均低影響冗餘。 |
| cross-view-29 | 真語意錯 | online銷量選product_monthly但沒有通路條件能力，notes宣稱online無法取代真正filter；另庫存metadata無group_by屬機械問題，即使修此仍語意錯。 |
| cross-view-30 | 安全完整 | 庫存成本按店合計附完整日期集合，九月daily_sales有銷售日期逐日nest；不補零日期、不重複庫存，<=09-30合法。 |

## 欄位用途與核准邊界

每題JSON保留全部欄位角色、條件、查詢粒度、整合形狀、extra欄位、required-only與used-not-required集合，並以response/case/catalog hashes綁定。所有原prepared payload都可由其draft精確重算；這不會證明draft滿足需求。

原15與19的額外store_name有contract_review中的stores主鍵與來源JOIN證據，可核准展示FD；現行typed guard因未編碼此證據而拒絕，屬保守false positive，不能當新安全成效。原09與28的額外度量只在真唯一鍵或固定單月下提供明示背景，沒有跨日或背景重加總，屬低影響冗餘。原05額外SUM(stock_qty)則真正跨未對齊日期，不能用日期metadata救回。

原04兩個固定月份request是合法完整表示；原06月初欄位的整月半開範圍、原17 date含八月31日區間，均有契約證據可核准。原14錯在全域缺貨filter刪母體，不能因COUNT與COUNT DISTINCT可等價而判正確。原26自創order_count且漏明確兩通路條件，不能改名補分。

所有需求都有足夠七View契約可處理；原21要求重定義既有旗標/月份是錯誤拒絕，沒有真正資訊不足。機械錯只表示核心商業語意已存在而結構不一致，仍是端到端失敗，不把自然語言承諾當已備妥request。
