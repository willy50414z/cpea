"""Replay every saved prompt trial on the restored product; no LLM or SQL calls."""
import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path.cwd()))
from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT_VERSION, DECOMPOSITION_PROMPT
from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
rows=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
assert not subprocess.check_output(['git','diff','HEAD','--binary'])
assert DECOMPOSITION_PROMPT_VERSION=='v3'
catalog=SchemaCatalog(Path('projects/retail'))
casefile=Path('projects/retail/evaluations/task_decomposition_cases.jsonl')
cases={c['case_id']:c for c in load_decomposition_cases(casefile,catalog)}
prompts={'v3_raw':DECOMPOSITION_PROMPT}
for version,arm in [('v4','v4_resolved'),('v5','v5_resolved'),('v6','v6_raw')]:
    source=(ROOT/'.local'/f'prompt-{version}-snapshot.py').read_text(encoding='utf-8')
    prompts[arm]=next(ast.literal_eval(n.value) for n in ast.parse(source).body
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DECOMPOSITION_PROMPT' for t in n.targets))
folders=[('v4','prompt-v4-20261020T112256Z',16),('v5','prompt-v5-20261020T112607Z',60),
         ('v6','prompt-v6-20261020T113508Z',60)]
out={'result':'PASS','product_restored_to':'v3','source_diff_empty':True,'replayed_calls':0,'rounds':{}}
for version,dirname,count in folders:
    folder=ROOT/'.local'/dirname
    meta=read(folder/'run.json');rr,cc=rows(folder/'results.jsonl'),rows(folder/'calls.jsonl')
    assert len(rr)==len(cc)==count and meta['model']=='DeepSeek-V4.1-Flash' and meta['provider']=='azure'
    assert meta['contract_fingerprint']==catalog.fingerprint
    assert meta['casefile_sha256']==sha256(casefile.read_bytes()).hexdigest()
    assert meta['harness_sha256']==sha256((ROOT/'.local'/f'compare_prompt_{version}.py').read_bytes()).hexdigest()
    if version!='v4':
        assert meta['finished_at'] and meta['harness_unchanged']
        assert meta['diff_sha256']==sha256((ROOT/'.local'/f'prompt-{version}.patch').read_bytes()).hexdigest()
    else:
        assert read(folder/'interruption.json')['not_a_completed_benchmark']
    events={(c['case_id'],c['arm']):c for c in cc}
    for row in rr:
        assert row['status']=='completed'
        event=events[(row['case_id'],row['arm'])]
        assert 'error' not in event and len(event['messages'])==2
        assert event['messages'][0]=={'role':'system','content':prompts[row['arm']]}
        context=json.loads(event['messages'][1]['content'])
        views=[{'view':v.name,**v.policy} for v in catalog.views()]
        if row['arm'].endswith('_resolved'):
            views=[{**v.policy,'view':v.name,'columns':{column:catalog.field_contract(v.name,column)
                for column in catalog.columns(v.name)}} for v in catalog.views()]
        assert context=={'request':cases[row['case_id']]['request'],'views':views,
                         'response_schema':DecompositionDraft.model_json_schema()}
        response=DecompositionResponse.model_validate(row['response'])
        errors=[];payloads=[];code=None
        try:draft=parse_model(SimpleNamespace(content=event['response']),DecompositionDraft)
        except (ValueError,TypeError):draft=None;status='error';code='invalid_model_response'
        else:
            status=draft.status
            if status=='ready':
                errors=validate_decomposition(draft,catalog)
                if errors:status='error';code='invalid_plan'
                else:
                    try:payloads=prepare_requests(draft,catalog)
                    except ValueError:status='error';code='invalid_prepared_request'
        assert response.draft==draft
        assert (response.status,response.code,response.validation_errors,response.prepared_requests)==(status,code,errors,payloads)
        assert grade_decomposition(cases[row['case_id']],response,catalog)==row['score']
    if version=='v6':
        assert all(events[(cid,'v3_raw')]['messages'][1]==events[(cid,'v6_raw')]['messages'][1] for cid in cases)
    out['replayed_calls']+=count
    out['rounds'][version]={'replayed':count,'partial':version=='v4',
        'hashes':{name:sha256((folder/name).read_bytes()).hexdigest() for name in ('run.json','calls.jsonl','results.jsonl')}}
decision=read(ROOT/'reports/prompt-view-matching-decision.json')
a,b=(decision['summary'][arm] for arm in ('v3_raw','v6_raw'))
assert (a['views_and_columns'],a['ready'],a['automated_pass'])==(25,18,15)
assert (b['views_and_columns'],b['ready'],b['automated_pass'])==(26,16,16)
assert decision['adopt'] is False and out['replayed_calls']==136
assert not subprocess.check_output(['git','diff','HEAD','--binary'])
for path in (ROOT/'reports').glob('*'):
    if path.suffix in ('.md','.json','.py'):
        assert not path.read_bytes().startswith(b'\xef\xbb\xbf')
        path.read_text(encoding='utf-8')
out['report_sha256']=sha256((ROOT/'reports/prompt-view-matching-results.md').read_bytes()).hexdigest()
(ROOT/'reports/prompt-final-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
