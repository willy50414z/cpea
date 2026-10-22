"""Offline evidence audit; revalidation does not rewrite the original result."""
from hashlib import sha256
import json
from pathlib import Path

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.three_stage_view_selection import VERSION, RecallResult, ViewCoverage, validate_recall, validate_coverage
from evaluations.three_stage_view_selection_runner import fingerprint, messages_for, replay


def main():
    task = Path('evidence-driven-dev/tasks/ollama-planning-mvp')
    folder = task / '.local/three-stage-20261021T015033Z-466574'
    load = lambda name: json.loads((folder / name).read_text(encoding='utf-8'))
    meta = load('run.json')
    catalog = SchemaCatalog('projects/retail')
    case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog)
                if c['case_id'] == 'cross-view-11')
    assert {p.name for p in folder.iterdir()} == set(meta['artifact_hashes']) | {'run.json'}
    for name, digest in meta['artifact_hashes'].items():
        assert sha256((folder / name).read_bytes()).hexdigest() == digest, name
    assert meta['calls'] == 2 and len(list(folder.glob('*-call.json'))) == 2
    assert meta['stopped'] == {'error_type': 'ValueError', 'error': 'invalid contract evidence path /grain/keys/0'}
    for name in ('three_stage_view_selection.py', 'three_stage_view_selection_runner.py'):
        old = task / '.local/three-stage-v1-sources' / name
        assert sha256(old.read_bytes()).hexdigest() == meta['frozen']['source_hashes']['evaluations/' + name]
    current = fingerprint(catalog, case)
    changed = [name for name, digest in meta['frozen']['source_hashes'].items() if current['source_hashes'][name] != digest]
    assert set(changed) == {'evaluations/three_stage_view_selection.py', 'evaluations/three_stage_view_selection_runner.py',
                            'tests/unit/test_three_stage_view_selection.py'}
    assert current['schemas'] == meta['frozen']['schemas']
    assert current['catalog'] == meta['frozen']['catalog']
    assert current['case_sha256'] == meta['frozen']['case_sha256']
    recall = RecallResult.model_validate_json(load('recall-call.json')['response'])
    validate_recall(recall, case['request'], catalog)
    assert recall.model_dump() == load('recall-result.json')
    mapped = ViewCoverage.model_validate_json(load('map-01-call.json')['response'])
    validate_coverage(mapped, recall, case['request'], catalog)
    assert mapped.view == recall.candidate_views[0].view == 'demo_retail.v_customer_value'
    assert len(mapped.entries) == len(recall.requirements) == 10
    assert all(e.status == 'unsupported' for e in mapped.entries)
    for name, messages in [
        ('recall', messages_for('recall', RecallResult, case['request'], views=[v.policy for v in catalog.views()])),
        ('map-01', messages_for('coverage', ViewCoverage, case['request'],
            requirements=[r.model_dump() for r in recall.requirements],
            view=next(v.policy for v in catalog.views() if v.name == mapped.view))),
    ]:
        assert load(name + '-request.json')['messages'] == [dict(role=m.type, content=m.content) for m in messages]
    assert not (folder / 'response.json').exists() and not (folder / 'selection-call.json').exists()
    continuation = task / '.local/three-stage-20261021T015638Z-2e0352'
    continued_meta = json.loads((continuation / 'run.json').read_text(encoding='utf-8'))
    replayed = replay(continuation, catalog, case)
    assert replayed['raw_replays'] == 4 and replayed['stopped'] == {
        'error_type': 'ValueError', 'error': 'invalid contract evidence quote /grain/keys'}
    assert continued_meta['new_provider_calls'] == continued_meta['cached_raw_replayed'] == 2
    assert not continued_meta['fixed_version_first_pass']
    assert continued_meta['original_run_sha256'] == sha256((folder / 'run.json').read_bytes()).hexdigest()
    for name in ('recall', 'map-01'):
        old = load(name + '-call.json')
        new = json.loads((continuation / (name + '-call.json')).read_text(encoding='utf-8'))
        assert old['response'] == new['response'] and old['usage'] == new['usage']
        assert new['origin'] == 'cached_raw'
    last = json.loads((continuation / 'map-03-call.json').read_text(encoding='utf-8'))
    inventory = ViewCoverage.model_validate_json(last['response'])
    assert inventory.view == 'demo_retail.v_inventory_status'
    policy = next(v.policy for v in catalog.views() if v.name == inventory.view)
    assert policy['grain']['keys'] == ['store_id', 'product_id']
    assert any(e.path == '/grain/keys' and e.quote == 'store_id' for e in inventory.contract_evidence)
    try:
        validate_coverage(inventory, recall, case['request'], catalog)
    except ValueError as exc:
        assert str(exc) == 'invalid contract evidence quote /grain/keys'
    else:
        raise AssertionError('invalid inventory evidence was accepted')
    for product_file in ('src/cpea/application/models/decomposition.py', 'src/cpea/workflows/task_decomposition/prompt.py'):
        assert current['source_hashes'][product_file] == meta['frozen']['source_hashes'][product_file]
    summary = dict(result='PASS_WITH_WARNINGS', original_run_version=meta['version'],
                   original_stop=meta['stopped'], original_result_unchanged=True,
                   revalidation_version=VERSION, raw_revalidated=2, new_provider_calls=0,
                   changed_sources=changed, unchanged_prompt_schema_catalog_case=True,
                   recall_requirement_count=10, recall_candidate_count=7,
                   mapped_views_revalidated=1, mapped_views_remaining=6,
                   stage_three='NOT_EXECUTED', end_to_end_semantics='NOT_VERIFIED',
                   calls=meta['calls'], input_tokens_actual=meta['input_tokens_actual'],
                   output_tokens_actual=meta['output_tokens_actual'], elapsed_seconds=meta['elapsed_seconds'],
                   cost_usd=None, raw_run_sha256=sha256((folder / 'run.json').read_bytes()).hexdigest(),
                   continuation_result=replayed, continuation_new_calls=continued_meta['new_provider_calls'],
                   total_distinct_provider_calls=meta['calls'] + continued_meta['new_provider_calls'],
                   combined_input_tokens_actual=continued_meta['input_tokens_actual'],
                   combined_output_tokens_actual=continued_meta['output_tokens_actual'],
                   combined_elapsed_seconds=continued_meta['elapsed_seconds'],
                   completed_mapping_views=2, attempted_mapping_views=3,
                   continuation_run_sha256=sha256((continuation / 'run.json').read_bytes()).hexdigest(),
                   product_sources_unchanged=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    main()
