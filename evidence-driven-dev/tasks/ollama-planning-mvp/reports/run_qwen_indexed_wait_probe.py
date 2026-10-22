"""單次 Qwen 第一階段無時間截止診斷；預設只核對。"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from cpea.config.settings import AssistantSettings, SQLServerSettings
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from evaluations.three_stage_view_selection_runner import (
    TASK, VERSION, Budget, IndexedRecallResult, SchemaCatalog, fingerprint,
    messages_for, run_pipeline,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw = (TASK / '.local/index-recall-request.txt').read_bytes()
    case = dict(case_id='diagnostic-request-' + sha256(raw).hexdigest()[:12],
                request=raw.decode('utf-8'), source_case_id='cross-view-11',
                profile_id='retail')
    catalog = SchemaCatalog('projects/retail')
    case.update(profile_id=catalog.profile_id, contract_fingerprint=catalog.fingerprint)
    frozen = fingerprint(catalog, case)
    previous = TASK / '.local/three-stage-20261021T034827Z-e0692c'
    prior = json.loads((previous / 'run.json').read_text(encoding='utf-8'))
    assert frozen == prior['frozen'], 'Frozen comparison input changed'
    messages = messages_for('recall', IndexedRecallResult, case['request'], views=[v.policy for v in catalog.views()])
    prior_request = json.loads((previous / 'recall-request.json').read_text(encoding='utf-8'))
    assert prior_request['messages'] == [dict(role=m.type, content=m.content) for m in messages]
    base = AssistantSettings.from_env(Path('.env'))
    assert base.llm_provider == 'ollama'
    with urlopen(base.llm_base_url.rstrip('/') + '/api/tags', timeout=15) as response:
        model = next(m for m in json.load(response)['models'] if m['name'] == 'qwen3.8:27b')
    budget = Budget(calls_limit=1, total_input_limit=30000, total_output_limit=4096, wall_seconds=900)
    settings = replace(base, llm_model=model['name'], temperature=1, top_p=1, seed=42,
                       max_output_tokens=4096, context_window=32768, context_safety_tokens=1024,
                       request_timeout_seconds=None, sqlserver=SQLServerSettings(),
                       integration_path=None, deployment_file=None, token_count_endpoint=None)
    print(json.dumps(dict(execute=args.execute, model=model['name'], digest=model['digest'],
                          same_frozen=True, same_messages=True, reasoning=settings.llm_reasoning,
                          calls_limit=1, output_limit=4096, network_timeout_seconds=None, outer_timeout_seconds=None), ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    folder = TASK / '.local' / ('qwen-indexed-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)

    def save(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)

    meta = dict(version=VERSION, provider='ollama', model=model['name'], model_details=model,
                case_id=case['case_id'], request=case['request'], frozen=frozen,
                recall_only=True, custom_diagnostic=True, sdk_retries=0,
                temperature=1, top_p=1, seed=42, reasoning=settings.llm_reasoning,
                context_window=32768, output_limit=4096, schema_enforcement='Ollama format JSON schema',
                budget={k: v for k, v in vars(budget).items() if k != 'started'},
                harness_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                same_messages=True, comparison_run=str(previous),
                network_timeout_seconds=None, outer_timeout_seconds=None, wait_until_complete=True,
                started_at=datetime.now(timezone.utc).isoformat(), stopped=None, calls=0)
    save('run.json', meta)

    def check_version():
        if fingerprint(SchemaCatalog('projects/retail'), case) != frozen:
            raise ValueError('Frozen source/catalog/schema changed')

    def invoke(messages, schema):
        return bind_response_schema(get_llm_config(settings=settings), schema).invoke(messages)

    try:
        response = run_pipeline(case['request'], catalog, invoke, save, budget, check_version, recall_only=True)
        save('diagnostic.json', dict(status='structurally_valid', semantic_status='REQUIRES_REVIEW',
                                    requirements=len(response.requirements), source_mapping='NOT_EXECUTED'))
    except Exception as exc:
        meta['stopped'] = dict(error_type=type(exc).__name__, error=str(exc))
    finally:
        meta.update(budget.state(), finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
        print(json.dumps(dict(folder=str(folder), calls=budget.calls, stopped=meta['stopped']), ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
