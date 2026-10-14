"""Schema-guided, compiler-only single-View SQL workflow."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.llm.factory import bind_response_schema, response_schema_for
from cpea.application.models.query import CandidateAttempt, ConversationTurn, QueryTaskTrace, SourceReference, SQLGenerationResponse
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping, SchemaLinkDraft
from cpea.domain.models import QueryFact, QueryFilter, QueryPlan, SchemaLink
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever
from cpea.config.settings import AssistantSettings


MATCH_PROMPT = """你是單一 View 的需求對應器。根據需求與提供的 View 契約，回傳純 JSON，不輸出 SQL、Markdown 或額外文字。
固定 keys：fields、table、criteria、order、group、ignored。fields/criteria/order/group/ignored 都是陣列，沒有項目用 []。
fields 每項含 text、column、aggregation；criteria 每項含 text、column、operator、value；order/group 每項含 text、column；ignored 每項含 text、reason。table 是含 text、view 的物件；無法完整滿足需求或需要 JOIN 時為 null。table.text 可為 null。
text 必須逐字擷取需求中的連續片段，不改寫、不做繁簡轉換。column/view 必須使用契約的原始名稱。criteria.value 保留原文值與型別；不可把欄位名稱當值、猜測代碼或新增條件。只有契約明確提供的詞彙對應可轉換值。
fields 對應要顯示的欄位；criteria 對應限制資料的條件；order 對應明確排序要求；group 僅用於彙總維度或明確去重。列出明細不代表分組。aggregation 只能為契約允許的 sum/count/avg/min/max 或 null；依指標與需求選擇，分組維度不聚合，明細欄位不聚合。
所有明確的欄位、條件、時間範圍、排序與分組需求都要處理；不可為了適配 View 忽略缺失資訊或改變業務語意。ignored 只收不影響查詢的語助詞，或已由 View 定義滿足的範圍並說明原因；不確定或缺欄位時 table=null。
未要求明細、逐筆資料或同列呈現識別欄位時，指標遵循契約的 default_aggregation；若需求要列出明細識別欄位，保持原值，除非明確要求彙總。
業務含義須同時符合需求與欄位描述，不能僅因字面相近就替換指標或資料來源。View 名稱與摘要是概述，須綜合欄位、資料範圍判斷；若需求只是要該來源已有的紀錄，不額外猜測存在性條件。只有明確的條件值才放 criteria，text 必須包含授權該值的原文片段。
依 capabilities、scope_rules、term_mappings 與 filter_operators 遵守契約。operator 使用契約允許的 SQL 運算子（例如 =、IN），不可回傳 default 等政策鍵。string/date 欄位的條件值保留為字串，number 欄位才可用數值。
若提供多個 candidates，請比較完整需求與各候選契約，選出業務含義及所有欄位最吻合的一個 View；不可混用不同 View。未指定的時間或資料涵蓋範圍不自行擴大。table=null 時另提供 unsupported_reason，指出契約缺少的資訊。
若需求未限定來源種類，而所需欄位組合只完整匹配一個候選，可選該候選；不可將未指定來源解讀為必須包含所有來源種類。若明確限定的業務語意不符，仍須拒絕。table.text 只有需求逐字包含契約的完整 View 名稱時才填該名稱，否則一律 null；不要用摘要或推測的來源詞填入。
fields 只放明確要求顯示的資訊。條件欄位及其值屬於 criteria，不因需求提到條件欄位就自動將它列入 fields 或 group；只有另外要求顯示或分組該欄位時才加入。group 只包含需求指定的分組維度，不為了修補多餘的 fields 擴充分組。"""

_LEGACY_COLUMN_TYPES = {
    '字串': 'string', '字串（代碼）': 'string', '數值': 'number', '数值': 'number',
    '日期': 'date', '日期字串（`YYYY-MM-DD`）': 'string',
}


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
        response_schema = response_schema_for(SQLClauseMapping,
            column_names={column for schema in schemas.values() for column in schema['columns']},
            view_names=set(schemas))
        packed = self.context_packer.pack_documents(
            system_prompt=MATCH_PROMPT, question=request, history_text="", candidates=detailed,
            additional_prompt_text=json.dumps({'candidates': [], 'response_schema': response_schema}, ensure_ascii=False),
        )
        admitted = {source.document_id for source in packed.sources}
        attempts = [CandidateAttempt(view=view, outcome="context_budget",
                                     errors=["完整 View contract 超出 context budget"])
                    for view in schemas if view not in admitted]
        schemas = {view: schema for view, schema in schemas.items() if view in admitted}
        response_schema = response_schema_for(SQLClauseMapping,
            column_names={column for schema in schemas.values() for column in schema['columns']},
            view_names=set(schemas))
        prompt = ChatPromptTemplate.from_messages([
            ("system", MATCH_PROMPT),
            ("human", "需求: {request} table定義: {schema_context}"),
        ])
        variables = {"request": request,
                     "schema_context": json.dumps({"candidates": list(schemas.values()),
                                                  "response_schema": response_schema}, ensure_ascii=False)}
        facts: list[QueryFact] = []
        for _ in range(2 if schemas else 0):
            try:
                mapping = self._invoke_model(prompt, variables, SQLClauseMapping, response_schema=response_schema)
            except ValueError as exc:
                attempts.append(CandidateAttempt(view="(unselected)", outcome="schema_mismatch", errors=[str(exc)]))
                continue
            if isinstance(mapping.table, list):
                return {"request_facts": facts, "candidate_attempts": attempts,
                        "rejection_stage": "schema_selection",
                        "response": self._unsupported("單一查詢任務只支援一個 View。", [request])}
            if (mapping.table is None or mapping.table.view not in schemas
                    or (mapping.table.text and mapping.table.text != mapping.table.view and mapping.table.text not in request)):
                attempts.append(CandidateAttempt(
                    view=mapping.table.view if mapping.table else "(unselected)",
                    outcome="schema_mismatch", unresolved=[request],
                    errors=[mapping.unsupported_reason or "table mapping does not match the request and selected View"]))
                continue
            view = mapping.table.view
            schema = schemas[view]
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
            if not mapping.fields:
                errors.append("fields mapping is empty")
            for item in [*mapping.order, *mapping.group, *mapping.ignored]:
                if not item.text or item.text not in request:
                    errors.append(f"mapped text absent from request: {item.text}")
            if any(item.column not in schema["columns"] for item in mapping.order):
                errors.append("order column is not in selected View")
            missing_literals = unmapped_request_literals(request, mapping, self.catalog, view)
            if missing_literals:
                errors.append("unmapped request literals: " + ", ".join(missing_literals))
            if not errors:
                attempts.append(CandidateAttempt(view=view, outcome="matched", facts=facts, links=draft.links))
                return {"request_facts": facts, "candidate_attempts": attempts,
                        "selected_views": [view], "links": draft,
                        "order_by": [item.column for item in mapping.order],
                        "sources": [source for source in packed.sources if source.document_id == view],
                        "context_tokens": packed.context_tokens, "context_budget": packed.document_budget}
            attempts.append(CandidateAttempt(view=view, outcome="schema_mismatch", facts=facts,
                                             links=draft.links, unresolved=[*draft.unresolved_facts, *missing_literals], errors=errors))
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

    def _invoke_model(self, prompt: ChatPromptTemplate, variables: dict[str, Any], model: type[Any], *, response_schema=None):
        serialized = {key: value.model_dump_json() if hasattr(value, "model_dump_json") else value
                      for key, value in variables.items()}
        messages = prompt.invoke(serialized).to_messages()
        response_llm = bind_response_schema(self.llm, model, schema=response_schema)
        last_error: ValueError | None = None
        for _ in range(2):
            counter = self.context_packer.token_counter
            tokens = counter.count_messages([(message.type, str(message.content)) for message in messages])
            if tokens + self.settings.output_token_reserve + self.settings.context_safety_tokens > self.settings.context_window:
                raise ValueError("prompt exceeds context budget")
            try:
                raw = response_llm.invoke(messages)
                from cpea.infrastructure.llm.parsing import parse_model
                return parse_model(raw, model)
            except ValueError as exc:
                last_error = exc
        raise last_error or ValueError("LLM did not return a structured response")

    @staticmethod
    def _unsupported(explanation: str, limitations: list[str], **metadata: Any) -> SQLGenerationResponse:
        return SQLGenerationResponse(supported=False, explanation=explanation, limitations=limitations, **metadata)


def candidate_schema(definition) -> dict[str, Any]:
    """Expose approved metadata only; samples and evaluation data never enter context."""
    schema = {
        "view": definition.name, "summary": definition.summary,
        "columns": {name: {
            "data_type": _LEGACY_COLUMN_TYPES.get(spec["type"], spec["type"]),
            "description": spec["description"], "aliases": spec.get("aliases", []),
            "capabilities": spec.get("capabilities", []),
            "aggregations": spec.get("aggregations", []),
            "default_aggregation": spec.get("default_aggregation"),
        } for name, spec in definition.policy["columns"].items()},
    }
    for key in ("temporal_scope", "data_scope", "grain", "filter_operators", "term_mappings", "scope_rules"):
        if definition.policy.get(key):
            schema[key] = definition.policy[key]
    return schema


def unmapped_request_literals(request, mapping, catalog, view) -> list[str]:
    """Prevent silent loss of explicit codes; this is not a natural-language parser."""
    token = re.compile(r"[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*")
    sql_words = {"SQL", "SELECT", "FROM", "WHERE", "ORDER", "BY", "GROUP", "JOIN",
                 "ASC", "DESC", "SUM", "COUNT", "AVG", "MIN", "MAX", "AND", "OR",
                 "IN", "LIKE", "NULL", "TOP", "DISTINCT"}
    literals = {item for item in token.findall(request)
                if any(char.isdigit() for char in item)
                or (len(item) > 1 and item.isupper() and item not in sql_words)}
    covered = {view}
    for item in [*mapping.fields, *mapping.criteria, *mapping.group, *mapping.order]:
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
    definition = next(item for item in catalog.views() if item.name == view)
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
