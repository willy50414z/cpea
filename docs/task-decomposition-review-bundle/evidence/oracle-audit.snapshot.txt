# 原 30 題獨立 Oracle 審核

審核結果：**核准作為嚴格 sidecar 的需求參考語意（30/30）**，限本報告 profile。原 JSONL 的 30 個 `pending` 保持不變；這份帶 case/catalog 指紋的 manifest 是獨立核准紀錄，不把 pending 當成通過。這是 oracle 審核，不是任何模型的品質驗收。

基準 Git：`bc09c67fc4078501599c37e4cdfecdee40af2ef8`。契約指紋：`e5e5a5a2cc29a1be93dc4d6875aba8c47a35ed48c019c7d6838a45831d0441dc`。新模型、網路、SQL、DB 呼叫皆為 0；未改產品、契約、原題庫或原分。

## 核准範圍與限制

canonical 30 題的來源、欄位角色、條件、根及 child 粒度、母體、快照、缺值與整合形狀皆已逐題審核。題庫明列的替代來源在保留相同條件、度量與粒度下亦核准。未列等價、日期改寫、條件 pivot 或新增FD規則不能自動繼承核准。

- **STRICT-1**：v_sales_detail的(order_id,product_id)唯一性與contract_review.md矛盾。視其source keys為未知，不得依YAML鍵做raw粒度、FD、attribute退化、COUNT=COUNT DISTINCT或額外維度等價證明；明確COUNT DISTINCT及不依唯一性的SUM可核准。
- **STRICT-2**：required_columns不是輸出角色；所有使用者要求欄位須出現在正確attributes/metrics/conditional_metrics/metadata/group中。額外欄位/度量均須有用途與契約，不能只以required子集通過。
- **STRICT-3**：保留母體需依anchor方向的left edge，保留root粒度；child多餘維度必須由明確nest/pivot保留或有需求授權aggregate；不能僅存在任意preparation就算等價。
- **STRICT-4**：日期metadata僅DISTINCT來源日期集合；不能作同日證明，不能解除stock_qty不可跨不同日期直接SUM；目前不同商品列成本合計只能解讀為帶來源日期的目前列估值。
- **STRICT-5**：缺值不得臆填0；合法條件計數、來源欄位明示的真0/NULL分開。pivot、空child與未匹配的輸出形狀必須不損失此區別；通路域不視為封閉。
- **STRICT-6**：payload必須由已核准draft確定生成，request內view、fields、roles、filters、grain及history=[]逐一匹配且長度<=4000；任何未列等價需獨立審查，不以grader替代。

## 逐題處置

全部為 `APPROVED_WITH_PROFILE_RESTRICTIONS`，逐題精確欄位角色、filters、根/查詢粒度、整合規則與 hashes 詳見 `review-manifest.json`。此表列各題審核理由；無 canonical ready 必須改成澄清的已確認矛盾。

| 題目 | 處置與依據 |
|---|---|
| cross-view-01 | 核准，須遵守嚴格 profile。庫存件數取目前唯一店×商品列；九月銷量先按店×商品彙總；不得求採購量。 |
| cross-view-02 | 核准，須遵守嚴格 profile。折扣後銷售額須net_sales，庫存stock_qty，不以gross_sales或成本取代。 |
| cross-view-03 | 核准，須遵守嚴格 profile。inventory_cost_value對gross_profit金額，非營收、毛利率；庫存保留每列日期。 |
| cross-view-04 | 核准，須遵守嚴格 profile。八月、九月必須各自保留；pivot兩明示月份合法，nest兩月集合亦可；少月不能臆填零，不複製庫存。 |
| cross-view-05 | 核准，須遵守嚴格 profile。店×分類分別SUM庫存成本與九月net_sales；目前列成本合計須揭露完整日期集合。 |
| cross-view-06 | 核准，須遵守嚴格 profile。以庫存region為母體，兩側各自聚合到region；庫存成本不是跨日stock_qty。 |
| cross-view-07 | 核准，須遵守嚴格 profile。九月online條件只套明細；商品月表不含通路，不能取代具通路需求明細。 |
| cross-view-08 | 核准，須遵守嚴格 profile。九月in_store條件只套明細，不能用online或過去30日銷量替代。 |
| cross-view-09 | 核准，須遵守嚴格 profile。銷售日期含9月14日，使用[09-01,09-15)；按日集合只包含有銷售日期，不生造日曆列。 |
| cross-view-10 | 核准，須遵守嚴格 profile。VIP只篩銷售來源，不篩庫存；按店×商品SUM quantity，不將會員維度加到庫存根。 |
| cross-view-11 | 核准，須遵守嚴格 profile。online與九月均不可遺失；discount_amount及net_sales是兩項金額，非折扣率或gross_sales。 |
| cross-view-12 | 核准，須遵守嚴格 profile。庫存成本先SUM到store_id，取九月KPI revenue與target_amount；KPI月值各保留一次。 |
| cross-view-13 | 核准，須遵守嚴格 profile。只取單店九月target_achievement_pct原值；零目標原NULL保留，不SUM/AVG百分比。 |
| cross-view-14 | 核准，須遵守嚴格 profile。所有庫存門市上COUNT DISTINCT product_id WHERE stock_qty=0作條件度量，非全域filter；零缺貨門市必須回0。 |
| cross-view-15 | 核准，須遵守嚴格 profile。單店單月gross_margin_pct及avg_order_value用attribute，不能直接SUM/AVG；保留其既有0語意。 |
| cross-view-16 | 核准，須遵守嚴格 profile。會員city是註冊城市；每會員lifetime_spend只保留一次；九月各通路是會員child集合。 |
| cross-view-17 | 核准，須遵守嚴格 profile。註冊日期[08-01,09-01)只限會員母體；訂單日期[09-01,10-01)與online只限訂單。 |
| cross-view-18 | 核准，須遵守嚴格 profile。active_in_last_90d是會員既有旗標，不用九月實體訂單重算；包含未下單會員。 |
| cross-view-19 | 核准，須遵守嚴格 profile。每會員根配各交易store_id子集合；不可將會員city改作store_city。 |
| cross-view-20 | 核准，須遵守嚴格 profile。每會員根配product_id子集合，九月SUM quantity；lifetime_spend不按商品重加總。 |
| cross-view-21 | 核准，須遵守嚴格 profile。會員registered_on及active_in_last_90d為屬性；九月category子集合SUM net_sales，不以九月交易重算活躍。 |
| cross-view-22 | 核准，須遵守嚴格 profile。台北市只篩會員city；online只篩銷售；會員根保留無購買，商品子集合保留product_id。 |
| cross-view-23 | 核准，須遵守嚴格 profile。九月KPI門市為母體；商品child含units_sold與net_sales，target_amount不重複加總。 |
| cross-view-24 | 核准，須遵守嚴格 profile。is_complete_month=true只取KPI母體；category毛利是child，不對商品來源施加不存在的完整月欄位。 |
| cross-view-25 | 核准，須遵守嚴格 profile。九月KPI門市為母體；category子集合保留discount_amount及net_sales兩度量。 |
| cross-view-26 | 核准，須遵守嚴格 profile。通路明確限online/in_store，不能假設域封閉；按店×通路COUNT DISTINCT order_id及SUM order_amount。 |
| cross-view-27 | 核准，須遵守嚴格 profile。VIP與online同時套訂單，九月KPI母體不受影響；聚合為每店金額可scalar attach。 |
| cross-view-28 | 核准，須遵守嚴格 profile。店×商品為根：庫存與毛利以store_id/product_id合併，KPI僅store_id附背景，禁止加總背景目標。 |
| cross-view-29 | 核准，須遵守嚴格 profile。店×商品為根：九月online quantity與庫存配對，KPI僅store_id作背景。 |
| cross-view-30 | 核准，須遵守嚴格 profile。目前庫存成本先SUM到store_id附完整日期集合；九月daily_sales按有銷售日期nest，不補無交易日期、不重加總庫存。 |

