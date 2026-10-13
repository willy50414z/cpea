"""Schema-guided, compiler-only single-View SQL workflow."""

from __future__ import annotations

import re
from typing import Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.application.models.query import CandidateAttempt, ConversationTurn, QueryTaskTrace, SourceReference, SQLGenerationResponse
from cpea.workflows.text_to_sql.schemas import FactDraft, SchemaLinkDraft
from cpea.domain.models import QueryFact, QueryFilter, QueryPlan, SchemaLink
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever
from cpea.config.settings import AssistantSettings


EVIDENCE_PROMPT = """從使用者本次需求擷取每一項獨立的必要片段，並分類；這一步不選 View、欄位或資料庫代碼。
kind 定義：entity=指定對象或值（如 GN2300、成品良品倉）；metric=要求的數值（如 庫存數量、成本）；
dimension=分組或逐項呈現的維度（如 各倉庫）；time=時間語意或期間（如 目前、2025 年第一季）；
constraint=其他明確篩選或範圍（如 生產日期之後）；other=不能確定分類但仍須保留的需求片段。
同一片段可能同時涉及條件與時間；kind 只描述需求語意，不代表 SQL role 或欄位。
每項 facts.text 必須逐字出現在本次需求原文；明確寫出的項目 required=true。不要省略看似無法查詢的詞。
如果需求缺少必要資訊，列在 ambiguity，不能自行補年份、倉庫或代碼。
只回傳 JSON：supported、facts、ambiguity、explanation。"""

MATCH_PROMPT = """只針對提供的單一 View，將每個必要需求片段連到契約中的確切欄位。
links.fact_text 必須等於 items.text。role 僅能是 filter、metric、dimension。
temporal_scope 是 View 的時間語意，不是資料庫欄位；目前快照不需要額外時間 filter。
filter 的 value 必須來自需求原文或明確的 YAML term_mappings，不得猜代碼；日期「之後／後」是 >，「自／含當日」才是 >=。
單一指定倉庫是 filter；「各倉庫」是 dimension，不可加入單倉庫 filter。
型號、品號等英數識別碼不得當作品名 LIKE；地名不得在沒有倉庫語意依據時猜成倉庫名稱。
目前庫存 View 不能回答歷史時點庫存。無法連結的必要項目列入 unresolved_facts，不得跳過。
只回傳 JSON：supported、links、unresolved_facts、explanation、limitations。"""

