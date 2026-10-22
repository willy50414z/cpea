"""Whole-plan semantic oracles, separate from SQL gates and human review."""
from __future__ import annotations

from hashlib import sha256
from itertools import permutations
import json

from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.application.models.query_pipeline import QueryPipelineResponse
from cpea.workflows.query_pipeline.validation import normalized_filters, preflight_tasks
from cpea.workflows.task_decomposition.validation import validate_decomposition

GRADER_VERSION = 'query-pipeline-v1'


def content_hash(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _task_semantics(task, ids):
    data = task.model_dump(exclude={'task_id', 'request', 'filters', 'depends_on', 'conditional_metrics'})
    for key in ('required_columns', 'attributes', 'metadata_collections', 'group_by', 'output_grain', 'unbound_inputs'):
        data[key] = sorted(data[key])
    data['filters'] = sorted(normalized_filters(task.filters).items())
    data['depends_on'] = sorted(ids.get(dep, dep) for dep in task.depends_on)
    data['conditional_metrics'] = sorted((m.column, m.aggregation, sorted(normalized_filters(m.conditions).items()))
                                         for m in task.conditional_metrics)
    return data


def _integration_semantics(plan, ids):
    if plan is None:
        return None
    data = plan.model_dump(exclude={'notes', 'edges', 'preparation', 'anchor_task', 'output_grain'})
    data['anchor_task'] = ids.get(plan.anchor_task, plan.anchor_task)
    data['output_grain'] = sorted(plan.output_grain)
    data['edges'] = sorted((ids.get(e.left_task, e.left_task), ids.get(e.right_task, e.right_task),
        sorted(zip(e.left_keys, e.right_keys)), e.mode, e.cardinality, ids.get(e.preserve_task, e.preserve_task) or '')
        for e in plan.edges)
    data['preparation'] = sorted((ids.get(p.task_id, p.task_id), p.kind, sorted(p.keys)) for p in plan.preparation)
    return data


def plans_equivalent(expected, actual):
    """Match a complete approved alternative, including its integration topology."""
    if expected.status != actual.status or expected.strategy != actual.strategy or len(expected.tasks) != len(actual.tasks):
        return False
    if len(actual.tasks) > 8:
        return False
    expected_ids = {t.task_id: str(i) for i, t in enumerate(expected.tasks)}
    for ordering in permutations(actual.tasks):
        actual_ids = {t.task_id: str(i) for i, t in enumerate(ordering)}
        if (all(_task_semantics(e, expected_ids) == _task_semantics(a, actual_ids)
                for e, a in zip(expected.tasks, ordering))
                and _integration_semantics(expected.integration, expected_ids) == _integration_semantics(actual.integration, actual_ids)):
            return True
    return False


def grade_pipeline_case(case, response, *, mode, catalog):
    if mode not in {'planning', 'sql', 'integrated'} or (
            mode == 'planning' and not isinstance(response, DecompositionResponse)) or (
            mode != 'planning' and not isinstance(response, QueryPipelineResponse)):
        raise ValueError('evaluation mode and response type mismatch')
    planning = response if mode == 'planning' else response.planning
    expected = case.get('expected_planning_status', 'ready') if mode == 'planning' else case['expected_stage_status']
    status_match = response.status == expected
    alternatives = [DecompositionDraft.model_validate(p) for p in case.get('approved_plans', [])]
    semantics = bool(planning and planning.draft and any(plans_equivalent(p, planning.draft) for p in alternatives))
    # Pending / no-source cases must preserve their expected planning status.
    if not alternatives:
        semantics = bool(planning and planning.status == case.get('expected_planning_status') and planning.status != 'ready')
    planning_valid = bool(planning and (planning.status != 'ready' or
        (planning.draft and not validate_decomposition(planning.draft, catalog))))
    problems = response.issues if isinstance(response, QueryPipelineResponse) else []
    first_error = None
    if not semantics or not planning_valid:
        first_error = 'planning'
    elif not status_match:
        first_error = problems[0].stage if problems else ('planning' if mode == 'planning' else 'sql_generation')
    handoff = None
    if planning and planning.status == 'ready':
        handoff = not preflight_tasks(planning, catalog=catalog)
    gates = None if mode == 'planning' else (response.status == 'sql_ready' and all(r.gate_passed for r in response.task_results))
    automated = bool(status_match and semantics and planning_valid and
        (expected != 'sql_ready' or gates))
    fingerprint = content_hash(response.model_dump(mode='json'))
    review = case.get('output_reviews', {}).get(fingerprint, {})
    reviewed = bool(review.get('decision') == 'approved' and review.get('reviewer') and review.get('reviewed_at'))
    return {'grader_version': GRADER_VERSION, 'status_match': status_match,
        'planning_semantics': semantics, 'planning_contract': planning_valid,
        'capability_handoff': handoff, 'task_to_plan_and_sql_policy': gates,
        'automated_pass': automated, 'success': automated and reviewed,
        'semantic_review_required': not reviewed, 'response_sha256': fingerprint,
        'first_error_stage': first_error, 'issues': [i.model_dump() for i in problems],
        'supported_capability': case['expected_stage_status'] == 'sql_ready',
        'false_ready': response.status == 'sql_ready' and not automated}


def summarize_pipeline(entries, *, planned, runs, support_planned=None):
    completed = [e for e in entries if e['status'] == 'completed']
    natural = [e for e in completed if e.get('kind') == 'natural']
    success = [e for e in natural if e.get('grading', {}).get('success')]
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry['case_id'], []).append(entry)
    stable = sum(runs == 3 and len(rows) == 3 and {r['round'] for r in rows} == {0, 1, 2}
        and all(r in success for r in rows) for rows in grouped.values())
    supported_success = sum(bool(e.get('supported_case')) for e in success)
    return {'planned': planned, 'completed': len(completed),
        'failed': sum(e['status'] == 'failed' for e in entries),
        'skipped': sum(e['status'] == 'skipped' for e in entries),
        'unfinished': planned - len(entries), 'natural_success': len(success),
        'automated_pass': sum(bool(e.get('grading', {}).get('automated_pass')) for e in completed),
        'success_rate': len(success) / planned if planned else 0,
        'first_success': sum(e['round'] == 0 for e in success),
        'three_round_all_success': stable,
        'pending': sum(e.get('response', {}).get('status') in {'needs_confirmation', 'needs_clarification'} for e in completed),
        'awaiting_semantic_review': sum(bool(e.get('grading', {}).get('semantic_review_required')) for e in completed),
        'support_planned': support_planned, 'supported_natural_success': supported_success,
        'supported_success_rate': supported_success / support_planned if support_planned else None,
        'total_elapsed_ms': sum(e.get('elapsed_ms', 0) for e in entries),
        'false_ready': sum(bool(e.get('grading', {}).get('false_ready')) for e in completed)}