## 快照結論

`metadata_collections=[snapshot_date]` **不能允許跨日 SUM(stock_qty)**。它只保存完整來源日期集合。題庫 05、06、12、13、15、30 的 canonical 庫存彙總是 `SUM(inventory_cost_value)`，14 是 `COUNT DISTINCT product_id` 的條件計數，沒有 canonical 要求跨日 SUM(stock_qty)。成本合計可表達目前各列估值總額，必須揭露來源日期，不能稱單日盤點總額。若新需求要求同日庫存或跨日期庫存件數合計，沒有日期一致證據就澄清或按日期保留，不以metadata救回 ready。

## 評分盲點與新鮮反例

`grader-witnesses.json` 保存本次 fresh subprocess 對現行 grader 的七個見證：一個 canonical 基線及六個盲點。前五個錯誤變異仍得到 `automated_pass=true`，第六個不實 COUNT 等價得到 task metrics=true。這些是合成計畫與記憶體資料，不是模型結果，也未執行 SQL。

| 見證 | 實測結果 | 影響 |
|---|---|
| missing-output-role | automated_pass=true | required_columns含庫存但attributes清空，request實際未選庫存仍過 |
| extra-metric | automated_pass=true | 加入無需求gross_sales，grader只驗預期metrics包含 |
| fill-zero | automated_pass=true | 把所有缺值填0的政策與oracle相反仍過 |
| wrong-payload-body | automated_pass=true | payload僅非空不核對request正文，錯月份仍ready |
| wrong-child-preparation | automated_pass=true | 第09題應每日nest，改aggregate抹掉日期仍過 |
| unproved-count-equivalence | task metrics=true | 未證實明細唯一鍵讓COUNT(order_id)等同DISTINCT，兩筆重複order/product列可反證 |

現行 grader 還不直接比對 attributes、group_by、額外 conditional metrics、必需 preparation 的用途、背景禁止重加總及 child 空集合形狀。validator 能檢查欄位/型別/合法聚合、連通與部分粒度，但不證明自由描述的 preparation 實作，也不理解任意 request 自然語言。需要嚴格 sidecar，不能只提高現行結構分。

## 合法等價邊界

- 月等號與完整月日期半開區間，須來自相同事件日期軸且型別/月份第一日語意成立；同軸名稱相似不是充分條件。非完整月、付款日期、盤點日期不等價。
- 唯一店×商品或固定單月店×商品的原值與SUM/MIN/MAX等價，必須有真實唯一鍵且未加入不同維度；v_sales_detail禁用此推導。
- 訂單級v_order_summary可在其order_id主鍵證據下COUNT/COUNT DISTINCT等價；銷售明細永遠保留明確COUNT DISTINCT，不採可疑複合鍵證明。
- 第04題兩個明示月份可pivot或保留有標籤的完整月份集合；不得抹月、填缺月0或把庫存沿月份再加總。
- 一般child維度（商品、分類、交易門市、每日、通路）須可重建完整集合；有限pivot需需求明示值集合及零/缺值等價證據。第26題未觀察通路不能臆生成0。
- 三來源28/29的KPI只按store_id背景附加，不能用product_id合併，不能把門市目標加總到多商品。

## 下一步

主 agent 應整合並凍結此 manifest/profile，依同一保守規則完成離線重播與語意 sidecar；原自動分與新語意分分列。只有新8題亦核准、固定版本兩輪首次結果各38/38後才可進Ollama。此審核沒有證明新的模型方案通過。
