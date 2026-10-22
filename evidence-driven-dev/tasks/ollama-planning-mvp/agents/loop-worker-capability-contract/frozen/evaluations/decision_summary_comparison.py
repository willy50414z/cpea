"""Compare explicit decision summaries using the same v3 planning inputs."""
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
    DecompositionDraft, ExplainedDecompositionDraft, ExplainedDecompositionResponse,
)
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.factory import get_llm_config, bind_response_schema
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT
from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.planning_mvp import finish, semantic_check


TASK = Path('evidence-driven-dev/tasks/ollama-planning-mvp')
MODELS = ('gpt-6-sol','DeepSeek-V4.1-Flash')
CASES = ('cross-view-11','cross-view-14','cross-view-26')
PROMPT_VERSION = 'v3-decision-summary-1'
SUMMARY_INSTRUCTION = '''\n本次使用診斷schema，必填decision_summary。其六欄source_selection、field_roles、conditions、grain、population、integration各用一至兩句繁體中文，簡短記錄最終決策及可由需求或View契約核對的依據。只提供決策摘要，不提供逐步內部思維鏈。說明須與tasks/integration一致；若不支援或需澄清，摘要須指出實際契約缺口。摘要不代替typed欄位：所有條件、粒度、度量與整合仍須在對應結構完整表達。'''


def decision_messages(request, catalog):
    return [SystemMessage(content=DECOMPOSITION_PROMPT+SUMMARY_INSTRUCTION),
            HumanMessage(content=json.dumps({'request':request,
                'views':[{'view':v.name,**v.policy} for v in catalog.views()],
                'response_schema':ExplainedDecompositionDraft.model_json_schema()},ensure_ascii=False))]


def finish_explained(draft, catalog):
    # The explanation is retained as data and never interpreted as an instruction.
    plain = DecompositionDraft.model_validate(draft.model_dump(exclude={'decision_summary'}))
    response = finish(plain,catalog)
    return ExplainedDecompositionResponse(**response.model_dump(),decision_summary=draft.decision_summary)


