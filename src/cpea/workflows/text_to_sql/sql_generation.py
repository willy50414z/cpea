"""Schema-guided, compiler-only single-View SQL workflow."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.application.models.query import CandidateAttempt, ConversationTurn, QueryTaskTrace, SourceReference, SQLGenerationResponse
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping, SchemaLinkDraft
from cpea.domain.models import QueryFact, QueryFilter, QueryPlan, SchemaLink
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever
from cpea.config.settings import AssistantSettings


MATCH_PROMPT = """你是一個資料庫專家，需要根據 user 提出的需求、view 的欄位資訊、以下提供的 SQL template，提供一個 JSON，包含每個變數（fields/table/criteria/order/group）對應到原文的什麼詞，還有對應到 table/view 的哪個欄位。若有部分關鍵字屬於冗詞贅字，不需做為 SQL 的一部分，請說明原因。參考用的 SQL 樣板：'select {{fields}} from {{table}} where {{criteria}} order by {{order}} group by {{group}}'。
JSON 中 fields、criteria、order、group 是陣列；每項使用 text 表示需求原文中的詞、column 表示 View 欄位，不能把欄位名稱當成原文詞。fields 只放要顯示的欄位；篩選用詞放 criteria，另有 operator 和 value；「各／每個類別的數量」屬於按類別彙總，group 應對應該類別欄位；只有逐筆列出原始紀錄時 group 才留空。table 使用 text 和 view；原文沒有 View 名稱時 text 可為 null。冗詞贅字放在 ignored，使用 text 和 reason。沒有對應項目時使用空陣列；只回傳 JSON。"""


class SQLGenerationState(TypedDict, total=False):
    request: str
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
    links: SchemaLinkDraft
    order_by: list[str]
    selected_views: list[str]
    plan: QueryPlan
    compiled_sql: str
    rejection_stage: str
    response: SQLGenerationResponse


class SQLGenerationWorkflow:
    def __init__(self, llm: Any, catalog: CatalogProvider | None = None, *,
                 settings: AssistantSettings | None = None,
                 retriever: SchemaRetriever | None = None,
                 context_packer: ContextPacker | None = None) -> None:
        self.llm = llm
        self.catalog = catalog or _default_catalog()
        self.settings = settings or AssistantSettings.from_env()
        if self.settings.sql_generation_mode != "compiler":
            raise ValueError("ASSISTANT_SQL_GENERATION_MODE supports only compiler; legacy is unsupported")
        self.retriever = retriever or SchemaRetriever(self.settings, catalog=self.catalog)
        self.context_packer = context_packer or ContextPacker(self.settings)
        self.graph = self._build_graph()

    def invoke(self, request: str, history: list[ConversationTurn] | None = None) -> SQLGenerationResponse:
        state = self.graph.invoke({"request": request, "history": history or []})
        return state["response"]

    def _build_graph(self):
        graph = StateGraph(SQLGenerationState)
        # 從doc篩選views並加入tokens budget/latency ms打包成context
        graph.add_node("retrieve_schema", self._retrieve_schema)
        graph.add_node("match_candidates", self._match_candidates)
        graph.add_node("compile_query", self._compile_query)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "retrieve_schema")
        graph.add_conditional_edges("retrieve_schema", self._continue_or_end, {"continue": "match_candidates", "end": "finalize"})
        graph.add_conditional_edges("match_candidates", self._continue_or_end, {"continue": "compile_query", "end": "finalize"})
        graph.add_edge("compile_query", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    @staticmethod
    def _continue_or_end(state: SQLGenerationState) -> str:
        return "end" if "response" in state else "continue"

    def _retrieve_schema(self, state: SQLGenerationState) -> dict[str, Any]:
        # 標準化與清理request
        # 根據doc撈出可用的views
        result = self.retriever.retrieve(state["request"])
        # 根據歷史資訊篩選最近且最重要的加入context
        history_context = self.context_packer.pack_history(state["request"], state.get("history", []))
        # 根據context budget設定,篩選並打包成PackedContext dto
        packed = self.context_packer.pack_documents(
            system_prompt=MATCH_PROMPT, question=state["request"],
            history_text=history_context, candidates=result.candidates,
        )
        if not packed.sources:
            return {"rejection_stage": "retrieval", "response": self._unsupported(
                "Context budget 無法容納任何候選 schema。", ["請提高 context window 或縮短 schema 文件。"],
                retrieval_latency_ms=result.retrieval_latency_ms,
                reranker_latency_ms=result.reranker_latency_ms,
                context_budget=packed.document_budget,
            )}
        by_id = {item.document.metadata["document_id"]: item for item in result.candidates}
        admitted = [by_id[source.document_id] for source in packed.sources]
        return {
            "history_context": history_context,
            "candidates": admitted[:self.settings.rerank_top_k],
            "retrieved_candidates": [self.context_packer.source_reference(item) for item in result.candidates],
            "sources": packed.sources,
            "retrieval_latency_ms": result.retrieval_latency_ms,
            "reranker_latency_ms": result.reranker_latency_ms,
            "context_tokens": packed.context_tokens,
            "context_budget": packed.document_budget,
        }

    def _match_candidates(self, state: SQLGenerationState) -> dict[str, Any]:
        request = state["request"]
        attempts: list[CandidateAttempt] = []
        facts: list[QueryFact] = []
        for candidate in state["candidates"]:
            view = str(candidate.document.metadata["document_id"])
            definition = next(item for item in self.catalog.views() if item.name == view)
            schema = {
                "view": definition.name,
                "summary": definition.summary,
                "columns": {
                    name: {"data_type": "number" if any(word in spec["type"] for word in ("數值", "数值", "number")) else "string"}
                    for name, spec in definition.policy["columns"].items()
                },
            }
            detailed = RetrievalCandidate(
                document=Document(id=candidate.document.id,
                                  page_content=json.dumps(schema, ensure_ascii=False),
                                  metadata=candidate.document.metadata),
                retrieval_score=candidate.retrieval_score, reranker_score=candidate.reranker_score,
            )
            packed = self.context_packer.pack_documents(
                system_prompt=MATCH_PROMPT, question=request, history_text="", candidates=[detailed],
            )
            if not packed.sources:
                attempts.append(CandidateAttempt(view=view, outcome="context_budget",
                                                 errors=["完整 View contract 超出 context budget"]))
                continue
            prompt = ChatPromptTemplate.from_messages([
                ("system", MATCH_PROMPT),
                ("human", "需求: {request} table定義: {schema_context}"),
            ])
            variables = {"request": request, "schema_context": json.dumps(schema, ensure_ascii=False)}
            draft = SchemaLinkDraft()
            errors: list[str] = []
            for _ in range(2):
                try:
                    mapping = self._invoke_model(prompt, variables, SQLClauseMapping)
                except ValueError as exc:
                    errors = [str(exc)]
                    continue
                if isinstance(mapping.table, list):
                    return {"request_facts": facts, "rejection_stage": "schema_selection",
                            "response": self._unsupported("單一查詢任務只支援一個 View。", [request])}
                if (mapping.table is None or mapping.table.view != view
                        or (mapping.table.text and mapping.table.text != view and mapping.table.text not in request)):
                    errors = ["table mapping does not match the request and selected View"]
                    continue
                facts_by_text: dict[str, QueryFact] = {}
                links: list[SchemaLink] = []
                grouped = {item.column for item in mapping.group}
                for item in mapping.criteria:
                    facts_by_text.setdefault(item.text, QueryFact(kind="entity", text=item.text))
                    links.append(SchemaLink(fact_text=item.text, view=view, column=item.column,
                                            role="filter", operator=item.operator, value=item.value))
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
                    link = SchemaLink(fact_text=fact_text, view=view, column=item.column, role=role)
                    if link not in links:
                        links.append(link)
                draft = SchemaLinkDraft(
                    supported=True, facts=list(facts_by_text.values()), links=links,
                    explanation="；".join(f"{item.text}：{item.reason}" for item in mapping.ignored),
                )
                facts = draft.facts
                errors = self._link_errors(facts, draft, view, request)
                if not mapping.fields:
                    errors.append("fields mapping is empty")
                for item in [*mapping.order, *mapping.group, *mapping.ignored]:
                    if not item.text or item.text not in request:
                        errors.append(f"mapped text absent from request: {item.text}")
                if any(item.column not in schema["columns"] for item in mapping.order):
                    errors.append("order column is not in selected View")
                if not errors:
                    attempts.append(CandidateAttempt(view=view, outcome="matched", facts=facts, links=draft.links))
                    return {"request_facts": facts, "candidate_attempts": attempts,
                            "selected_views": [view], "links": draft, "order_by": [item.column for item in mapping.order], "sources": packed.sources,
                            "context_tokens": packed.context_tokens, "context_budget": packed.document_budget}
            covered = {link.fact_text for link in draft.links} | {item.fact_text for item in draft.view_satisfied}
            unmatched = [fact.text for fact in facts if fact.required and fact.text not in covered]
            attempts.append(CandidateAttempt(
                view=view, outcome="context_budget" if any("context budget" in e for e in errors) else "schema_mismatch",
                facts=draft.facts, links=draft.links,
                unresolved=list(dict.fromkeys([*draft.unresolved_facts, *unmatched, *([request] if not facts else [])])), errors=errors))
        reasons = [f"{attempt.view}: {', '.join(attempt.errors or attempt.unresolved)}" for attempt in attempts]
        return {"request_facts": facts, "candidate_attempts": attempts, "rejection_stage": "schema_linking",
                "response": self._unsupported("沒有單一 View 能完整承接需求。", reasons)}

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

    def _compile_query(self, state: SQLGenerationState) -> dict[str, Any]:
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
            if link.column not in columns:
                columns.append(link.column)
            if link.role == "dimension" and link.column not in group_by:
                group_by.append(link.column)
            if link.aggregation:
                if link.column in aggregations and aggregations[link.column] != link.aggregation:
                    return {"rejection_stage": "query_plan", "response": self._unsupported(
                        "指標聚合定義衝突。", [f"conflicting aggregation: {link.column}"])}
                aggregations[link.column] = link.aggregation
        for link in state["links"].links:
            if link.role == "metric" and link.column not in aggregations:
                default = self.catalog.field_contract(view, link.column).get("default_aggregation")
                if default:
                    aggregations[link.column] = default
        plan = QueryPlan(supported=True, source_views=[view], select_columns=columns,
                         filters=filters, group_by=group_by, aggregations=aggregations,
                         order_by=state.get("order_by", []),
                         explanation="由核准的 Schema Links 與 View 契約組成。")
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
        errors.extend(self.catalog.validate_plan_contract(plan, state["request"]))
        return errors

    def _finalize(self, state: SQLGenerationState) -> dict[str, Any]:
        response = state["response"]
        stage = state.get("rejection_stage")
        if not response.supported and not stage:
            stage = "sql_validation" if state.get("compiled_sql") else "query_plan" if state.get("plan") else "schema_linking"
        trace = QueryTaskTrace(
            request=state["request"], request_facts=state.get("request_facts", []),
            candidate_attempts=state.get("candidate_attempts", []),
            selected_view=state.get("selected_views", [None])[0],
            links=state.get("links"), plan=state.get("plan"),
            sql=response.sql or state.get("compiled_sql"),
            sources=state.get("sources", []), rejection_stage=stage,
            validation_errors=response.limitations if not response.supported else [],
        )
        return {"response": response.model_copy(update={"query_trace": trace})}

    def _invoke_model(self, prompt: ChatPromptTemplate, variables: dict[str, Any], model: type[Any]):
        serialized = {key: value.model_dump_json() if hasattr(value, "model_dump_json") else value
                      for key, value in variables.items()}
        messages = prompt.invoke(serialized).to_messages()
        last_error: ValueError | None = None
        for _ in range(2):
            counter = self.context_packer.token_counter
            tokens = counter.count_messages([(message.type, str(message.content)) for message in messages])
            if tokens + self.settings.output_token_reserve + self.settings.context_safety_tokens > self.settings.context_window:
                raise ValueError("prompt exceeds context budget")
            try:
                raw = self.llm.invoke(messages)
                from cpea.infrastructure.llm.parsing import parse_model
                return parse_model(raw, model)
            except ValueError as exc:
                last_error = exc
        raise last_error or ValueError("LLM did not return a structured response")

    @staticmethod
    def _unsupported(explanation: str, limitations: list[str], **metadata: Any) -> SQLGenerationResponse:
        return SQLGenerationResponse(supported=False, explanation=explanation, limitations=limitations, **metadata)


def _default_catalog():
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    return SchemaCatalog(AssistantSettings.from_env().integration_path)


def create_graph(runtime=None):
    """LangGraph factory; dependency construction is lazy and performs no model calls."""
    if runtime is None:
        from cpea.bootstrap import AssistantRuntime
        runtime = AssistantRuntime.from_env()
    return runtime.generation_service().workflow.graph
