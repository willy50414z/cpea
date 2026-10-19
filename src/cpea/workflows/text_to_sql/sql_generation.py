"""Schema-guided, compiler-only single-View SQL workflow."""

from __future__ import annotations

import json
import re
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command, interrupt
from langgraph.config import get_stream_writer
from cpea.application.models.progress import WorkflowStep
from cpea.application.models.confirmation import (Clarification, ConfirmationItem, ConfirmationOption, ConfirmationError, TermMappingReasoning)
from cpea.application.ports.term_mappings import (MappingScope, MappingStoreError, MappingConflict, TermMapping, normalize_term, view_fingerprint)
from cpea.application.services.confirmation import ConfirmationRegistry
from cpea.infrastructure.terms_mapping import JsonTermMappingRepository
from cpea.workflows.text_to_sql.semantics import assess
from cpea.workflows.text_to_sql.clarification import (
    MAX_BUSINESS_OPTIONS, RESOLUTION_PROMPT, business_label, requires_resolution, semantic_choices,
)
from typing import Any, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.llm.factory import bind_response_schema, response_schema_for
from cpea.application.models.query import (CandidateAttempt, ClarificationChoice, ClarificationOption,
    ClarificationRequest, ConversationTurn, MappingAttempt, QueryTaskTrace, SourceReference, SQLGenerationResponse)
from cpea.workflows.text_to_sql.schemas import ClarificationResolution, SQLClauseMapping, SchemaLinkDraft
from cpea.domain.models import HavingFilter, QueryFact, QueryFilter, QueryPlan, SchemaLink
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_compiler import compile_single_view, validate_single_view_plan
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever, explicit_column_references
from cpea.config.settings import AssistantSettings
from cpea.workflows.text_to_sql.prompt_resources import MatchPrompt, load_match_prompt


MATCH_PROMPT = load_match_prompt().system

_LEGACY_COLUMN_TYPES = {
    '字串': 'string', '字串（代碼）': 'string', '數值': 'number', '数值': 'number',
    '日期': 'date', '日期字串（`YYYY-MM-DD`）': 'string',
}


class ViewComparison(BaseModel):
    decision: Literal["select", "clarify"]
    selected_view: str | None = None
    request_evidence: str | None = None
    contract_evidence: str | None = None
    reason: str = ""
    question: str | None = None
    options: list[ClarificationOption] = Field(default_factory=list)


COMPARE_SYSTEM = """比較已通過契約與查詢計畫驗證的單一 View 方案。只使用問題原文與提供的 YAML 契約證據。
若問題明確指出其中一種業務粒度或指標口徑，可選擇該 View；需提供問題原文中的連續片段 request_evidence，及所選契約中的連續片段 contract_evidence。
若多種解讀仍合理，回傳 decision=clarify、自然語言問題及每個候選 View 的業務選項。不要用技術欄位名作為選項標籤。
SQL 能編譯或排序較高，不足以證明業務語意正確。不得假設不同口徑的金額等價。"""


class SQLGenerationState(TypedDict, total=False):
    semantic_retry: bool
    run_id: str
    view_contract_fingerprint: str
    clause_mapping: Any
    semantic_uses: list[dict]
    clarification: Clarification | None
    proposals: list[TermMapping]
    used_mappings: list[TermMapping]
    snapshot: Any
    replacements: dict[str, str]
    replace_targets: dict[str, str]
    reasoning: list[TermMappingReasoning]
    request: str
    clarification_choice: ClarificationChoice
    history: list[ConversationTurn]
    history_context: str
    candidates: list[RetrievalCandidate]
    retrieved_candidates: list[SourceReference]
    sources: list[SourceReference]
    retrieval_latency_ms: float
    reranker_latency_ms: float
    context_tokens: int
    context_budget: int
    request_facts: list[QueryFact]
    candidate_attempts: list[CandidateAttempt]
    mapping_attempts: list[MappingAttempt]
    selected_mapping_index: int
    links: SchemaLinkDraft
    having: list[HavingFilter]
    order_by: list[str]
    order_directions: dict[str, str]
    selected_views: list[str]
    plan: QueryPlan
    compiled_sql: str
    rejection_stage: str
    response: SQLGenerationResponse