_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*(?![A-Za-z0-9])")
_QUARTER = re.compile(r"第[一二三四1-4]季|\bQ[1-4]\b", re.IGNORECASE)
_YEAR = re.compile(r"(?:19|20)\d{2}\s*年?")
_JOIN = re.compile(r"\bjoin\b|(?:連接|聯結|串接).*(?:View|資料表|視圖)", re.IGNORECASE)
_ALL_WAREHOUSES = re.compile(r"各(?:個)?倉庫|所有倉庫|全部倉庫|每(?:個)?倉庫")


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
            system_prompt=EVIDENCE_PROMPT, question=state["request"],
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

    def _request_evidence(self, state: SQLGenerationState) -> FactDraft:
        prompt = ChatPromptTemplate.from_messages([
            ("system", EVIDENCE_PROMPT),
            ("human", "需求：{request}\n相關對話：{history_context}"),
        ])
        draft = self._invoke_model(prompt, state, FactDraft)
        request = state["request"]
        facts_by_text: dict[str, QueryFact] = {}
        absent: list[str] = []
        for fact in draft.facts:
            if fact.text and fact.text in request:
                facts_by_text.setdefault(fact.text, fact.model_copy(update={"required": True}))
            else:
                absent.append(fact.text)
        anchors = set(_IDENTIFIER.findall(request))
        for definition in self.catalog.views():
            for mapping in definition.policy.get("term_mappings", []):
                anchors.update(term for term in mapping.get("terms", []) if isinstance(term, str) and term in request)
            for rule in definition.policy.get("scope_rules", []):
                for pattern in rule.get("request_patterns", []):
                    anchors.update(match.group(0) for match in re.finditer(pattern, request))
        anchors.update(match.group(0) for match in _ALL_WAREHOUSES.finditer(request))
        for anchor in sorted(anchors):
            if not any(anchor in fact.text for fact in facts_by_text.values()):
                kind = "entity" if _IDENTIFIER.fullmatch(anchor) else (
                    "dimension" if _ALL_WAREHOUSES.fullmatch(anchor) else "constraint"
                )
                facts_by_text[anchor] = QueryFact(kind=kind, text=anchor, reason="原文錨點")
        uncovered = request
        for fact in sorted(facts_by_text.values(), key=lambda value: len(value.text), reverse=True):
            uncovered = uncovered.replace(fact.text, " ")
        uncovered = re.sub(r"請幫我|幫我|請查詢|查詢|請查|列出|顯示|目前|現在|多少|一下|的|在|與|以及|和|及|有", " ", uncovered)
        for fragment in re.findall(r"[A-Za-z0-9_-]{2,}|[\u3400-\u9fff]{2,}", uncovered):
            if fragment in request and not any(fragment in fact.text for fact in facts_by_text.values()):
                facts_by_text[fragment] = QueryFact(kind="other", text=fragment, reason="原文中未由模型列出的片段")
        ambiguity = [*draft.ambiguity, *[f"無法驗證需求片段：{item}" for item in absent]]
        if _QUARTER.search(request) and not _YEAR.search(request + " " + state.get("history_context", "")):
            ambiguity.append("季度需求缺少年份")
        return draft.model_copy(update={"facts": list(facts_by_text.values()),
                                        "ambiguity": list(dict.fromkeys(ambiguity))})

    def _match_candidates(self, state: SQLGenerationState) -> dict[str, Any]:
        request = state["request"]
        if _JOIN.search(request):
            return {"rejection_stage": "schema_selection", "response": self._unsupported(
                "單一查詢任務尚不支援跨 View JOIN。", ["請拆成多個單一 View 查詢任務。"])}
        evidence = self._request_evidence(state)
        facts = evidence.facts
        if not evidence.supported or evidence.ambiguity or not facts:
            reasons = evidence.ambiguity or ([evidence.explanation] if evidence.explanation else ["無法辨識必要需求項目"])
            return {"request_facts": facts, "rejection_stage": "request_ambiguity",
                    "response": self._unsupported("需求需要釐清。", reasons)}
        attempts: list[CandidateAttempt] = []
        for candidate in state["candidates"]:
            view = str(candidate.document.metadata["document_id"])
            definition = next(item for item in self.catalog.views() if item.name == view)
            link_facts = [fact for fact in facts if not (
                definition.policy.get("temporal_scope") == "current_snapshot"
                and fact.text in {"目前", "現在", "當前", "現時"}
            )]
            detailed = RetrievalCandidate(
                document=Document(id=candidate.document.id,
                                  page_content=f"# {view}\n\n{self.catalog.detail(view)}",
                                  metadata=candidate.document.metadata),
                retrieval_score=candidate.retrieval_score,
                reranker_score=candidate.reranker_score,
            )
            packed = self.context_packer.pack_documents(
                system_prompt=MATCH_PROMPT, question=request,
                history_text=state.get("history_context", ""), candidates=[detailed],
                additional_prompt_text=FactDraft(facts=link_facts).model_dump_json(),
            )
            if not packed.sources:
                attempts.append(CandidateAttempt(view=view, outcome="context_budget", facts=facts,
                                                 errors=["詳細 schema 超出 context budget"]))
                continue
            temporal_error = self._temporal_mismatch(view, request)
            if temporal_error:
                temporal_facts = [fact.text for fact in facts if _QUARTER.search(fact.text)
                                  or re.search(r"(?:19|20)\d{2}年|截至|當時|歷史|過去", fact.text)]
                attempts.append(CandidateAttempt(view=view, outcome="schema_mismatch", facts=facts,
                                                 unresolved=temporal_facts, errors=[temporal_error]))
                continue
            mandatory = self._mandatory_links(view, request, link_facts)
            prompt = ChatPromptTemplate.from_messages([
                ("system", MATCH_PROMPT),
                ("human", "需求：{request}\n必要事實：{request_facts}\nView：{view}\n詳細 schema：{schema_context}"),
            ])
            variables = {"request": request, "request_facts": FactDraft(facts=link_facts).model_dump_json(),
                         "view": view, "schema_context": packed.text}
            draft = self._invoke_model(prompt, variables, SchemaLinkDraft)
            errors: list[str] = []
            for correction in range(2):
                links = list(draft.links)
                for link in mandatory:
                    links = [other for other in links if not (
                        other.fact_text == link.fact_text and other.role == link.role
                        and (other.column == link.column or (
                            link.role == "filter" and _IDENTIFIER.fullmatch(link.fact_text)
                            and link.column in {"品号", "品號", "料号", "料號"}
                        ))
                    )]
                    links.append(link)
                draft = draft.model_copy(update={"links": links})
                errors = self._link_errors(link_facts, draft, view, request)
                if not errors:
                    attempts.append(CandidateAttempt(view=view, outcome="matched", facts=facts, links=links))
                    return {"request_facts": facts, "candidate_attempts": attempts,
                            "selected_views": [view], "links": draft, "sources": packed.sources,
                            "context_tokens": packed.context_tokens, "context_budget": packed.document_budget}
                if correction == 0:
                    repair = ChatPromptTemplate.from_messages([
                        ("system", MATCH_PROMPT),
                        ("human", "需求：{request}\n必要事實：{request_facts}\nView：{view}\n詳細 schema：{schema_context}"
                                  "\n前次連結：{previous_links}\n違規：{link_errors}\n只回傳完整修正版 JSON。"),
                    ])
                    draft = self._invoke_model(repair, {**variables, "previous_links": draft.model_dump_json(),
                                                         "link_errors": errors}, SchemaLinkDraft)
            unmatched = [fact.text for fact in facts if fact.required
                         and not any(link.fact_text == fact.text for link in draft.links)]
            attempts.append(CandidateAttempt(view=view, outcome="schema_mismatch", facts=facts,
                                             links=draft.links,
                                             unresolved=list(dict.fromkeys([*draft.unresolved_facts, *unmatched])),
                                             errors=errors))
        reasons = [f"{attempt.view}: {', '.join(attempt.errors or attempt.unresolved)}" for attempt in attempts]
        return {"request_facts": facts, "candidate_attempts": attempts, "rejection_stage": "schema_linking",
                "response": self._unsupported("沒有單一 View 能完整承接需求。", reasons)}

    def _temporal_mismatch(self, view: str, request: str) -> str | None:
        definition = next(item for item in self.catalog.views() if item.name == view)
        if definition.policy.get("temporal_scope") == "current_snapshot" and (
            _QUARTER.search(request) or re.search(r"(?:19|20)\d{2}年|截至|當時|歷史|过去|過去", request)
        ) and not re.search(r"生產日期|有效日期|效期", request):
            return "View 僅提供目前快照，不能回答歷史時點需求"
        return None

    def _mandatory_links(self, view: str, request: str, facts: list[QueryFact]) -> list[SchemaLink]:
        mandatory: list[SchemaLink] = []
        definition = next(item for item in self.catalog.views() if item.name == view)
        code_columns = [column for column in self.catalog.columns(view)
                        if column in {"品号", "品號", "料号", "料號"}
                        and "filter" in self.catalog.field_contract(view, column).get("capabilities", [])]
        if len(code_columns) == 1:
            for fact in facts:
                if not _IDENTIFIER.fullmatch(fact.text):
                    continue
                warehouse_code = re.search(
                    rf"(?:倉庫|仓库)\s*(?:編號|编号|代碼|代码)?\s*{re.escape(fact.text)}", request
                )
                if not warehouse_code:
                    mandatory.append(SchemaLink(fact_text=fact.text, view=view,
                                                column=code_columns[0], role="filter",
                                                operator="=", value=fact.text))
        for mapping in definition.policy.get("term_mappings", []):
            term = next((term for term in mapping.get("terms", []) if term in request), None)
            if term is None:
                continue
            fact = next((item.text for item in facts if term in item.text), term)
            for clause in mapping.get("filters", []):
                mandatory.append(SchemaLink(fact_text=fact, view=view, role="filter", **clause))
        for _, rule in self.catalog.matching_scope_rules(request, [view]):
            fact = next((item.text for item in facts if any(re.search(pattern, item.text)
                         for pattern in rule.get("request_patterns", []))), None)
            if fact:
                mandatory.append(SchemaLink(fact_text=fact, view=view,
                                            column=rule["required_dimension"], role="dimension"))
        return mandatory

    def _link_errors(self, facts: list[QueryFact], draft: SchemaLinkDraft, view: str, request: str) -> list[str]:
        errors: list[str] = []
        if not draft.supported:
            errors.append("schema linking marked unsupported")
        required = {fact.text for fact in facts if fact.required}
        linked = {link.fact_text for link in draft.links}
        if required - linked:
            errors.append("unlinked items: " + ", ".join(sorted(required - linked)))
        if draft.unresolved_facts:
            errors.append("unresolved items: " + ", ".join(draft.unresolved_facts))
        mappings = self.catalog.mapped_filters(request, [view])
        prohibited = {column for _, rule in self.catalog.matching_scope_rules(request, [view])
                      for column in rule.get("prohibited_filter_columns", [])}
        filter_values: dict[str, str] = {}
        for link in draft.links:
            if link.fact_text not in required or link.fact_text not in request:
                errors.append(f"link references unknown request item: {link.fact_text}")
            violation = self.catalog.validate_link(link, {view})
            if violation:
                errors.append(violation)
                continue
            if link.role == "filter":
                if link.column in prohibited:
                    errors.append(f"prohibited scope filter: {link.column}")
                if _IDENTIFIER.fullmatch(link.fact_text) and (
                    link.operator != "=" or re.search(r"品名|名称|名稱", link.column)
                ):
                    errors.append(f"identifier requires an exact code filter: {link.fact_text}")
                if re.search(r"仓库|倉庫", link.column) and not re.search(r"倉|仓|庫|库", link.fact_text) and not any(
                    link.column == item["column"] and link.operator == item["operator"]
                    and link.value == item["value"] for item in mappings
                ):
                    errors.append(f"warehouse filter lacks warehouse evidence: {link.fact_text}")
                if not self._filter_is_grounded(link, request, mappings):
                    errors.append(f"ungrounded filter: {link.column} {link.value}")
                value = str(link.value)
                if link.column in filter_values and filter_values[link.column] != value:
                    errors.append(f"conflicting linked filters: {link.column}")
                filter_values[link.column] = value
        return list(dict.fromkeys(errors))

    def _filter_is_grounded(self, link: SchemaLink, request: str, mappings: list[dict[str, Any]]) -> bool:
        if any(link.column == item["column"] and link.operator == item["operator"]
               and link.value == item["value"] for item in mappings):
            return True
        normalize = lambda value: str(value).replace("倉", "仓").replace("庫", "库").replace("號", "号")
        values = link.value if isinstance(link.value, list) else [link.value]
        fragments = [normalize(value).replace("%", "").replace("_", "") for value in values if value is not None]
        names = [link.column, *self.catalog.field_contract(link.view, link.column).get("aliases", [])]
        labels = {normalize(name) for name in names}
        return len(fragments) == len(values) and all(
            fragment and fragment in normalize(request) and fragment not in labels for fragment in fragments
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
        structured = self.llm.with_structured_output(model, method="json_schema")
        last_error: ValueError | None = None
        for _ in range(2):
            try:
                return structured.invoke(messages)
            except ValueError as exc:
                last_error = exc
                messages = [*messages, HumanMessage(content=f"前一份回覆未符合 JSON contract：{exc}。請只輸出完整修正版 JSON。")]
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
