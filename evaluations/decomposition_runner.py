"""Benchmark only the planning boundary against one Azure deployment."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from urllib.parse import urlparse

from dotenv import dotenv_values
from cpea.application.models.decomposition import DecompositionDraft
from cpea.application.services.task_decomposition import TaskDecompositionService
from cpea.config.database import SQLServerSettings
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.factory import get_llm_config
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT, DECOMPOSITION_PROMPT_VERSION
from evaluations.call_budget import provider_stop_reason
from evaluations.decomposition_cases import load_decomposition_cases, approved_for
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_reports import summarize, write_reports


def azure_planning_settings(env_file: Path,model: str) -> AssistantSettings:
    values=dotenv_values(env_file,encoding='utf-8',interpolate=False)
    def value(key):return os.environ.get(key) or values.get(key)
    endpoint=value('CPEA_AZURE_LLM_BASE_URL')
    key=value('CPEA_AZURE_LLM_API_KEY')
    if not endpoint or not key or not model.strip():
        raise ValueError('Azure planning requires endpoint, key and explicit deployment')
    parsed=urlparse(endpoint)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Azure endpoint must be an absolute URL without credentials or query')
    endpoint=endpoint.rstrip('/')
    if parsed.path.strip('/') not in ('','openai/v1'):
        raise ValueError('Azure planning supports a resource root or /openai/v1 endpoint')
    if not endpoint.endswith('/openai/v1'):endpoint+='/openai/v1'
    base=AssistantSettings.from_env(env_file)
    return replace(base,llm_provider='azure',llm_base_url=endpoint,llm_api_key=key,llm_model=model,
                   temperature=1.0,top_p=1.0,sqlserver=SQLServerSettings(),integration_path=None,
                   deployment_file=None,token_count_endpoint=None,datasource_id='retail')


def _json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def evaluate_decomposition(*,profile: Path,env_file: Path,model: str,cases_path: Path,
                           runs: int=1,exploratory: bool=False,llm_factory=None) -> dict:
    if runs<1:raise ValueError('runs must be positive')
    catalog=SchemaCatalog(profile)
    cases=load_decomposition_cases(cases_path,catalog)
    cases=[c for c in cases if c.get('review_status')!='rejected' and (exploratory or approved_for(c,catalog))]
    if not cases:raise ValueError('no approved cases; pending cases require --exploratory')
    settings=azure_planning_settings(env_file,model)
    repo=Path(__file__).resolve().parents[1]
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()
    diff=subprocess.run(['git','diff','HEAD','--binary'],cwd=repo,capture_output=True,check=True).stdout
    created=datetime.now(timezone.utc)
    output=profile.resolve()/'artifacts/task_decomposition'/f"{created.strftime('%Y%m%dT%H%M%S%fZ')}-{revision[:8]}-{uuid4().hex[:6]}"
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    metadata={'project':'retail','model':model,'provider':'azure','runs':runs,'planned':len(cases)*runs,
              'max_model_calls':None,'exploratory':exploratory,'started_at':created.isoformat(),
              'revision':revision,'diff_sha256':sha256(diff).hexdigest(),
              'contract_fingerprint':catalog.fingerprint,'casefile_sha256':sha256(cases_path.read_bytes()).hexdigest(),
              'prompt_version':DECOMPOSITION_PROMPT_VERSION,'prompt_sha256':sha256(DECOMPOSITION_PROMPT.encode('utf-8')).hexdigest(),
              'schema_sha256':sha256(json.dumps(DecompositionDraft.model_json_schema(),sort_keys=True).encode('utf-8')).hexdigest(),
              'context_window':settings.context_window,'max_output_tokens':settings.max_output_tokens,
              'context_safety_tokens':settings.context_safety_tokens,'timeout_seconds':settings.request_timeout_seconds,
              'temperature':settings.temperature,'top_p':settings.top_p,'seed':settings.seed,
              'sdk_retries':0,'model_calls':0}
    _json(output/'run.json',metadata)
    llm=(llm_factory or get_llm_config)(settings=settings) if llm_factory is None else llm_factory(settings)
    events=[]
    service=TaskDecompositionService(llm,catalog,settings=settings,observer=events.append)
    results=[];stopped=None
    # Private streams intentionally contain raw model inputs/outputs; summaries do not.
    with (output/'calls.jsonl').open('x',encoding='utf-8') as calls, (output/'results.jsonl').open('x',encoding='utf-8') as rows:
        os.chmod(output/'calls.jsonl',0o600)
        for run in range(runs):
            for case in cases:
                entry={'case_id':case['case_id'],'run':run}
                if stopped:
                    entry.update(status='skipped',reason=stopped)
                else:
                    events.clear()
                    response=service.plan(case['request'])
                    for event in events:
                        metadata['model_calls']+=1
                        calls.write(json.dumps({**entry,**event},ensure_ascii=False)+'\n');calls.flush()
                        if 'error' in event:
                            stopped=provider_stop_reason(RuntimeError(event['error'])) or 'provider_error'
                            private=output/'provider-error.txt'
                            private.write_text(event['error_type']+': '+event['error']+'\n',encoding='utf-8')
                            os.chmod(private,0o600)
                    if stopped:
                        entry.update(status='failed',reason=stopped,response=response.model_dump())
                    else:
                        entry.update(status='completed',response=response.model_dump(),
                                     score=grade_decomposition(case,response,catalog))
                results.append(entry)
                rows.write(json.dumps(entry,ensure_ascii=False)+'\n');rows.flush()
                # Persist progress after every case so interrupted runs retain real counts.
                metadata.update(summarize(results,planned=len(cases)*runs,runs=runs))
                _json(output/'run.json',metadata)
                print(json.dumps({'case_id':entry['case_id'],'run':run+1,'status':entry['status'],
                                  'pass':entry.get('score',{}).get('automated_pass'),
                                  'model_calls':metadata['model_calls']},ensure_ascii=False),flush=True)
    metadata['finished_at']=datetime.now(timezone.utc).isoformat()
    _json(output/'run.json',metadata)
    write_reports(output,cases,results,metadata)
    return {'output':str(output),'model_calls':metadata['model_calls'],**summarize(results,planned=len(cases)*runs,runs=runs)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',choices=['retail'],required=True)
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    parser.add_argument('--model',required=True)
    parser.add_argument('--runs',type=int,default=1)
    parser.add_argument('--exploratory',action='store_true')
    args=parser.parse_args(argv)
    profile=Path('projects')/args.project
    try:
        result=evaluate_decomposition(profile=profile,env_file=args.env_file,model=args.model,
                                      cases_path=profile/'evaluations/task_decomposition_cases.jsonl',
                                      runs=args.runs,exploratory=args.exploratory)
    except (ValueError,FileNotFoundError) as exc:parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['failed'] or result['skipped'] else 0


if __name__=='__main__':raise SystemExit(main())
