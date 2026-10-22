"""Generate a factual report from completed paired prompt evaluations."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
audit=read(ROOT/'reports/prompt-v6-audit.json')
review=read(ROOT/'reports/prompt-v6-review.json')
folder=Path(audit['run'])
meta=read(folder/'run.json')
rows=[json.loads(l) for l in (folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
a,b=(audit['summary'][arm] for arm in ('v3_raw','v6_raw'))
keys=('views_and_columns','ready','automated_pass')
adopt=all(b[k]>=a[k] for k in keys) and any(b[k]>a[k] for k in keys)
assert a['completed']==b['completed']==30 and a['model_calls']==b['model_calls']==30
metrics=[('主要 View 任務配置','canonical_views'),('來源與必要欄位原評分','views_and_columns'),
         ('Request 結構就緒','ready'),('完整結構自動通過','automated_pass')]
table='\n'.join(f'| {label} | {a[key]}/30 | {b[key]}/30 |' for label,key in metrics)
pairtable=[]
for cid in sorted({r['case_id'] for r in rows}):
    rr=[next(r for r in rows if r['case_id']==cid and r['arm']==arm) for arm in ('v3_raw','v6_raw')]
    pairtable.append('| '+cid+' | '+' | '.join('通過' if r['score']['automated_pass'] else r['response']['code'] or r['response']['status'] for r in rr)+' |')
blind={arm:[r['case_id'] for r in rows if r['arm']==arm and r['score']['views_and_columns_match']
    and any('used column absent from required_columns' in e for e in r['response']['validation_errors'])]
    for arm in ('v3_raw','v6_raw')}
v5=read(ROOT/'reports/prompt-v5-audit.json')['summary']
state='保留 v6 prompt 修訂' if adopt else 'v6 未達標，恢復原 v3 預設；候選 prompt 與全部測試保留於任務產物'
oldtokens=sum(a['usage'].values());newtokens=sum(b['usage'].values())
text=f'''# 參考 text-to-sql 篩選 View 的 prompt 調整結果

決策：**{state}**。這是固定三十題單輪的同批對照，並非統計顯著性或所有題目已正確的證明。

## 改動依據與最終候選

參考 `sql_generation.py::_match_candidates` 與 `prompts/match/v10.txt` 的候選映射：逐項檢查欄位語意、條件、粒度與口徑；來源名稱相近不代表可承接。planner 需要跨來源聯合覆蓋，所以不能把單 View 流程的整題單來源限制直接套過來。

v6 在既有 v3 上小幅修訂：

- 先把資訊、條件與期間分配到子需求，再逐候選確認指標、篩選欄位及合併鍵；無法承接就改選合法來源，不以文字冒充已完成的篩選。
- 各來源完成自己的部分即可，不要求每個 View 單獨滿足整題。
- 已有旗標／統計值不重問計算基準；準備評估資料不多問精確決策門檻。
- 顯示欄位須有明確輸出角色；頂層與 task 的 JSON 欄位分清楚。

日期、通路、條件計數、母體保留及 integration 規則沿用 v3。一次模型呼叫完成規劃，不新增檢索節點或多輪修補。兩版 human context、schema、View 契約、題庫與 grader 完全相同，只有 system prompt 改變。

## 最終成對結果

| 指標 | 原版 v3 | 候選 v6 |
|---|---:|---:|
{table}

兩版各完成 30 次 Azure DeepSeek-V4.1-Flash 呼叫，provider 失敗／略過均為零；逐題輪替先後順序。共同設定 temperature=1、top_p=1、seed=42、context_window=16384、max_output_tokens=-1、timeout=300 秒、SDK retries=0、JSON object。

原版輸入／輸出 tokens：{a['usage']['input_tokens']:,}／{a['usage']['output_tokens']:,}；候選：{b['usage']['input_tokens']:,}／{b['usage']['output_tokens']:,}；總 tokens 比約 {newtokens/oldtokens:.2f}。累計模型呼叫耗時分別為 {a['elapsed_ms']/1000:.1f} 與 {b['elapsed_ms']/1000:.1f} 秒，未控制快取／網路／服務負載，不推估計費金額。

自動結構改善案例：{', '.join(audit['improved']) or '無'}。

自動結構退步案例：{', '.join(audit['regressed']) or '無'}。

採用標準預先固定為來源／欄位、ready、自動結構皆不下降，且至少一項增加；本次 {'達到' if adopt else '未達到'}。不因某單項進步就忽略其他退步，不針對候選改答案。

## 限制與未通過項目

- 所有題目都是既有、已見三十題，沒有新外部 holdout，未做多輪穩定性測試。
- 相同 v3 在先前不同執行已有 18/30、16/30 等不同結果，因此不能用跨批次分數代替本次成對比較，也不能把一次差異解讀為穩定因果。
- View／欄位原評分不是完整語意正確率。已知日期 alias 寬鬆規則可能放過使用欄位漏列；本批相關案例：{json.dumps(blind,ensure_ascii=False)}。原分保留。
- 自動評分未涵蓋所有等價表示，也可能放過額外聚合、必要值僅列 required_columns、未證明的單值屬性等問題。補充風險整理於 `prompt-v6-review.json`，需正式逐題人工語意審查；不自行加分或把所有自動未過視為真實語意錯誤。
- ready 只代表通過現有結構驗證並備妥 request，沒有生成或執行 SQL、查 DB、驗證實際資料或採購結論。模型輸入沒有 oracle、題號或 GPT 答案；本次沒有 GPT／Ollama 呼叫。

## 未採用的實驗

先嘗試明列解析後全部欄位能力與完整重寫 prompt。v4 因 task 專用 unbound_inputs 被放到頂層，執行到 16 筆完整回覆後中止；原始結果未覆寫，另有一筆 in-flight 結果未知且可能計費，不能當作完整輪次。

修正欄位層級後，v5 完整三十題同批對照：來源欄位 {v5['v3_raw']['views_and_columns']} → {v5['v5_resolved']['views_and_columns']}，ready {v5['v3_raw']['ready']} → {v5['v5_resolved']['ready']}，自動結構 {v5['v3_raw']['automated_pass']} → {v5['v5_resolved']['automated_pass']}。整體未達標，已撤回 context／workflow 變更及其專用新增測試；原型、patch、失敗與 392/1 測試證據仍保留。不能僅由該組合對照區分是 prompt 還是 context 造成退步。

最終候選只改 prompt，不保留未達標的程式或契約呈現改動；本輪不再追加 prompt 調參。

## 驗證與版本

模型原始產物：`{folder}`。原始輸入、最終 JSON、usage、prepared requests 與原分均保存。

候選固定 HEAD：`{meta['revision']}`，另有已記錄的工作樹差異 SHA-256：`{meta['diff_sha256']}`；不能只用 HEAD 當作候選版本。prompt／harness／題庫與契約指紋見 run.json；`prompt-v6-audit.json` 已 fresh 重播六十筆並逐題核對兩版 human context 相同。

恢復 v3 後完整回歸 **391 passed／1 skipped**，略過原因為缺少私有 SQL Server profile，證據 `EV-20261020T114258-46fc2ee0`。最終產品沒有保留程式碼變更。

在恢復後的相同 validator／grader 上，fresh 重播 v4 部分 16 筆、v5／v6 各 60 筆，合計 **136 筆已保存回覆**，原始訊息、回應、payload 與原分一致；證據 `EV-20261020T114415-e09774d7`。不包含一筆中止時在途且結果未知的呼叫。

調整版保留於 [v6 候選 prompt](../.local/prompt-v6-candidate.py)，對應 patch 為 `../.local/prompt-v6.patch`，供後續審閱；未作為產品預設。

測試與驗證均由同一主 agent 使用既有 oracle 與 fresh subprocess 執行，沒有冒稱跨 agent 獨立驗收。早期 EDD 任務及三階段負結果維持原樣。

## 逐題自動結構結果

| 案例 | v3 | v6 |
|---|---|---|
{chr(10).join(pairtable)}
'''
(ROOT/'reports/prompt-view-matching-results.md').write_text(text,encoding='utf-8')
(ROOT/'reports/prompt-view-matching-decision.json').write_text(json.dumps({'adopt':adopt,'summary':audit['summary'],
    'source_and_fields_false_positive_cases':blind,'run':str(folder)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'adopt':adopt,'summary':audit['summary']},ensure_ascii=False))
