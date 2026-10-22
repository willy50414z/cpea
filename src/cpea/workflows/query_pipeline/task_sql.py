"""Reuse the single-view service without retaining resumable inner runs."""
from __future__ import annotations

from uuid import uuid4

from cpea.application.models.decomposition import DecompositionDraft, IntegrationPlan
from cpea.application.models.query import SQLGenerationResponse
from cpea.application.models.query_pipeline import TaskSQLResult
from cpea.workflows.query_pipeline.validation import issue, task_capability_issues, validate_task_sql
from cpea.workflows.task_decomposition.validation import render_task_request, validate_decomposition


def generate_task_sql(task_input, *, generator, catalog, settings, observer=None):
    task = task_input.task
    problems = []
    if task_input.contract_fingerprint != catalog.fingerprint:
        problems = [issue('handoff', 'stale_contract', task.task_id)]
    else:
        problems = task_capability_issues(task, catalog)
    if not problems:
        draft = DecompositionDraft(status='ready', strategy='single_view', tasks=[task],
            integration=IntegrationPlan(anchor_task=task.task_id, output_grain=task.output_grain))
        if validate_decomposition(draft, catalog):
            problems = [issue('handoff', 'invalid_handoff', task.task_id)]
    if problems:
        return TaskSQLResult(task_id=task.task_id,
            status='unsupported' if all(p.code == 'unsupported_task_capability' for p in problems) else 'error', issues=problems)
    try:
        request = render_task_request(task)
    except ValueError:
        return TaskSQLResult(task_id=task.task_id, status='error', issues=[issue('handoff', 'handoff_too_long', task.task_id)])
    owner = 'query-pipeline-' + uuid4().hex
    registry = getattr(getattr(generator, 'workflow', None), 'registry', None)
    try:
        try:
            output = generator.generate(request, history=[], mode='sql', owner=owner)
        except Exception:
            return TaskSQLResult(task_id=task.task_id, status='error',
                issues=[issue('sql_generation', 'provider_error', task.task_id)])
        if not isinstance(output, SQLGenerationResponse):
            return TaskSQLResult(task_id=task.task_id, status='error',
                issues=[issue('sql_generation', 'invalid_model_response', task.task_id)])
        if observer:
            observer(output.model_dump(mode='json'))
        trace = output.query_trace
        if (output.status == 'unsupported' and trace and trace.mapping_attempts
                and all(a.outcome == 'parse_error' for a in trace.mapping_attempts)):
            return TaskSQLResult(task_id=task.task_id, status='error',
                issues=[issue('sql_generation', 'invalid_model_response', task.task_id)])
        if output.status != 'ready':
            problems = []
            if output.status in ('error', 'cancelled'):
                code = 'provider_error' if output.code == 'provider_error' else 'invalid_model_response'
                problems = [issue('sql_generation', code, task.task_id)]
            return TaskSQLResult(task_id=task.task_id, status=output.status, generation=output, issues=problems)
        problems = validate_task_sql(task_input, output, catalog=catalog, settings=settings)
        if problems:
            return TaskSQLResult(task_id=task.task_id, status='error', issues=problems)
        return TaskSQLResult(task_id=task.task_id, status='ready', generation=output, gate_passed=True)
    finally:
        # Ownership works even for HILP responses lacking run_id and never reaps a sibling request.
        if registry is not None:
            with registry.lock:
                for run in list(registry.runs.values()):
                    if run.owner == owner:
                        registry.finish(run.id)
