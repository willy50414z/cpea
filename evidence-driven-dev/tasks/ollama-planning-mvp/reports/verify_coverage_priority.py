"""離線核對優先序成對實驗；不呼叫模型。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from cpea.application.models import decomposition as models
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT, DECOMPOSITION_PROMPT_VERSION, COVERAGE_FIRST_PRIORITY
from evaluations.coverage_priority_probe import priority_messages, MODEL, VARIANTS
from evaluations.decision_chain_probe import finish_chained, fingerprint
from evaluations.decision_summary_comparison import TASK
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.planning_mvp import semantic_check


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


folder = TASK / '.local/coverage-priority-20261020T160325Z-d48244'
meta = read(folder / 'run.json')
assert meta['calls'] == meta['completed'] == 2 and meta['stopped'] is None
for name, digest in meta['artifact_hashes'].items():
    assert sha256((folder / name).read_bytes()).hexdigest() == digest
assert sha256((ROOT / 'evaluations/coverage_priority_probe.py').read_bytes()).hexdigest() == meta['runner_sha256']
catalog = SchemaCatalog(Path('projects/retail'))
case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog) if c['case_id'] == meta['case_id'])
assert meta['frozen'] == fingerprint(catalog, case)
old_source = subprocess.run(['git', 'show', 'HEAD:src/cpea/workflows/task_decomposition/prompt.py'], capture_output=True, text=True, encoding='utf-8', check=True).stdout
old_constants = {}
exec(old_source, old_constants)
assert old_constants['DECOMPOSITION_PROMPT'] == DECOMPOSITION_PROMPT
assert old_constants['DECOMPOSITION_PROMPT_VERSION'] == DECOMPOSITION_PROMPT_VERSION
for name, digest in read(TASK / '.local/decision-chain-baseline-schemas.json').items():
    assert sha256(json.dumps(getattr(models, name).model_json_schema(), sort_keys=True).encode()).hexdigest() == digest
events, rows = {}, []
for variant in VARIANTS:
    event = read(folder / (variant + '-call.json'))
    row = read(folder / (variant + '-result.json'))
    assert event['model'] == row['model'] == MODEL
    assert event['messages'] == read(folder / (variant + '-request.json'))['messages']
    assert event['messages'] == [{'role': m.type, 'content': m.content} for m in priority_messages(case['request'], catalog, variant)]
    assert row['parse_error'] is None
    draft = parse_model(SimpleNamespace(content=event['response']), models.DecisionChainDecompositionDraft)
    response = finish_chained(draft, catalog)
    assert response.model_dump() == row['response']
    assert grade_decomposition(case, response, catalog) == row['score']
    assert semantic_check(case, response, catalog) == row['diagnostic']
    for prepared in response.prepared_requests:
        payload = json.loads(prepared.payload['request'].split('\n', 1)[1])
        assert 'decision_chain' not in payload and 'decision_summary' not in payload
    events[variant] = event
    rows.append({**row, 'usage': event.get('usage'), 'elapsed_seconds': event['elapsed_seconds']})
assert events['baseline']['messages'][1] == events['coverage_first']['messages'][1]
assert events['coverage_first']['messages'][0]['content'].replace(COVERAGE_FIRST_PRIORITY, '', 1) == events['baseline']['messages'][0]['content']
historical = read(TASK / '.local/decision-chain-20261020T153804Z-eea260/DeepSeek-V4.1-Flash-request.json')
assert historical['messages'] == events['baseline']['messages']
report = {'artifact_result': 'PASS', 'case_id': case['case_id'], 'request': case['request'],
          'prompt_version': meta['prompt_version'], 'calls': 2, 'model': MODEL,
          'only_prompt_priority_changed': True, 'v3_default_unchanged': True,
          'old_four_schemas_unchanged': True, 'raw_response_score_payload_replayed': 2,
          'runtime_ready': {r['variant']: r['response']['status'] for r in rows},
          'automated_pass': {r['variant']: r['score']['automated_pass'] for r in rows},
          'input_tokens_estimated': meta['input_tokens_estimated'], 'elapsed_seconds': meta['elapsed_seconds'],
          'results': rows, 'raw_folder': str(folder), 'verification_model_calls': 0,
          'sql_db_calls': 0, 'ollama_calls': 0,
          'limitation': '單題、每版一次；順序為原版再候選，非統計或因果驗證，不能取代完整Gate。'}
(TASK / 'reports/coverage-priority-comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('artifact_result', 'calls', 'runtime_ready', 'automated_pass', 'elapsed_seconds')}, ensure_ascii=False))
