"""A stateless planning graph with no SQL generation or execution dependency."""
from __future__ import annotations

import json
from time import perf_counter
from typing import Any, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import START, END, StateGraph
from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.infrastructure.llm.context_budget import build_token_counter
from cpea.infrastructure.llm.factory import bind_response_schema, prepare_structured_messages
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT
from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests


class PlanningState(TypedDict, total=False):
    request: str
    messages: list[Any]
    draft: DecompositionDraft
    response: DecompositionResponse
    context_tokens: int


class TaskDecompositionWorkflow:
    def __init__(self,llm,catalog,*,settings,token_counter=None,observer=None):
        self.llm,self.catalog,self.settings=llm,catalog,settings
        self.token_counter=token_counter or build_token_counter(settings)
        self.observer=observer
        graph=StateGraph(PlanningState)
        for name,fn in [('load_contracts',self._load),('plan_tasks',self._plan),
                        ('validate_plan',self._validate),('prepare_requests',self._prepare)]:
            graph.add_node(name,fn)
        graph.add_edge(START,'load_contracts')
        for source,target in [('load_contracts','plan_tasks'),('plan_tasks','validate_plan'),('validate_plan','prepare_requests')]:
            graph.add_conditional_edges(source,lambda state:'end' if state.get('response') else 'next',
                                        {'end':END,'next':target})
        graph.add_edge('prepare_requests',END)
        self.graph=graph.compile()

    def invoke(self,request: str) -> DecompositionResponse:
        if not isinstance(request,str) or not request.strip() or len(request)>4000:
            return self._result('error',code='invalid_request')
        return self.graph.invoke({'request':request})['response']

    def _result(self,status,*,tokens=0,**kw):
        return DecompositionResponse(status=status,contract_fingerprint=self.catalog.fingerprint,
                                     context_tokens=tokens,token_counter=self.token_counter.name,**kw)

    def _load(self,state):
        views=self.catalog.views()
        if not views:
            return {'response':self._result('unsupported',code='empty_catalog')}
        context={'request':state['request'],'views':[{'view':v.name,**v.policy} for v in views],
                 'response_schema':DecompositionDraft.model_json_schema()}
        messages=[SystemMessage(content=DECOMPOSITION_PROMPT),HumanMessage(content=json.dumps(context,ensure_ascii=False))]
        messages=prepare_structured_messages(messages,DecompositionDraft,schema=context['response_schema'])
        tokens=self.token_counter.count_messages([('system',messages[0].content),('user',messages[1].content)])
        budget=self.settings.context_window-self.settings.output_token_reserve-self.settings.context_safety_tokens
        if tokens>budget:
            return {'response':self._result('error',tokens=tokens,code='context_budget_exceeded')}
        return {'messages':messages,'context_tokens':tokens}

    def _plan(self,state):
        started=perf_counter()
        event={'messages':[{'role':m.type,'content':m.content} for m in state['messages']]}
        try:
            llm=bind_response_schema(self.llm,DecompositionDraft)
            raw=llm.invoke(state['messages'])
        except Exception as exc:
            event.update(error_type=type(exc).__name__,error=str(exc),elapsed_ms=(perf_counter()-started)*1000)
            if self.observer:self.observer(event)
            return {'response':self._result('error',tokens=state['context_tokens'],code='provider_error')}
        event.update(response=getattr(raw,'content',raw),usage=getattr(raw,'usage_metadata',None),
                     elapsed_ms=(perf_counter()-started)*1000)
        if self.observer:self.observer(event)
        try:
            draft=parse_model(raw,DecompositionDraft)
        except (ValueError,TypeError):
            return {'response':self._result('error',tokens=state['context_tokens'],code='invalid_model_response')}
        return {'draft':draft}

    def _validate(self,state):
        draft=state['draft']
        if draft.status!='ready':
            return {'response':self._result(draft.status,tokens=state['context_tokens'],draft=draft)}
        errors=validate_decomposition(draft,self.catalog)
        if errors:
            return {'response':self._result('error',tokens=state['context_tokens'],code='invalid_plan',draft=draft,validation_errors=errors)}
        return {}

    def _prepare(self,state):
        try:
            requests=prepare_requests(state['draft'],self.catalog)
        except ValueError:
            return {'response':self._result('error',tokens=state['context_tokens'],code='invalid_prepared_request',draft=state['draft'])}
        return {'response':self._result('ready',tokens=state['context_tokens'],draft=state['draft'],prepared_requests=requests)}
