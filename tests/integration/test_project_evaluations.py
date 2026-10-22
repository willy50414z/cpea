import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pytest
import yaml

from cpea.config.projects import resolve_project
from evaluations.governance_inputs import ProjectCase, load_cases
from evaluations.governance_reports import regenerate
from evaluations.project_runner import _runtime_for_project, evaluate_project
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from tests.support import QUESTION, StubLLM, VIEW, write_profile


ROOT = Path(__file__).resolve().parents[2]


def project_fixture(tmp_path):
    projects = tmp_path / "projects"
    root = write_profile(projects / "acme")
    (root / ".env").write_text(
        "ASSISTANT_LLM_PROVIDER=ollama\nASSISTANT_LLM_MODEL=offline-test\n"
        "ASSISTANT_RETRIEVAL_MODE=lexical\nASSISTANT_LLM_NUM_CTX=16000\n"
        "ASSISTANT_LLM_API_KEY=secret-only-for-test\n", encoding="utf-8")
    case = ProjectCase(case_id="CORE-001", category="core", profile_id="synthetic",
        question=QUESTION, expected_supported=True, expected_view=VIEW,
        expected_filters={"品号": "ZX100"}, expected_group_by=["仓库名称"],
        expected_aggregations={"库存数量": "sum"})
    file = root / "evaluations" / "cases.jsonl"
    file.parent.mkdir(parents=True)
    file.write_text(case.model_dump_json() + "\n", encoding="utf-8")
    return projects, root, file


def test_project_resolution_and_identity_preflight(tmp_path, monkeypatch):
    projects, root, file = project_fixture(tmp_path)
    workspace = resolve_project("acme", projects_root=projects)
    assert workspace.root == root.resolve()
    runtime = _runtime_for_project(workspace)
    assert runtime.catalog.profile_id == "synthetic"
    assert runtime.datasource_id == runtime.settings.datasource_id == "acme"
    for bad in ("../acme", "other/acme", "/tmp/acme"):
        with pytest.raises(ValueError, match="project ID"):
            resolve_project(bad, projects_root=projects)
    monkeypatch.setenv("CPEA_PROFILE_PATH", str(tmp_path / "other"))
    with pytest.raises(ValueError, match="conflicts"):
        _runtime_for_project(workspace)
    monkeypatch.delenv("CPEA_PROFILE_PATH")
    file.unlink()
    with pytest.raises(ValueError, match="cases.jsonl"):
        resolve_project("acme", projects_root=projects)


def test_project_rejects_artifact_symlink_escape(tmp_path):
    projects, root, _ = project_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "artifacts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="artifacts must remain"):
        resolve_project("acme", projects_root=projects)


def test_draft_profile_requires_evaluation_opt_in(tmp_path):
    projects, root, _ = project_fixture(tmp_path)
    manifest = root / "manifest.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["status"] = "draft"
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    workspace = resolve_project("acme", projects_root=projects)
    with pytest.raises(ValueError, match="draft contracts"):
        _runtime_for_project(workspace)
    assert _runtime_for_project(workspace, allow_draft_profile=True).catalog.status == "draft"
    with pytest.raises(ValueError, match="draft profile requires"):
        evaluate_project("acme", projects_root=projects, repo_root=ROOT,
                         runtime=_runtime_for_project(workspace, allow_draft_profile=True),
                         model_factory=lambda target, settings: StubLLM())


