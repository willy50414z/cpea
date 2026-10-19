from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from cpea.application.models.query import ClarificationChoice
from cpea.bootstrap import AssistantRuntime
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.interfaces.api.app import create_app
from cpea.interfaces.cli.main import main as cli_main
from cpea.interfaces.web.ui import SessionGate, query_updates
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow, ViewComparison
from cpea.workflows.text_to_sql.schemas import SQLClauseMappingV3
from tests.support import Counter


PROFILE = Path("projects/retail")
REQUEST = "列出逐筆銷售的金額"
ORDER = "demo_retail.v_order_summary"
DETAIL = "demo_retail.v_sales_detail"


class AmbiguousLLM:
    def __init__(self, comparison=None):
        self.calls = 0
        self.comparison = comparison

    def with_response_schema(self, schema):
        model = ViewComparison if schema["title"] == "ViewComparison" else SQLClauseMappingV3
        def invoke(messages):
            self.calls += 1
            if model is ViewComparison:
                payload = model.model_validate(self.comparison or {
                    "decision": "clarify", "question": "逐筆是指訂單還是商品明細？",
                    "options": [
                        {"id": ORDER, "label": "每筆訂單", "description": "每筆已完成訂單一列"},
                        {"id": DETAIL, "label": "每筆商品明細", "description": "訂單中的每個商品品項"},
                    ],
                })
                return SimpleNamespace(content=payload.model_dump_json())
            content = str(messages[-1].content)
            view = ORDER if ORDER in content else DETAIL if DETAIL in content else None
            column = "order_amount" if view == ORDER else "net_sales"
            request_text = "訂單金額" if "訂單金額" in content.split("table定義:", 1)[0] else "金額"
            fields = ([{"text": request_text, "column": column, "aggregation": None}]
                      if view else [])
            if view and "訂單編號" in content.split("table定義:", 1)[0]:
                fields.insert(0, {"text": "訂單編號", "column": "order_no", "aggregation": None})
            payload = model.model_validate({
                "fields": fields,
                "table": {"text": None, "view": view} if view else None,
                "criteria": [], "having": [], "order": [], "group": [], "ignored": [],
                "unsupported_reason": None if view else "沒有逐筆銷售金額欄位",
            })
            return SimpleNamespace(content=payload.model_dump_json())
        return SimpleNamespace(invoke=invoke)


def workflow(comparison=None):
    settings = replace(AssistantSettings.from_env(PROFILE / ".env"),
                       retrieval_mode="lexical", context_window=16000)
    catalog = SchemaCatalog(PROFILE, allow_drafts=True)
    llm = AmbiguousLLM(comparison)
    packer = ContextPacker(settings, token_counter=Counter())
    retriever = SchemaRetriever(settings, catalog=catalog)
    return SQLGenerationWorkflow(llm, catalog, settings=settings,
                                 retriever=retriever, context_packer=packer), llm, catalog


def test_ambiguous_views_request_clarification_before_sql():
    runtime, llm, catalog = workflow()
    response = runtime.invoke(REQUEST)
    assert response.status == "needs_clarification"
    assert not response.supported and response.sql is None and response.query_plan is None
    assert response.clarification.contract_fingerprint == catalog.fingerprint
    assert {item.id for item in response.clarification.options} == {ORDER, DETAIL}
    assert response.query_trace.selected_view is None
    assert llm.calls >= 3


def test_choice_revalidates_and_rejects_stale_or_unoffered_option():
    runtime, _, catalog = workflow()
    selected = runtime.invoke(REQUEST, clarification_choice=ClarificationChoice(
        option_id=DETAIL, contract_fingerprint=catalog.fingerprint))
    assert selected.status == "ready" and selected.selected_views == [DETAIL]
    assert "v_sales_detail" in selected.sql
    stale = runtime.invoke(REQUEST, clarification_choice=ClarificationChoice(
        option_id=DETAIL, contract_fingerprint="stale"))
    assert stale.status == "unsupported" and stale.sql is None
    forged = runtime.invoke(REQUEST, clarification_choice=ClarificationChoice(
        option_id="demo_retail.v_inventory_status", contract_fingerprint=catalog.fingerprint))
    assert forged.status == "unsupported" and forged.sql is None


def test_comparison_cannot_select_using_a_shared_ambiguous_term():
    runtime, _, _ = workflow({"decision": "select", "selected_view": ORDER,
        "request_evidence": "逐筆", "contract_evidence": "每筆已完成訂單一列"})
    response = runtime.invoke(REQUEST)
    assert response.status == "needs_clarification" and response.sql is None


def test_unique_mapped_contract_phrase_selects_clear_order_view():
    runtime, _, _ = workflow()
    response = runtime.invoke("列出每筆已完成訂單的訂單編號與訂單金額")
    assert response.status == "ready"
    assert response.selected_views == [ORDER]
    assert "order_amount" in response.sql


def test_api_and_ui_do_not_execute_before_clarification():
    generator, llm, catalog = workflow()
    database_calls = []
    runtime = AssistantRuntime(generator.settings, catalog=catalog, llm=llm,
        retriever=generator.retriever, context_packer=generator.context_packer,
        executor=lambda datasource, sql: (database_calls.append(sql) or (["金額"], [[10]])),
        datasource_id="retail-test")
    client = TestClient(create_app(runtime))
    sql = client.post("/api/assistant/sql", json={"request": REQUEST})
    assert sql.status_code == 200 and sql.json()["status"] == "needs_clarification"
    assert sql.json()["sql"] is None
    query = client.post("/api/assistant/query", json={"request": REQUEST})
    assert query.status_code == 200 and query.json()["status"] == "needs_clarification"
    streamed = client.post("/api/assistant/query/stream", json={"request": REQUEST})
    assert streamed.status_code == 200 and "event: clarification" in streamed.text
    assert "event: sql" not in streamed.text and not database_calls
    assert cli_main(["--request", REQUEST, "--execute"], runtime=runtime) == 2
    assert not database_calls

    updates = list(query_updates(runtime, REQUEST, SessionGate()))
    assert updates[-1][5]["question"] == "逐筆是指訂單還是商品明細？"
    assert updates[-1][1].visible is False and not database_calls
    pending = updates[-1][5]
    resolved = list(query_updates(runtime, "", SessionGate(), pending, DETAIL))
    assert resolved[-1][5] is None and resolved[-1][1].visible
    assert len(database_calls) == 1

    selected = client.post("/api/assistant/sql", json={"request": REQUEST,
        "clarification_choice": {"option_id": DETAIL, "contract_fingerprint": catalog.fingerprint}})
    assert selected.status_code == 200 and selected.json()["status"] == "ready"
    assert cli_main(["--request", REQUEST, "--execute", "--clarification-option", DETAIL,
                     "--clarification-fingerprint", catalog.fingerprint], runtime=runtime) == 0
    assert len(database_calls) == 2