class SQLGenerationWorkflow:
    def __init__(self, llm: Any, catalog: CatalogProvider | None = None, *,
                 settings: AssistantSettings | None = None,
                 retriever: SchemaRetriever | None = None,
                 context_packer: ContextPacker | None = None,
                 match_prompt: MatchPrompt | None = None,
                 repository=None, checkpointer=None) -> None:
        self.llm = llm
        self.catalog = catalog or _default_catalog()
        self.settings = settings or AssistantSettings.from_env()
        if self.settings.sql_generation_mode != "compiler":
            raise ValueError("ASSISTANT_SQL_GENERATION_MODE supports only compiler; legacy is unsupported")
        self.retriever = retriever or SchemaRetriever(self.settings, catalog=self.catalog)
        self.context_packer = context_packer or ContextPacker(self.settings)
        self.match_prompt = match_prompt or load_match_prompt()
        self.repository = repository or JsonTermMappingRepository(
            self.settings.terms_mapping_path or Path(getattr(self.catalog, 'root', None) or self.settings.integration_path or '.') / 'terms_mapping.json',
            MappingScope(profile_id=getattr(self.catalog, 'profile_id', 'default'), datasource_id=self.settings.datasource_id))
        from pydantic import BaseModel
        from cpea.application.models import query as query_models, confirmation as confirmation_models
        from cpea.application.ports import term_mappings as mapping_models
        from cpea.domain import models as domain_models
        from cpea.workflows.text_to_sql import schemas as draft_models
        allowed = {(RetrievalCandidate.__module__, RetrievalCandidate.__name__),
                   (Document.__module__, Document.__name__)}
        for module in (query_models, confirmation_models, mapping_models, domain_models, draft_models):
            allowed.update((value.__module__, value.__name__) for value in vars(module).values()
                           if isinstance(value, type) and issubclass(value, BaseModel)
                           and value.__module__ == module.__name__)
        self.checkpointer = checkpointer or InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=allowed))
        self.registry = ConfirmationRegistry(self.checkpointer.delete_thread)
        self.graph = self._build_graph()

    def invoke(self, request: str, history: list[ConversationTurn] | None = None,
               clarification_choice: ClarificationChoice | None = None,
               *, mode='sql', owner=None) -> SQLGenerationResponse:
        for update in self.generate_updates(request, history, mode=mode, owner=owner,
                                            clarification_choice=clarification_choice):
            if isinstance(update, SQLGenerationResponse):
                result = update
        return result

    def generate_updates(self, request: str, history: list[ConversationTurn] | None = None,
                         *, mode='sql', owner=None, clarification_choice=None):
        if history:
            raise ConfirmationError('history_not_supported')
        if not request.strip() or len(request) > 4000:
            raise ConfirmationError('invalid_request')
        run_id = token_urlsafe(32)
        self.registry.begin(run_id, mode, owner)
        delivered = False
        try:
            state = yield from self._graph_updates({'request': request, 'history': [], 'run_id': run_id,
                'proposals': [], 'used_mappings': [], 'replacements': {},
                **({'clarification_choice': clarification_choice} if clarification_choice else {})}, run_id)
            response = self._public_result(run_id, state)
            delivered = True
            yield response
        finally:
            if not delivered:
                self.registry.finish(run_id)

    def _graph_updates(self, inputs, run_id):
        state = {}
        with closing(self.graph.stream(inputs, self._config(run_id), stream_mode=['custom', 'values'])) as updates:
            for mode, value in updates:
                if mode == 'custom' and isinstance(value, WorkflowStep):
                    yield value
                elif mode == 'values':
                    state.update(value)
        return state

    @staticmethod
    def _emit(step, info):
        get_stream_writer()(WorkflowStep(step, info))

    @staticmethod
    def _config(run_id):
        return {'configurable': {'thread_id': run_id}}

    def confirm(self, payload, *, mode='sql', owner=None, claimed=None):
        for update in self.confirm_updates(payload, mode=mode, owner=owner, claimed=claimed):
            if not isinstance(update, WorkflowStep):
                result = update
        return result

    def confirm_updates(self, payload, *, mode='sql', owner=None, claimed=None):
        run = claimed or self.registry.claim(payload, mode, owner)
        delivered = False
        try:
            saved_state = self.graph.get_state(self._config(run.id)).values
            question = saved_state['request']
            if saved_state.get('view_contract_fingerprint') != view_fingerprint(self.catalog, saved_state['selected_views'][0]):
                raise ConfirmationError('confirmation_contract_changed', 410)
            if payload.action in ('cancel', 'rephrase'):
                self.registry.finish(run.id)
                yield WorkflowStep('HILP confirmation', '已取消')
                response = SQLGenerationResponse(status='cancelled', supported=False,
                    code='clarification_rephrase' if payload.action == 'rephrase' else None,
                    explanation='請修改原題的詞彙或補充說明，再送出查詢。' if payload.action == 'rephrase' else '已停止本題。')
            else:
                state = yield from self._graph_updates(Command(resume=payload.model_dump()), run.id)
                response = self._public_result(run.id, state)
            delivered = True
            yield question, response
        finally:
            if not delivered:
                self.registry.finish(run.id)
            run.lock.release()

    def _public_result(self, run_id, state):
        if state.get('__interrupt__'):
            clarification = Clarification.model_validate(state['__interrupt__'][0].value)
            self.registry.pause(run_id, clarification)
            return SQLGenerationResponse(status='needs_confirmation', supported=False,
                explanation='請確認以下詞彙的意思，再繼續查詢。', clarification=clarification)
        response = state['response'].model_copy(update={'run_id': run_id})
        run = self.registry.runs.get(run_id)
        if response.status != 'ready' or run.mode == 'sql':
            self.registry.finish(run_id)
        return response

    def _build_graph(self):
        graph = StateGraph(SQLGenerationState)
        # 從doc篩選views並加入tokens budget/latency ms打包成context
        graph.add_node("retrieve_schema", self._retrieve_schema)
        graph.add_node("match_candidates", self._match_candidates)
        graph.add_node('assess_semantics', self._assess_semantics)
        graph.add_node('confirm_fields', self._confirm_fields)
        graph.add_node('persist_term_mappings', self._persist_term_mappings)
        graph.add_node("compile_query", self._compile_query)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "retrieve_schema")
        graph.add_conditional_edges("retrieve_schema", self._continue_or_end, {"continue": "match_candidates", "end": "finalize"})
        graph.add_conditional_edges("match_candidates", self._continue_or_end, {"continue": "assess_semantics", "end": "finalize"})
        graph.add_conditional_edges('assess_semantics', self._semantic_route,
            {'end': 'finalize', 'confirm': 'confirm_fields', 'compile': 'compile_query', 'retry': 'match_candidates'})
        graph.add_conditional_edges('confirm_fields', self._continue_or_end,
            {'end': 'finalize', 'continue': 'compile_query'})
        graph.add_edge('compile_query', 'persist_term_mappings')
        graph.add_conditional_edges('persist_term_mappings', lambda state: 'confirm' if state.get('clarification') else 'end',
            {'confirm': 'confirm_fields', 'end': 'finalize'})
        graph.add_edge("finalize", END)
        return graph.compile(checkpointer=self.checkpointer)

    @staticmethod
    def _continue_or_end(state: SQLGenerationState) -> str:
        return "end" if state.get("response") is not None else "continue"

    def _retrieve_schema(self, state: SQLGenerationState) -> dict[str, Any]:
        # 標準化與清理request
        # 根據doc撈出可用的views
        self._emit('load terms mapping', '讀取來源詞彙對應')
        try:
            snapshot = self.repository.read()
        except MappingStoreError:
            return {'response': self._store_error()}
        matches = [m for m in snapshot.mappings if m.status == 'active'
                   and normalize_term(m.term) in normalize_term(state['request'])
                   and m.view in {v.name for v in self.catalog.views()}
                   and m.column in self.catalog.columns(m.view)
                   and m.view_contract_fingerprint == view_fingerprint(self.catalog, m.view)]
        named = [v.name for v in self.catalog.views() if v.name in state['request']]
        if not named:
            by_term = {}
            for m in matches:
                by_term.setdefault(m.normalized_term, set()).add(m.view)
            if any(len(views) > 1 for views in by_term.values()):
                return {'response': SQLGenerationResponse(supported=False, code='ambiguous_source',
                    explanation='相同詞彙有多個來源，請指定 View 後重新提問。',
                    selected_views=sorted({m.view for m in matches}))}
        if len(named) > 1:
            return {'response': self._unsupported('單一問題只支援一個 View。', named)}
        if (re.search(r'上一題|剛才|剛剛|前一題', state['request']) and not named
                and not any(name in state['request'] for v in self.catalog.views()
                            for column in self.catalog.columns(v.name)
                            for name in [column, *self.catalog.field_contract(v.name, column).get('aliases', [])])):
            return {'response': SQLGenerationResponse(supported=False, code='history_not_supported',
                explanation='目前每次只處理一個完整問題，請重新提供條件。')}
        search = 'vector' if self.settings.retrieval_mode == 'vector' else 'lexical'
        self._emit(f'{search} search', '搜尋候選 View')
        if isinstance(self.retriever, SchemaRetriever):
            result = self.retriever.retrieve(state["request"], limit=max(5, self.settings.rerank_top_k))
        else:
            result = self.retriever.retrieve(state["request"])
        self._emit(f'{search} search candidate views',
            [str(item.document.metadata['document_id']) for item in result.candidates])
        if not result.candidates:
            required = explicit_column_references(state['request'], self.catalog)
            if required:
                return {'rejection_stage': 'retrieval', 'response': self._unsupported(
                    '檢索未找到同時包含明確指定欄位的核准 View。', sorted(required))}
        # Confirmed sources enter the same allowlist/budget admission path.
        candidate_ids = {c.document.metadata['document_id'] for c in result.candidates}
        for m in matches:
            if (not named or m.view in named) and m.view not in candidate_ids:
                definition = next(v for v in self.catalog.views() if v.name == m.view)
                result.candidates.insert(0, RetrievalCandidate(document=Document(
                    page_content=json.dumps(candidate_schema(definition), ensure_ascii=False),
                    metadata={'document_id': m.view, 'source': 'catalog', 'filename': m.view,
                              'chunk_id': m.view}), retrieval_score=1.0))
                candidate_ids.add(m.view)
        if named:
            result.candidates[:] = [c for c in result.candidates if c.document.metadata['document_id'] in named]
        # 本功能不帶入歷史；保留原有 budget 介面。
        history_context = self.context_packer.pack_history(state["request"], state.get("history", []))
        # 根據context budget設定,篩選並打包成PackedContext dto
        admitted: list[RetrievalCandidate] = []
        sources: list[SourceReference] = []
        context_tokens = 0
        document_budget = 0
        for candidate in result.candidates:
            packed = self.context_packer.pack_documents(
                system_prompt=self.match_prompt.system, question=state["request"],
                history_text=history_context, candidates=[candidate],
            )
            document_budget = packed.document_budget
            if packed.sources:
                admitted.append(candidate)
                sources.extend(packed.sources)
                context_tokens = max(context_tokens, packed.context_tokens)
        if not admitted:
            return {"rejection_stage": "retrieval", "response": self._unsupported(
                "Context budget 無法容納任何候選 schema。", ["請提高 context window 或縮短 schema 文件。"],
                retrieval_latency_ms=result.retrieval_latency_ms,
                reranker_latency_ms=result.reranker_latency_ms,
                context_budget=document_budget,
            )}
        self._emit('context budget candidate views', {
            'views': [str(item.document.metadata['document_id']) for item in admitted],
            'context_tokens': context_tokens, 'context_budget': document_budget})
        return {
            "snapshot": snapshot.model_copy(update={"mappings": matches}),
            "history_context": history_context,
            "candidates": admitted,
            "retrieved_candidates": [self.context_packer.source_reference(item) for item in result.candidates],
            "sources": sources,
            "retrieval_latency_ms": result.retrieval_latency_ms,
            "reranker_latency_ms": result.reranker_latency_ms,
            "context_tokens": context_tokens,
            "context_budget": document_budget,
        }

    def _match_candidates(self, state: SQLGenerationState) -> dict[str, Any]:
        request = state["request"]
        definitions = {item.name: item for item in self.catalog.views()}
        schemas = {str(item.document.metadata["document_id"]):
                   candidate_schema(definitions[str(item.document.metadata["document_id"])])
                   for item in state["candidates"]}
        detailed = [RetrievalCandidate(
            document=Document(id=item.document.id,
                              page_content=json.dumps(schemas[str(item.document.metadata["document_id"])], ensure_ascii=False),
                              metadata=item.document.metadata),
            retrieval_score=item.retrieval_score, reranker_score=item.reranker_score,
        ) for item in state["candidates"]]
        response_model = self.match_prompt.response_model
        attempts: list[CandidateAttempt] = list(state.get('candidate_attempts', []))
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.match_prompt.system),
            ("human", self.match_prompt.human),
        ])
        facts: list[QueryFact] = []
        mapping_attempts: list[MappingAttempt] = list(state.get('mapping_attempts', []))
        successful: list[tuple[str, dict[str, Any], dict[str, Any], int]] = []
        failure_stage = "schema_linking"
        pending = [(candidate, None) for candidate in detailed]
        while pending:
            candidate, repair = pending.pop(0)
            failure_stage = "schema_linking"
            candidate_view = str(candidate.document.metadata["document_id"])
            candidate_schema_data = schemas[candidate_view]
            response_schema = response_schema_for(response_model,
                column_names=set(candidate_schema_data["columns"]), view_names={candidate_view})
            context = {"candidates": [candidate_schema_data]}
            if self.match_prompt.version != "v4":
                context["response_schema"] = response_schema
            if self.match_prompt.version == 'v10':
                context['confirmed_term_mappings'] = [m.model_dump() for m in state['snapshot'].mappings
                    if m.status == 'active' and m.view == candidate_view
                    and normalize_term(m.term) in normalize_term(request)
                    and m.view_contract_fingerprint == view_fingerprint(self.catalog, m.view)]
            if repair is not None:
                context["repair"] = repair
            packed = self.context_packer.pack_documents(
                system_prompt=self.match_prompt.system, question=request, history_text="",
                candidates=[candidate],
                additional_prompt_text=(json.dumps({**context, 'candidates': []}, ensure_ascii=False)
                                        if self.match_prompt.version != "v4" else ""),
            )
            if not packed.sources:
                attempts.append(CandidateAttempt(view=candidate_view, outcome="context_budget",
                                                 errors=["完整 View contract 超出 context budget"]))
                continue
            variables = {"request": request, "schema_context": json.dumps(context, ensure_ascii=False)}
            self._emit('repair candidate mapping' if repair is not None else 'match candidate view',
                {'view': candidate_view, 'attempt': 2 if repair is not None else 1})
            try:
                mapping = self._invoke_model(prompt, variables, response_model, response_schema=response_schema,
                    on_parse_error=lambda exc: mapping_attempts.append(MappingAttempt(
                        attempt_index=len(mapping_attempts) + 1, outcome="parse_error", reason=str(exc))))
            except ValueError as exc:
                self._emit('validate candidate mapping', {'view': candidate_view, 'status': '格式驗證未通過'})
                attempts.append(CandidateAttempt(view=candidate_view, outcome="schema_mismatch", errors=[str(exc)]))
                continue
            mapping_attempts.append(MappingAttempt(attempt_index=len(mapping_attempts) + 1,
                                                   mapping=mapping, outcome="rejected"))
            if isinstance(mapping.table, list):
                self._emit('validate candidate mapping', {'view': candidate_view, 'status': '草稿包含多個 View，拒絕'})
                mapping_attempts[-1].reason = "multiple Views selected"
                attempts.append(CandidateAttempt(view=candidate_view, outcome="schema_mismatch",
                                                 errors=["multiple Views selected"]))
                failure_stage = "schema_selection"
                continue
            if mapping.table is None and getattr(mapping, 'candidate_view', None) == candidate_view:
                from cpea.workflows.text_to_sql.schemas import ClauseTable
                mapping = mapping.model_copy(update={'table': ClauseTable(view=candidate_view)})
            if (mapping.table is None or mapping.table.view != candidate_view
                    or (mapping.table.text and mapping.table.text != mapping.table.view and mapping.table.text not in request)):
                attempts.append(CandidateAttempt(
                    view=candidate_view,
                    outcome="schema_mismatch", unresolved=[request],
                    errors=[mapping.unsupported_reason or "table mapping does not match the request and selected View"]))
                mapping_attempts[-1].reason = mapping.unsupported_reason or "table mismatch"
                self._emit('validate candidate mapping', {'view': candidate_view, 'status': '草稿未選定此 View'})
                continue
            view = mapping.table.view
            for term in getattr(mapping, 'terms', []):
                items = getattr(mapping, term.clause, [])
                if (term.index < len(items) and items[term.index].text not in request
                        and 0 <= term.start < term.end <= len(request)
                        and request[term.start:term.end] == term.term):
                    items[term.index].text = term.term
            schema = candidate_schema_data
            facts_by_text: dict[str, QueryFact] = {}
            links: list[SchemaLink] = []
            grouped = {item.column for item in mapping.group}
            for item in mapping.criteria:
                facts_by_text.setdefault(item.text, QueryFact(kind="entity", text=item.text))
                links.append(SchemaLink(fact_text=item.text, view=view, column=item.column,
                                        role="filter", operator=item.operator, value=item.value))
            for item in getattr(mapping, "having", []):
                facts_by_text.setdefault(item.text, QueryFact(kind="constraint", text=item.text))
                links.append(SchemaLink(fact_text=item.text, view=view, column=item.column,
                                        role="having", aggregation=item.aggregation,
                                        operator=item.operator, value=item.value))
            for item in [*mapping.fields, *mapping.group]:
                fact_text = item.text
                if fact_text not in request and item in mapping.fields:
                    if item.column in {criterion.column for criterion in mapping.criteria} or item.column in grouped:
                        continue
                    if item.column in schema["columns"]:
                        names = [item.column, *self.catalog.field_contract(view, item.column).get("aliases", [])]
                        fact_text = next((name for name in names if name in request), fact_text)
                role = "dimension" if item.column in grouped else "metric"
                facts_by_text.setdefault(fact_text, QueryFact(kind=role, text=fact_text))
                link = SchemaLink(fact_text=fact_text, view=view, column=item.column, role=role,
                                  aggregation=getattr(item, "aggregation", None))
                if link not in links:
                    links.append(link)
            draft = SchemaLinkDraft(
                supported=True, facts=list(facts_by_text.values()), links=links,
                explanation="；".join(f"{item.text}：{item.reason}" for item in mapping.ignored),
            )
            facts = draft.facts
            errors = self._link_errors(facts, draft, view, request)
            if mapping.unsupported_reason:
                errors.append("selected View cannot also declare an unsupported reason")
            for item in mapping.ignored:
                if re.search(r"(?:合計|總和|加總|平均|最大|最小|單列|分組|排序|篩選|條件|大於|小於|超過|低於|至少|以上|以下|[<>]=?)", item.text):
                    errors.append(f"required request clause cannot be ignored: {item.text}")
            if not mapping.fields:
                errors.append("fields mapping is empty")
            if getattr(mapping, "having", []) and not mapping.group:
                errors.append("HAVING requires GROUP BY")
            if (self.match_prompt.version in {"v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10"} and
                    re.search(r"(?:只保留|只顯示).*(?:合計|總和|平均).*(?:大於|小於|超過|低於|至少|以上|以下|[<>]=?)", request)
                    and not mapping.having):
                errors.append("missing HAVING aggregate threshold")
            if getattr(mapping, "having", []) and re.search(r"(?:\bOR\b|或者|或是|或\s*者|COUNT\s*\(\s*\*\s*\))", request, re.IGNORECASE):
                errors.append("unsupported HAVING expression")
            for item in getattr(mapping, "having", []):
                if not re.search(r"(?:合計|總和|加總|累計|平均|最大|最小|聚合後|分組後|\b(?:SUM|COUNT|AVG|MAX|MIN)\b)",
                                 item.text, re.IGNORECASE):
                    errors.append(f"HAVING requires an explicit aggregate threshold; use criteria for row filters: {item.text}")
            if any(re.search(r"(?:合計|總和|平均|計數|筆數).*(?:大於|小於|超過|低於|至少|以上|以下|[<>]=?)", item.text)
                   for item in mapping.criteria):
                errors.append("aggregate threshold cannot be a WHERE criterion")
            for item in [*mapping.order, *mapping.group, *mapping.ignored]:
                if not item.text or item.text not in request:
                    errors.append(f"mapped text absent from request: {item.text}")
            if any(item.column not in schema["columns"] for item in mapping.order):
                errors.append("order column is not in selected View")
            missing_literals = unmapped_request_literals(request, mapping, self.catalog, view)
            if missing_literals:
                errors.append("unmapped request literals: " + ", ".join(missing_literals))
            outcome = "schema_mismatch"
            if not errors:
                selected = {"semantic_retry": False, "request_facts": facts, "selected_mapping_index": len(mapping_attempts),
                            "clause_mapping": mapping,
                            "view_contract_fingerprint": view_fingerprint(self.catalog, view),
                            "selected_views": [view], "links": draft,
                            "order_by": [item.column for item in mapping.order],
                            "order_directions": {item.column: item.direction for item in mapping.order
                                                 if item.direction != "asc"},
                            "having": [HavingFilter(column=item.column, aggregation=item.aggregation,
                                                    operator=item.operator, value=item.value)
                                       for item in getattr(mapping, "having", [])],
                            "sources": [source for source in packed.sources if source.document_id == view],
                            "context_tokens": packed.context_tokens, "context_budget": packed.document_budget}
                candidate_state = {**state, **selected}
                if self.match_prompt.version == 'v10':
                    plan = self._draft_plan(candidate_state)
                    if isinstance(plan, dict):
                        compiled = plan
                    else:
                        plan_stage = 'query_plan'
                        plan_errors = self._plan_errors(plan, candidate_state)
                        if not plan_errors:
                            try:
                                validate_single_view_plan(plan, self.catalog, max_rows=self.settings.max_rows, request=request)
                            except SQLPolicyError as exc:
                                plan_errors = [str(exc)]
                                plan_stage = 'sql_compilation'
                        if not plan_errors:
                            uses, _, plan_errors = assess(request, mapping, self.catalog, view, state['snapshot'])
                            if plan_errors:
                                plan_stage = 'semantic_validation'
                        if not plan_errors:
                            missing = [use for use in uses
                                       if requires_resolution(mapping, use['term'], self.catalog, view)]
                            if missing:
                                try:
                                    resolved = self._resolve_clarifications(candidate_state, missing)
                                except ValueError as exc:
                                    return {**selected, 'candidate_attempts': attempts,
                                        'mapping_attempts': mapping_attempts,
                                        'response': SQLGenerationResponse(status='error', supported=False,
                                            code='clarification_generation_failed',
                                            explanation='暫時無法整理確認選項，請稍後再試。', limitations=[str(exc)])}
                                if resolved is None:
                                    reason = 'source cannot preserve the requested business object, grain or conditions'
                                    mapping_attempts[-1].reason = reason
                                    attempts.append(CandidateAttempt(view=view, outcome='schema_mismatch', errors=[reason]))
                                    self._emit('reject semantic source', {'view': view, 'reason': reason})
                                    continue
                                mapping = resolved
                                selected['clause_mapping'] = mapping
                                mapping_attempts[-1].mapping = mapping
                            mapping_attempts[-1].outcome = 'candidate'
                            attempts.append(CandidateAttempt(view=view, outcome='matched', facts=facts, links=draft.links))
                            self._emit('selected columns', {'view': view,
                                'fields': [{'column': item.column, 'aggregation': item.aggregation} for item in mapping.fields],
                                'criteria': [item.column for item in mapping.criteria],
                                'having': [item.column for item in mapping.having],
                                'group': [item.column for item in mapping.group],
                                'order': [item.column for item in mapping.order]})
                            self._emit('validate query plan', '通過欄位能力、篩選與聚合檢查')
                            successful.append((view, selected, {}, len(mapping_attempts) - 1))
                            continue
                        compiled = {'rejection_stage': plan_stage,
                                    'response': self._unsupported('核准的 Schema Links 無法組成安全查詢。', plan_errors)}
                else:
                    compiled = self._compile_query(candidate_state)
                if compiled["response"].supported:
                    mapping_attempts[-1].outcome = "candidate"
                    attempts.append(CandidateAttempt(view=view, outcome="matched", facts=facts, links=draft.links))
                    successful.append((view, selected, compiled, len(mapping_attempts) - 1))
                    continue
                errors = compiled["response"].limitations
                failure_stage = compiled["rejection_stage"]
                outcome = "validation_failed"
            attempts.append(CandidateAttempt(view=view, outcome=outcome, facts=facts,
                                             links=draft.links, unresolved=[*draft.unresolved_facts, *missing_literals], errors=errors))
            mapping_attempts[-1].reason = "; ".join(errors)
            self._emit('validate candidate mapping', {'view': view, 'status': '未通過',
                'error_count': len(errors), 'errors': errors})
            if repair is None:
                pending.insert(0, (candidate, {
                    "previous_mapping": mapping.model_dump(mode="json"),
                    "validation_errors": errors,
                    "instruction": "Revise the mapping for this same View using its contract and the original request. "
                                   "Fix the validation errors without dropping required request items. "
                                   "If the View cannot satisfy the request, return table=null with a specific reason.",
                }))
        if successful:
            choice = state.get("clarification_choice")
            if choice and choice.contract_fingerprint != self.catalog.fingerprint:
                return {"candidate_attempts": attempts, "mapping_attempts": mapping_attempts,
                        "rejection_stage": "schema_selection", "response": self._unsupported(
                            "View 契約已更新，請重新提出問題。", ["待確認選項的契約版本已過期。"])}
            selected_view: str | None = successful[0][0] if len(successful) == 1 else None
            clarification: ClarificationRequest | None = None
            if len(successful) > 1:
                selected_view, clarification = self._compare_valid_candidates(request, schemas, successful)
            if choice:
                if clarification is None or choice.option_id not in {item.id for item in clarification.options}:
                    return {"candidate_attempts": attempts, "mapping_attempts": mapping_attempts,
                            "rejection_stage": "schema_selection", "response": self._unsupported(
                                "待確認選項已失效，請重新提出問題。", ["選項不在目前有效的歧義候選中。"])}
                selected_view = choice.option_id
                clarification = None
            if clarification is not None:
                return {"candidate_attempts": attempts, "mapping_attempts": mapping_attempts,
                        "rejection_stage": "clarification", "response": SQLGenerationResponse(
                            supported=False, status="needs_clarification", explanation=clarification.question,
                            clarification=clarification, retrieved_candidates=state.get("retrieved_candidates", []),
                            retrieval_latency_ms=state.get("retrieval_latency_ms", 0.0),
                            reranker_latency_ms=state.get("reranker_latency_ms", 0.0))}
            winner = next(item for item in successful if item[0] == selected_view)
            mapping_attempts[winner[3]].outcome = "selected"
            return {**winner[1], **winner[2], "candidate_attempts": attempts,
                    "mapping_attempts": mapping_attempts}
        reasons = [f"{attempt.view}: {', '.join(attempt.errors or attempt.unresolved)}" for attempt in attempts]
        return {"request_facts": facts, "candidate_attempts": attempts,
                "mapping_attempts": mapping_attempts, "rejection_stage": failure_stage,
                "response": self._unsupported(
                    "單一查詢任務只支援一個 View。" if failure_stage == "schema_selection"
                    else "沒有單一 View 能完整承接需求。", reasons)}

    def _compare_valid_candidates(self, request: str, schemas: dict[str, dict[str, Any]],
                                  successful: list[tuple[str, dict[str, Any], dict[str, Any], int]]
                                  ) -> tuple[str | None, ClarificationRequest | None]:
        names = {item[0] for item in successful}
        explicitly_named = [name for name in names if name in request]
        if len(explicitly_named) == 1:
            return explicitly_named[0], None
        evidence = []
        for view, selected, _, _ in successful:
            schema = schemas[view]
            columns = schema["columns"]
            evidence.append({"view": view, "summary": schema["summary"],
                             "grain": schema.get("grain"), "temporal_scope": schema.get("temporal_scope"),
                             "data_scope": schema.get("data_scope"), "term_mappings": schema.get("term_mappings"),
                             "scope_rules": schema.get("scope_rules"),
                             "mapped_fields": [{"request_text": link.fact_text, "role": link.role,
                                                "aggregation": link.aggregation,
                                                "description": columns[link.column]["description"]}
                                               for link in selected["links"].links
                                               if link.column in columns]})
        def signature(item: dict[str, Any]) -> str:
            return json.dumps({
                "summary": item["summary"], "grain": item["grain"],
                "temporal_scope": item["temporal_scope"], "data_scope": item["data_scope"],
                "term_mappings": item["term_mappings"], "scope_rules": item["scope_rules"],
                "mapped_fields": sorted(item["mapped_fields"], key=lambda field:
                                        (field["request_text"], field["role"], field["description"])),
            }, ensure_ascii=False, sort_keys=True)
        if len({signature(item) for item in evidence}) == 1:
            return successful[0][0], None
        # A mapped request phrase that appears in only one contract is stronger
        # evidence than the model's general preference between compatible Views.
        contract_texts = {item["view"]: json.dumps({
            "summary": item["summary"], "grain": item["grain"],
            "temporal_scope": item["temporal_scope"], "data_scope": item["data_scope"],
            "term_mappings": item["term_mappings"], "scope_rules": item["scope_rules"],
            "mapped_field_descriptions": [field["description"] for field in item["mapped_fields"]],
        }, ensure_ascii=False) for item in evidence}
        exact_matches = set()
        for item in evidence:
            view = item["view"]
            if any(len(field["request_text"]) >= 4
                   and field["request_text"] in request
                   and field["request_text"] in contract_texts[view]
                   and all(field["request_text"] not in text for other_view, text in contract_texts.items()
                           if other_view != view)
                   for field in item["mapped_fields"]):
                exact_matches.add(view)
        if len(exact_matches) == 1:
            return exact_matches.pop(), None
        prompt = ChatPromptTemplate.from_messages([
            ("system", COMPARE_SYSTEM),
            ("human", "問題：{request}\n候選證據：{candidates}"),
        ])
        try:
            result = self._invoke_model(prompt, {"request": request,
                "candidates": json.dumps(evidence, ensure_ascii=False)}, ViewComparison)
        except ValueError:
            result = None
        if (result is not None and result.decision == "select" and result.selected_view in names
                and result.request_evidence and result.request_evidence in request
                and result.contract_evidence
                and result.contract_evidence in contract_texts[result.selected_view]
                and result.request_evidence in contract_texts[result.selected_view]
                and all(result.request_evidence not in text for view, text in contract_texts.items()
                        if view != result.selected_view)):
            return result.selected_view, None
        labels = {item["view"]: item for item in evidence}
        def grain_label(item: dict[str, Any]) -> str:
            grain = item.get("grain")
            if isinstance(grain, dict):
                return str(grain.get("description") or item["summary"])
            return str(grain or item["summary"])
        default_options = [ClarificationOption(id=view,
            label=grain_label(labels[view]),
            description=labels[view]["summary"]) for view, *_ in successful]
        options = default_options
        if (result is not None and result.decision == "clarify" and len(result.options) == len(names)
                and {item.id for item in result.options} == names):
            options = result.options
        question = (result.question if result is not None and result.decision == "clarify"
                    and result.question else "你要以哪一種業務粒度與口徑查詢？")
        return None, ClarificationRequest(original_request=request,
            contract_fingerprint=self.catalog.fingerprint, question=question, options=options)

    @staticmethod
    def _semantic_route(state):
        if state.get('response') is not None:
            return 'end'
        if state.get('semantic_retry'):
            return 'retry'
        return 'confirm' if state.get('clarification') else 'compile'

    @staticmethod
    def _store_error():
        return SQLGenerationResponse(status='error', supported=False, code='terms_mapping_store_error',
            explanation='詞彙對應檔案無法讀取或保存，未執行查詢；請修正儲存問題後重新提問。')

    def _assess_semantics(self, state):
        self._emit('check field semantics', '核對完整詞彙、欄位契約與既有確認紀錄')
        plan = self._draft_plan(state)
        if isinstance(plan, dict):
            return plan
        hard_errors = self._plan_errors(plan, state)
        if hard_errors:
            return {'response': self._unsupported('核准的 Schema Links 無法組成安全查詢。', hard_errors)}
        all_uses = []
        uses, reused, errors = assess(state['request'], state['clause_mapping'], self.catalog,
                                      state['selected_views'][0], state['snapshot'], all_uses=all_uses)
        if errors:
            self._emit('check field semantics', {'status': '未通過', 'error_count': len(errors)})
            return {'response': self._unsupported('原始需求尚有無法安全承接的內容。', errors)}
        result = {'used_mappings': reused, 'reasoning': [self._reason(m, 'reused_confirmation') for m in reused],
                  'semantic_uses': all_uses, 'clarification': None}
        if reused:
            self._emit('reuse terms mapping', [{'term': item.term, 'view': item.view,
                'column': item.column, 'source': 'reused_confirmation'} for item in reused])
        if uses:
            view = state['selected_views'][0]
            missing = [use for use in uses if self.match_prompt.version == 'v10'
                       and requires_resolution(state['clause_mapping'], use['term'], self.catalog, view)]
            if missing:
                try:
                    mapping = self._resolve_clarifications(state, missing)
                except ValueError as exc:
                    return {**result, 'response': SQLGenerationResponse(status='error', supported=False,
                        code='clarification_generation_failed',
                        explanation='暫時無法整理確認選項，請稍後再試。', limitations=[str(exc)])}
                if mapping is None:
                    return self._reject_semantic_source(state)
                state = {**state, 'clause_mapping': mapping}
                result['clause_mapping'] = mapping
                # Keep the actual, resolved proposal in the developer trace.
                attempts = [attempt.model_copy(deep=True) for attempt in state.get('mapping_attempts', [])]
                selected = state.get('selected_mapping_index')
                for attempt in attempts:
                    if attempt.attempt_index == selected:
                        attempt.mapping = mapping
                result['mapping_attempts'] = attempts
            result['clarification'] = self._make_clarification(state, uses)
            if len(result['clarification'].items) != len({normalize_term(u['term']) for u in uses}):
                offered = {normalize_term(item.term) for item in result['clarification'].items}
                unresolved = list(dict.fromkeys(u['term'] for u in uses if normalize_term(u['term']) not in offered))
                result['response'] = SQLGenerationResponse(supported=False, code='clarification_rephrase',
                    explanation='請補充「' + '」、「'.join(unresolved) + '」的統計對象或計算口徑。',
                    limitations=['clarification_unavailable: ' + term for term in unresolved])
                result['clarification'] = None
            elif result.get('response') is None:
                result.update(self._adopt_single_choices({**state, **result}))
        if result.get('clarification') is not None:
            self._emit('HILP required', [{'term': item.term, 'view': item.view,
                'candidates': [option.column for option in item.options if option.column]}
                for item in result['clarification'].items])
        elif result.get('response') is None:
            self._emit('check field semantics', '通過，無待確認欄位')
        return result

    def _adopt_single_choices(self, state):
        """Adopt unique validated meanings for this request, without recording consent."""
        clarification = state['clarification']
        active = self.repository.read().active()
        automatic, pending = [], []
        for item in clarification.items:
            choices = [option for option in item.options if option.column is not None]
            current = active.get((normalize_term(item.term), item.view))
            if len(choices) == 1 and (current is None or current.column == choices[0].column):
                automatic.append((item, choices[0]))
            else:
                pending.append(item)
        if not automatic:
            return {}
        choices = {normalize_term(item.term): option.column for item, option in automatic}
        mapping = state['clause_mapping'].model_copy(deep=True)
        for use in state['semantic_uses']:
            if normalize_term(use['term']) in choices:
                getattr(mapping, use['clause'])[use['index']].column = choices[normalize_term(use['term'])]
        mapped = self._mapped_state(mapping, state)
        candidate = {**state, **mapped, 'clause_mapping': mapping}
        if mapped.get('response') is not None:
            return {**mapped, 'clarification': None}
        plan = self._draft_plan(candidate)
        if isinstance(plan, dict):
            return {**plan, 'clarification': None}
        errors = self._plan_errors(plan, candidate)
        errors.extend(assess(state['request'], mapping, self.catalog,
                             state['selected_views'][0], state['snapshot'])[2])
        try:
            validate_single_view_plan(plan, self.catalog, max_rows=self.settings.max_rows, request=state['request'])
        except SQLPolicyError as exc:
            errors.append(str(exc))
        if errors:
            return {'clarification': None, 'response': self._unsupported('詞彙對應無法完整保留原始需求。', errors)}
        reasoning = [*state.get('reasoning', []), *[
            TermMappingReasoning(term=item.term, view=item.view, column=option.column,
                source='automatically_resolved', description=option.description,
                reason='排除不相關或不合法候選後，僅剩一個符合本題的業務含義；只用於本次查詢。')
            for item, option in automatic]]
        self._emit('check field semantics', '已自動採用唯一符合條件的業務含義')
        return {**mapped, 'clause_mapping': mapping, 'reasoning': reasoning,
                'semantic_uses': [{**use, 'column': choices.get(normalize_term(use['term']), use['column'])}
                                  for use in state['semantic_uses']],
                'clarification': clarification.model_copy(update={'items': pending}) if pending else None}

    def _reject_semantic_source(self, state):
        """A grain failure rejects this source, not the remaining candidates."""
        view = state['selected_views'][0]
        reason = 'source cannot preserve the requested business object, grain or conditions'
        self._emit('reject semantic source', {'view': view, 'reason': reason})
        candidates = [candidate for candidate in state['candidates']
                      if candidate.document.metadata['document_id'] != view]
        attempts = [attempt.model_copy(deep=True) for attempt in state.get('candidate_attempts', [])]
        for attempt in attempts:
            if attempt.view == view and attempt.outcome == 'matched':
                attempt.outcome = 'schema_mismatch'
                attempt.errors.append(reason)
        mappings = [attempt.model_copy(deep=True) for attempt in state.get('mapping_attempts', [])]
        for attempt in mappings:
            if attempt.attempt_index == state.get('selected_mapping_index'):
                attempt.outcome, attempt.reason = 'rejected', reason
        return {'candidates': candidates, 'candidate_attempts': attempts, 'mapping_attempts': mappings,
                'selected_views': [], 'selected_mapping_index': None, 'semantic_retry': True,
                'response': None, 'clarification': None, 'used_mappings': [], 'reasoning': []}

    def _resolve_clarifications(self, state, uses):
        """Repair missing choice metadata once, without remapping the query."""
        self._emit('resolve semantic choices', '整理待確認詞彙的相關業務選項')
        view = state['selected_views'][0]
        grouped = {}
        for use in uses:
            grouped.setdefault(normalize_term(use['term']), []).append(use)
        required = [{'term': group[0]['term'],
                     'uses': [getattr(state['clause_mapping'], use['clause'])[use['index']].model_dump()
                              for use in group],
                     'eligible_columns': [column for column in self.catalog.columns(view)
                                          if self._candidate_allowed(state, group, column)]}
                    for group in grouped.values()]
        definition = next(item for item in self.catalog.views() if item.name == view)
        context = {'contract': candidate_schema(definition), 'required_terms': required}
        schema = response_schema_for(ClarificationResolution, column_names=set(self.catalog.columns(view)))
        prompt = ChatPromptTemplate.from_messages([
            ('system', RESOLUTION_PROMPT), ('human', '需求: {request}\n語意確認資料: {context}')])
        resolution = self._invoke_model(prompt, {'request': state['request'],
            'context': json.dumps(context, ensure_ascii=False)}, ClarificationResolution, response_schema=schema)
        if not resolution.source_compatible:
            return None
        resolved_terms = [normalize_term(item.term) for item in resolution.clarifications]
        if len(resolved_terms) != len(grouped) or set(resolved_terms) != set(grouped):
            raise ValueError('semantic resolution must cover exactly the required terms')
        eligible = {normalize_term(item['term']): set(item['eligible_columns']) for item in required}
        for proposal in resolution.clarifications:
            if any(option.column not in eligible[normalize_term(proposal.term)] for option in proposal.options):
                raise ValueError('semantic resolution proposed an ineligible column')
        retained = [item for item in state['clause_mapping'].clarifications
                    if normalize_term(item.term) not in grouped]
        mapping = state['clause_mapping'].model_copy(update={
            'clarifications': [*retained, *resolution.clarifications]})
        if any(requires_resolution(mapping, group[0]['term'], self.catalog, view) for group in grouped.values()):
            raise ValueError('semantic resolution contains invalid evidence or business labels')
        return mapping

    def _reason(self, record, source):
        reason = ('本次使用者確認此完整詞彙在此來源對應此欄位。' if source == 'confirmed_this_request'
                  else '沿用相同來源與欄位契約下，先前由使用者確認的完整詞彙對應。')
        return TermMappingReasoning(term=record.term, view=record.view, column=record.column,
            mapping_id=record.id, source=source, confirmed_at=record.confirmed_at,
            description=business_label(str(self.catalog.field_contract(record.view, record.column).get('description', '')), self.catalog) or '',
            reason=reason + '這項對應不代表已驗證稅額、發票或其他業務保證。')

    def _candidate_allowed(self, state, uses, column):
        view = state['selected_views'][0]
        mapping = state['clause_mapping']
        for use in uses:
            item = getattr(mapping, use['clause'])[use['index']]
            explicit = explicit_column_references(use['term'], self.catalog)
            if explicit and explicit != {column}:
                return False
            original = self.catalog.field_contract(view, item.column)
            candidate = self.catalog.field_contract(view, column)
            original_type = _LEGACY_COLUMN_TYPES.get(original['type'], original['type'])
            candidate_type = _LEGACY_COLUMN_TYPES.get(candidate['type'], candidate['type'])
            if original_type != candidate_type:
                return False
            if original.get('unit', '') != candidate.get('unit', ''):
                return False
            if original.get('role') and candidate.get('role') and original['role'] != candidate['role']:
                return False
            if use['clause'] == 'order':
                if 'order_by' not in self.catalog.field_contract(view, column).get('capabilities', []):
                    return False
                continue
            role = {'criteria': 'filter', 'having': 'having', 'group': 'dimension', 'order': 'metric'}.get(use['clause'],
                'dimension' if item.column in {g.column for g in mapping.group} else 'metric')
            link = SchemaLink(fact_text=item.text, view=view, column=column, role=role,
                aggregation=getattr(item, 'aggregation', None), operator=getattr(item, 'operator', None),
                value=getattr(item, 'value', None))
            if self.catalog.validate_link(link, {view}):
                return False
        # Validate each proposed substitution against the whole request before
        # asking a user to choose it. This never compiles or executes SQL.
        replacement = mapping.model_copy(deep=True)
        for use in uses:
            getattr(replacement, use['clause'])[use['index']].column = column
        mapped = self._mapped_state(replacement, state)
        if mapped.get('response') is not None:
            return False
        candidate_state = {**state, **mapped, 'clause_mapping': replacement}
        plan = self._draft_plan(candidate_state)
        if isinstance(plan, dict) or self._plan_errors(plan, candidate_state):
            return False
        try:
            validate_single_view_plan(plan, self.catalog, max_rows=self.settings.max_rows, request=state['request'])
        except SQLPolicyError:
            return False
        return not assess(state['request'], replacement, self.catalog, view, state['snapshot'])[2]

    def _make_clarification(self, state, uses, *, conflicts=None):
        view = state['selected_views'][0]
        grouped = {}
        for use in uses:
            grouped.setdefault(normalize_term(use['term']), []).append(use)
        items, targets = [], {}
        active = self.repository.read().active()
        for normalized, group in grouped.items():
            term = group[0]['term']
            current = active.get((normalized, view))
            desired = group[0]['column']
            reason = '請選擇符合你原意的業務含義；確認後會記住這項選擇。'
            if conflicts is not None:
                labels = dict(semantic_choices(state['clause_mapping'], term, self.catalog, view))
                label = labels.get(desired) or business_label(
                    str(self.catalog.field_contract(view, desired).get('description', '')), self.catalog)
                choices = [(desired, label)] if label else []
                if current:
                    reason = '這個詞彙先前的選擇與本次不同，是否改用以下含義？'
                    targets[normalized] = current.id
                else:
                    reason = '本題沿用的對應已撤銷或變更，請重新確認。'
            else:
                choices = semantic_choices(state['clause_mapping'], term, self.catalog, view)
            options = [ConfirmationOption(id=token_urlsafe(24), column=column,
                description=label) for column, label in choices
                if self._candidate_allowed(state, group, column)]
            if not options or len(options) > MAX_BUSINESS_OPTIONS:
                continue
            options.append(ConfirmationOption(id=token_urlsafe(24), column=None, description='都不符合，重新描述'))
            items.append(ConfirmationItem(id=token_urlsafe(24), term=term, view=view, reason=reason, options=options))
        if conflicts is not None:
            state['replace_targets'] = targets
        run = self.registry.runs[state['run_id']]
        return Clarification(confirmation_id=token_urlsafe(32),
            expires_at=datetime.fromtimestamp(run.expires, timezone.utc).isoformat(),
            kind='replace_mapping' if conflicts is not None else 'field_mapping', items=items)

    def _confirm_fields(self, state):
        # Interrupt replays this node from its start. No file or DB side effects.
        clarification = state['clarification']
        payload = interrupt(clarification.model_dump())
        decisions = {d['item_id']: d['option_id'] for d in payload['decisions']}
        choices = {normalize_term(item.term): next(o.column for o in item.options
                   if o.id == decisions[item.id]) for item in clarification.items}
        self._emit('HILP confirmation', [{'term': item.term, 'view': item.view,
            'column': choices[normalize_term(item.term)]} for item in clarification.items])
        if any(column is None for column in choices.values()):
            return {'clarification': None, 'response': SQLGenerationResponse(status='cancelled',
                    supported=False, code='clarification_rephrase', explanation='請修改原題的詞彙或補充說明，再送出查詢。')}
        mapping = state['clause_mapping'].model_copy(deep=True)
        for use in state['semantic_uses']:
            key = normalize_term(use['term'])
            if key in choices:
                getattr(mapping, use['clause'])[use['index']].column = choices[key]
        semantic_errors = assess(state['request'], mapping, self.catalog,
                                 state['selected_views'][0], state['snapshot'])[2]
        if semantic_errors:
            return {'clarification': None, 'response': self._unsupported(
                '確認後的欄位無法完整保留原始需求，請重新描述。', semantic_errors)}
        proposals = {m.key: m for m in state.get('proposals', [])}
        replacements = dict(state.get('replacements', {}))
        view = state['selected_views'][0]
        for item in clarification.items:
            key = normalize_term(item.term)
            column = choices[key]
            previous = proposals.get((key, view))
            proposals[(key, view)] = TermMapping(id=previous.id if previous and previous.column == column else token_urlsafe(24),
                term=item.term, normalized_term=key, view=view, column=column,
                view_contract_fingerprint=view_fingerprint(self.catalog, view),
                confirmed_at=datetime.now(timezone.utc).isoformat())
            if key in state.get('replace_targets', {}):
                replacements[key] = state['replace_targets'][key]
        result = self._mapped_state(mapping, state)
        result.update({'clause_mapping': mapping, 'proposals': list(proposals.values()),
                       'replacements': replacements, 'clarification': None,
                       'semantic_uses': [{**u, 'column': choices.get(normalize_term(u['term']), u['column'])} for u in state['semantic_uses']],
                       'used_mappings': [m for m in state.get('used_mappings', []) if m.normalized_term not in choices]})
        result['reasoning'] = [r for r in state.get('reasoning', []) if normalize_term(r.term) not in choices]
        return result

    def _mapped_state(self, mapping, state):
        view = state['selected_views'][0]
        grouped = {item.column for item in mapping.group}
        links, facts = [], {}
        for clause in ('fields', 'criteria', 'having', 'group'):
            for item in getattr(mapping, clause, []):
                role = {'criteria': 'filter', 'having': 'having'}.get(clause,
                    'dimension' if item.column in grouped else 'metric')
                facts.setdefault(item.text, QueryFact(kind={'filter': 'entity', 'having': 'constraint'}.get(role, role), text=item.text))
                link = SchemaLink(fact_text=item.text, view=view, column=item.column, role=role,
                    aggregation=getattr(item, 'aggregation', None), operator=getattr(item, 'operator', None),
                    value=getattr(item, 'value', None))
                if link not in links:
                    links.append(link)
        draft = SchemaLinkDraft(supported=True, facts=list(facts.values()), links=links)
        errors = self._link_errors(draft.facts, draft, view, state['request'])
        if errors:
            return {'response': self._unsupported('確認後的欄位仍須符合核准能力與原始條件。', errors)}
        return {'links': draft, 'request_facts': draft.facts, 'response': None,
                'order_by': [item.column for item in mapping.order],
                'order_directions': {item.column: item.direction for item in mapping.order if item.direction != 'asc'},
                'having': [HavingFilter(column=item.column, aggregation=item.aggregation, operator=item.operator,
                                       value=item.value) for item in getattr(mapping, 'having', [])]}

    def _persist_term_mappings(self, state):
        if state['response'].status != 'ready':
            return {'clarification': None}
        self._emit('persist terms mapping', '檢查並保存本題確認的詞彙對應')
        try:
            saved = self.repository.commit(state.get('proposals', []), used=state.get('used_mappings', []),
                replacements={(term, state['selected_views'][0]): ident for term, ident in state.get('replacements', {}).items()})
        except MappingConflict as conflict:
            view = state['selected_views'][0]
            uses = list(state.get('semantic_uses', []))
            keys = {normalize_term(u['term']) for u in uses}
            for record in conflict.records:
                if record.normalized_term not in keys:
                    for clause in ('fields', 'criteria', 'group', 'order', 'having'):
                        for index, item in enumerate(getattr(state['clause_mapping'], clause, [])):
                            if item.column == record.column:
                                uses.append({'term': record.term, 'column': record.column, 'clause': clause,
                                             'index': index, 'candidates': [record.column]})
            conflict_keys = {m.normalized_term for m in conflict.records}
            selected = [u for u in uses if normalize_term(u['term']) in conflict_keys]
            clarification = self._make_clarification(state, selected, conflicts=conflict.records)
            self._emit('HILP required', {'kind': 'replace_mapping', 'terms': [item.term for item in clarification.items]})
            if len(clarification.items) != len(conflict_keys):
                return {'response': self._unsupported('變更後沒有合法欄位可供確認，請重新提問。', []), 'clarification': None}
            return {'semantic_uses': uses, 'response': None, 'clarification': clarification,
                    'replace_targets': state.get('replace_targets', {})}
        except MappingStoreError:
            return {'response': self._store_error(), 'clarification': None}
        reasoning = [r for r in state.get('reasoning', []) if r.source == 'automatically_resolved']
        reasoning.extend(self._reason(m, 'reused_confirmation') for m in state.get('used_mappings', []))
        reasoning.extend(self._reason(m, 'confirmed_this_request') for m in saved)
        self._emit('persist terms mapping', {'saved': len(saved), 'reused': len(state.get('used_mappings', []))})
        return {'response': state['response'].model_copy(update={
                    'term_mapping_reasoning': list({(r.term, r.view, r.column): r for r in reasoning}.values())}),
                'clarification': None}

    def _link_errors(self, facts: list[QueryFact], draft: SchemaLinkDraft, view: str, request: str) -> list[str]:
        errors: list[str] = []
        if not draft.supported:
            errors.append("schema linking marked unsupported")
        errors.extend(draft.ambiguity)
        if not facts:
            errors.append("no request facts")
        if any(not fact.text or fact.text not in request for fact in facts):
            errors.append("fact absent from original request")
        if any(not fact.required for fact in facts):
            errors.append("explicit facts must be required")
        if len({fact.text for fact in facts}) != len(facts):
            errors.append("duplicate request facts")
        required = {fact.text for fact in facts if fact.required}
        definition = next(item for item in self.catalog.views() if item.name == view)
        for item in draft.view_satisfied:
            fact = next((fact for fact in facts if fact.text == item.fact_text), None)
            if (fact is None or fact.kind != "time" or not item.reason.strip()
                    or not definition.policy.get("temporal_scope")
                    or any(link.fact_text == item.fact_text for link in draft.links)):
                errors.append(f"invalid View-satisfied fact: {item.fact_text}")
        linked = {link.fact_text for link in draft.links} | {item.fact_text for item in draft.view_satisfied}
        if required - linked:
            errors.append("unlinked items: " + ", ".join(sorted(required - linked)))
        if draft.unresolved_facts:
            errors.append("unresolved items: " + ", ".join(draft.unresolved_facts))
        mappings = self.catalog.mapped_filters(request, [view])
        prohibited = {column for _, rule in self.catalog.matching_scope_rules(request, [view])
                      for column in rule.get("prohibited_filter_columns", [])}
        for mapping in mappings:
            if not any(link.role == "filter" and link.column == mapping["column"]
                       and link.operator == mapping["operator"] and link.value == mapping["value"]
                       for link in draft.links):
                errors.append(f"missing catalog mapping: {mapping['column']}")
        filter_values: dict[str, str] = {}
        for link in draft.links:
            if link.fact_text not in required or link.fact_text not in request:
                errors.append(f"link references unknown request item: {link.fact_text}")
            violation = self.catalog.validate_link(link, {view})
            if violation:
                errors.append(violation)
                continue
            if link.role == "dimension" and link.aggregation is not None:
                errors.append(f"dimension contains aggregation: {link.column}")
            if link.role == "filter":
                if link.column in prohibited:
                    errors.append(f"prohibited scope filter: {link.column}")
                fact = next((item for item in facts if item.text == link.fact_text), None)
                if fact and fact.kind in {"dimension", "metric"}:
                    errors.append(f"fact does not authorize a filter: {link.fact_text}")
                if link.aggregation is not None:
                    errors.append(f"filter contains aggregation: {link.column}")
                if not self._filter_is_grounded(link, request, mappings):
                    errors.append(f"ungrounded filter: {link.column} {link.value}")
                value = str(link.value)
                if link.column in filter_values and filter_values[link.column] != value:
                    errors.append(f"conflicting linked filters: {link.column}")
                filter_values[link.column] = value
            if link.role == "having":
                if not self._filter_is_grounded(link, request, mappings):
                    errors.append(f"ungrounded HAVING: {link.column} {link.value}")
        return list(dict.fromkeys(errors))

    def _filter_is_grounded(self, link: SchemaLink, request: str, mappings: list[dict[str, Any]]) -> bool:
        if any(link.column == item["column"] and link.operator == item["operator"]
               and link.value == item["value"] for item in mappings) and any(
                   link.column == item["column"] and link.operator == item["operator"]
                   and link.value == item["value"]
                   for item in self.catalog.mapped_filters(link.fact_text, [link.view])):
            return True
        values = link.value if isinstance(link.value, list) else [link.value]
        names = {link.column, *self.catalog.field_contract(link.view, link.column).get("aliases", [])}
        return bool(values) and all(
            value is not None and str(value) and str(value) in link.fact_text
            and str(value) not in names for value in values
        )

    def _draft_plan(self, state: SQLGenerationState) -> dict[str, Any]:
        view = state["selected_views"][0]
        columns: list[str] = []
        group_by: list[str] = []
        filters: list[QueryFilter] = []
        aggregations: dict[str, str] = {}
        for link in state["links"].links:
            if link.role == "filter":
                item = QueryFilter(column=link.column, operator=link.operator or "", value=link.value)
                if item not in filters:
                    filters.append(item)
                continue
            if link.role == "having":
                continue
            if link.column not in columns:
                columns.append(link.column)
            if link.role == "dimension" and link.column not in group_by:
                group_by.append(link.column)
            if link.aggregation:
                if link.column in aggregations and aggregations[link.column] != link.aggregation:
                    return {"rejection_stage": "query_plan", "response": self._unsupported(
                        "指標聚合定義衝突。", [f"conflicting aggregation: {link.column}"])}
                aggregations[link.column] = link.aggregation
        plan = QueryPlan(supported=True, source_views=[view], select_columns=columns,
                         filters=filters, having=state.get("having", []), group_by=group_by, aggregations=aggregations,
                         order_by=state.get("order_by", []),
                         order_directions=state.get("order_directions", {}),
                         explanation="由核准的 Schema Links 與 View 契約組成。")
        return plan

    def _compile_query(self, state: SQLGenerationState) -> dict[str, Any]:
        self._emit('compile SQL', {'view': state['selected_views'][0], 'status': '開始'})
        plan = self._draft_plan(state)
        if isinstance(plan, dict):
            return plan
        view = state['selected_views'][0]
        errors = self._plan_errors(plan, state)
        if errors:
            return {"plan": plan, "rejection_stage": "query_plan", "response": self._unsupported(
                "核准的 Schema Links 無法組成安全查詢。", errors)}
        try:
            sql = compile_single_view(plan, self.catalog, max_rows=self.settings.max_rows, request=state["request"])
        except SQLPolicyError as exc:
            return {"plan": plan, "rejection_stage": "sql_compilation", "response": self._unsupported(
                "Query Plan 無法編譯為安全的單一 View SQL。", [str(exc)])}
        try:
            validate_generated_sql(sql, {view})
        except SQLPolicyError as exc:
            return {"plan": plan, "compiled_sql": sql, "rejection_stage": "sql_validation", "response": self._unsupported(
                "產出的 SQL 未通過安全檢查。", [str(exc)])}
        response = SQLGenerationResponse(
            supported=True, sql=sql, selected_views=[view], explanation="由核准的 Query Plan 確定性編譯。",
            limitations=state["links"].limitations,
            sources=state.get("sources", []), retrieved_candidates=state.get("retrieved_candidates", []),
            context_tokens=state.get("context_tokens", 0), context_budget=state.get("context_budget", 0),
            retrieval_latency_ms=state.get("retrieval_latency_ms", 0.0),
            reranker_latency_ms=state.get("reranker_latency_ms", 0.0), query_plan=plan,
        )
        self._emit('validate SQL', '通過唯讀、單一 View 與筆數上限檢查')
        return {"plan": plan, "compiled_sql": sql, "response": response}

    def _plan_errors(self, plan: QueryPlan, state: SQLGenerationState) -> list[str]:
        errors: list[str] = []
        links = state["links"].links
        linked_columns = {link.column for link in links if link.role != "filter"}
        if not plan.select_columns:
            errors.append("Query Plan 沒有可選取欄位")
        if set(plan.select_columns) - linked_columns:
            errors.append("unlinked select columns")
        if set(plan.group_by) - {link.column for link in links if link.role == "dimension"}:
            errors.append("unlinked GROUP BY dimension")
        linked_filters = {(link.column, link.operator, str(link.value)) for link in links if link.role == "filter"}
        for item in plan.filters:
            if (item.column, item.operator, str(item.value)) not in linked_filters:
                errors.append(f"unlinked filter: {item.column}")
        linked_having = {(link.column, link.aggregation, link.operator, str(link.value))
                         for link in links if link.role == "having"}
        for item in plan.having:
            if (item.column, item.aggregation, item.operator, str(item.value)) not in linked_having:
                errors.append(f"unlinked HAVING: {item.column}")
        errors.extend(self.catalog.validate_plan_contract(plan, state["request"]))
        return errors

    def _finalize(self, state: SQLGenerationState) -> dict[str, Any]:
        response = state["response"]
        self._emit('generation result', {'status': response.status, 'views': response.selected_views})
        stage = state.get("rejection_stage")
        if not response.supported and not stage:
            stage = "sql_validation" if state.get("compiled_sql") else "query_plan" if state.get("plan") else "schema_linking"
        trace = QueryTaskTrace(
            request=state["request"], request_facts=state.get("request_facts", []),
            candidate_attempts=state.get("candidate_attempts", []),
            mapping_attempts=state.get("mapping_attempts", []),
            selected_mapping_index=state.get("selected_mapping_index"),
            mapping_unavailable_reason=("no mapping returned" if not state.get("mapping_attempts") else None),
            selected_view=next(iter(state.get("selected_views", [])), None),
            links=state.get("links"), plan=state.get("plan"),
            sql=response.sql,
            sources=state.get("sources", []), rejection_stage=stage,
            validation_errors=response.limitations if not response.supported else [],
        )
        return {"response": response.model_copy(update={"query_trace": trace})}

    def _invoke_model(self, prompt: ChatPromptTemplate, variables: dict[str, Any], model: type[Any], *,
                      response_schema=None, on_parse_error=None):
        serialized = {key: value.model_dump_json() if hasattr(value, "model_dump_json") else value
                      for key, value in variables.items()}
        messages = prompt.invoke(serialized).to_messages()
        response_llm = bind_response_schema(self.llm, model, schema=response_schema)
        last_error: ValueError | None = None
        for attempt in range(2):
            counter = self.context_packer.token_counter
            tokens = counter.count_messages([(message.type, str(message.content)) for message in messages])
            if tokens + self.settings.output_token_reserve + self.settings.context_safety_tokens > self.settings.context_window:
                raise ValueError("prompt exceeds context budget")
            try:
                raw = response_llm.invoke(messages)
                from cpea.infrastructure.llm.parsing import parse_model
                return parse_model(raw, model)
            except ValueError as exc:
                self._emit('parse model response', {'status': 'JSON 格式未通過', 'attempt': attempt + 1})
                last_error = exc
                if on_parse_error is not None:
                    on_parse_error(exc)
        raise last_error or ValueError("LLM did not return a structured response")

    @staticmethod
    def _unsupported(explanation: str, limitations: list[str], **metadata: Any) -> SQLGenerationResponse:
        return SQLGenerationResponse(supported=False, explanation=explanation, limitations=limitations, **metadata)


