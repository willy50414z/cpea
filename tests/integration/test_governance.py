import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from evaluations.governance_inputs import CaseFile, GovernanceCase, ModelTarget, load_cases, load_models
from evaluations.governance_runner import _provider_preflight, evaluate, grade, main, preflight
from tests.integration.test_runtime import runtime_fixture
from tests.support import StubLLM, QUESTION, VIEW
from evaluations.governance_trace import CallRecorder, TracedModel
from langchain_core.messages import AIMessage


ROOT = Path(__file__).resolve().parents[2]


def test_separate_inputs_and_invalid_cases(tmp_path):
    cases = load_cases(ROOT / "evaluations/datasets/governance_cases.json")
    models = load_models(ROOT / "evaluations/config/models.json")
    assert len(cases.cases) == 4
    assert [target.model for target in models.models][:2] == ["gemma4:e4b", "qwen3:4b"]
    duplicate = {"version": 1, "cases": [cases.cases[0].model_dump(), cases.cases[0].model_dump()]}
    with pytest.raises(ValueError, match="case_id must be unique"):
        CaseFile.model_validate(duplicate)
    with pytest.raises(ValueError, match="provider and transport"):
        ModelTarget(provider="gcp", transport="ollama", model="x", deployment="x")
    assert GovernanceCase(case_id="REJECT", category="security", difficulty="easy",
                          question="拒絕查詢", expected_result={"supported": False}).expected_result.supported is False


def _case():
    return GovernanceCase(case_id="SIMPLE-TEST", category="simple", difficulty="easy",
                          question=QUESTION, expected_result={"supported": True, "view": VIEW,
                              "filters": {"品号": "ZX100"}, "group_by": ["仓库名称"],
                              "aggregations": {"库存数量": "sum"}})


def _output():
    return ROOT / "artifacts" / "evaluations" / uuid4().hex


def test_offline_stability_records_calls_and_regenerates(tmp_path):
    runtime = runtime_fixture(tmp_path, executor=lambda datasource, sql: (["仓库名称", "库存数量"], [["A", 10]]), datasource_id="test")
    target = ModelTarget(provider="local", transport="ollama", model="stub")
    output = _output()
    results, calls = evaluate([_case()], [target], runtime=runtime, output=output, runs=2,
                              model_factory=lambda target, settings: StubLLM(), repo_root=ROOT)
    assert [result["status"] for result in results] == ["pass", "pass"]
    assert len(calls) >= 2 and {call["node_name"] for call in calls} == {"schema_match"}
    assert all(call["git_sha"] and call["request"] and call["response"] for call in calls)
    assert all(call["input_tokens"] is None and call["token_source"] == "unavailable" for call in calls)
    assert output.joinpath("summary.csv").exists() and output.joinpath("overview.md").exists()
    assert json.loads(output.joinpath("run.json").read_text(encoding="utf-8"))["kind"] == "offline-synthetic"
    assert output.joinpath("cases/SIMPLE-TEST.md").exists()
    original = output.joinpath("summary.csv").read_bytes()
    assert main(["report", str(output)]) == 0
    assert output.joinpath("summary.csv").read_bytes() == original


def test_compare_traces_retry_and_answer(tmp_path):
    runtime = runtime_fixture(tmp_path, executor=lambda datasource, sql: (["仓库名称", "库存数量"], [["A", 10]]), datasource_id="test")
    case = _case().model_copy(update={"expected_result": _case().expected_result.model_copy(update={
        "answer_contains": ["合成庫存資料"], "require_citation": True})})
    class RetryModel(StubLLM):
        def with_structured_output(self, schema, **kwargs):
            underlying = super().with_structured_output(schema, **kwargs)
            def invoke(messages):
                if not getattr(self, "retried", False):
                    self.retried = True
                    raise ValueError("malformed first response")
                return underlying.invoke(messages)
            return SimpleNamespace(invoke=invoke)
    targets = [ModelTarget(provider="local", transport="ollama", model=name) for name in ("stub-a", "stub-b")]
    results, calls = evaluate([case], targets, runtime=runtime, output=_output(),
                              model_factory=lambda target, settings: RetryModel(), repo_root=ROOT)
    assert [record["status"] for record in results] == ["pass", "pass"]
    assert sum(call["node_name"] == "schema_match" for call in calls) >= 4
    assert sum(call["node_name"] == "answer_synthesis" for call in calls) == 2
    assert sum(bool(call["error"]) for call in calls) == 2
    assert all(record["call_ids"] for record in results)


