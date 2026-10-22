"""重用第一步，序列執行第二步；預設離線核對，不呼叫第三步。"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from urllib.request import urlopen
from uuid import uuid4

from langchain_core.messages import AIMessage
from cpea.config.settings import AssistantSettings, SQLServerSettings
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from cpea.infrastructure.llm.parsing import parse_model
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from evaluations.indexed_requirement_recall import IndexedRecallResult, materialize_recall
from evaluations.three_stage_view_selection_runner import (
    TASK, SchemaCatalog, ViewCoverage, messages_for, fingerprint,
    _verify_artifacts, RecordedProviderError, error_record,
)
from evaluations.three_stage_view_selection import validate_coverage

SOURCE = TASK / '.local/qwen-indexed-20261021T075802Z-66d3ec'


def load_source():
    meta = json.loads((SOURCE / 'run.json').read_text(encoding='utf-8'))
    _verify_artifacts(SOURCE, meta)
    catalog = SchemaCatalog('projects/retail')
    raw = (TASK / '.local/index-recall-request.txt').read_bytes()
    case = dict(case_id='diagnostic-request-' + sha256(raw).hexdigest()[:12],
                request=raw.decode('utf-8'), source_case_id='cross-view-11',
                profile_id=catalog.profile_id, contract_fingerprint=catalog.fingerprint)
    if meta['stopped'] or meta['frozen'] != fingerprint(catalog, case):
        raise ValueError('recall source failed or frozen inputs changed')
    harness = TASK / 'reports/run_qwen_indexed_uncapped_probe.py'
    if sha256(harness.read_bytes()).hexdigest() != meta['harness_sha256']:
        raise ValueError('recall harness changed')
    call = json.loads((SOURCE / 'recall-call.json').read_text(encoding='utf-8'))
    parsed = parse_model(AIMessage(content=call['response']), IndexedRecallResult)
    recall = materialize_recall(parsed, case['request'], catalog)
    if recall.model_dump() != json.loads((SOURCE / 'recall-result.json').read_text(encoding='utf-8')):
        raise ValueError('recall derived result differs')
    original = json.loads((SOURCE / 'recall-request.json').read_text(encoding='utf-8'))
    messages = messages_for('recall', IndexedRecallResult, case['request'], views=[v.policy for v in catalog.views()])
    if original['messages'] != [dict(role=m.type, content=m.content) for m in messages]:
        raise ValueError('recall prompt changed')
    return catalog, case, recall, meta


def run_mappings(catalog, case, recall, invoke, save, check_version=lambda: None):
    """Single-view calls only; first invalid response stops the original sequence."""
    calls, input_actual, output_actual = 0, 0, 0
    coverages = []
    stopped = None
    for index, candidate in enumerate(recall.candidate_views, 1):
        name = f'map-{index:02}'
        raw = None
        try:
            check_version()
            policy = next(v.policy for v in catalog.views() if v.name == candidate.view)
            messages = messages_for('coverage', ViewCoverage, case['request'],
                requirements=[r.model_dump() for r in recall.requirements], view=policy)
            tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in messages])
            if calls >= 7 or tokens + 1024 >= 32768:
                raise ValueError('call count exhausted or input cannot fit model context')
            save(name + '-request.json', dict(view=candidate.view, schema='ViewCoverage',
                messages=[dict(role=m.type, content=m.content) for m in messages], input_tokens_estimated=tokens))
            calls += 1
            save('progress.json', dict(calls=calls, valid_views=len(coverages), current_view=candidate.view))
            started = monotonic()
            try:
                raw = invoke(name, messages, ViewCoverage)
            except Exception as exc:
                save(name + '-provider-error.json', dict(**error_record(exc), elapsed_seconds=monotonic()-started))
                raise
            usage = getattr(raw, 'usage_metadata', None)
            save(name + '-call.json', dict(response=raw.content, usage=usage,
                response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-started))
            if usage:
                input_actual += usage['input_tokens']
                output_actual += usage['output_tokens']
            parsed = parse_model(raw, ViewCoverage)
            save(name + '-parsed.json', parsed.model_dump())
            if parsed.view != candidate.view:
                raise ValueError('mapping returned another view')
            validate_coverage(parsed, recall, case['request'], catalog)
            save(name + '-result.json', parsed.model_dump())
            coverages.append(parsed)
            save('progress.json', dict(calls=calls, valid_views=len(coverages), completed_view=candidate.view))
        except Exception as exc:
            stopped = dict(node=name, view=candidate.view, **error_record(exc))
            save(name + '-error.json', dict(**error_record(exc), raw_saved=raw is not None))
            break
    return dict(calls=calls, valid_views=len(coverages), stopped=stopped,
                input_tokens_actual=input_actual, output_tokens_actual=output_actual)


def replay(folder, catalog, case, recall, source_meta):
    meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    _verify_artifacts(folder, meta)
    if (meta['frozen'] != fingerprint(catalog, case)
            or meta['source_run_sha256'] != sha256((SOURCE / 'run.json').read_bytes()).hexdigest()
            or meta['harness_sha256'] != sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('stage-two replay version/source changed')
    saved = {}

    def invoke(name, messages, schema):
        original = json.loads((folder / (name + '-request.json')).read_text(encoding='utf-8'))
        if original['messages'] != [dict(role=m.type, content=m.content) for m in messages]:
            raise ValueError('stage-two replay messages changed')
        path = folder / (name + '-provider-error.json')
        if path.exists():
            raise RecordedProviderError(json.loads(path.read_text(encoding='utf-8')))
        call = json.loads((folder / (name + '-call.json')).read_text(encoding='utf-8'))
        return AIMessage(content=call['response'], usage_metadata=call.get('usage'),
                         response_metadata=call.get('response_metadata') or {})

    actual = run_mappings(catalog, case, recall, invoke, saved.__setitem__)
    for key, value in actual.items():
        if meta[key] != value:
            raise ValueError('stage-two replay outcome differs: ' + key)
    for name, value in saved.items():
        if name.endswith(('-request.json', '-parsed.json', '-result.json', '-error.json')):
            original = json.loads((folder / name).read_text(encoding='utf-8'))
            if name.endswith('-provider-error.json'):
                value = {k: v for k, v in value.items() if k != 'elapsed_seconds'}
                original = {k: v for k, v in original.items() if k != 'elapsed_seconds'}
            if value != original:
                raise ValueError('stage-two replay artifact differs: ' + name)
    expected = {p.name for p in folder.iterdir() if p.name.startswith('map-')}
    if expected != {name for name in saved if name.startswith('map-')}:
        raise ValueError('stage-two replay node artifact set differs')
    return dict(result='PASS', raw_replays=sum(n.endswith('-call.json') for n in saved), **actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true')
    group.add_argument('--replay', type=Path)
    args = parser.parse_args()
    catalog, case, recall, source_meta = load_source()
    if args.replay:
        print(json.dumps(replay(args.replay, catalog, case, recall, source_meta), ensure_ascii=False))
        return 0
    settings = replace(AssistantSettings.from_env(Path('.env')), llm_model='qwen3.8:27b',
        temperature=1, top_p=1, seed=42, max_output_tokens=-1, context_window=32768,
        context_safety_tokens=1024, request_timeout_seconds=None, sqlserver=SQLServerSettings(),
        integration_path=None, deployment_file=None, token_count_endpoint=None)
    if settings.llm_provider != 'ollama' or settings.llm_reasoning != source_meta['reasoning']:
        raise ValueError('source model provider/reasoning changed')
    with urlopen(settings.llm_base_url.rstrip('/') + '/api/tags', timeout=15) as response:
        model = next(m for m in json.load(response)['models'] if m['name'] == settings.llm_model)
    if model['digest'] != source_meta['model_details']['digest']:
        raise ValueError('model digest changed')
    print(json.dumps(dict(execute=args.execute, stage=2, model=model['name'], source=str(SOURCE),
        new_calls_max=7, recall_calls=0, selection_calls=0, output_limit=None, timeout=None,
        ordered_views=[v.view for v in recall.candidate_views]), ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    folder = TASK / '.local' / ('qwen-coverage-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)

    def save(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)

    frozen = fingerprint(catalog, case)
    meta = dict(stage=2, model=model['name'], model_details=model, request=case['request'],
        frozen=frozen, source_run=str(SOURCE), source_run_sha256=sha256((SOURCE / 'run.json').read_bytes()).hexdigest(),
        harness_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), calls=0, valid_views=0, stopped=None,
        ordered_views=[v.view for v in recall.candidate_views], temperature=1, top_p=1, seed=42,
        reasoning=settings.llm_reasoning, num_predict=-1, context_window=32768,
        HTTP_timeout_seconds=None, outer_timeout_seconds=None, input_token_quota=None, output_token_quota=None,
        started_at=datetime.now(timezone.utc).isoformat())
    save('run.json', meta)

    def check_version():
        if (fingerprint(SchemaCatalog('projects/retail'), case) != frozen
                or sha256((SOURCE / 'run.json').read_bytes()).hexdigest() != meta['source_run_sha256']
                or sha256(Path(__file__).read_bytes()).hexdigest() != meta['harness_sha256']):
            raise ValueError('stage-two source/version changed')

    def invoke(name, messages, schema):
        return bind_response_schema(get_llm_config(settings=settings), schema).invoke(messages)

    started = monotonic()
    try:
        meta.update(run_mappings(catalog, case, recall, invoke, save, check_version))
    finally:
        meta.update(elapsed_seconds=monotonic()-started, finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
        print(json.dumps(dict(folder=str(folder), calls=meta['calls'], valid_views=meta['valid_views'], stopped=meta['stopped']), ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