def candidate_schema(definition) -> dict[str, Any]:
    """Expose approved metadata only; samples and evaluation data never enter context."""
    from cpea.application.catalog_contract import CatalogContract
    class _SingleView(CatalogContract):
        def views(self):
            return [definition]
    contract = _SingleView()
    schema = {
        "view": definition.name, "summary": definition.summary,
        "columns": {name: {
            "data_type": _LEGACY_COLUMN_TYPES.get(spec["type"], spec["type"]),
            "description": spec["description"], "aliases": spec.get("aliases", []),
            "capabilities": contract.field_contract(definition.name, name).get("capabilities", []),
            "aggregations": contract.field_contract(definition.name, name).get("aggregations", []),
            **({"default_aggregation": spec["default_aggregation"]} if spec.get("default_aggregation") else {}),
            **({"role": spec["role"]} if "role" in spec else {}),
            **({"unit": spec["unit"]} if "unit" in spec else {}),
            **({key: spec[key] for key in ("disallowed_aggregations", "disallowed_operators", "disallowed_capabilities") if key in spec}),
        } for name, spec in definition.policy["columns"].items()},
    }
    if definition.policy.get('version') == 3:
        base = ['!=', '<>', '=', 'IN']
        schema['filter_operators'] = {
            'default': [*base, 'LIKE'],
            'number': [*base, '<', '<=', '>', '>='],
            'date': [*base, '<', '<=', '>', '>='],
            'columns': {
                name: sorted(contract._operators_for(definition.name, name))
                for name, spec in definition.policy['columns'].items()
                if spec['type'] == 'boolean' or spec.get('disallowed_operators')
            },
        }
    for key in ("temporal_scope", "data_scope", "grain", "filter_operators", "term_mappings", "scope_rules"):
        if definition.policy.get(key):
            schema[key] = definition.policy[key]
    return schema


