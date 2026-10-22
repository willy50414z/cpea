"""Ask each model once to fill an ordered, public decision record."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from langchain_core.messages import SystemMessage, HumanMessage
from cpea.application.models.decomposition import (
    DecisionChainDecompositionDraft, DecisionChainDecompositionResponse, ExplainedDecompositionDraft,
)
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.decision_summary_comparison import TASK,MODELS,decision_messages,finish_explained
from evaluations.planning_mvp import semantic_check


PROMPT_VERSION='v3-decision-chain-1'
CHAIN_INSTRUCTION='''\n另必填decision_chain，必須由你填寫，程式不會代填。這是有序的公開決策紀錄，不要求私有內部思維鏈。用六個節點各記錄一類最終決策：source_selection、field_roles、conditions、grain、population、integration，每類恰好一次；可自行安排紀錄順序。step_id依序1至6；每個decision用一句簡短選擇，evidence填一至四項需求短引文或View契約欄位依據，task_ids引用實際tasks的task_id，depends_on只能引用本紀錄中已出現的節點ID、無前置則[]。每節點應能與typed計畫核對；不要寫假設成真、不得用紀錄取代filters/grain等結構。節點依賴只是公開決策的關係，不宣稱內部思考發生順序。'''


def chain_messages(request,catalog):
    base=decision_messages(request,catalog)
    context=json.loads(base[1].content)
    context['response_schema']=DecisionChainDecompositionDraft.model_json_schema()
    return [SystemMessage(content=base[0].content+CHAIN_INSTRUCTION),
            HumanMessage(content=json.dumps(context,ensure_ascii=False))]


def finish_chained(draft,catalog):
    plain=ExplainedDecompositionDraft.model_validate(draft.model_dump(exclude={'decision_chain'}))
    response=finish_explained(plain,catalog)
    return DecisionChainDecompositionResponse(**response.model_dump(),decision_chain=draft.decision_chain)


def fingerprint(catalog,case):
    files=('src/cpea/application/models/decomposition.py','src/cpea/workflows/task_decomposition/prompt.py',
           'src/cpea/workflows/task_decomposition/validation.py','evaluations/decision_chain_probe.py',
           'evaluations/decision_summary_comparison.py','evaluations/decomposition_grading.py','evaluations/planning_mvp.py')
    return {'source_hashes':{f:sha256(Path(f).read_bytes()).hexdigest() for f in files},
            'schema_sha256':sha256(json.dumps(DecisionChainDecompositionDraft.model_json_schema(),sort_keys=True).encode()).hexdigest(),
            'messages_sha256':sha256(json.dumps([{'role':m.type,'content':m.content} for m in chain_messages(case['request'],catalog)],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'catalog':catalog.fingerprint,'case_sha256':case_sha256(case)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args(argv)
    catalog=SchemaCatalog(Path('projects/retail'))
    case=next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'),catalog) if c['case_id']=='cross-view-11')
    review=json.loads((TASK/'agents/oracle-audit/review-manifest.json').read_text(encoding='utf-8'))
    approved=next(c for c in review['cases'] if c['case_id']==case['case_id'])
    if review['catalog_fingerprint']!=catalog.fingerprint or approved['case_sha256']!=case_sha256(case):raise ValueError('oracle fingerprint mismatch')
    msgs=chain_messages(case['request'],catalog)
    tokens=TiktokenCounter('cl100k_base').count_messages([(m.type,m.content) for m in msgs])
    print(json.dumps({'prompt_version':PROMPT_VERSION,'models':MODELS,'case':case['case_id'],'calls':2,
                      'input_tokens_estimated':tokens,'output_reserve':4096,'safety':1024,'execute':args.execute},ensure_ascii=False),flush=True)
    if tokens+4096+1024>16384:raise ValueError('context budget exceeded before provider construction')
    if not args.execute:return 0
    frozen=fingerprint(catalog,case)
    folder=TASK/'.local'/('decision-chain-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    def dump(name,value):
        p=folder/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');p.chmod(0o600)
    metadata={'models':MODELS,'case_id':case['case_id'],'prompt_version':PROMPT_VERSION,'api':'chat_completions',
              'calls':0,'completed':0,'max_calls':2,'sdk_retries':0,'temperature':1,'top_p':1,'seed':42,
              'timeout_seconds':300,'wall_budget_seconds':900,'context_window':16384,'max_output_tokens':4096,
              'frozen':frozen,'started_at':datetime.now(timezone.utc).isoformat()}
    stopped=None;started=monotonic();dump('run.json',metadata)
    try:
        for model in MODELS:
            if 900-(monotonic()-started)<300:stopped='wall_budget';break
            if fingerprint(catalog,case)!=frozen:raise RuntimeError('frozen source changed')
            settings=replace(azure_planning_settings(Path('.env'),model),max_output_tokens=4096,
                             context_safety_tokens=1024,request_timeout_seconds=300)
            llm=bind_response_schema(get_llm_config(settings=settings),DecisionChainDecompositionDraft).bind(response_format={'type':'json_object'})
            event={'case_id':case['case_id'],'model':model,'messages':[{'role':m.type,'content':m.content} for m in msgs]}
            dump(model+'-request.json',event);metadata['calls']+=1;dump('run.json',metadata);call_start=monotonic()
            try:raw=llm.invoke(msgs)
            except Exception as exc:
                event.update(error_type=type(exc).__name__,error=str(exc),elapsed_seconds=monotonic()-call_start)
                dump(model+'-provider-error.json',event)
                (folder/'provider-error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n',encoding='utf-8');(folder/'provider-error.txt').chmod(0o600)
                stopped='provider_error_no_retry';break
            event.update(response=raw.content,usage=getattr(raw,'usage_metadata',None),response_metadata=getattr(raw,'response_metadata',None),elapsed_seconds=monotonic()-call_start)
            dump(model+'-call.json',event)
            row={'case_id':case['case_id'],'model':model,'decision_chain':None,'response':None,'score':None,'diagnostic':None,'parse_error':None}
            try:
                draft=parse_model(raw,DecisionChainDecompositionDraft);response=finish_chained(draft,catalog)
                row.update(decision_chain=[d.model_dump() for d in draft.decision_chain],response=response.model_dump(),
                           score=grade_decomposition(case,response,catalog),diagnostic=semantic_check(case,response,catalog))
            except (ValueError,TypeError,KeyError) as exc:row['parse_error']=str(exc)
            dump(model+'-result.json',row);metadata['completed']+=1;dump('run.json',metadata)
            print(json.dumps({'model':model,'chain_valid':row['decision_chain'] is not None,
                'status':row['response']['status'] if row['response'] else 'parse_error'},ensure_ascii=False),flush=True)
    finally:
        metadata.update(stopped=stopped,finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=monotonic()-started)
        metadata['artifact_hashes']={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name!='run.json'}
        dump('run.json',metadata)
        print(json.dumps({'output':str(folder),'calls':metadata['calls'],'completed':metadata['completed'],'stopped':stopped},ensure_ascii=False),flush=True)
    return 1 if stopped else 0


if __name__=='__main__':raise SystemExit(main())
