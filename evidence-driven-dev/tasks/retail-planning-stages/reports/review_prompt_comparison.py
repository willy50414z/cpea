"""Offline diagnostics for prompt comparisons; never changes raw grades."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from pydantic import ValidationError
from cpea.application.models.decomposition import DecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
rows=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]


def review(folder, partial):
    meta=read(folder/'run.json');results,calls=rows(folder/'results.jsonl'),rows(folder/'calls.jsonl')
    events={(c['case_id'],c['arm']):c for c in calls}
    assert len(events)==len(calls)==len(results)
    catalog=SchemaCatalog(Path('projects/retail'))
    arms=sorted({r['arm'] for r in results})
    output={'run':str(folder),'partial':partial,'arms':{},'diagnostics':[]}
    for arm in arms:
        selected=[r for r in results if r['arm']==arm]
        errors=Counter()
        top_unbound=[]
        extra_fields=[]
        required_only=[]
        scalar_risks=[]
        statuses=Counter()
        for r in selected:
            statuses[(r['response']['status'],r['response']['code'])]+=1
            event=events[(r['case_id'],arm)]
            try:
                draft=DecompositionDraft.model_validate_json(event['response'])
            except ValidationError as exc:
                for e in exc.errors(include_input=False,include_url=False):
                    errors['parse:'+e['type']]+=1
                    if e['type']=='extra_forbidden':
                        extra_fields.append({'case_id':r['case_id'],'location':list(e['loc'])})
                        if e['loc']==('unbound_inputs',):top_unbound.append(r['case_id'])
                continue
            for error in r['response']['validation_errors']:
                errors[error.split(': ',1)[-1]]+=1
            for task in draft.tasks:
                roles=set(task.attributes+task.group_by+task.output_grain+task.metadata_collections)|set(task.metrics)
                roles.update(m.column for m in task.conditional_metrics)
                condition_fields={f.column for f in task.filters}|{f.column for m in task.conditional_metrics for f in m.conditions}
                unused=set(task.required_columns)-roles-condition_fields
                if unused:required_only.append({'case_id':r['case_id'],'task_id':task.task_id,'columns':sorted(unused)})
                definition=next((v for v in catalog.views() if v.name==task.view),None)
                if definition:
                    keys=set(definition.policy.get('grain',{}).get('keys') or [])
                    fixed={f.column for f in task.filters if f.operator=='='}
                    for lower in task.filters:
                        if lower.operator=='>=' and any(upper.column==lower.column and upper.operator=='<='
                            and upper.value==lower.value for upper in task.filters):fixed.add(lower.column)
                    unique=bool(keys) and keys-fixed<=set(task.output_grain)
                    aggregated=bool(task.metrics or task.conditional_metrics or task.metadata_collections or task.group_by)
                    if aggregated and not unique and set(task.attributes)-set(task.group_by):
                        scalar_risks.append({'case_id':r['case_id'],'task_id':task.task_id,
                            'columns':sorted(set(task.attributes)-set(task.group_by))})
            if not r['score']['automated_pass']:
                output['diagnostics'].append({'case_id':r['case_id'],'arm':arm,'status':r['response']['status'],
                    'code':r['response']['code'],'errors':r['response']['validation_errors'],
                    'clarifications':draft.clarifications,'task_scores':r['score']['task_scores']})
        output['arms'][arm]={'completed':len(selected),'status_counts':{f'{s}/{c}':n for (s,c),n in statuses.items()},
            'error_occurrences':dict(errors),'top_level_unbound_inputs_cases':sorted(set(top_unbound)),
            'extra_field_locations':extra_fields,'required_columns_without_explicit_role':required_only,
            'aggregate_scalar_without_key_proof':scalar_risks}
    output['hashes']={name:sha256((folder/name).read_bytes()).hexdigest() for name in ('calls.jsonl','results.jsonl','run.json')}
    suffix=('prompt-v4-partial-review.json' if partial else
            'prompt-v6-review.json' if 'v6_raw' in arms else 'prompt-v5-review.json')
    (ROOT/'reports'/suffix).write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--partial',action='store_true')
    a=p.parse_args();review(a.run,a.partial)
