import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpea.application.models.query import MappingAttempt, QueryTaskTrace, SQLGenerationResponse
from cpea.domain.models import QueryPlan
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from cpea.workflows.text_to_sql.sql_generation import candidate_schema
from cpea.bootstrap import AssistantRuntime
from evaluations.call_budget import CallBudget, ModelStopped, provider_stop_reason
from evaluations.governance_inputs import load_cases
from evaluations.view_matching_cases import ViewMatchingCase, validate_view_case
from evaluations.view_matching_grading import grade_view_matching
from evaluations.governance_reports import model_metrics
from tests.support import QUESTION, dependencies
from tests.support import StubLLM


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def retail():
    catalog = SchemaCatalog(ROOT / "projects" / "retail", allow_drafts=True)
    path = ROOT / "projects" / "retail" / "evaluations" / "cases.jsonl"
    cases = load_cases(path).cases
    return catalog, path, cases[0].view_matching_case, cases[45].view_matching_case


def test_case_preflight_rejects_stale_contract_columns_text_and_duplicate_ids(retail, tmp_path):
    catalog, path, normal, _ = retail
    validate_view_case(normal, catalog)
    with pytest.raises(ValueError, match="fingerprint"):
        validate_view_case(normal.model_copy(update={"contract_fingerprint": "0" * 64}), catalog)
    with pytest.raises(ValueError, match="MATCH_PROMPT fingerprint"):
        validate_view_case(normal.model_copy(update={"prompt_sha256": "0" * 64}), catalog)
    raw = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    raw["expected_match"]["fields"][0]["column"] = "invented_column"
    with pytest.raises(ValueError, match="unknown mapping column"):
        validate_view_case(ViewMatchingCase.model_validate(raw), catalog)
    raw["expected_match"]["fields"][0]["column"] = normal.expected_match.fields[0].column
    raw["expected_match"]["fields"][0]["text"] = "absent text"
    with pytest.raises(ValueError, match="text absent"):
        validate_view_case(ViewMatchingCase.model_validate(raw), catalog)
    duplicate = tmp_path / "cases.jsonl"
    duplicate.write_text(json.dumps(raw, ensure_ascii=False) + "\n" + json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case_id must be unique"):
        load_cases(duplicate)


def test_review_approval_is_bound_to_case_and_contract(retail):
    catalog, _, normal, _ = retail
    approved = normal.model_copy(update={"review_status": "approved", "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-15T00:00:00Z", "reviewed_case_sha256": normal.content_sha256(),
        "reviewed_contract_fingerprint": catalog.fingerprint})
    validate_view_case(approved, catalog)
    assert approved.approved_for(catalog.fingerprint)
    with pytest.raises(ValueError, match="stale human approval"):
        validate_view_case(approved.model_copy(update={"rationale": "changed"}), catalog)


def test_retail_gap_cases_remain_reviewable_rejections(retail):
    catalog, path, _, _ = retail
    cases = [wrapped.view_matching_case for wrapped in load_cases(path).cases]
    gaps = {case.case_id: case for case in cases if "-G-" in case.case_id}
    assert len(cases) == 395 and len(gaps) == 10
    assert {case.target_view for case in gaps.values()} == {item.name for item in catalog.views()}
    descending = [case for case in gaps.values() if case.expected_sql and case.expected_sql.order_directions]
    assert len(descending) == 7
    for case in descending:
        validate_view_case(case, catalog)
        spec = case.expected_sql
        plan = QueryPlan(supported=True, source_views=[case.target_view],
                         select_columns=spec.select_columns, filters=spec.filters,
                         aggregations=spec.aggregations, group_by=spec.group_by,
                         order_by=spec.order_by, order_directions=spec.order_directions)
        assert " DESC" in compile_single_view(plan, catalog, request=case.request)
    distinct = next(case for case in gaps.values()
                    if case.expected_sql and case.expected_sql.aggregations.get("order_id") == "count_distinct")
    validate_view_case(distinct, catalog)
    spec = distinct.expected_sql
    plan = QueryPlan(supported=True, source_views=[distinct.target_view],
                     select_columns=spec.select_columns, group_by=spec.group_by,
                     aggregations=spec.aggregations)
    assert "COUNT(DISTINCT [order_id])" in compile_single_view(plan, catalog, request=distinct.request)
    for case in gaps.values():
        validate_view_case(case, catalog)
        if case.category != "normal":
            assert case.expected_match.table is None and case.expected_sql is None
            assert case.unsupported_evidence and case.review_status == "pending"


def test_match_and_query_plan_have_independent_results(retail):
    catalog, _, case, rejected = retail
    spec = case.expected_sql
    plan = QueryPlan(supported=True, source_views=[case.target_view], select_columns=spec.select_columns,
                     filters=spec.filters, aggregations=spec.aggregations, group_by=spec.group_by,
                     order_by=spec.order_by)
    sql = compile_single_view(plan, catalog, request=case.request)
    trace = QueryTaskTrace(request=case.request, mapping_attempts=[MappingAttempt(
        attempt_index=1, mapping=case.expected_match, outcome="selected")], selected_mapping_index=1)
    generation = SQLGenerationResponse(supported=True, sql=sql, selected_views=[case.target_view],
        explanation="test", query_plan=plan, query_trace=trace)
    assert grade_view_matching(case, generation) == ("pass", "pass", [])
    wrong_plan = plan.model_copy(update={"select_columns": spec.select_columns[:1]})
    assert grade_view_matching(case, generation.model_copy(update={"query_plan": wrong_plan}))[:2] == ("pass", "fail")
    wrong_mapping = case.expected_match.model_copy(update={"fields": []})
    wrong_trace = trace.model_copy(update={"mapping_attempts": [MappingAttempt(
        attempt_index=1, mapping=wrong_mapping, outcome="selected")]})
    assert grade_view_matching(case, generation.model_copy(update={"query_trace": wrong_trace}))[:2] == ("fail", "pass")
    refused = SQLGenerationResponse(supported=False, explanation="safe refusal", query_trace=QueryTaskTrace(
        request=rejected.request, mapping_attempts=[MappingAttempt(attempt_index=1,
        mapping=rejected.expected_match.model_copy(update={"unsupported_reason": "different explanation"}), outcome="rejected")]))
    assert grade_view_matching(rejected, refused) == ("pass", "pass", [])
    assert grade_view_matching(case, refused)[0] != "pass"


@pytest.mark.parametrize("sql_difficulty", "SMH")
@pytest.mark.parametrize("semantic_difficulty", ("L1", "L2", "L3"))
def test_all_nine_cells_have_compilable_ground_truth(retail, sql_difficulty, semantic_difficulty):
    catalog, path, _, _ = retail
    case = next(wrapped.view_matching_case for wrapped in load_cases(path).cases
                if wrapped.view_matching_case.target_view == catalog.views()[0].name
                and wrapped.view_matching_case.sql_difficulty == sql_difficulty
                and wrapped.view_matching_case.semantic_difficulty == semantic_difficulty)
    validate_view_case(case, catalog)
    spec = case.expected_sql
    plan = QueryPlan(supported=True, source_views=[case.target_view], select_columns=spec.select_columns,
        filters=spec.filters, aggregations=spec.aggregations, group_by=spec.group_by, order_by=spec.order_by)
    response = SQLGenerationResponse(supported=True, sql=compile_single_view(plan, catalog, request=case.request),
        selected_views=[case.target_view], explanation="test", query_plan=plan,
        query_trace=QueryTaskTrace(request=case.request, selected_mapping_index=1,
            mapping_attempts=[MappingAttempt(attempt_index=1, mapping=case.expected_match, outcome="selected")]))
    assert grade_view_matching(case, response) == ("pass", "pass", [])


def test_prompt_version_and_atomic_persistent_budget(tmp_path):
    prompt = load_match_prompt()
    assert prompt.version == "v6" and len(prompt.system_sha256) == 64
    assert len(prompt.response_schema_sha256) == 64
    assert load_match_prompt("v1").version == "v1"
    assert load_match_prompt("v2").version == "v2"
    assert load_match_prompt("v3").version == "v3"
    assert load_match_prompt("v4").version == "v4"
    assert load_match_prompt("v5").version == "v5"
    with pytest.raises(ValueError, match="unknown"):
        load_match_prompt("v7")
    ledger = tmp_path / "private" / "calls.json"
    budget = CallBudget(3, ledger)
    def reserve(_):
        try:
            budget.reserve("model")
            return "called"
        except ModelStopped:
            return "skipped"
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, range(20)))
    assert outcomes.count("called") == 3 and outcomes.count("skipped") == 17
    assert json.loads(ledger.read_text(encoding="utf-8"))["model"] == 3
    with pytest.raises(ModelStopped, match="quota_cap_reached"):
        CallBudget(3, ledger).reserve("model")
    assert provider_stop_reason(RuntimeError("429 Too Many Requests")) == "rate_limit"
    assert provider_stop_reason(RuntimeError("401 unauthorized")) == "authentication"


