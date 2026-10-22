"""核對未修改的第二步自然輸出；不修補或生成答案。"""
import json
from pathlib import Path

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.three_stage_view_selection import ViewCoverage, _evidence

task = Path('evidence-driven-dev/tasks/ollama-planning-mvp')
folder = task / '.local/qwen-coverage-20261021T100803Z-e0f13d'
meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
coverage = ViewCoverage.model_validate_json((folder / 'map-01-parsed.json').read_text(encoding='utf-8'))
policy = next(v.policy for v in SchemaCatalog('projects/retail').views() if v.name == coverage.view)
assert meta['calls'] == 1 and meta['valid_views'] == 0
assert meta['stopped']['error'] == 'invalid contract evidence quote /grain/keys'
assert coverage.grain == policy['grain']['description'] and coverage.keys == policy['grain']['keys']
findings = []
for entry in coverage.entries:
    for evidence in entry.contract_evidence:
        try:
            _evidence([evidence], policy)
        except ValueError as exc:
            findings.append(dict(requirement_id=entry.requirement_id, path=evidence.path, error=str(exc)))
    for mapping in entry.mappings:
        for evidence in mapping.contract_evidence:
            _evidence([evidence], policy)
        required = f'/columns/{mapping.column}/description'
        if not any(e.path == required for e in mapping.contract_evidence):
            findings.append(dict(requirement_id=entry.requirement_id, column=mapping.column,
                                 required_path=required, error='missing own column description evidence'))
assert len(findings) == 3
assert findings[0]['requirement_id'] == 'R_GRAIN' and findings[0]['path'] == '/grain/keys'
assert isinstance(policy['grain']['keys'], list)
assert {x.get('column') for x in findings[1:]} == {'store_id', 'product_id'}
entries = {e.requirement_id: e for e in coverage.entries}
assert entries['R_STOCK_QTY'].mappings[0].column == 'stock_qty'
assert entries['R_SNAPSHOT_DATE'].mappings[0].column == 'snapshot_date'
for identifier in ('F_TIME', 'F_CHANNEL', 'R_DISCOUNT', 'R_NET_SALES', 'R_PURPOSE'):
    assert entries[identifier].status == 'unsupported' and not entries[identifier].mappings
assert not list(folder.glob('map-02-*'))
print(json.dumps(dict(result='PASS', scope='unchanged raw findings audit; not a passing ViewCoverage',
                      findings=findings, attempted_views=1, remaining_not_executed=6,
                      model_calls=0, repaired=False), ensure_ascii=False))
