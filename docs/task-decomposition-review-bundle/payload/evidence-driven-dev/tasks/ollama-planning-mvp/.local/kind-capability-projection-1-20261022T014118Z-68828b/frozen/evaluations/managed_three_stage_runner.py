"""Controller-managed local diagnostic; dry-run and replay never use the network."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic
from urllib.request import urlopen
from uuid import uuid4

from langchain_core.messages import AIMessage

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.coverage_reference_runner import reference_messages, REFERENCE_SOURCES
from evaluations.indexed_requirement_recall import IndexedRecallResult, materialize_recall
from evaluations.referenced_view_coverage import ReferencedViewCoverage, materialize_coverage
from evaluations.slotted_view_coverage import (
    SLOT_SOURCES, coverage_schema, materialize_slots, parse_slots, slot_messages,
)
from evaluations.three_stage_view_selection import MISSING_POLICIES, SelectionResult, finish_selection
from evaluations.three_stage_view_selection_runner import (
    TASK, RecordedProviderError, _verify_artifacts, error_record,
    fingerprint as base_fingerprint, messages_for,
)

ROOT = Path(__file__).resolve().parents[1]
LOOPCTL = Path.home() / '.codex/skills/edd-loop/scripts/loopctl.py'
MODEL = 'qwen3.8:27b'
MODEL_DIGEST = 'aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813'
VERSION = 'managed-indexed-slots-three-stage-2'
MODEL_OPTIONS = dict(num_predict=-1, num_ctx=32768, temperature=1, top_p=1, seed=42)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def diagnostic_case(catalog, request=None):
    if request is None:
        request = (TASK / '.local/index-recall-request.txt').read_bytes().decode('utf-8')
    return dict(case_id='diagnostic-request-' + sha256(request.encode('utf-8')).hexdigest()[:12],
        request=request, source_case_id='cross-view-11', profile_id=catalog.profile_id,
        contract_fingerprint=catalog.fingerprint)


def fingerprint(catalog, case, *, contract=None):
    result = base_fingerprint(catalog, case)
    paths = [Path(__file__), Path('tests/unit/test_managed_three_stage_runner.py'),
             Path('tests/unit/test_referenced_view_coverage.py'), *REFERENCE_SOURCES, *SLOT_SOURCES, LOOPCTL]
    frozen = dict(result, managed_version=VERSION,
        managed_sources={str(p): sha256(p.read_bytes()).hexdigest() for p in paths},
        managed_schemas={s.__name__: sha256(json.dumps(s.model_json_schema(), sort_keys=True).encode()).hexdigest()
                         for s in (IndexedRecallResult, ReferencedViewCoverage, SelectionResult)},
        model=dict(name=MODEL, digest=MODEL_DIGEST, think=True, options=MODEL_OPTIONS))
    if contract is not None:
        frozen['managed_version'] = contract.VERSION
        frozen['managed_sources'].update({str(p): sha256(p.read_bytes()).hexdigest() for p in [*contract.SOURCES, *sorted(Path('src/cpea').rglob('*.py')),
                *[Path('evaluations') / name for name in ('call_budget.py','decomposition_reports.py','metadata.py')],
                Path('pyproject.toml'), Path('uv.lock')]})
        frozen['managed_schemas'].update({s.__name__: sha256(json.dumps(s.model_json_schema(), sort_keys=True).encode()).hexdigest()
                                         for s in (contract.RecallWire, contract.SelectionWire)})
    return frozen


def run_pipeline(request, catalog, invoke, save, check_version=lambda: None, *, context_window=32768, contract=None):
    """Keep every first response; validate using the existing strict adapters."""
    usage = dict(calls=0, input_tokens_actual=0, output_tokens_actual=0, usage_missing_calls=0)
    views = [v.policy for v in catalog.views()]

    def node(name, messages, schema, normalize=lambda parsed: parsed, parser=parse_model):
        raw = None
        try:
            check_version()
            tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in messages])
            save(name + '-request.json', dict(messages=[dict(role=m.type, content=m.content) for m in messages],
                schema=schema.__name__, response_schema=schema.model_json_schema(), input_tokens_estimated=tokens))
            save('usage.json', dict(usage))
            # Only physical input capacity is checked; no output reservation/quota.
            if tokens >= context_window:
                raise ValueError('input cannot fit model context')
            usage['calls'] += 1
            save('usage.json', dict(usage))
            started = monotonic()
            try:
                raw = invoke(name, messages, schema)
            except Exception as exc:
                save(name + '-provider-error.json', dict(**error_record(exc), elapsed_seconds=monotonic()-started))
                raise
            actual = getattr(raw, 'usage_metadata', None)
            save(name + '-call.json', dict(response=raw.content, usage=actual,
                response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-started))
            if actual:
                usage['input_tokens_actual'] += actual['input_tokens']
                usage['output_tokens_actual'] += actual['output_tokens']
            else:
                usage['usage_missing_calls'] += 1
            save('usage.json', dict(usage))
            parsed = parser(raw, schema)
            save(name + '-parsed.json', parsed.model_dump(by_alias=True))
            if contract is not None:
                refs = ({r.requirement_id: dict(grain_binding=r.grain_binding, grain_requirement_ids=r.grain_requirement_ids,
                                               scope_ids=r.scope_ids) for r in parsed.requirements}
                        if name == 'recall' else parsed.model_dump(by_alias=True))
                save(name + '-refs.json', refs)
            normalized = normalize(parsed)
            save(name + '-normalized.json', normalized.model_dump())
            save(name + '-result.json', normalized.model_dump())
            return normalized
        except Exception as exc:
            save(name + '-error.json', dict(**error_record(exc), raw_saved=raw is not None))
            raise

    if contract is None:
        recall = node('recall', messages_for('recall', IndexedRecallResult, request, views=views),
                      IndexedRecallResult, lambda parsed: materialize_recall(parsed, request, catalog))
        coverages = []
        for index, candidate in enumerate(recall.candidate_views, 1):
            policy = next(v for v in views if v['view'] == candidate.view)

            schema = coverage_schema(recall)
            coverages.append(node(f'map-{index:02}', slot_messages(schema, request,
                requirements=[r.model_dump() for r in recall.requirements], view=policy), schema,
                lambda parsed: materialize_slots(parsed, recall, request, catalog, policy), parse_slots))
        selection = node('selection', messages_for('selection', SelectionResult, request,
            requirements=[r.model_dump() for r in recall.requirements], coverages=[c.model_dump() for c in coverages],
            views=views, missing_policy_options=MISSING_POLICIES), SelectionResult,
            lambda parsed: _validated_selection(parsed, recall, coverages, request, catalog))
    else:
        recall = node('recall', contract.messages('recall', contract.RecallWire, request),
            contract.RecallWire, lambda parsed: contract.materialize_recall(parsed, request, catalog), contract.parse_wire)
        coverages = []
        for index, candidate in enumerate(recall.candidate_views, 1):
            policy = next(v for v in views if v['view'] == candidate.view)
            schema = contract.coverage_schema(recall)
            coverages.append(node(f'map-{index:02}', contract.messages('coverage', schema, request,
                requirements=[r.model_dump() for r in recall.requirements], view=policy), schema,
                lambda parsed: contract.materialize_coverage(parsed, recall, request, catalog, policy), contract.parse_wire))
        selection = node('selection', contract.messages('selection', contract.SelectionWire, request,
            requirements=[r.model_dump() for r in recall.requirements], coverages=[c.model_dump() for c in coverages],
            views=views, missing_policy_options=MISSING_POLICIES), contract.SelectionWire,
            lambda parsed: contract.materialize_selection(parsed, recall, coverages, request, catalog), contract.parse_wire)
    response = finish_selection(selection, recall, coverages, request, catalog)
    save('response.json', response.model_dump())
    return response


def _validated_selection(parsed, recall, coverages, request, catalog):
    finish_selection(parsed, recall, coverages, request, catalog)
    return parsed


class ManagedInvoke:
    """One subprocess, one controller-managed POST, no automatic retries."""
    def __init__(self, folder, ticket, case_id, save):
        self.folder, self.ticket, self.case_id, self.save = folder, ticket, case_id, save

    def __call__(self, name, messages, schema):
        roles = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
        body = dict(model=MODEL, messages=[dict(role=roles[m.type], content=m.content) for m in messages],
            stream=False, think=True, options=MODEL_OPTIONS, format=schema.model_json_schema())
        path = self.folder / (name + '-body.json')
        write_json(path, body)
        command = [sys.executable, str(LOOPCTL), '--root', str(ROOT), '--id', 'ollama-planning-mvp',
            'request', '--ticket', self.ticket, '--provider', 'local', '--case', self.case_id + ':' + name,
            '--url-env', 'EDD_LOCAL_ENDPOINT', '--file', str(path.resolve())]
        completed = subprocess.run(command, cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
        try:
            receipt = json.loads(completed.stdout)
        except ValueError:
            raise RuntimeError('managed request returned no valid receipt; inspect controller state before resuming') from None
        self.save(name + '-managed.json', receipt)
        response = None
        if receipt.get('response_path'):
            text = Path(receipt['response_path']).read_text(encoding='utf-8')
            try:
                response = json.loads(text)
            except ValueError:
                response = dict(raw_text=text)
            self.save(name + '-provider-response.json', response)
        if completed.returncode or receipt.get('result') != 'ok':
            raise RuntimeError('managed request failed: ' + str(receipt.get('result')))
        if not isinstance(response, dict) or response.get('model') != MODEL or response.get('done') is not True:
            raise ValueError('managed response model/completion differs')
        if response.get('done_reason') not in (None, 'stop'):
            raise ValueError('managed response did not finish normally')
        content = response.get('message', {}).get('content')
        if not isinstance(content, str):
            raise ValueError('managed response lacks assistant content')
        usage = None
        if all(isinstance(response.get(key), int) for key in ('prompt_eval_count', 'eval_count')):
            usage = dict(input_tokens=response['prompt_eval_count'], output_tokens=response['eval_count'],
                total_tokens=response['prompt_eval_count'] + response['eval_count'])
        return AIMessage(content=content, usage_metadata=usage,
            response_metadata={k: v for k, v in response.items() if k != 'message'})


def record_run(folder, catalog, case, invoke, *, context_window=32768, identity=None, contract=None):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(folder.iterdir()):
        raise ValueError('run folder must be empty; never overwrite an earlier run')
    save = lambda name, value: write_json(folder / name, value)
    frozen = fingerprint(catalog, case, **({'contract': contract} if contract is not None else {}))
    meta = dict(version=contract.VERSION if contract is not None else VERSION, frozen=frozen, case=case, context_window=context_window,
        model=MODEL, model_identity=identity, think=True, options=MODEL_OPTIONS,
        HTTP_timeout_seconds=None, outer_timeout_seconds=None,
        stopped=dict(error_type='InterruptedRun', error='run did not reach completion'),
        started_at=datetime.now(timezone.utc).isoformat())
    save('run.json', meta)

    def check_version():
        if fingerprint(SchemaCatalog('projects/retail'), case, **({'contract': contract} if contract is not None else {})) != frozen:
            raise ValueError('source/version changed during run')

    try:
        run_pipeline(case['request'], catalog, invoke, save, check_version, context_window=context_window, contract=contract)
        meta['stopped'] = None
    except Exception as exc:
        meta['stopped'] = error_record(exc)
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
    return meta


def replay(folder, catalog, case, *, contract=None):
    meta = read_json(folder / 'run.json')
    _verify_artifacts(folder, meta)
    if meta['frozen'] != fingerprint(catalog, case, **({'contract': contract} if contract is not None else {})) or meta['case'] != case:
        raise ValueError('replay version/input mismatch')
    saved = {}

    def invoke(name, messages, schema):
        original = read_json(folder / (name + '-request.json'))
        if (original['messages'] != [dict(role=m.type, content=m.content) for m in messages]
                or original['response_schema'] != schema.model_json_schema()):
            raise ValueError('replay input messages differ')
        error_path = folder / (name + '-provider-error.json')
        if error_path.exists():
            raise RecordedProviderError(read_json(error_path))
        call = read_json(folder / (name + '-call.json'))
        return AIMessage(content=call['response'], usage_metadata=call['usage'], response_metadata=call['response_metadata'] or {})

    stopped = None
    try:
        run_pipeline(case['request'], catalog, invoke, saved.__setitem__, context_window=meta['context_window'], contract=contract)
    except Exception as exc:
        stopped = error_record(exc)
    if stopped != meta['stopped']:
        raise ValueError('replay stopped result differs')
    for name, value in saved.items():
        expected = read_json(folder / name)
        if name.endswith(('-call.json', '-provider-error.json')):
            expected.pop('elapsed_seconds', None)
            value.pop('elapsed_seconds', None)
        if value != expected:
            raise ValueError('replay artifact differs: ' + name)
    generated = {n for n in meta['artifact_hashes'] if not n.endswith(('-body.json', '-managed.json', '-provider-response.json'))}
    if generated != set(saved):
        raise ValueError('replay node artifact set differs')
    return dict(result='PASS', raw_replays=sum(n.endswith('-call.json') for n in saved), stopped=stopped)


def verify_model_identity(base_url):
    # Identity metadata only; all inference POSTs still go through loopctl.
    with urlopen(base_url.rstrip('/') + '/api/tags', timeout=15) as response:
        model = next((m for m in json.load(response)['models'] if m['name'] == MODEL), None)
    if model is None or model.get('digest') != MODEL_DIGEST:
        raise ValueError('local model digest changed or model missing')
    return dict(name=model['name'], digest=model['digest'], checked_at=datetime.now(timezone.utc).isoformat())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true')
    group.add_argument('--replay', type=Path)
    parser.add_argument('--ticket')
    contracts = parser.add_mutually_exclusive_group()
    contracts.add_argument('--evidence-bound', action='store_true')
    contracts.add_argument('--own-responsibility', action='store_true')
    contracts.add_argument('--kind-mapping', action='store_true')
    args = parser.parse_args(argv)
    contract = None
    if args.evidence_bound:
        from evaluations import evidence_bound_managed_contract as contract
    elif args.own_responsibility:
        from evaluations import own_responsibility_managed_contract as contract
    elif args.kind_mapping:
        from evaluations import kind_mapping_managed_contract as contract
    version = contract.VERSION if contract is not None else VERSION
    catalog = SchemaCatalog('projects/retail')
    case = diagnostic_case(catalog)
    if args.replay:
        print(json.dumps(replay(args.replay, catalog, case, contract=contract), ensure_ascii=False))
        return 0
    if not args.execute:
        print(json.dumps(dict(execute=False, version=version, model=MODEL, num_predict=-1,
            HTTP_timeout_seconds=None, think=True, options=MODEL_OPTIONS,
            stages=['indexed_recall', 'all_candidate_fixed_slot_mapping', 'selection_prepared_requests'],
            request_sha256=sha256(case['request'].encode('utf-8')).hexdigest(),
            candidate_views=[v.name for v in catalog.views()]), ensure_ascii=False))
        return 0
    if not args.ticket:
        parser.error('--execute requires the active controller worker --ticket')
    settings = AssistantSettings.from_env(Path('.env'))
    if settings.llm_provider != 'ollama':
        raise ValueError('only the configured local Ollama provider is authorized')
    os.environ['EDD_LOCAL_ENDPOINT'] = settings.llm_base_url.rstrip('/') + '/api/chat'
    identity = verify_model_identity(settings.llm_base_url)
    folder = TASK / '.local' / ('qwen-managed-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)
    invoke = ManagedInvoke(folder, args.ticket, case['case_id'] + ':' + version,
        lambda name, value: write_json(folder / name, value))
    meta = record_run(folder, catalog, case, invoke, identity=identity, contract=contract)
    print(json.dumps(dict(folder=str(folder), stopped=meta['stopped']), ensure_ascii=False))
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