def test_v5_contract_omits_unset_default_aggregation():
    catalog = SchemaCatalog(ROOT / "projects" / "retail", allow_drafts=True)
    schema = candidate_schema(catalog.views()[0])
    assert all("default_aggregation" not in column for column in schema["columns"].values())
    assert "default_aggregation" not in load_match_prompt().system
    policy = catalog.views()[0].policy.copy()
    policy["columns"] = {name: spec.copy() for name, spec in policy["columns"].items()}
    policy["columns"][next(iter(policy["columns"]))]["default_aggregation"] = "sum"
    with pytest.raises(ValueError, match="unsupported column settings"):
        SchemaCatalog._validate_policy(policy)


@pytest.mark.parametrize("version, has_response_schema", [("v4", False), ("v5", True), ("v6", True)])
def test_match_prompt_schema_visibility(tmp_path, version, has_response_schema):
    settings, catalog, packer, _, retriever = dependencies(tmp_path / "profile")
    class CapturingLLM(StubLLM):
        human = ""

        def invoke(self, messages):
            if "table定義:" in messages[-1].content:
                self.human = messages[-1].content
            return super().invoke(messages)

    llm = CapturingLLM()
    runtime = AssistantRuntime(settings, catalog=catalog, llm=llm,
                               retriever=retriever, context_packer=packer,
                               match_prompt=load_match_prompt(version))
    assert runtime.generate(QUESTION).supported
    assert '"candidates"' in llm.human
    assert ('"response_schema"' in llm.human) is has_response_schema


