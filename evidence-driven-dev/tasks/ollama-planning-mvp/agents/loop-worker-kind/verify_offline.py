"""Record offline kind fixtures and freeze their complete repository dependencies."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[5]
WORK = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests/unit')]

from langchain_core.messages import AIMessage
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import managed_three_stage_runner as runner
from evaluations import kind_mapping_managed_contract as contract
from test_kind_mapping_managed_contract import SEMANTIC_CASES, apply, entry, inputs, recall, requirement
from test_kind_mapping_managed_runner import FAILURES, fake


def save(name, value):
    (WORK / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


catalog = SchemaCatalog('projects/retail')
request, recall_data, mapping_data, selection = inputs(catalog)
recalled = contract.materialize_recall(contract.RecallWire.model_validate(recall_data), request, catalog)
case = runner.diagnostic_case(catalog, request)
frozen = runner.fingerprint(catalog, case, contract=contract)
save('candidate-fingerprint.json', frozen)

sources = set(json.loads((WORK / 'sources-before.json').read_text(encoding='utf-8')))
sources.update(frozen['source_hashes'])
sources.update(frozen['managed_sources'])
sources.update(['tests/unit/test_kind_mapping_managed_contract.py', 'tests/unit/test_kind_mapping_managed_runner.py'])
sources.update(str(Path(module.__file__).resolve().relative_to(ROOT))
               for module in list(sys.modules.values())
               if getattr(module, '__file__', None) and Path(module.__file__).resolve().is_relative_to(ROOT)
               and '.venv' not in Path(module.__file__).resolve().parts)
# Freeze replay tooling too; it restores only canonical absolute path identities.
sources.update(str(p.relative_to(ROOT)) for p in [WORK / 'verify_offline.py', WORK / 'replay_frozen.py'])
manifest = {}
for name in sorted(sources):
    path = Path(name)
    manifest[name] = sha256(path.read_bytes()).hexdigest()
    target = WORK / 'sources-after' / name.lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
save('sources-after.json', manifest)

schemas = {s.__name__: s.model_json_schema() for s in [contract.RecallWire, contract.SelectionWire, contract.coverage_schema(recalled)]}
for kind in ['metric', 'filter', 'key', 'grain', 'population', 'attribute', 'metadata']:
    rec = recall(catalog, '需求', [requirement('需求', 'model_dump/🧾', '需求', kind, binding='independent' if kind == 'metric' else None)])
    schema = contract.coverage_schema(rec)
    schemas[schema.__name__] = schema.model_json_schema()
save('schemas.json', schemas)

runs, compiled = [], {}
for failure in FAILURES:
    label = failure or 'complete'
    request, invoke, calls = fake(catalog, failure)
    folder = WORK / 'fake-runs' / label
    meta = runner.record_run(folder, catalog, runner.diagnostic_case(catalog, request), invoke, contract=contract)
    assert bool(meta['stopped']) == bool(failure), (label, meta['stopped'])
    replay = runner.replay(folder, catalog, meta['case'], contract=contract)
    assert replay['result'] == 'PASS'
    runs.append(dict(failure=failure, folder=str(folder.relative_to(ROOT)), calls=calls, stopped=meta['stopped'], replay=replay))
    print(json.dumps(runs[-1], ensure_ascii=False), flush=True)
    if not failure:
        response = runner.read_json(folder / 'response.json')
        assert response['status'] == 'ready' and len(response['prepared_requests']) == 2
        for name in calls[1:-1]:
            parsed = runner.read_json(folder / (name + '-parsed.json'))
            wire = contract.coverage_schema(recalled).model_validate(parsed)
            compiled[name] = dict(raw_parsed=parsed, compiled_own_wire=contract.compile_coverage(wire, recalled).model_dump(by_alias=True),
                normalized=runner.read_json(folder / (name + '-normalized.json')))
save('fake-manifest.json', runs)
save('compilation-comparison.json', compiled)

semantics = []
for name, kind, quote, view, row, verdict in SEMANTIC_CASES:
    rec = recall(catalog, quote, [requirement(quote, 'arbitrary', quote, kind, binding='independent' if kind == 'metric' else None)])
    normalized = apply(catalog, quote, rec, view, {'arbitrary': row})
    semantics.append(dict(name=name, expected_semantic_verdict=verdict, structural_result='ACCEPT',
        source=view, request=quote, recall=rec.model_dump(), wire=dict(entries={'arbitrary': row}), normalized=normalized.model_dump(),
        boundary='預先人工指定的語意對照；通用parser接受不代表語意正確。'))
save('semantic-controls.json', semantics)

original = Path('evidence-driven-dev/tasks/ollama-planning-mvp/.local/qwen-managed-20261021T194515Z-8cb75b')
oldrec = runner.read_json(original / 'recall-normalized.json')
oldwire = contract.RecallWire.model_validate(json.loads(runner.read_json(original / 'recall-call.json')['response']))
original_recall = contract.materialize_recall(oldwire, runner.read_json(original / 'run.json')['case']['request'], catalog)
assert oldrec == original_recall.model_dump()
try:
    contract.parse_wire(AIMessage(content=runner.read_json(original / 'map-02-call.json')['response']), contract.coverage_schema(original_recall))
except ValueError as exc:
    save('old-mixed-wire-rejected.json', dict(result='STRUCTURAL_REJECT', error_type=type(exc).__name__, error=str(exc),
        original_semantic_verdict='FAIL：GRN-001遺漏需求有用店key；原第8輪FAIL保持，不轉譯raw。'))
else:
    raise AssertionError('old mixed-role output accepted')

history = json.loads((WORK / 'history-before.json').read_text(encoding='utf-8'))
changed = [name for name, digest in history.items() if sha256(Path(name).read_bytes()).hexdigest() != digest]
assert not changed, changed
before = json.loads((WORK / 'sources-before.json').read_text(encoding='utf-8'))
source_changes = [name for name, digest in before.items() if sha256(Path(name).read_bytes()).hexdigest() != digest]
assert all(name.endswith('evaluations/managed_three_stage_runner.py') for name in source_changes), source_changes
assert frozen == runner.fingerprint(catalog, case, contract=contract)
save('hash-verification.json', dict(before_sources=len(before), after_sources=len(manifest), historical_files=len(history),
    historical_changes=changed, permitted_runner_changes=source_changes, protected_changes=[], candidate_fingerprint_unchanged=True,
    model_POSTs=0, SQL_DB=0))
print(json.dumps(dict(result='PASS', sources=len(manifest), historical_files=len(history), runs=len(runs),
    prepared_requests=2, semantic_rejects=sum(c['expected_semantic_verdict']=='SEMANTIC_REJECT' for c in semantics), model_POSTs=0), ensure_ascii=False))
