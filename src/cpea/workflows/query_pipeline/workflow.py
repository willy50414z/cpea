"""Two core nodes; sequential SQL generation, with no database runtime."""
from __future__ import annotations

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from cpea.application.models.decomposition import DecompositionResponse
from cpea.application.models.query_pipeline import QueryPipelineResponse, TaskSQLInput
from cpea.workflows.query_pipeline.task_sql import generate_task_sql
from cpea.workflows.query_pipeline.validation import issue, preflight_tasks


class PipelineState(TypedDict, total=False):
    request: str
    run_id: str
    planning: DecompositionResponse
    response: QueryPipelineResponse


class QueryPipelineWorkflow:
    def __init__(self, planner, generator, *, catalog, settings, observer=None):
        self.planner, self.generator = planner, generator
        self.catalog, self.settings, self.observer = catalog, settings, observer
        graph = StateGraph(PipelineState)
        graph.add_node('decompose_request', self._decompose)
        graph.add_node('generate_task_sql', self._generate)
        graph.add_edge(START, 'decompose_request')
        graph.add_conditional_edges('decompose_request', lambda s: 'end' if s.get('response') else 'sql',
                                    {'end': END, 'sql': 'generate_task_sql'})
        graph.add_edge('generate_task_sql', END)
        self.graph = graph.compile()

    def _emit(self, event, state, **data):
        if self.observer:
            self.observer({'event': event, 'run_id': state['run_id'], **data})

    def _response(self, state, status, **values):
        return QueryPipelineResponse(run_id=state['run_id'], status=status,
            planning=state.get('planning'), contract_fingerprint=self.catalog.fingerprint, **values)

    def _start(self, request, run_id):
        state = {'request': request, 'run_id': run_id or uuid4().hex}
        self._emit('run_started', state)
        if not isinstance(request, str) or not request.strip() or len(request) > 4000:
            state['response'] = self._response(state, 'error', issues=[issue('planning', 'invalid_request')])
        return state

    def _finish(self, state):
        response = state['response']
        self._emit('run_finished', state, status=response.status)
        return response

    def invoke(self, request, *, run_id=None):
        state = self._start(request, run_id)
        if 'response' not in state:
            state = self.graph.invoke(state)
        return self._finish(state)

    def generate_from_plan(self, request, planning, *, run_id=None):
        state = self._start(request, run_id)
        if 'response' not in state:
            # Own a snapshot; never mutate caller-supplied approved input.
            state['planning'] = planning.model_copy(deep=True)
            if planning.status != 'ready':
                state.update(self._planning_stop(state))
            else:
                state.update(self._generate(state))
        return self._finish(state)

    def _decompose(self, state):
        try:
            planning = self.planner.plan(state['request'])
        except Exception:
            planning = DecompositionResponse(status='error', code='provider_error',
                                             contract_fingerprint=self.catalog.fingerprint)
        if not isinstance(planning, DecompositionResponse):
            planning = DecompositionResponse(status='error', code='invalid_model_response',
                                             contract_fingerprint=self.catalog.fingerprint)
        state = {**state, 'planning': planning.model_copy(deep=True)}
        self._emit('planning_finished', state, status=planning.status)
        return {'planning': state['planning'], **(self._planning_stop(state) if planning.status != 'ready' else {})}

    def _planning_stop(self, state):
        planning = state['planning']
        problems = [issue('planning', planning.code or 'invalid_model_response')] if planning.status == 'error' else []
        ids = list(dict.fromkeys(t.task_id for t in planning.draft.tasks)) if planning.draft else []
        return {'response': self._response(state, planning.status, skipped_task_ids=ids, issues=problems)}

    def _generate(self, state):
        planning = state['planning']
        problems = preflight_tasks(planning, catalog=self.catalog)
        self._emit('preflight_finished', state, issues=[i.model_dump() for i in problems])
        ids = list(dict.fromkeys(t.task_id for t in planning.draft.tasks)) if planning.draft else []
        if problems:
            status = 'unsupported' if all(p.code == 'unsupported_task_capability' for p in problems) else 'error'
            return {'response': self._response(state, status, skipped_task_ids=ids, issues=problems)}
        results = []
        status = 'sql_ready'
        for task in planning.draft.tasks:
            envelope = TaskSQLInput(original_request=state['request'], task=task,
                                    contract_fingerprint=planning.contract_fingerprint)
            diagnostics = []
            result = generate_task_sql(envelope, generator=self.generator, catalog=self.catalog,
                                       settings=self.settings, observer=diagnostics.append)
            results.append(result)
            # Observer diagnostics are private evidence. Public event writers must omit this field.
            self._emit('task_finished', state, task_id=task.task_id, status=result.status,
                       task_input=envelope.model_dump(mode='json'), diagnostic=result.model_dump(mode='json'),
                       candidate_generation=diagnostics[0] if diagnostics else None)
            if result.status != 'ready':
                status = 'error' if result.status == 'cancelled' else result.status
                problems.extend(result.issues)
                break
        return {'response': self._response(state, status, task_results=results,
            skipped_task_ids=ids[len(results):], issues=problems)}