def test_equivalent_grounded_spans_and_select_order_pass(retail):
    catalog, path, _, _ = retail
    raw = next(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if '"case_id": "RETAIL-SALES_DETAIL-M3-01"' in line)
    case = ViewMatchingCase.model_validate(raw)
    spec = case.expected_sql
    assert spec is not None
    mapping = case.expected_match.model_copy(deep=True)
    fields = list(mapping.fields)
    fields[1].text = "扣完折扣的銷售金額合計"
    fields[2].text = "這行商品賣了幾件的單列最大值"
    group = mapping.group[0].model_copy(update={"text": "照訂單落在哪個月分組"})
    mapping = mapping.model_copy(update={"fields": [fields[1], fields[2], fields[0]], "group": [group]})
    plan = QueryPlan(supported=True, source_views=[case.target_view],
                     select_columns=[spec.select_columns[1], spec.select_columns[2], spec.select_columns[0]],
                     filters=spec.filters, having=spec.having or [], aggregations=spec.aggregations,
                     group_by=spec.group_by, order_by=spec.order_by)
    sql = compile_single_view(plan, catalog, request=case.request)
    trace = QueryTaskTrace(request=case.request, selected_mapping_index=1,
        mapping_attempts=[MappingAttempt(attempt_index=1, mapping=mapping, outcome="selected")])
    generation = SQLGenerationResponse(supported=True, sql=sql, selected_views=[case.target_view],
                                       explanation="test", query_plan=plan, query_trace=trace)
    assert grade_view_matching(case, generation, catalog=catalog) == ("pass", "pass", [])
    altered = generation.model_copy(update={"sql": sql.replace("SUM([net_sales])", "AVG([net_sales])")})
    assert "sql_compiled_structure" in grade_view_matching(case, altered, catalog=catalog)[2]


def test_workflow_trace_keeps_selected_parsed_mapping(tmp_path):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path / "profile")
    runtime = AssistantRuntime(settings, catalog=catalog, llm=llm,
                               retriever=retriever, context_packer=packer)
    result = runtime.generate(QUESTION)
    trace = result.query_trace
    assert result.supported and trace.selected_mapping_index == 1
    assert trace.mapping_attempts[0].outcome == "selected"
    assert trace.mapping_attempts[0].mapping.table.view == catalog.views()[0].name


@pytest.mark.parametrize("first_response", ("parse_error", "rejected"))
def test_workflow_trace_keeps_retry_sequence(tmp_path, first_response):
    settings, catalog, packer, _, retriever = dependencies(tmp_path / "profile")
    class RetryStub(StubLLM):
        def __init__(self):
            super().__init__()
            self.first = True
        def invoke(self, messages):
            if self.first and "table定義:" in messages[-1].content:
                self.first = False
                content = ("{bad" if first_response == "parse_error" else
                           '{"fields":[],"table":null,"criteria":[],"having":[],"order":[],"group":[],"ignored":[]}')
                return SimpleNamespace(content=content)
            return super().invoke(messages)
    runtime = AssistantRuntime(settings, catalog=catalog, llm=RetryStub(),
                               retriever=retriever, context_packer=packer)
    trace = runtime.generate(QUESTION).query_trace
    assert [attempt.outcome for attempt in trace.mapping_attempts] == [
        "parse_error" if first_response == "parse_error" else "rejected", "selected"]
    assert trace.selected_mapping_index == 2


def test_stability_requires_all_repetitions_correct():
    records = [{"case_id": "A", "repetition": index, "status": status,
                "generation": {"supported": True, "selected_views": [], "query_plan": None, "sql": None},
                "elapsed_ms": 1.0} for index, status in enumerate(("pass", "pass", "fail"), 1)]
    metrics = model_metrics(records, [], 3)
    assert metrics["complete_repeated_cases"] == 1
    assert metrics["all_pass_cases"] == 0
    assert metrics["status_consistent_cases"] == 0
    failed = [{**record, "status": "fail"} for record in records]
    metrics = model_metrics(failed, [], 3)
    assert metrics["status_consistent_cases"] == 1 and metrics["all_pass_cases"] == 0
    pending = [{**record, "status": None} for record in records]
    assert model_metrics(pending, [], 3)["complete_repeated_cases"] == 0
