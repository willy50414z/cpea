"""Structural grading with strict measure/population invariants, no model calls."""
from __future__ import annotations

from itertools import permutations
from collections import Counter
import re

from cpea.application.models.decomposition import DecompositionResponse
from evaluations.decomposition_grading import _filters, _task_score, grade_decomposition


_TASK_CHECKS = ('view', 'columns', 'filters', 'metrics', 'conditional_metrics', 'metadata', 'grain')


def _task_match(expected, actual, catalog):
    score = _task_score(expected, actual, catalog)
    # Existing grading deliberately accepts metric subsets. Here the reverse
    # inclusion closes extra measures without losing approved count equivalence.
    score['no_extra_metrics'] = set(actual.metrics) <= set(expected.get('metrics', {}))
    actual_conditions = actual.conditional_metrics
    expected_conditions = expected.get('conditional_metrics', [])
    score['no_extra_conditional_metrics'] = len(actual_conditions) == len(expected_conditions) and all(
        any(e['column'] == a.column and e['aggregation'] == a.aggregation
            and _filters(e['conditions']) == _filters(a.conditions) for e in expected_conditions)
        for a in actual_conditions)
    # A raw background attribute cannot silently turn into another measure.
    score['attributes'] = set(expected.get('attributes', [])) <= set(actual.attributes)
    return all(score[k] for k in (*_TASK_CHECKS, 'no_extra_metrics', 'no_extra_conditional_metrics', 'attributes'))


def _null_policy_matches(oracle, integration):
    text = integration.missing_data_policy.strip()
    if text in oracle.get('acceptable_missing_data_policies', []):
        return True
    # This is a bounded semantic recognizer, not an NLP claim. Every clause
    # must match an approved behavior grammar; unknown prose fails closed.
    # Oracle reviewers may explicitly approve additional equivalent policies.
    grammars = {
        'preserve_rows': (
            r'保留(?:所有)?(?:未匹配|未配對|未對應|未命中)(?:的)?(?:資料|記錄|列)',
            r'(?:preserve|keep|retain)(?:all)?(?:unmatched|nonmatching)(?:rows|records)',
        ),
        'preserve_null': (
            r'(?:標記|保留|保持)(?:缺值|缺失值|null)',
            r'(?:缺值|缺失值|null)(?:仍為|仍是|維持為|保持為|保留為)(?:缺值|null)',
            r'(?:preserve|keep|retain)(?:null(?:values)?|missing(?:values)?)(?:asnull|unchanged)?',
            r'leave(?:missing(?:values)?|null(?:values)?)null',
        ),
        'forbid_zero': (
            r'(?:契約(?:沒有|未)保證時)?(?:不可|不得|不要|不應)(?:把)?(?:缺值|缺失值|null)(?:當成|視為|補成|補為)(?:零|0)',
            r'(?:缺值|缺失值|null)?(?:不可|不得|不要|不應)(?:補|填)(?:零|0)',
            r'(?:donot|never|without)(?:fill|replace|coalesce)(?:missing(?:values)?|null(?:values)?)?(?:with)?(?:zero|0)',
        ),
        'zero_fill': (
            r'(?:缺值|缺失值|null)(?:一律|全部)?(?:補|填|設為|改為)(?:零|0)',
            r'(?:fill|replace|coalesce)(?:missing(?:values)?|null(?:values)?)(?:with)?(?:zero|0)',
        ),
    }
    behaviors = set()
    clauses = [clause for clause in re.split(r'[，；。,;.]|\band\b|並|且', text.lower()) if clause.strip()]
    for clause in clauses:
        normalized = re.sub(r'\s+', '', clause)
        recognized = {name for name, forms in grammars.items() if any(re.fullmatch(form, normalized) for form in forms)}
        if not recognized:
            return False
        behaviors.update(recognized)
    if 'preserve_rows' not in behaviors:
        return False
    if oracle.get('null_policy') == 'zero_fill':
        return 'zero_fill' in behaviors and not ({'preserve_null', 'forbid_zero'} & behaviors)
    return (oracle.get('null_policy') == 'preserve_null' and bool({'preserve_null', 'forbid_zero'} & behaviors)
            and 'zero_fill' not in behaviors)


