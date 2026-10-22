"""離線重播六筆可見決策摘要，產生比較報告；不呼叫模型。"""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from cpea.application.models.decomposition import DecompositionDraft,DecompositionResponse,ExplainedDecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decision_summary_comparison import TASK,MODELS,decision_messages,finish_explained,fingerprint
from evaluations.planning_mvp import semantic_check


folder=TASK/'.local/decision-summary-20261020T152551Z-3f8ec7'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
meta=read(folder/'run.json')
assert meta['calls']==meta['completed']==6 and meta['stopped'] is None
for name,h in meta['artifact_hashes'].items():assert sha256((folder/name).read_bytes()).hexdigest()==h
catalog=SchemaCatalog(Path('projects/retail'))
all_cases=load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'),catalog)
cases=[next(c for c in all_cases if c['case_id']==cid) for cid in meta['cases']]
assert fingerprint(catalog,cases)==meta['frozen']
baseline=read(TASK/'.local/decision-summary-baseline-schema.json')
for name,cls in [('DecompositionDraft',DecompositionDraft),('DecompositionResponse',DecompositionResponse)]:
    assert sha256(json.dumps(cls.model_json_schema(),sort_keys=True).encode()).hexdigest()==baseline[name]
rows=[json.loads(s) for s in (folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(rows)==len({(r['case_id'],r['model']) for r in rows})==6
by_key={(r['case_id'],r['model']):r for r in rows}
totals={model:{'calls':0,'ready':0,'summary_present':0,'original_automated_pass':0,
               'input_tokens':0,'output_tokens':0,'total_tokens':0,'elapsed_call_seconds':0} for model in MODELS}
for case in cases:
    calls=[]
    for model in MODELS:
        name=case['case_id']+'-'+model
        event=read(folder/(name+'-call.json'));row=by_key[case['case_id'],model]
        assert event['messages']==[{'role':m.type,'content':m.content} for m in decision_messages(case['request'],catalog)]
        calls.append(event)
        draft=parse_model(SimpleNamespace(content=event['response']),ExplainedDecompositionDraft)
        response=finish_explained(draft,catalog)
        assert response.model_dump()==row['response']
        assert draft.decision_summary.model_dump()==row['decision_summary']
        assert grade_decomposition(case,response,catalog)==row['score']
        assert semantic_check(case,response,catalog)==row['diagnostic']
        assert all('decision_summary' not in json.loads(p.payload['request'].split('\n',1)[1]) for p in response.prepared_requests)
        t=totals[model];t['calls']+=1;t['ready']+=response.status=='ready';t['summary_present']+=row['decision_summary'] is not None
        t['original_automated_pass']+=row['score']['automated_pass']
        for k in ('input_tokens','output_tokens','total_tokens'):t[k]+=(event.get('usage') or {}).get(k,0)
        t['elapsed_call_seconds']+=event['elapsed_seconds']
    assert calls[0]['messages']==calls[1]['messages']

# These are offline review findings for the immutable run, never runtime rules.
findings={
 'cross-view-11':{
  'first_visible_difference':'source_selection：GPT排除無通路欄位的商品月表；DeepSeek仍選該表。',
  'gpt_verdict':'安全ready；來源、九月online條件、兩金額、店商品鍵與庫存母體完整。',
  'deepseek_verdict':'error；選v_product_monthly卻引用其不存在的sales_channel，欄位亦未列required_columns。',
  'consistency':'DeepSeek摘要與typed filters都要求online，但所選來源沒有該能力；是契約依據錯誤，不能把摘要承諾當已完成條件。'},
 'cross-view-14':{
  'first_visible_difference':'field_roles／grain：DeepSeek多輸出未要求的COUNT(stock_qty)，摘要未交代；另將來源鍵描述為店×商品×日期。',
  'gpt_verdict':'安全ready；缺貨條件留在conditional_metrics，沒有全域filter刪母體；固定月份目標取原值。',
  'deepseek_verdict':'ready；核心條件計數、店母體與日期metadata合理；多出未要求的一般COUNT(stock_qty)，未有用途核准，不宣稱整題嚴格語意全對。',
  'consistency':'摘要未覆蓋額外一般計數，且來源契約鍵實為store_id/product_id，與其grain文字不同。stock_status=缺貨與stock_qty=0、COUNT與DISTINCT在真店商品唯一鍵下有既有等價依據。'},
 'cross-view-26':{
  'first_visible_difference':'conditions：GPT明列online/in_store；DeepSeek摘要明說不限制通路集合，typed filters亦無IN。',
  'gpt_verdict':'安全ready；訂單級COUNT合法，明示兩通路集合，按店pivot後保KPI母體與缺值。',
  'deepseek_verdict':'error；漏使用者指定雙通路限制；pivot準備使用子查詢沒有的sales_month鍵，且兩側月份欄位無已核准mapping。',
  'consistency':'摘要與typed計畫一致地漏通路限制，均違反需求；摘要稱按月份完成pivot，實際準備鍵不合法。'}
}

summary={'artifact_result':'PASS','prompt_version':meta['prompt_version'],'models':totals,
         'calls':6,'elapsed_seconds':meta['elapsed_seconds'],'same_messages_per_pair':True,
         'original_v3_schemas_unchanged':True,'all_six_summaries_present':True,
         'explanations_excluded_from_sql_payloads':True,'raw_response_score_payload_replayed':6,
         'findings':findings,'self_reported_summaries':[
             {'case_id':r['case_id'],'model':r['model'],'decision_summary':r['decision_summary']} for r in rows],
         'reviewer':'main-agent using previously independently approved oracle and contract evidence',
         'model_evidence_scope':'新增摘要schema與prompt後的三題單輪；不是原v3同輪對照，也不是模型私有推理順序的證明。',
         'raw_folder':str(folder),'sql_db_calls':0,'ollama_calls':0,'new_model_calls_in_verification':0}
(TASK/'reports/decision-summary-comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

labels={'source_selection':'來源選擇','field_roles':'欄位角色','conditions':'條件與期間','grain':'根／子粒度','population':'保留母體','integration':'整合方式'}
esc=lambda s:s.replace('|','\\|').replace('\n','<br>')
lines=['# GPT 與 DeepSeek 可見決策摘要比較','',
 '已新增獨立診斷型別 `ExplainedDecompositionDraft` 與 `ExplainedDecompositionResponse`，必填 `decision_summary`。六欄各限 1–600 字元，要求一至兩句可核對的決策及契約依據；原 v3 schema、預設流程與舊結果不變。', '',
 '此欄位是模型自述的高層決策理由，不是私有思維鏈，亦不能證明模型內部先後順序。說明可能錯誤或不完整，驗證與 request 組裝只使用 typed 計畫，摘要不成為執行指令。', '',
 '| 模型 | 呼叫 | 摘要完整 | Request ready | 原自動分 |', '|---|---:|---:|---:|---:|']
for model,t in totals.items():lines.append(f"| {model} | {t['calls']} | {t['summary_present']}/3 | {t['ready']}/3 | {t['original_automated_pass']}/3 |")
lines+=['', '三題11、14、26使用相同Chat Completions輸入；temperature=1、top_p=1、seed=42、context=16384、輸出上限4096、SDK retries=0，每題每模型一次，順序交替。六次共約64秒。這是新增摘要後的新版本觀測，不能將與歷史差異歸因為只多一欄。', '',
 'GPT三題由主agent依既有獨立oracle核對為安全ready；DeepSeek只有14為ready，但有未核准額外計數及摘要缺漏，沒有將ready直接當嚴格語意全對。原sidecar的自由文字缺值政策與COUNT等價存在已知保守誤判，原分與診斷結果皆保留，未回寫追分。', '']
for case in cases:
    cid=case['case_id'];f=findings[cid]
    lines += ['## '+cid,'',case['request'],'', '**第一個可見差異**：'+f['first_visible_difference'],'',
              '**GPT 判定**：'+f['gpt_verdict'],'','**DeepSeek 判定**：'+f['deepseek_verdict'],'',
              '**摘要與計畫一致性**：'+f['consistency'],'',
              '| 摘要欄位 | GPT 原文 | DeepSeek 原文 |','|---|---|---|']
    for key,label in labels.items():
        lines.append('| '+label+' | '+esc(by_key[cid,MODELS[0]]['decision_summary'][key])+' | '+esc(by_key[cid,MODELS[1]]['decision_summary'][key])+' |')
    lines += ['', '完整typed計畫、payload、原始說明與分數見本Task的 `.local/'+folder.name+'/`，或[機器比較資料](decision-summary-comparison.json)。','']
lines+=['## 驗證紀錄','',
        '六筆raw→診斷draft→response→payload／原分／sidecar均在fresh subprocess重播一致，同題messages完全相同，原兩個v3 schema SHA256未變。新增五項測試涵蓋摘要必填、原schema相容、摘要不改payload、不合法計畫不因說明而放行、context無oracle；相關回歸86 passed。', '',
        '未增加模型重試、未查DB、未產生或執行SQL、未呼叫Ollama。DeepSeek完整Gate仍未通過。']
(TASK/'reports/decision-summary-comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('artifact_result','calls','elapsed_seconds','models','same_messages_per_pair','original_v3_schemas_unchanged','all_six_summaries_present')},ensure_ascii=False))