def test_project_cases_have_stable_unique_ids_and_profile(tmp_path):
    projects, root, file = project_fixture(tmp_path)
    case = json.loads(file.read_text(encoding="utf-8"))
    file.write_text(json.dumps(case) + "\n" + json.dumps(case) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case_id must be unique"):
        load_cases(file)
    case["profile_id"] = "another-profile"
    file.write_text(json.dumps(case) + "\n", encoding="utf-8")
    from evaluations.project_runner import _cases_for_project
    with pytest.raises(ValueError, match="profile_id"):
        _cases_for_project(resolve_project("acme", projects_root=projects),
                           _runtime_for_project(resolve_project("acme", projects_root=projects)))


def test_project_run_reports_and_collision(tmp_path):
    projects, _, _ = project_fixture(tmp_path)
    when = datetime(2026, 10, 15, 9, 30, 1, 123456, tzinfo=timezone.utc)
    run = evaluate_project("acme", runs=2, concurrency=1, projects_root=projects,
        repo_root=ROOT, model_factory=lambda target, settings: StubLLM(), timestamp=when)
    output = Path(run["output"])
    assert run["mode"] == "offline-synthetic" and run["completed_total"] == 2
    assert run["run_id"].startswith("20261015T093001123456Z-")
    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert metadata["project_id"] == "acme" and metadata["completed_total"] == 2
    assert len(metadata["project_casefile_sha256"]) == 64
    assert metadata["prompt"]["system_sha256"] == load_match_prompt().system_sha256
    assert metadata["prompt"]["human_sha256"] == load_match_prompt().human_sha256
    calls = [json.loads(line) for line in (output / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 2
    assert all(call["request"][0]["content"] == load_match_prompt().system for call in calls)
    assert "secret-only-for-test" not in json.dumps(metadata)
    assert {"run.json", "calls.jsonl", "results.jsonl", "summary.csv", "model_summary.csv",
            "category_summary.csv", "overview.md"} <= {p.name for p in output.iterdir()}
    with (output / "category_summary.csv").open(encoding="utf-8", newline="") as stream:
        categories = list(csv.DictReader(stream))
    assert len(categories) == 1 and categories[0]["category"] == "core"
    overview = (output / "overview.md").read_text(encoding="utf-8")
    assert "預定：2；已完成：2；略過：0" in overview
    assert QUESTION not in overview and "secret-only-for-test" not in overview
    before = (output / "overview.md").read_bytes()
    regenerate(output)
    assert (output / "overview.md").read_bytes() == before
    with pytest.raises(FileExistsError):
        evaluate_project("acme", runs=2, concurrency=1, projects_root=projects,
            repo_root=ROOT, model_factory=lambda target, settings: StubLLM(), timestamp=when)


@pytest.mark.skipif(not (ROOT / "projects/retail/manifest.yaml").is_file(), reason="private Retail profile and approved cases are not installed")
def test_retail_pending_case_is_exploratory_only(tmp_path):
    source = ROOT / "projects" / "retail"
    projects = tmp_path / "projects"
    project = projects / "retail"
    (project / "evaluations").mkdir(parents=True)
    for name in ("manifest.yaml", "catalog.yaml"):
        shutil.copyfile(source / name, project / name)
    shutil.copytree(source / "views", project / "views")
    first = (source / "evaluations" / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0]
    (project / "evaluations" / "cases.jsonl").write_text(first + "\n", encoding="utf-8")
    (project / ".env").write_text("ASSISTANT_LLM_PROVIDER=ollama\nASSISTANT_LLM_MODEL=offline-test\n"
        "ASSISTANT_RETRIEVAL_MODE=lexical\nASSISTANT_LLM_NUM_CTX=16000\n", encoding="utf-8")
    prompt_version = json.loads(first)["prompt_version"]
    factory_calls = []
    def factory(target, settings):
        factory_calls.append(1)
        return StubLLM()
    with pytest.raises(ValueError, match="no approved cases"):
        evaluate_project("retail", projects_root=projects, repo_root=ROOT,
                         allow_draft_profile=True, model_factory=factory, prompt_version=prompt_version)
    assert not factory_calls
    result = evaluate_project("retail", projects_root=projects, repo_root=ROOT,
                              allow_draft_profile=True, exploratory=True,
                              runs=1, model_factory=factory, prompt_version=prompt_version)
    assert result["planned_total"] == 1 and result["completed_total"] == 1
    record = json.loads((Path(result["output"]) / "results.jsonl").read_text(encoding="utf-8"))
    assert record["review_state"] == "pending" and record["status"] is None
    with (Path(result["output"]) / "view_grid_summary.csv").open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["target_view"] == record["target_view"] and row["pending"] == "1"
