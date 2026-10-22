"""單次 Qwen 第一階段無輸出token／時間截止診斷；預設只核對。"""
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


class UncappedSingleCallBudget(Budget):
    """Only the single-call and model input-context guards remain."""

    def __init__(self):
        super().__init__(calls_limit=1, output_limit=-1, total_input_limit=None,
                         total_output_limit=None, wall_seconds=None, timeout_seconds=None)

    def begin(self, messages):
        from cpea.infrastructure.llm.context_budget import TiktokenCounter
        tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in messages])
        if self.calls >= 1:
            raise ValueError('single-call diagnostic exhausted before provider construction')
        if tokens + self.safety >= self.context_window:
            raise ValueError('input cannot fit model context')
        self.calls += 1
        self.input_tokens += tokens
        return tokens

    def record_usage(self, usage, estimated_input):
        if not usage:
            self.usage_missing_calls += 1
            return
        self.input_tokens_actual += usage['input_tokens']
        self.output_tokens_actual += usage['output_tokens']
        self.input_tokens += max(0, usage['input_tokens'] - estimated_input)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true')
    group.add_argument('--replay', type=Path)
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
    budget = UncappedSingleCallBudget()
    settings = replace(base, llm_model=model['name'], temperature=1, top_p=1, seed=42,
                       max_output_tokens=-1, context_window=32768, context_safety_tokens=1024,
                       request_timeout_seconds=None, sqlserver=SQLServerSettings(),
                       integration_path=None, deployment_file=None, token_count_endpoint=None)
    print(json.dumps(dict(execute=args.execute, model=model['name'], digest=model['digest'],
                          same_frozen=True, same_messages=True, reasoning=settings.llm_reasoning,
                          calls_limit=1, output_limit=None, num_predict=-1, network_timeout_seconds=None, outer_timeout_seconds=None), ensure_ascii=False), flush=True)
    if args.replay:
        from unittest.mock import patch
        from evaluations import three_stage_view_selection_runner as runner
        stored = json.loads((args.replay / 'run.json').read_text(encoding='utf-8'))
        if stored['harness_sha256'] != sha256(Path(__file__).read_bytes()).hexdigest():
            raise ValueError('uncapped harness changed')
        # Replay exactly the quota policy used for this user-authorized experiment.
        with patch.object(runner, 'Budget', UncappedSingleCallBudget):
            print(json.dumps(runner.replay(args.replay, catalog, case), ensure_ascii=False))
        return 0
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
                context_window=32768, output_limit=None, num_predict=-1, schema_enforcement='Ollama format JSON schema',
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