def _integration_match(oracle, actual, matched):
    if actual is None or not _null_policy_matches(oracle, actual):
        return False
    if actual.anchor_task != matched.get(oracle['anchor_task']):
        return False
    expected_preparation = Counter((matched.get(p['task_id']), p['kind'], tuple(sorted(p['keys'])))
                                   for p in oracle.get('preparation', []))
    actual_preparation = Counter((p.task_id, p.kind, tuple(sorted(p.keys))) for p in actual.preparation)
    if expected_preparation != actual_preparation:
        return False
    expected_edges = oracle.get('edges', [])
    if len(expected_edges) != len(actual.edges):
        return False
    return all(any(
        edge.left_task == matched.get(e['left_task']) and edge.right_task == matched.get(e['right_task'])
        and set(edge.left_keys) == set(e['left_keys']) and set(edge.right_keys) == set(e['right_keys'])
        and edge.mode == e.get('mode', 'left') and edge.cardinality == e['cardinality']
        and edge.preserve_task == matched.get(e.get('preserve_task'))
        for edge in actual.edges) for e in expected_edges)


def _selection_score(actual, oracle):
    required = oracle['required_columns']
    helpers = oracle.get('allowed_helper_columns', {})
    if not isinstance(actual, dict):
        return {'pass': False, 'recall': 0.0, 'precision': 0.0}
    selected = {(view, column) for view, columns in actual.items() for column in columns}
    needed = {(view, column) for view, columns in required.items() for column in columns}
    allowed = needed | {(view, column) for view, columns in helpers.items() for column in columns}
    return {'pass': needed <= selected <= allowed,
            'recall': len(needed & selected) / len(needed) if needed else 1.0,
            'precision': len(selected & allowed) / len(selected) if selected else 0.0}


def _node_scores(case, run):
    scores = {}
    for node, oracle in case.get('node_oracles', {}).items():
        actual = run.get('nodes', {}).get(node, {})
        if node == 'retrieval':
            scores[node] = {name: _selection_score(actual.get(name), oracle)
                            for name in ('raw_selection', 'rendered_columns')}
            scores[node]['pass'] = all(s['pass'] for s in scores[node].values())
        elif node == 'intent':
            rewrite = actual.get('rephrased_question', '')
            facts = oracle.get('required_facts', [])
            # Each independently reviewed fact has acceptable surface forms;
            # reasoning prose is deliberately excluded from this comparison.
            facts_match = isinstance(rewrite, str) and all(
                any(term in rewrite for term in alternatives) for alternatives in facts)
            scores[node] = {'pass': actual.get('intent') in oracle.get('acceptable_intents', ['TEXT_TO_SQL']) and facts_match,
                            'required_facts_match': facts_match}
        else:
            scores[node] = {'pass': False, 'code': 'unsupported_node_oracle'}
    return scores


def grade_wrenai_run(case: dict, run: dict, catalog) -> dict:
    try:
        response = DecompositionResponse.model_validate(run.get('response', run))
    except (ValueError, TypeError):
        return {'automated_pass': False, 'code': 'invalid_response', 'node_scores': {}}
    if response.draft is not None and response.draft.status != response.status:
        return {'automated_pass': False, 'code': 'inconsistent_response_status', 'node_scores': {}}
    nodes = _node_scores(case, run)
    status = response.status == case['expected_status']
    catalog_match = response.contract_fingerprint == catalog.fingerprint == case['contract_fingerprint']
    if case['expected_status'] != 'ready':
        clean = not response.prepared_requests and (response.draft is None or
                (not response.draft.tasks and response.draft.integration is None and response.draft.status == response.status))
        return {'status_match': status, 'nonready_clean': clean, 'node_scores': nodes,
                'automated_pass': status and clean and catalog_match and all(n['pass'] for n in nodes.values())}
    result = grade_decomposition(case, response, catalog)
    from cpea.workflows.task_decomposition.validation import prepare_requests
    try:
        expected_payloads = {p.task_id: p.model_dump() for p in prepare_requests(response.draft, catalog)} if response.draft else {}
        actual_payloads = {p.task_id: p.model_dump() for p in response.prepared_requests}
        prepared_match = bool(expected_payloads) and expected_payloads == actual_payloads
    except ValueError:
        prepared_match = False
    invariant = False
    if response.draft and len(case['expected_tasks']) == len(response.draft.tasks) <= 8:
        for ordering in permutations(response.draft.tasks):
            if all(any(_task_match(v, actual, catalog) for v in [expected, *expected.get('acceptable_alternatives', [])])
                   for expected, actual in zip(case['expected_tasks'], ordering)):
                matched = {e['task_id']: a.task_id for e, a in zip(case['expected_tasks'], ordering)}
                if _integration_match(case['expected_integration'], response.draft.integration, matched):
                    invariant = True
                    break
    result.update(node_scores=nodes, semantic_invariants_match=invariant, catalog_match=catalog_match,
                  prepared_tasks_match=prepared_match)
    result['automated_pass'] = bool(result['automated_pass'] and invariant and catalog_match and prepared_match and all(n['pass'] for n in nodes.values()))
    return result
