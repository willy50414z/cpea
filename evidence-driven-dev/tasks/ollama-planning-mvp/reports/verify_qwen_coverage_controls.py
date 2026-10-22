"""第二步接續器的離線控制；合成輸出不作模型品質證據。"""
import json
from pathlib import Path
import runpy

from langchain_core.messages import AIMessage

path = Path('evidence-driven-dev/tasks/ollama-planning-mvp/reports/run_qwen_coverage_uncapped_probe.py')
module = runpy.run_path(str(path))
catalog, case, recall, _ = module['load_source']()
run = module['run_mappings']


def control(fail_at=None):
    calls, saved = [], {}

    def invoke(name, messages, schema):
        assert schema is module['ViewCoverage']
        payload = json.loads(messages[1].content)
        policy = payload['view']
        assert payload['requirements'] == [r.model_dump() for r in recall.requirements]
        assert payload['request'] == case['request']
        calls.append(name)
        data = dict(view=policy['view'], grain=policy['grain']['description'], keys=policy['grain']['keys'],
            population='離線合成控制，非自然模型能力',
            contract_evidence=[dict(path='/summary', quote=policy['summary'])],
            entries=[dict(requirement_id=r.requirement_id, status='unsupported', mappings=[],
                          contract_evidence=[], missing_requirements=['離線控制未宣稱能力']) for r in recall.requirements])
        if name == fail_at:
            data['contract_evidence'][0]['quote'] = '這不是契約中存在的引文'
        return AIMessage(content=json.dumps(data, ensure_ascii=False))

    return run(catalog, case, recall, invoke, saved.__setitem__), calls, saved


success, calls, saved = control()
assert success['calls'] == success['valid_views'] == 7 and success['stopped'] is None
assert calls == [f'map-{i:02}' for i in range(1, 8)]
assert not any('recall-' in name or 'selection' in name for name in saved)
failure, calls, saved = control('map-02')
assert calls == ['map-01', 'map-02'] and failure['valid_views'] == 1
assert failure['stopped']['node'] == 'map-02'
assert 'invalid contract evidence quote' in failure['stopped']['error']
assert 'map-02-call.json' in saved and 'map-02-parsed.json' in saved and 'map-02-error.json' in saved
assert not any(name.startswith('map-03') for name in saved)
print('PASS: seven coverage calls only; failed second view stops sequence; raw/parsed/error retained; provider invocations=0; synthetic controls are not semantic acceptance')
