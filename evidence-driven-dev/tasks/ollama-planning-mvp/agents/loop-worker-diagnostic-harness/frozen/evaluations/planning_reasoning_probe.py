"""One Responses API attempt per previously failed B1 case; preserve summaries."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.planning_mvp import SemanticPlan, compile_plan, finish, semantic_check
from evaluations.planning_mvp_runner import TASK, messages, freeze


MODEL = 'gpt-6-sol'


def failure_ids(review):
    return list(dict.fromkeys(r['case_id'] for r in review['reviews']
        if r['arm'] == 'B1' and not r['first_pass_semantically_safe_ready']))


def capture_response(raw):
    summaries, texts = [], []
    for item in raw.get('output') or []:
        if item.get('type') == 'reasoning':
            summaries.extend(s['text'] for s in item.get('summary') or []
                             if s.get('type') == 'summary_text' and s.get('text'))
        elif item.get('type') == 'message':
            texts.extend(s['text'] for s in item.get('content') or [] if s.get('type') == 'output_text')
    usage = raw.get('usage') or {}
    return {'output_text':''.join(texts), 'reasoning_summary':summaries,
            'reasoning_summary_status':'available' if summaries else 'not_returned',
            'reasoning_tokens':(usage.get('output_tokens_details') or {}).get('reasoning_tokens'),
            'usage':usage, 'api_status':raw.get('status'), 'response_id':raw.get('id')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args(argv)
    read = lambda p:json.loads(p.read_text(encoding='utf-8'))
    catalog = SchemaCatalog(Path('projects/retail'))
    review_path = TASK/'agents/oracle-audit/mvp1-semantic-review.json'
    review = read(review_path)
    selected = failure_ids(review)
    cases_by_id = {c['case_id']:c for c in load_decomposition_cases(
        Path('projects/retail/evaluations/task_decomposition_cases.jsonl'),catalog)}
    cases = [cases_by_id[cid] for cid in selected]
    approved = {c['case_id']:c for c in read(TASK/'agents/oracle-audit/review-manifest.json')['cases']}
    for c in cases:
        if case_sha256(c) != approved[c['case_id']]['case_sha256']:
            raise ValueError('case independent approval mismatch')
    # Reuse the original candidate exactly, including its known limitations.
    expected = review['run']['fingerprints']
    frozen = freeze(catalog,cases)
    for key in ('version','catalog','source_hashes','schema_sha256','prompt_sha256'):
        if frozen[key] != expected[key]:
            raise ValueError('B1 frozen version mismatch: ' + key)
    print(json.dumps({'model':MODEL,'cases':selected,'max_attempts':len(cases),
        'reasoning':{'effort':'medium','summary':'auto'},'execute':args.execute},ensure_ascii=False),flush=True)
    if not args.execute:
        return 0
    from openai import OpenAI
    settings = azure_planning_settings(Path('.env'),MODEL)
    client = OpenAI(base_url=settings.llm_base_url,api_key=settings.llm_api_key,max_retries=0,timeout=300)
    folder = TASK/'.local'/('gpt-sol-b1-failures-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    def dump(name,value):
        path = folder/name
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        path.chmod(0o600)
    metadata = {'model':MODEL,'provider':'azure','api':'responses','cases':selected,'sdk_retries':0,
        'max_attempts':len(cases),'attempts':0,'completed':0,'reasoning':{'effort':'medium','summary':'auto'},
        'max_output_tokens':7168,'temperature':'omitted','top_p':'omitted','seed':'Responses API has no seed parameter',
        'store':False,'timeout_seconds':300,'wall_budget_seconds':1200,'frozen':frozen,
        'review_source_sha256':sha256(review_path.read_bytes()).hexdigest(),
        'probe_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'started_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Diagnostic comparison only; does not replace DeepSeek Gate or enable Ollama.'}
    dump('run.json',metadata)
    started = monotonic(); stopped = None
    try:
        for case in cases:
            if 1200-(monotonic()-started)<300:
                stopped = 'wall_budget'; break
            if freeze(catalog,cases) != frozen:
                raise RuntimeError('frozen source changed')
            msgs = messages(case,catalog)
            body = {'model':MODEL,'input':[{'role':'system' if m.type=='system' else 'user','content':m.content} for m in msgs],
                    'reasoning':metadata['reasoning'],'max_output_tokens':7168,'store':False,
                    'text':{'format':{'type':'json_object'}},'truncation':'disabled'}
            dump(case['case_id']+'-request.json',body)
            metadata['attempts'] += 1; dump('run.json',metadata)
            call_start = monotonic()
            try:
                raw = client.responses.create(**body)
            except Exception as exc:
                error = {'case_id':case['case_id'],'type':type(exc).__name__,'message':str(exc),
                         'http_status':getattr(exc,'status_code',None),'elapsed_seconds':monotonic()-call_start}
                dump('provider-error.json',error)
                (folder/'provider-error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n',encoding='utf-8')
                (folder/'provider-error.txt').chmod(0o600)
                stopped = 'provider_error_no_retry'
                print(json.dumps({'case_id':case['case_id'],'status':'provider_error','type':type(exc).__name__,
                    'http_status':getattr(exc,'status_code',None),'output':str(folder)},ensure_ascii=False),flush=True)
                break
            raw_dict = raw.model_dump(mode='json')
            dump(case['case_id']+'-raw.json',raw_dict)
            captured = capture_response(raw_dict)
            dump(case['case_id']+'-reasoning.json',{
                'kind':'provider_reasoning_summary','summary':captured['reasoning_summary'],
                'status':captured['reasoning_summary_status'],'reasoning_tokens':captured['reasoning_tokens'],
                'raw_chain_of_thought_available':False,'response_id':captured['response_id']})
            row = {'case_id':case['case_id'],'model':MODEL,'elapsed_seconds':monotonic()-call_start,
                   **captured,'semantic_plan':None,'response':None,'original_score':None,
                   'diagnostic':None,'compile_error':None}
            try:
                if captured['api_status'] != 'completed':
                    raise ValueError('incomplete API output')
                plan = parse_model(SimpleNamespace(content=captured['output_text']),SemanticPlan)
                row['semantic_plan'] = plan.model_dump()
                response = finish(compile_plan(plan,catalog),catalog,guard=True)
                row.update(response=response.model_dump(),original_score=grade_decomposition(case,response,catalog),
                           diagnostic=semantic_check(case,response,catalog))
            except (ValueError,TypeError,KeyError) as exc:
                row['compile_error'] = str(exc)
            dump(case['case_id']+'-result.json',row)
            with (folder/'results.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            (folder/'results.jsonl').chmod(0o600)
            metadata['completed'] += 1;dump('run.json',metadata)
            print(json.dumps({'case_id':case['case_id'],'status':row['response']['status'] if row['response'] else 'error',
                'reasoning_summary':captured['reasoning_summary_status'],'reasoning_tokens':captured['reasoning_tokens'],
                'diagnostic':row['diagnostic']},ensure_ascii=False),flush=True)
    finally:
        metadata.update(stopped=stopped,finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=monotonic()-started)
        metadata['artifact_hashes'] = {p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name!='run.json'}
        dump('run.json',metadata)
        client.close()
        print(json.dumps({'output':str(folder),'attempts':metadata['attempts'],'completed':metadata['completed'],
                          'stopped':stopped},ensure_ascii=False),flush=True)
    return 1 if stopped else 0


if __name__ == '__main__':
    raise SystemExit(main())