def _pointer(value, pointer):
    if not pointer.startswith('/'):
        raise ValueError('obligation requires an absolute JSON pointer')
    for part in pointer[1:].split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def independent_review_valid(review, *, input_sha256, artifact_sha256, rules_sha256):
    """Input approval is separate; this validates a hash-bound output review only."""
    return bool(review and review.get('decision') == 'approved' and review.get('author')
        and review.get('reviewer') and review['reviewer'] != review['author'] and review.get('reviewed_at')
        and review.get('input_sha256') == input_sha256
        and review.get('artifact_sha256') == artifact_sha256 and review.get('rules_sha256') == rules_sha256)


def assess_requirements(normalized, *, rules, input_sha256, review=None):
    """Score approved semantic projections, never repair or enrich native output.

    Callers own projection validity; unknown native semantics remain unobserved.
    Match one WHOLE legal alternative rather than selecting a best rule per field.
    SQL/compiler, reference, integration and natural gates require separate evidence.
    """
    from evaluations.query_pipeline_experiments import LAYERS, RequirementAssessment, SemanticAssessment
    alternatives = rules.get('alternatives', [])
    if not rules.get('version') or not alternatives or any(not a for a in alternatives):
        raise ValueError('versioned complete obligation alternatives required')
    identifiers = [r['requirement_id'] for r in alternatives[0]]
    if len(set(identifiers)) != len(identifiers) or any(
            {r['requirement_id'] for r in a} != set(identifiers) or len(a) != len(identifiers) for a in alternatives):
        raise ValueError('alternatives must cover identical unique requirement IDs')
    candidates = []
    for alternative in alternatives:
        assessments = []
        for rule in alternative:
            verdict, coverage, evidence = 'NOT_OBSERVED', 'unknown', []
            if rule.get('match', 'exact') not in {'exact', 'set'} or not rule['pointer'].startswith('/'):
                raise ValueError('unsupported obligation comparison')
            # Access expected even when evidence is absent: malformed rules must fail early.
            expected = rule['expected']
            try:
                actual = _pointer(normalized, rule['pointer'])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            else:
                if rule.get('match') == 'set':
                    equal = isinstance(actual, list) and isinstance(expected, list) and (
                        {content_hash(v) for v in actual} == {content_hash(v) for v in expected})
                else:
                    equal = content_hash(actual) == content_hash(expected)
                verdict, coverage = ('PASS', 'satisfied') if equal else ('FAIL', 'partial')
                evidence = [rule['pointer']]
            assessments.append(RequirementAssessment(requirement_id=rule['requirement_id'],
                obligation=rule['obligation'], evidence=evidence, verdict=verdict, coverage=coverage))
        candidates.append(assessments)
    chosen = max(candidates, key=lambda rows: sum(r.verdict == 'PASS' for r in rows))
    verdicts = {r.verdict for r in chosen}
    verdict = 'FAIL' if 'FAIL' in verdicts else ('NOT_OBSERVED' if 'NOT_OBSERVED' in verdicts else 'PASS')
    layers = dict.fromkeys(LAYERS, 'NOT_OBSERVED')
    layers['requirements'] = verdict
    rule_hash = content_hash(rules)
    return SemanticAssessment(grading_version='query-pipeline-requirements-v1', rules_sha256=rule_hash,
        requirements=chosen, layers=layers, first_error='requirements' if verdict == 'FAIL' else None,
        independent_approval=independent_review_valid(review, input_sha256=input_sha256,
            artifact_sha256=content_hash(normalized), rules_sha256=rule_hash))