def test_security_failure_and_pending_review(tmp_path):
    runtime = runtime_fixture(tmp_path)
    generation = runtime.generate(QUESTION)
    unsafe = GovernanceCase(case_id="SEC-TEST", category="security", difficulty="hard",
                            question=QUESTION, expected_result={"supported": False, "sql_forbidden": ["SELECT"]})
    assert grade(unsafe, generation, None, [])[0] == "fail"
    review = GovernanceCase(case_id="REVIEW-TEST", category="simple", difficulty="easy",
                            question=QUESTION, expected_result={"supported": True, "human_review": True})
    assert grade(review, generation, None, [])[:2] == (None, "pending")
    ambiguous = GovernanceCase(case_id="AMB-TEST", category="ambiguous", difficulty="medium",
                               question="請查第一季庫存數量", expected_result={"supported": False, "clarification": True})
    ambiguous_result = runtime.generate(ambiguous.question)
    assert grade(ambiguous, ambiguous_result, None, [])[0] == "pass"


def test_live_preflight_refuses_dirty_worktree_and_unignored_output(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="output must be under"):
        preflight(ROOT, tmp_path / "result", live=False)
    output = _output()
    assert preflight(ROOT, output, live=False)
    monkeypatch.setattr("evaluations.governance_runner._git", lambda root, *args: "dirty" if args[0] == "status" else "a" * 40)
    with pytest.raises(ValueError, match="clean Git worktree"):
        preflight(ROOT, output, live=True)


def test_cli_stability_requires_explicit_live_or_stub(tmp_path):
    runtime = runtime_fixture(tmp_path)
    cases = tmp_path / "cases.json"
    cases.write_text(CaseFile(version=1, cases=[_case()]).model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="select --live"):
        main(["stability", "--cases", str(cases)], runtime=runtime)
    assert main(["stability", "--cases", str(cases), "--runs", "1", "--output-dir", str(_output())],
                runtime=runtime, model_factory=lambda target, settings: StubLLM()) == 0
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"version": 1, "models": [
        {"provider": "local", "transport": "ollama", "model": "stub-a"},
        {"provider": "local", "transport": "ollama", "model": "stub-b"}]}), encoding="utf-8")
    assert main(["compare", "--cases", str(cases), "--models", str(models),
                 "--output-dir", str(_output())], runtime=runtime,
                model_factory=lambda target, settings: StubLLM()) == 0


def test_model_error_retains_failed_call(tmp_path):
    runtime = runtime_fixture(tmp_path)
    class BrokenModel(StubLLM):
        def with_structured_output(self, schema, **kwargs):
            return SimpleNamespace(invoke=lambda messages: (_ for _ in ()).throw(TimeoutError("offline timeout")))
    result, calls = evaluate([_case()], [ModelTarget(provider="local", transport="ollama", model="broken")],
                             runtime=runtime, output=_output(), model_factory=lambda target, settings: BrokenModel(),
                             repo_root=ROOT)
    assert result[0]["status"] == "error"
    assert calls and calls[0]["error"].startswith("TimeoutError")


def test_provider_usage_is_not_estimated(tmp_path):
    settings = runtime_fixture(tmp_path).settings
    target = ModelTarget(provider="local", transport="ollama", model="usage-stub")
    recorder = CallRecorder(run_id="offline", git_sha="a" * 40)
    response = AIMessage(content="ok", usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15})
    model = SimpleNamespace(invoke=lambda messages: response)
    assert TracedModel(model, recorder, case_id="ONE", repetition=1,
                       target=target, settings=settings).invoke("test").content == "ok"
    assert recorder.calls[0]["input_tokens"] == 12
    assert recorder.calls[0]["output_tokens"] == 3
    assert recorder.calls[0]["token_source"] == "provider"


def test_cloud_preflight_is_configuration_only(tmp_path, monkeypatch):
    settings = runtime_fixture(tmp_path).settings
    monkeypatch.setattr("evaluations.governance_runner.find_spec", lambda name: object())
    azure = ModelTarget(provider="azure", transport="azure", model="a", deployment="a",
                        endpoint_env="CPEA_AZURE_LLM_BASE_URL")
    with pytest.raises(ValueError, match="configure CPEA_AZURE_LLM_BASE_URL"):
        _provider_preflight(azure, settings, {})
    gcp = ModelTarget(provider="gcp", transport="google", model="g", deployment="g")
    with pytest.raises(ValueError, match="configure GCP project"):
        _provider_preflight(gcp, settings, {})


def test_explicit_env_selects_stability_model_without_live_service(tmp_path):
    env = tmp_path / "selected.env"
    env.write_text("ASSISTANT_LLM_PROVIDER=ollama\nASSISTANT_LLM_MODEL=qwen3:4b\nASSISTANT_RETRIEVAL_MODE=lexical\nASSISTANT_LLM_NUM_CTX=16000\n", encoding="utf-8")
    output = _output()
    assert main(["stability", "--cases", str(ROOT / "evaluations/datasets/governance_cases.json"),
                 "--env-file", str(env), "--runs", "1", "--output-dir", str(output)],
                model_factory=lambda target, settings: StubLLM(view="demo.v_inventory")) == 0
    records = [json.loads(line) for line in (output / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4 and {record["model"] for record in records} == {"qwen3:4b"}
