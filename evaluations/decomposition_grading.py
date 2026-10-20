"""Order-independent structural grading, with semantic review kept explicit."""
from datetime import date
from itertools import permutations
import json


def _filters(filters):
    normalized=[]
    for item in filters:
        item=item.model_dump() if hasattr(item,'model_dump') else item
        col,op,val=item['column'],item['operator'],item.get('value')
        if col.endswith('_month') and op=='=' and isinstance(val,str):
            try:
                d=date.fromisoformat(val)
                if d.day==1:
                    axis=col[:-6]+'_period'
                    end=date(d.year+1,1,1) if d.month==12 else date(d.year,d.month+1,1)
                    normalized.extend([(axis,'>=',json.dumps(val)),(axis,'<',json.dumps(end.isoformat()))]);continue
            except ValueError:pass
        if col.endswith('_date') and op in ('>=','<'):
            col=col[:-5]+'_period'
        if op in ('IN','NOT IN') and isinstance(val,list):val=sorted(val,key=str)
        normalized.append((col,op,json.dumps(val,ensure_ascii=False,sort_keys=True)))
    return set(normalized)


def _task_score(expected,actual):
    fields=set(actual.required_columns);required=set(expected['required_columns'])
    conditions=[m.model_dump() for m in actual.conditional_metrics]
    expected_conditions=expected.get('conditional_metrics',[])
    actual_metrics=dict(actual.metrics)
    def grain(columns,filters):
        fixed={f['column'] for f in filters if f['operator']=='='}
        return set(columns)-fixed
    return {'view':expected['view']==actual.view,'columns':required<=fields,
            'column_recall':len(required&fields)/len(required) if required else 1.0,
            'column_precision':len(required&fields)/len(fields) if fields else 0.0,
            'filters':_filters(expected.get('filters',[]))==_filters(actual.filters),
            'metrics':all(actual_metrics.get(c)==a for c,a in expected.get('metrics',{}).items()),
            'conditional_metrics':all(any(e['column']==a['column'] and e['aggregation']==a['aggregation']
                 and _filters(e['conditions'])==_filters(a['conditions']) for a in conditions) for e in expected_conditions),
            'grain':grain(expected['output_grain'],expected.get('filters',[]))==grain(actual.output_grain,[f.model_dump() for f in actual.filters])}


def grade_decomposition(case,response,catalog) -> dict:
    from cpea.workflows.task_decomposition.validation import validate_decomposition
    draft=response.draft
    result={'status_match':response.status==case['expected_status'],'canonical_views_match':False,
            'equivalent_tasks_match':False,'payload_ready':False,'integration_keys_match':False,
            'automated_pass':False,'semantic_review_required':True,'task_scores':[]}
    if response.status!='ready' or draft is None:
        return result
    expected=case['expected_tasks'];actual=draft.tasks
    result['canonical_views_match']=sorted(t['view'] for t in expected)==sorted(t.view for t in actual)
    if len(expected)!=len(actual) or len(actual)>8:return result
    best=None
    checks=('view','columns','filters','metrics','conditional_metrics','grain')
    for ordering in permutations(actual):
        scores=[]
        for task,match in zip(expected,ordering):
            variants=[task,*task.get('acceptable_alternatives',[])]
            options=[_task_score(v,match) for v in variants]
            scores.append(max(options,key=lambda s:(sum(bool(s[k]) for k in checks),s['column_recall'])))
        merit=sum(sum(bool(s[k]) for k in checks) for s in scores)
        if best is None or merit>best[0]:best=(merit,ordering,scores)
    _,ordering,scores=best
    result['task_scores']=scores
    result['equivalent_tasks_match']=all(all(s[k] for k in checks) for s in scores)
    integration=draft.integration;oracle=case['expected_integration']
    matched={e['task_id']:a for e,a in zip(expected,ordering)}
    anchor=matched.get(oracle['anchor_task'])
    keys=set(oracle['keys'])
    if integration and anchor:
        edges=integration.edges
        # The product-fact keys apply to product facts only; store context has its own edge.
        expected_by_actual={a.task_id:e for e,a in zip(expected,ordering)}
        keys_ok=len(edges)==len(actual)-1
        for edge in edges:
            left=expected_by_actual.get(edge.left_task);right=expected_by_actual.get(edge.right_task)
            if not left or not right:
                keys_ok=False;continue
            pair_keys=set(left['output_grain']) & set(right['output_grain']) & keys
            if not pair_keys or set(edge.left_keys)!=pair_keys or set(edge.right_keys)!=pair_keys:
                keys_ok=False
        fixed={f['column'] for f in next(e for e in expected if e['task_id']==oracle['anchor_task']).get('filters',[]) if f['operator']=='='}
        output_ok=set(integration.output_grain)-fixed==set(anchor.output_grain)-fixed
        result['integration_keys_match']=bool(keys_ok and integration.anchor_task==anchor.task_id
                    and output_ok and all(e.mode==oracle['mode'] for e in edges) and not validate_decomposition(draft,catalog))
    payloads=response.prepared_requests
    result['payload_ready']=(len(payloads)==len(actual) and {p.task_id for p in payloads}=={a.task_id for a in actual}
                              and all(set(p.payload)=={'request','history'} and p.payload['history']==[] and p.payload['request'].strip() for p in payloads))
    result['strategy_match']=draft.strategy==case['expected_strategy']
    result['automated_pass']=all(result[k] for k in ('status_match','strategy_match','equivalent_tasks_match','integration_keys_match','payload_ready'))
    return result
