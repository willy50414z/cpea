"""Persist offline fake evidence; never constructs a model/database provider."""
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import managed_three_stage_runner as runner
from test_managed_three_stage_runner import fake

out = Path('evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-slots')
catalog = SchemaCatalog('projects/retail')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
results = []
failures = [None, 'duplicate_slot', 'conflicting_slot', 'nested_duplicate', 'missing', 'extra',
            'old_list', 'source_override', 'contract', 'provider', 'parse', 'input']
for failure in failures:
    request, original, calls = fake(catalog, fail='map-02' if failure == 'contract' else None)
    def invoke(name, messages, schema):
        if name == 'recall' and failure == 'provider':
            raise OSError('offline fake provider failure')
        if name == 'recall' and failure == 'parse':
            return AIMessage(content='not json')
        raw = original(name, messages, schema)
        if name == 'map-01' and failure in failures[1:8]:
            data = json.loads(raw.content)
            if failure in ('duplicate_slot', 'conflicting_slot'):
                key, value = next(iter(data['entries'].items()))
                other = value if failure == 'duplicate_slot' else dict(status='supported', mappings=[], contract_path=None, missing_requirements=[])
                text = '{"entries":{' + json.dumps(key) + ':' + json.dumps(value) + ',' + json.dumps(key) + ':' + json.dumps(other) + '}}'
            elif failure == 'nested_duplicate':
                text = raw.content.replace('"mappings": []', '"mappings":[{"column":"fake","column":"stock_qty","role":"metric"}]', 1)
            else:
                if failure == 'missing': data['entries'].pop('stock')
                if failure == 'extra': data['entries']['unexpected'] = data['entries']['stock']
                if failure == 'old_list': data['entries'] = list(data['entries'].values())
                if failure == 'source_override': data['population'] = '不含退貨'
                text = json.dumps(data,ensure_ascii=False)
            return AIMessage(content=text)
        return raw
    folder = runner.TASK / '.local' / ('slots-fake-' + (failure or 'complete') + '-' + stamp)
    case = runner.diagnostic_case(catalog, request)
    meta = runner.record_run(folder, catalog, case, invoke, context_window=1 if failure == 'input' else 32768)
    assert bool(meta['stopped']) == bool(failure), (failure, meta['stopped'])
    replay = runner.replay(folder, catalog, case)
    assert replay['result'] == 'PASS'
    expected = 0 if failure == 'input' else 1 if failure in ('provider','parse') else 3 if failure == 'contract' else 2 if failure else 9
    usage = runner.read_json(folder/'usage.json')
    assert usage['calls'] == expected
    if not failure:
        response = runner.read_json(folder/'response.json')
        assert response['status'] == 'ready' and len(response['prepared_requests']) == 2
    results.append(dict(case=failure or 'complete',folder=str(folder),calls=usage['calls'],replay=replay))
(out/'offline-final.log').write_text(json.dumps(dict(result='PASS',model_calls=0,sql_db_calls=0,runs=results),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(result='PASS',runs=len(results),raw_replays=sum(x['replay']['raw_replays'] for x in results),model_calls=0),ensure_ascii=False))
