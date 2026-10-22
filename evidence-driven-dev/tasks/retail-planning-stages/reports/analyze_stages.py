"""離線比較實驗 arms 與中間契約；不修改原始分數。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local'))
from compare_stages import Route, PlanningTask, DecompositionDraft, SELECTED, CONTROLS, rows
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.decomposition_cases import load_decomposition_cases


def analyze(folder):
    catalog = SchemaCatalog(Path('projects/retail'))
    cases = {c['case_id']: c for c in load_decomposition_cases(
        Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog)}
    results, calls = rows(folder / 'results.jsonl'), rows(folder / 'calls.jsonl')
    indexed = {(r['case_id'], r['arm']): r for r in results}
    assert len(indexed) == len(SELECTED) * 3
    paired = {}
    for left, right in [('A_original', 'B_checklist'), ('A_original', 'C_staged'), ('B_checklist', 'C_staged')]:
        delta = {'improved': [], 'regressed': [], 'both_pass': [], 'both_fail': []}
        for n in SELECTED:
            cid = f'cross-view-{n:02d}'
            a, b = (indexed[(cid, arm)]['score']['automated_pass'] for arm in (left, right))
            delta['both_pass' if a and b else 'both_fail' if not a and not b else 'improved' if b else 'regressed'].append(cid)
        paired[f'{left}_to_{right}'] = delta
    phase = {'routes': [], 'generated_task_calls': 0, 'generated_integration_calls': 0,
             'task_contract_failure_cases': [], 'route_status_failure_cases': []}
    for c in calls:
        if c['arm'] != 'C_staged':
            continue
        if c['stage'] == 'route':
            route = Route.model_validate_json(c['response'])
            expected = cases[c['case_id']]['expected_tasks']
            phase['routes'].append({'case_id': c['case_id'], 'status': route.status,
                'views': [t.view for t in route.tasks], 'output_grain': route.output_grain,
                'canonical_views_match': sorted(t.view for t in route.tasks) == sorted(t['view'] for t in expected),
                'anchor_task': route.anchor_task})
        elif c['stage'].startswith('task:'):
            phase['generated_task_calls'] += 1
        elif c['stage'] == 'integration':
            phase['generated_integration_calls'] += 1
    for r in results:
        if r['arm'] == 'C_staged' and r['stop_stage'] == 'task_contract':
            phase['task_contract_failure_cases'].append(r['case_id'])
        if r['arm'] == 'C_staged' and r['stop_stage'] == 'route_status':
            phase['route_status_failure_cases'].append(r['case_id'])
    risks = []
    for r in results:
        draft = DecompositionDraft.model_validate(r['response']['draft']) if r['response']['draft'] else None
        if not draft:
            continue
        for t in draft.tasks:
            grain = next(v for v in catalog.views() if v.name == t.view).policy.get('grain', {})
            keys = set(grain.get('keys') or [])
            fixed = {f.column for f in t.filters if f.operator == '='}
            # Supplementary diagnostic only: a closed singleton interval proves equality.
            for lower in t.filters:
                if lower.operator == '>=' and any(upper.column == lower.column
                        and upper.operator == '<=' and upper.value == lower.value for upper in t.filters):
                    fixed.add(lower.column)
            unique = bool(keys) and keys - fixed <= set(t.output_grain)
            aggregated = bool(t.metrics or t.conditional_metrics or t.group_by or t.metadata_collections)
            if aggregated and not unique and set(t.attributes) - set(t.group_by):
                risks.append({'case_id': r['case_id'], 'arm': r['arm'], 'task_id': t.task_id,
                    'kind': 'aggregate_scalar_attributes_without_unique_key_proof',
                    'columns': sorted(set(t.attributes)-set(t.group_by))})
            source_columns = set(catalog.columns(t.view))
            if not set(t.metrics) <= source_columns:
                risks.append({'case_id':r['case_id'],'arm':r['arm'],'task_id':t.task_id,
                    'kind':'metric_not_source_column','columns':sorted(set(t.metrics)-source_columns)})
            output_roles = set(t.attributes + t.group_by + t.output_grain + t.metadata_collections) | set(t.metrics)
            output_roles.update(m.column for m in t.conditional_metrics)
            filter_roles = {f.column for f in t.filters} | {f.column for m in t.conditional_metrics for f in m.conditions}
            required_only = set(t.required_columns) - output_roles - filter_roles
            if required_only:
                risks.append({'case_id':r['case_id'],'arm':r['arm'],'task_id':t.task_id,
                    'kind':'required_column_without_explicit_role_review_needed',
                    'columns':sorted(required_only)})
        if draft.integration:
            for edge in draft.integration.edges:
                if edge.mode == 'inner':
                    risks.append({'case_id':r['case_id'],'arm':r['arm'],
                        'kind':'inner_join_requires_population_review'})
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    comparison = {'run':str(folder),'summary':summary,'paired_changes':paired,'phase_diagnostics':phase,
        'supplementary_semantic_risk_flags':risks,
        'case_results':[{'case_id':f'cross-view-{n:02d}','control':n in CONTROLS,
            'arms':{a:{'pass':indexed[(f'cross-view-{n:02d}',a)]['score']['automated_pass'],
                       'ready':indexed[(f'cross-view-{n:02d}',a)]['response']['status']=='ready',
                       'stop':indexed[(f'cross-view-{n:02d}',a)]['stop_stage'],
                       'errors':indexed[(f'cross-view-{n:02d}',a)]['response']['validation_errors']}
                    for a in ('A_original','B_checklist','C_staged')}} for n in SELECTED],
        'caveats':['單次、已見案例的診斷小樣本，不是外部holdout或全30題結果。',
            '原始自動分數不等於完整語意正確率；補充風險標記不回寫原分。',
            'C改變schema、上下文與呼叫數；只能比較整體策略，不能隔離呼叫數本身。',
            'C任務契約失敗即停止，最終來源欄位分數會因部分任務缺席而失分，需另看route指標。']}
    (ROOT/'reports/stages-analysis.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(comparison,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    analyze(parser.parse_args().run)
