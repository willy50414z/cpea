"""Independently check the authored matrix against the admitted YAML contracts."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import json

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog


def main():
    root = Path(__file__).resolve().parents[4]
    catalog = SchemaCatalog(root / "projects/retail")
    path = root / "projects/retail/evaluations/task_decomposition_cases.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 30
    assert len({row["case_id"] for row in rows}) == 30
    coverage = Counter()
    for row in rows:
        assert row["contract_fingerprint"] == catalog.fingerprint
        assert row["profile_id"] == catalog.profile_id
        assert row["expected_status"] == "ready"
        assert row["expected_strategy"] == "multi_view"
        assert row["review_status"] == "pending"
        tasks = row["expected_tasks"]
        assert len(tasks) in (2, 3)
        assert len({task["task_id"] for task in tasks}) == len(tasks)
        assert len({task["view"] for task in tasks}) == len(tasks)
        ids = {task["task_id"] for task in tasks}
        assert row["expected_integration"]["anchor_task"] in ids
        assert row["expected_integration"]["requirements"]
        # A column-level witness of necessity, distinct from a model evaluation.
        assert not any(
            all(set(task["required_columns"]) <= set(catalog.columns(view.name))
                for task in tasks)
            for view in catalog.views()
        )
        for task in tasks:
            coverage[task["view"]] += 1
            for source in [task, *task["acceptable_alternatives"]]:
                fields = set(source["required_columns"])
                assert len(fields) == len(source["required_columns"])
                assert fields <= set(catalog.columns(source["view"]))
                assert set(source["group_by"]) <= fields
                assert set(source["output_grain"]) <= fields
                assert set(source["attributes"]) <= fields
                assert not set(source["attributes"]) & set(source["metrics"])
                for condition in source["filters"]:
                    assert condition["column"] in fields
                    assert condition["operator"] in {"=", ">=", "<", "IN"}
                    assert "value" in condition
                for column, aggregation in source["metrics"].items():
                    assert column in fields
                    contract = catalog.field_contract(source["view"], column)
                    assert aggregation in contract["aggregations"]
                for column in source["group_by"]:
                    assert "group_by" in catalog.field_contract(source["view"], column)["capabilities"]
        semantic = {key: value for key, value in row.items()
                    if key not in {"review_status", "reviewer", "reviewed_at", "case_sha256"}}
        digest = sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")).hexdigest()
        assert digest == row["case_sha256"]
    assert set(coverage) == {view.name for view in catalog.views()}
    assert sum(len(row["expected_tasks"]) == 2 for row in rows) == 28
    assert sum(len(row["expected_tasks"]) == 3 for row in rows) == 2
    for file in [path, path.with_name("task_decomposition_matrix.md"),
                 root / "docs/superpowers/specs/2026-10-20-retail-task-decomposition-design.md"]:
        content = file.read_bytes()
        content.decode("utf-8")
        assert not content.startswith(b"\xef\xbb\xbf")
    print(json.dumps({"result": "PASS", "cases": len(rows), "covered_views": len(coverage),
                      "two_source_cases": 28, "three_source_cases": 2,
                      "casefile_sha256": sha256(path.read_bytes()).hexdigest(),
                      "limitations": "欄位、聚合、指紋與來源覆蓋驗證；不代表人工審核或模型 benchmark 通過。"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