def unmapped_request_literals(request, mapping, catalog, view) -> list[str]:
    """Prevent silent loss of explicit codes; this is not a natural-language parser."""
    token = re.compile(r"[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*")
    sql_words = {"SQL", "SELECT", "FROM", "WHERE", "HAVING", "ORDER", "BY", "GROUP", "JOIN",
                 "ASC", "DESC", "SUM", "COUNT", "AVG", "MIN", "MAX", "AND", "OR",
                 "IN", "LIKE", "NULL", "TOP", "DISTINCT"}
    # A number inside a mapped field name is part of that field's identity,
    # provided the contract itself uses the same number. Keep other occurrences
    # of that number in the request available for filter coverage checks.
    field_spans: list[tuple[int, int, set[str]]] = []
    definition = next(item for item in catalog.views() if item.name == view)
    for field in mapping.fields:
        spec = definition.policy["columns"].get(field.column)
        if not spec or not field.text or re.search(
                r"(?:[<>!=]=?|\b(?:LIKE|IN)\b|大於|小於|超過|低於|至少|以上|以下)",
                field.text, re.IGNORECASE):
            continue
        contract_text = " ".join([field.column, spec["description"], *spec.get("aliases", [])])
        contract_literals = set(re.findall(r"\d+", contract_text))
        contract_literals.update(item for item in token.findall(contract_text)
                                 if any(char.isdigit() for char in item))
        for occurrence in re.finditer(re.escape(field.text), request):
            field_spans.append((occurrence.start(), occurrence.end(), contract_literals))
    literals = {match.group() for match in token.finditer(request)
                if (any(char.isdigit() for char in match.group())
                    or (len(match.group()) > 1 and match.group().isupper()
                        and match.group() not in sql_words))
                and not any(start <= match.start() and match.end() <= end
                            and match.group() in numbers
                            for start, end, numbers in field_spans)}
    covered = {view}
    for item in [*mapping.fields, *mapping.criteria, *getattr(mapping, "having", []), *mapping.group, *mapping.order]:
        try:
            contract = catalog.field_contract(view, item.column)
        except ValueError:
            continue  # Existing schema validation reports unknown columns.
        covered.update(token.findall(item.column))
        for alias in contract.get("aliases", []):
            covered.update(token.findall(alias))
    for item in mapping.criteria:
        values = item.value if isinstance(item.value, list) else [item.value]
        for value in values:
            covered.update(token.findall(str(value)))
    for item in getattr(mapping, "having", []):
        covered.update(token.findall(str(item.value)))
    for rule in definition.policy.get("term_mappings", []):
        filters = rule.get("filters", [])
        if filters and all(any(item.column == f["column"] and item.operator == f["operator"]
                               and item.value == f["value"] for item in mapping.criteria) for f in filters):
            for term in rule.get("terms", []):
                if term in request:
                    covered.update(token.findall(term))
    return sorted(literals - covered)


def _default_catalog():
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    return SchemaCatalog(AssistantSettings.from_env().integration_path)


def create_graph(runtime=None):
    """LangGraph factory; dependency construction is lazy and performs no model calls."""
    if runtime is None:
        from cpea.bootstrap import AssistantRuntime
        runtime = AssistantRuntime.from_env()
    return runtime.generation_service().workflow.graph