def _rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': numerator / denominator if numerator is not None and denominator else None}


def mapping_metrics(*, expected, observed):
    expected = {content_hash(v) for v in expected}
    if observed is None:
        return {'recall': _rate(None, len(expected)), 'precision': _rate(None, None)}
    observed = {content_hash(v) for v in observed}
    hits = len(expected & observed)
    return {'recall': _rate(hits, len(expected)), 'precision': _rate(hits, len(observed))}


def calibrate_oracle(rows, *, review=None, rules_sha256=None):
    """Report disagreements without changing the oracle or assuming labels approved."""
    if any(r.get('independent_verdict') not in {'legal', 'illegal', 'disputed', 'unknown'}
           or (r.get('automated_pass') is not None and type(r['automated_pass']) is not bool) for r in rows):
        raise ValueError('invalid calibration label')
    legal = [r for r in rows if r['independent_verdict'] == 'legal' and r['automated_pass'] is not None]
    illegal = [r for r in rows if r['independent_verdict'] == 'illegal' and r['automated_pass'] is not None]
    return {'planned': len(rows), 'false_reject': _rate(sum(not r['automated_pass'] for r in legal), len(legal)),
        'false_accept': _rate(sum(r['automated_pass'] for r in illegal), len(illegal)),
        'disputed': sum(r['independent_verdict'] == 'disputed' for r in rows),
        'unobserved': sum(r['independent_verdict'] == 'unknown' or r['automated_pass'] is None for r in rows),
        'approval_verified': independent_review_valid(review, input_sha256=content_hash(rows),
            artifact_sha256=content_hash(rows), rules_sha256=rules_sha256)}
