"""Read and validate planning oracles without exposing them to a model."""
from hashlib import sha256
import json
from pathlib import Path


def case_sha256(case):
    content={k:v for k,v in case.items() if k not in {'case_sha256','review_status','reviewer','reviewed_at',
                'reviewed_case_sha256','reviewed_contract_fingerprint'}}
    return sha256(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def load_decomposition_cases(path: Path,catalog) -> list[dict]:
    cases=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not cases or len({c['case_id'] for c in cases})!=len(cases):
        raise ValueError('cases must be nonempty with unique IDs')
    views={v.name for v in catalog.views()}
    for case in cases:
        if case.get('profile_id')!=catalog.profile_id or case.get('contract_fingerprint')!=catalog.fingerprint:
            raise ValueError('case profile/contract fingerprint mismatch')
        if case.get('case_sha256')!=case_sha256(case):
            raise ValueError('case content fingerprint mismatch')
        if not isinstance(case.get('request'),str) or not case['request'].strip():
            raise ValueError('case requires a request')
        tasks=case['expected_tasks']
        if len({t['task_id'] for t in tasks})!=len(tasks):
            raise ValueError('duplicate expected task ID')
        for task in tasks:
            for source in [task,*task.get('acceptable_alternatives',[])]:
                if source['view'] not in views:
                    raise ValueError('expected view is outside catalog')
                fields=set(source['required_columns'])
                used=set(source.get('group_by',[])+source['output_grain']+source.get('attributes',[])+source.get('metadata_collections',[]))
                used.update(source.get('metrics',{}))
                used.update(f['column'] for f in source.get('filters',[]))
                for metric in source.get('conditional_metrics',[]):
                    used.add(metric['column'])
                    used.update(f['column'] for f in metric['conditions'])
                if not used<=fields or not fields<=set(catalog.columns(source['view'])):
                    raise ValueError('expected field is outside source or required columns')
                for column,agg in source.get('metrics',{}).items():
                    if agg not in catalog.field_contract(source['view'],column).get('aggregations',[]):
                        raise ValueError('expected aggregation forbidden')
                for metric in source.get('conditional_metrics',[]):
                    if metric['aggregation'] not in catalog.field_contract(source['view'],metric['column']).get('aggregations',[]):
                        raise ValueError('expected conditional aggregation forbidden')
    return cases


def approved_for(case,catalog):
    return (case.get('review_status')=='approved' and bool(case.get('reviewer')) and bool(case.get('reviewed_at'))
            and case.get('reviewed_case_sha256')==case_sha256(case)
            and case.get('reviewed_contract_fingerprint')==catalog.fingerprint)
