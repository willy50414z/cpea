"""Order-independent structural grading, with semantic review kept explicit."""
from datetime import date, timedelta
from itertools import permutations
import json


def _filters(filters):
    normalized=[]
    for item in filters:
        item=item.model_dump() if hasattr(item,'model_dump') else item
        col,op,val=item['column'],item['operator'],item.get('value')
        if col.endswith('_date') and op in ('<=','>') and isinstance(val,str):
            try:val=(date.fromisoformat(val)+timedelta(days=1)).isoformat();op='<' if op=='<=' else '>='
            except ValueError:pass
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


def _task_score(expected,actual,catalog):
    fields=set(actual.required_columns);required=set(expected['required_columns'])
    filters_match=_filters(expected.get('filters',[]))==_filters(actual.filters)
    if filters_match:
        filter_only={f['column'] for f in expected.get('filters',[])}-set(expected.get('group_by',[])+expected['output_grain']+expected.get('attributes',[]))-set(expected.get('metrics',{}))
        actual_filter_columns={f.column for f in actual.filters}
        def axis(column):
            return column[:-5] if column.endswith('_date') else column[:-6] if column.endswith('_month') else None
        for missing in (required-fields)&filter_only:
            if axis(missing) and any(axis(missing)==axis(c) for c in actual_filter_columns):
                required.remove(missing)
    conditions=[m.model_dump() for m in actual.conditional_metrics]
    expected_conditions=expected.get('conditional_metrics',[])
    actual_metrics=dict(actual.metrics)
    definition=next((v for v in catalog.views() if v.name==actual.view),None)
    source_grain=definition.policy.get('grain',{}) if definition else {}
    source_keys=set(source_grain.get('keys') or []) if isinstance(source_grain,dict) else set()
    fixed={f.column for f in actual.filters if f.operator=='='}
    singleton=bool(source_keys) and (source_keys-fixed)<=set(actual.output_grain)
    if singleton and not actual.metrics and not actual.conditional_metrics and not actual.group_by:
        for column,aggregation in expected.get('metrics',{}).items():
            if aggregation in ('sum','min','max','avg') and column in actual.attributes:
                actual_metrics[column]=aggregation
    def equivalent_aggregation(column,expected_aggregation,actual_aggregation):
        if expected_aggregation==actual_aggregation:return True
        return ({expected_aggregation,actual_aggregation}=={'count','count_distinct'}
                and bool(source_keys) and source_keys<=(set(actual.group_by)|fixed|{column}))
    def grain(columns,filters):
        fixed={f['column'] for f in filters if f['operator']=='='}
        return set(columns)-fixed
    expected_grain=grain(expected['output_grain'],expected.get('filters',[]))
    actual_grain=grain(actual.output_grain,[f.model_dump() for f in actual.filters])
    grain_match=expected_grain==actual_grain or (expected_grain<=actual_grain and bool(source_keys)
                                                and source_keys-fixed<=expected_grain)
    return {'view':expected['view']==actual.view,'columns':required<=fields,
            'column_recall':len(required&fields)/len(required) if required else 1.0,
            'column_precision':len(required&fields)/len(fields) if fields else 0.0,
            'filters':filters_match,
            'metrics':all(equivalent_aggregation(c,a,actual_metrics.get(c)) for c,a in expected.get('metrics',{}).items()),
            'conditional_metrics':all(any(e['column']==a['column'] and equivalent_aggregation(e['column'],e['aggregation'],a['aggregation'])
                 and _filters(e['conditions'])==_filters(a['conditions']) for a in conditions) for e in expected_conditions),
            'grain':grain_match}


def grade_decomposition(case,response,catalog) -> dict:
    from cpea.workflows.task_decomposition.validation import validate_decomposition
    draft=response.draft
    result={'status_match':response.status==case['expected_status'],'canonical_views_match':False,
            'views_and_columns_match':False,
            'equivalent_tasks_match':False,'payload_ready':False,'integration_keys_match':False,
            'automated_pass':False,'semantic_review_required':True,'task_scores':[]}
    if draft is None:
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
            options=[_task_score(v,match,catalog) for v in variants]
            scores.append(max(options,key=lambda s:(sum(bool(s[k]) for k in checks),s['column_recall'])))
        merit=sum(sum(bool(s[k]) for k in checks) for s in scores)
        if best is None or merit>best[0]:best=(merit,ordering,scores)
    _,ordering,scores=best
    result['task_scores']=scores
    result['views_and_columns_match']=all(s['view'] and s['columns'] for s in scores)
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