def fingerprint(catalog,cases):
    files = ('src/cpea/application/models/decomposition.py','src/cpea/workflows/task_decomposition/prompt.py',
             'src/cpea/workflows/task_decomposition/validation.py','evaluations/decision_summary_comparison.py',
             'evaluations/decomposition_grading.py','evaluations/planning_mvp.py')
    return {'source_hashes':{name:sha256(Path(name).read_bytes()).hexdigest() for name in files},
            'schema_sha256':sha256(json.dumps(ExplainedDecompositionDraft.model_json_schema(),sort_keys=True).encode()).hexdigest(),
            'prompt_sha256':sha256((DECOMPOSITION_PROMPT+SUMMARY_INSTRUCTION).encode()).hexdigest(),
            'catalog':catalog.fingerprint,'cases':{c['case_id']:case_sha256(c) for c in cases}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    catalog=SchemaCatalog(Path('projects/retail'))
    all_cases=load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'),catalog)
    cases=[next(c for c in all_cases if c['case_id']==cid) for cid in CASES]
    review=json.loads((TASK/'agents/oracle-audit/review-manifest.json').read_text(encoding='utf-8'))
    approved={c['case_id']:c for c in review['cases']}
    if review['catalog_fingerprint']!=catalog.fingerprint or any(case_sha256(c)!=approved[c['case_id']]['case_sha256'] for c in cases):
        raise ValueError('independent case approval mismatch')
    frozen=fingerprint(catalog,cases)
    counter=TiktokenCounter('cl100k_base')
    tokens={c['case_id']:counter.count_messages([(m.type,m.content) for m in decision_messages(c['request'],catalog)]) for c in cases}
    print(json.dumps({'models':MODELS,'cases':CASES,'calls':6,'prompt_version':PROMPT_VERSION,
                      'input_tokens_estimated':tokens,'output_limit':4096,'safety':1024,'execute':args.execute},ensure_ascii=False),flush=True)
    if max(tokens.values())+4096+1024>16384:
        raise ValueError('context budget exceeded before provider construction')
    if not args.execute:return 0
    folder=TASK/'.local'/('decision-summary-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    def dump(name,value):
        p=folder/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');p.chmod(0o600)
    metadata={'models':MODELS,'cases':CASES,'prompt_version':PROMPT_VERSION,'api':'chat_completions','provider':'azure',
              'calls_limit':6,'calls':0,'completed':0,'sdk_retries':0,'temperature':1,'top_p':1,'seed':42,
              'max_output_tokens':4096,'context_window':16384,'safety':1024,'timeout_seconds':300,
              'wall_budget_seconds':1200,'estimated_input_tokens':tokens,'frozen':frozen,
              'started_at':datetime.now(timezone.utc).isoformat()}
    settings={m:replace(azure_planning_settings(Path('.env'),m),max_output_tokens=4096,
                        context_safety_tokens=1024,request_timeout_seconds=300) for m in MODELS}
    clients={m:bind_response_schema(get_llm_config(settings=settings[m]),ExplainedDecompositionDraft).bind(
                response_format={'type':'json_object'}) for m in MODELS}
    started=monotonic();stopped=None;dump('run.json',metadata)
    try:
        for index,case in enumerate(cases):
            order=MODELS if index%2==0 else MODELS[::-1]
            for model in order:
                if 1200-(monotonic()-started)<300:
                    stopped='wall_budget';break
                if fingerprint(catalog,cases)!=frozen:raise RuntimeError('frozen source changed')
                msgs=decision_messages(case['request'],catalog)
                event={'case_id':case['case_id'],'model':model,
                       'messages':[{'role':m.type,'content':m.content} for m in msgs]}
                name=case['case_id']+'-'+model
                dump(name+'-request.json',event)
                metadata['calls']+=1;dump('run.json',metadata);call_start=monotonic()
                try:raw=clients[model].invoke(msgs)
                except Exception as exc:
                    event.update(error_type=type(exc).__name__,error=str(exc),elapsed_seconds=monotonic()-call_start)
                    dump(name+'-provider-error.json',event)
                    (folder/'provider-error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n',encoding='utf-8')
                    (folder/'provider-error.txt').chmod(0o600)
                    stopped='provider_error_no_retry';break
                event.update(response=raw.content,usage=getattr(raw,'usage_metadata',None),
                             response_metadata=getattr(raw,'response_metadata',None),elapsed_seconds=monotonic()-call_start)
                dump(name+'-call.json',event)
                row={'case_id':case['case_id'],'model':model,'decision_summary':None,'response':None,
                     'score':None,'diagnostic':None,'parse_error':None}
                try:
                    draft=parse_model(raw,ExplainedDecompositionDraft)
                    response=finish_explained(draft,catalog)
                    row.update(decision_summary=draft.decision_summary.model_dump(),response=response.model_dump(),
                               score=grade_decomposition(case,response,catalog),diagnostic=semantic_check(case,response,catalog))
                except (ValueError,TypeError,KeyError) as exc:row['parse_error']=str(exc)
                dump(name+'-result.json',row)
                with (folder/'results.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                (folder/'results.jsonl').chmod(0o600)
                metadata['completed']+=1;dump('run.json',metadata)
                print(json.dumps({'case_id':case['case_id'],'model':model,'summary_present':row['decision_summary'] is not None,
                                  'status':row['response']['status'] if row['response'] else 'parse_error',
                                  'diagnostic':row['diagnostic']},ensure_ascii=False),flush=True)
            if stopped:break
    finally:
        metadata.update(stopped=stopped,finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=monotonic()-started)
        metadata['artifact_hashes']={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name!='run.json'}
        dump('run.json',metadata)
        print(json.dumps({'output':str(folder),'calls':metadata['calls'],'completed':metadata['completed'],'stopped':stopped},ensure_ascii=False),flush=True)
    return 1 if stopped else 0


if __name__=='__main__':raise SystemExit(main())
