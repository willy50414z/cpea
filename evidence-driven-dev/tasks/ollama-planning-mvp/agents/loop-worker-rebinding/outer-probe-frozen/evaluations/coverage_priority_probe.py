"""One paired DeepSeek probe of explicit requirement-coverage priority."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from langchain_core.messages import SystemMessage
from cpea.application.models.decomposition import DecisionChainDecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import (
    DECOMPOSITION_PROMPT, COVERAGE_FIRST_PROMPT, COVERAGE_FIRST_PROMPT_VERSION,
)
from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.decision_chain_probe import chain_messages, finish_chained, fingerprint
from evaluations.decision_summary_comparison import TASK
from evaluations.planning_mvp import semantic_check

MODEL = 'DeepSeek-V4.1-Flash'
VARIANTS = ('baseline', 'coverage_first')


def priority_messages(request, catalog, variant):
    messages = chain_messages(request, catalog)
    if variant == 'coverage_first':
        system = messages[0].content
        assert system.startswith(DECOMPOSITION_PROMPT)
        messages[0] = SystemMessage(content=COVERAGE_FIRST_PROMPT + system[len(DECOMPOSITION_PROMPT):])
    elif variant != 'baseline':
        raise ValueError('unknown prompt variant')
    return messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    catalog = SchemaCatalog(Path('projects/retail'))
    case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog) if c['case_id'] == 'cross-view-11')
    review = json.loads((TASK / 'agents/oracle-audit/review-manifest.json').read_text(encoding='utf-8'))
    approved = next(c for c in review['cases'] if c['case_id'] == case['case_id'])
    assert review['catalog_fingerprint'] == catalog.fingerprint and approved['case_sha256'] == case_sha256(case)
    all_messages = {v: priority_messages(case['request'], catalog, v) for v in VARIANTS}
    assert all_messages['baseline'][1].content == all_messages['coverage_first'][1].content
    counter = TiktokenCounter('cl100k_base')
    tokens = {v: counter.count_messages([(m.type, m.content) for m in ms]) for v, ms in all_messages.items()}
    print(json.dumps({'execute': args.execute, 'model': MODEL, 'calls': 2, 'input_tokens_estimated': tokens,
                      'output_limit': 4096, 'safety': 1024}, ensure_ascii=False), flush=True)
    if any(n + 4096 + 1024 > 16384 for n in tokens.values()):
        raise ValueError('context budget exceeded before provider construction')
    if not args.execute:
        return 0
    frozen = fingerprint(catalog, case)
    folder = TASK / '.local' / ('coverage-priority-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)
    def dump(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)
    meta = {'model': MODEL, 'variants': list(VARIANTS), 'case_id': case['case_id'],
            'prompt_version': COVERAGE_FIRST_PROMPT_VERSION, 'calls': 0, 'completed': 0, 'stopped': None,
            'temperature': 1, 'top_p': 1, 'seed': 42, 'max_output_tokens': 4096, 'context_window': 16384,
            'safety': 1024, 'timeout_seconds': 300, 'sdk_retries': 0, 'wall_budget_seconds': 900,
            'input_tokens_estimated': tokens, 'frozen': frozen,
            'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'started_at': datetime.now(timezone.utc).isoformat()}
    start = monotonic()
    dump('run.json', meta)
    try:
        for variant in VARIANTS:
            if 900 - (monotonic() - start) < 300:
                meta['stopped'] = 'wall_budget'
                break
            assert frozen == fingerprint(catalog, case)
            settings = replace(azure_planning_settings(Path('.env'), MODEL), max_output_tokens=4096,
                               context_safety_tokens=1024, request_timeout_seconds=300)
            llm = bind_response_schema(get_llm_config(settings=settings), DecisionChainDecompositionDraft).bind(response_format={'type': 'json_object'})
            messages = all_messages[variant]
            event = {'model': MODEL, 'variant': variant, 'case_id': case['case_id'],
                     'messages': [{'role': m.type, 'content': m.content} for m in messages]}
            dump(variant + '-request.json', event)
            meta['calls'] += 1
            dump('run.json', meta)
            call_start = monotonic()
            try:
                raw = llm.invoke(messages)
            except Exception as exc:
                event.update(error_type=type(exc).__name__, error=str(exc))
                dump(variant + '-provider-error.json', event)
                error_path = folder / 'provider-error.txt'
                error_path.write_text(type(exc).__name__ + ': ' + str(exc), encoding='utf-8')
                error_path.chmod(0o600)
                meta['stopped'] = 'provider_error_no_retry'
                break
            event.update(response=raw.content, usage=getattr(raw, 'usage_metadata', None),
                         response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-call_start)
            dump(variant + '-call.json', event)
            row = {'variant': variant, 'model': MODEL, 'response': None, 'score': None, 'diagnostic': None, 'parse_error': None}
            try:
                draft = parse_model(raw, DecisionChainDecompositionDraft)
                response = finish_chained(draft, catalog)
                row.update(response=response.model_dump(), score=grade_decomposition(case, response, catalog),
                           diagnostic=semantic_check(case, response, catalog))
            except (ValueError, TypeError, KeyError) as exc:
                row['parse_error'] = str(exc)
            dump(variant + '-result.json', row)
            meta['completed'] += 1
            dump('run.json', meta)
            print(json.dumps({'variant': variant, 'status': row['response']['status'] if row['response'] else 'parse_error',
                              'automated_pass': row['score']['automated_pass'] if row['score'] else False}, ensure_ascii=False), flush=True)
    finally:
        meta.update(elapsed_seconds=monotonic()-start, finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        dump('run.json', meta)
        print(json.dumps({'folder': str(folder), 'calls': meta['calls'], 'completed': meta['completed'], 'stopped': meta['stopped']}, ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
