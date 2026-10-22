"""Sequential three-stage diagnostic; default is dry-run, replay is offline."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.three_stage_view_selection import (
    MISSING_POLICIES, RecallResult, ViewCoverage, SelectionResult,
    validate_recall, validate_coverage, finish_selection,
)
from evaluations.indexed_requirement_recall import VERSION, IndexedRecallResult, materialize_recall, request_index

PROMPTS = Path(__file__).resolve().parent / 'prompts/three_stage'
TASK = Path('evidence-driven-dev/tasks/ollama-planning-mvp')
MODEL = 'DeepSeek-V4.1-Flash'


class RecordedProviderError(Exception):
    """Offline reconstruction of a saved error; never invokes a provider."""
    def __init__(self, record):
        self.record = {k: record[k] for k in ('error_type', 'error')}
        super().__init__(record['error'])


def error_record(exc):
    if isinstance(exc, RecordedProviderError):
        return exc.record
    return dict(error_type=type(exc).__name__, error=str(exc))


def _verify_artifacts(folder, meta):
    if {p.name for p in folder.iterdir()} != set(meta['artifact_hashes']) | {'run.json'}:
        raise ValueError('replay artifact set mismatch')
    for name, digest in meta['artifact_hashes'].items():
        if sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError('replay artifact hash mismatch')


def load_cached_prefix(folder, catalog, case):
    """Revalidate immutable raw after a mechanical fix, with unchanged inputs.

    This is a separate experiment, never a fresh fixed-version first pass.
    Provider errors cannot be resumed here because that would retry a call.
    """
    meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    _verify_artifacts(folder, meta)
    if list(folder.glob('*-provider-error.json')):
        raise ValueError('continuation after provider failure would retry; prohibited')
    current = fingerprint(catalog, case)
    if any(current[k] != meta['frozen'][k] for k in ('catalog', 'case_sha256', 'schemas')):
        raise ValueError('cached catalog/case/schema changed')
    changed = {name for name, digest in meta['frozen']['source_hashes'].items() if current['source_hashes'].get(name) != digest}
    allowed = {'evaluations/three_stage_view_selection.py', 'evaluations/three_stage_view_selection_runner.py',
               'tests/unit/test_three_stage_view_selection.py'}
    if not changed <= allowed:
        raise ValueError('cached prompt or dependency changed')
    if not meta['stopped'] or (folder / 'selection-call.json').exists():
        raise ValueError('continuation requires a stopped, unfinished prefix')
    names = ['recall', *[f'map-{i:02}' for i in range(1, 8)]]
    present = [name for name in names if (folder / (name + '-call.json')).exists()]
    if not present or present != names[:len(present)] or len(present) != meta['calls']:
        raise ValueError('cached node sequence/call count differs')
    records, recall = [], None
    for index, name in enumerate(present):
        call = json.loads((folder / (name + '-call.json')).read_text(encoding='utf-8'))
        original_input = json.loads((folder / (name + '-request.json')).read_text(encoding='utf-8'))
        schema = IndexedRecallResult if index == 0 else ViewCoverage
        parsed = schema.model_validate_json(call['response'])
        if index == 0:
            recall = materialize_recall(parsed, case['request'], catalog)
            messages = messages_for('recall', schema, case['request'], views=[v.policy for v in catalog.views()])
        else:
            view = recall.candidate_views[index-1].view
            if parsed.view != view:
                raise ValueError('cached mapping view differs')
            validate_coverage(parsed, recall, case['request'], catalog)
            messages = messages_for('coverage', schema, case['request'],
                requirements=[r.model_dump() for r in recall.requirements],
                view=next(v.policy for v in catalog.views() if v.name == view))
        if original_input['messages'] != [dict(role=m.type, content=m.content) for m in messages]:
            raise ValueError('cached input changed')
        records.append(dict(call=call, request=original_input, source_artifact=str(folder / (name + '-call.json'))))
    return records, meta


@dataclass
class Continuation:
    records: list
    live_invoke: object
    cached_calls: int = 0
    live_calls: int = 0

    def __call__(self, messages, schema):
        if self.cached_calls < len(self.records):
            record = self.records[self.cached_calls]
            if (record['request']['messages'] != [dict(role=m.type, content=m.content) for m in messages]
                    or record['request']['schema'] != schema.__name__):
                raise ValueError('cached input changed; no provider call')
            self.cached_calls += 1
            call = record['call']
            return AIMessage(content=call['response'], usage_metadata=call.get('usage'),
                response_metadata=call.get('response_metadata') or {}, additional_kwargs=dict(
                    evidence_origin='cached_raw', source_artifact=record['source_artifact'],
                    provider_elapsed_seconds=call['elapsed_seconds']))
        self.live_calls += 1
        return self.live_invoke(messages, schema)


@dataclass
class Budget:
    calls_limit: int = 9
    context_window: int = 32768
    output_limit: int = 4096
    safety: int = 1024
    total_input_limit: int = 150000
    total_output_limit: int = 36864
    wall_seconds: float = 3000
    timeout_seconds: float = 300
    calls: int = 0
    input_tokens: int = 0
    output_reserved: int = 0
    input_tokens_actual: int = 0
    output_tokens_actual: int = 0
    usage_missing_calls: int = 0
    started: float = field(default_factory=monotonic)

    def begin(self, messages):
        tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in messages])
        if (self.calls >= self.calls_limit or self.input_tokens + tokens > self.total_input_limit
                or tokens + self.output_limit + self.safety > self.context_window
                or self.output_reserved + self.output_limit > self.total_output_limit
                or self.wall_seconds - (monotonic() - self.started) < self.timeout_seconds):
            raise ValueError('calls/token/context/wall budget exhausted before provider construction')
        self.calls += 1
        self.input_tokens += tokens
        self.output_reserved += self.output_limit
        return tokens

    def record_usage(self, usage, estimated_input):
        if not usage:
            self.usage_missing_calls += 1
            return
        actual_input, actual_output = usage['input_tokens'], usage['output_tokens']
        self.input_tokens_actual += actual_input
        self.output_tokens_actual += actual_output
        self.input_tokens += max(0, actual_input - estimated_input)
        if (self.input_tokens > self.total_input_limit or actual_output > self.output_limit
                or self.output_tokens_actual > self.total_output_limit
                or actual_input + self.output_limit + self.safety > self.context_window):
            raise ValueError('provider usage budget exceeded; raw retained, no next call')

    def state(self):
        return dict(calls=self.calls, input_tokens_estimated=self.input_tokens,
                    input_tokens_actual=self.input_tokens_actual, output_tokens_actual=self.output_tokens_actual,
                    usage_missing_calls=self.usage_missing_calls, output_tokens_reserved=self.output_reserved,
                    elapsed_seconds=monotonic()-self.started)


def messages_for(phase, schema, request, **context):
    prompt = phase
    if phase == 'recall' and schema is IndexedRecallResult:
        prompt = 'recall_indexed'
        context = dict(context, request_length=len(request), request_characters=request_index(request))
    return [SystemMessage(content=(PROMPTS / (prompt + '.md')).read_text(encoding='utf-8')),
            HumanMessage(content=json.dumps(dict(request=request, **context, response_schema=schema.model_json_schema()), ensure_ascii=False))]


def run_pipeline(request, catalog, invoke, save, budget, check_version=lambda: None, *, recall_only=False):
    """The injected invoke is the only provider boundary; persist raw before parsing."""
    views = [v.policy for v in catalog.views()]

    def node(name, phase, schema, validate, normalize=None, **context):
        raw = None
        try:
            check_version()
            messages = messages_for(phase, schema, request, **context)
            tokens = budget.begin(messages)
            save(name + '-request.json', dict(messages=[dict(role=m.type, content=m.content) for m in messages],
                                             schema=schema.__name__, input_tokens_estimated=tokens))
            save('budget.json', budget.state())
            started = monotonic()
            try:
                raw = invoke(messages, schema)
            except Exception as exc:
                save(name + '-provider-error.json', dict(**error_record(exc), elapsed_seconds=monotonic()-started))
                raise
            save(name + '-call.json', dict(response=raw.content, usage=getattr(raw, 'usage_metadata', None),
                response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-started,
                origin=raw.additional_kwargs.get('evidence_origin', 'live'),
                source_artifact=raw.additional_kwargs.get('source_artifact'),
                provider_elapsed_seconds=raw.additional_kwargs.get('provider_elapsed_seconds', monotonic()-started)))
            budget.record_usage(getattr(raw, 'usage_metadata', None), tokens)
            parsed = parse_model(raw, schema)
            if normalize is not None:
                save(name + '-parsed.json', parsed.model_dump())
                parsed = normalize(parsed)
            validate(parsed)
            save(name + '-result.json', parsed.model_dump())
            save('budget.json', budget.state())
            return parsed
        except Exception as exc:
            save(name + '-error.json', dict(**error_record(exc), raw_saved=raw is not None))
            raise

    recall = node('recall', 'recall', IndexedRecallResult, lambda r: validate_recall(r, request, catalog),
                  normalize=lambda r: materialize_recall(r, request, catalog), views=views)
    if recall_only:
        return recall
    coverages = []
    for index, candidate in enumerate(recall.candidate_views, 1):
        policy = next(v for v in views if v['view'] == candidate.view)
        def validate_one(coverage):
            if coverage.view != candidate.view:
                raise ValueError('mapping returned another view')
            return validate_coverage(coverage, recall, request, catalog)
        coverage = node(f'map-{index:02}', 'coverage', ViewCoverage,
                        validate_one,
                        requirements=[r.model_dump() for r in recall.requirements], view=policy)
        coverages.append(coverage)
    selection = node('selection', 'selection', SelectionResult,
                     lambda s: finish_selection(s, recall, coverages, request, catalog),
                     requirements=[r.model_dump() for r in recall.requirements],
                     coverages=[c.model_dump() for c in coverages], views=views,
                     missing_policy_options=MISSING_POLICIES)
    response = finish_selection(selection, recall, coverages, request, catalog)
    save('response.json', response.model_dump())
    return response


def fingerprint(catalog, case):
    from evaluations.decomposition_cases import case_sha256
    files = ['evaluations/three_stage_view_selection.py', 'evaluations/three_stage_view_selection_runner.py',
             'evaluations/indexed_requirement_recall.py', 'tests/unit/test_indexed_requirement_recall.py',
             'evaluations/planning_mvp.py', 'evaluations/decomposition_grading.py', 'evaluations/decomposition_cases.py',
             'src/cpea/application/models/decomposition.py', 'src/cpea/workflows/task_decomposition/validation.py',
             'src/cpea/workflows/task_decomposition/prompt.py', 'src/cpea/infrastructure/catalog/yaml_catalog.py',
             'src/cpea/infrastructure/llm/factory.py', 'src/cpea/infrastructure/llm/parsing.py',
             'src/cpea/infrastructure/llm/context_budget.py', 'src/cpea/config/settings.py',
             'src/cpea/application/catalog_contract.py', 'src/cpea/domain/catalog.py',
             'evaluations/decomposition_runner.py', 'tests/unit/test_three_stage_view_selection.py',
             *[str(p) for p in sorted(PROMPTS.glob('*.md'))]]
    return dict(catalog=catalog.fingerprint, case_sha256=case_sha256(case),
                source_hashes={p: sha256(Path(p).read_bytes()).hexdigest() for p in files},
                schemas={s.__name__: sha256(json.dumps(s.model_json_schema(), sort_keys=True).encode()).hexdigest()
                         for s in (IndexedRecallResult, RecallResult, ViewCoverage, SelectionResult)})


def replay(folder, catalog, case):
    meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    if meta['frozen'] != fingerprint(catalog, case):
        raise ValueError('replay version mismatch')
    _verify_artifacts(folder, meta)
    names = [n for n in ['recall', *[f'map-{i:02}' for i in range(1, 8)], 'selection']
             if (folder / (n + '-call.json')).exists() or (folder / (n + '-provider-error.json')).exists()]
    nodes = iter(names)
    saved = {}
    def invoke(messages, schema):
        name = next(nodes)
        original = json.loads((folder / (name + '-request.json')).read_text(encoding='utf-8'))
        if original['messages'] != [dict(role=m.type, content=m.content) for m in messages]:
            raise ValueError('replay prompt/input mismatch')
        error_path = folder / (name + '-provider-error.json')
        if error_path.exists():
            raise RecordedProviderError(json.loads(error_path.read_text(encoding='utf-8')))
        call = json.loads((folder / (name + '-call.json')).read_text(encoding='utf-8'))
        return AIMessage(content=call['response'], usage_metadata=call.get('usage'), response_metadata=call.get('response_metadata') or {})
    stopped = None
    try:
        run_pipeline(case['request'], catalog, invoke, saved.__setitem__, Budget(), recall_only=meta.get('recall_only', False))
    except Exception as exc:
        stopped = error_record(exc)
    if stopped != meta['stopped']:
        raise ValueError('replay stop differs')
    for name, value in saved.items():
        if name.endswith(('-result.json', '-parsed.json', '-error.json')) or name == 'response.json':
            original = json.loads((folder / name).read_text(encoding='utf-8'))
            if name.endswith('-provider-error.json'):
                value = {k: v for k, v in value.items() if k != 'elapsed_seconds'}
                original = {k: v for k, v in original.items() if k != 'elapsed_seconds'}
            if value != original:
                raise ValueError('replay parsed result differs: ' + name)
    if len([n for n in saved if n.endswith('-call.json') or n.endswith('-provider-error.json')]) != meta['calls']:
        raise ValueError('replay node count differs')
    return dict(result='PASS', raw_replays=len([n for n in saved if n.endswith('-call.json')]), stopped=stopped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true')
    group.add_argument('--replay', type=Path)
    parser.add_argument('--continue-from', type=Path, help='Revalidate a saved raw prefix; requires a new experiment budget.')
    parser.add_argument('--recall-only', action='store_true', help='One-node diagnostic; no source mapping or benchmark grading.')
    parser.add_argument('--request-file', type=Path, help='UTF-8 diagnostic request; requires --recall-only.')
    args = parser.parse_args(argv)
    from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
    catalog = SchemaCatalog('projects/retail')
    case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog)
                if c['case_id'] == 'cross-view-11')
    approval = json.loads((TASK / 'agents/oracle-audit/review-manifest.json').read_text(encoding='utf-8'))
    if approval['catalog_fingerprint'] != catalog.fingerprint or next(c for c in approval['cases'] if c['case_id'] == case['case_id'])['case_sha256'] != case_sha256(case):
        raise ValueError('case/catalog oracle approval mismatch')
    if args.request_file:
        if not args.recall_only:
            raise ValueError('custom diagnostic requests require --recall-only; no benchmark oracle approval')
        raw_request = args.request_file.read_bytes()
        if raw_request.startswith(b'\xef\xbb\xbf') or not raw_request.decode('utf-8').strip():
            raise ValueError('diagnostic request must be nonempty UTF-8 without BOM')
        case = dict(case_id='diagnostic-request-' + sha256(raw_request).hexdigest()[:12], request=raw_request.decode('utf-8'),
                    source_case_id=case['case_id'], profile_id=catalog.profile_id, contract_fingerprint=catalog.fingerprint)
    if args.replay:
        if args.continue_from:
            raise ValueError('replay and continuation cannot be combined')
        print(json.dumps(replay(args.replay, catalog, case), ensure_ascii=False))
        return 0
    budget = Budget(calls_limit=1, total_input_limit=30000, total_output_limit=4096, wall_seconds=900) if args.recall_only else Budget()
    if args.recall_only and args.continue_from:
        raise ValueError('recall-only is a fresh diagnostic; cannot continue a prefix')
    cached_records, cached_meta = load_cached_prefix(args.continue_from, catalog, case) if args.continue_from else ([], None)
    if cached_meta:
        budget.started -= cached_meta.get('elapsed_seconds', 0)
    dry_messages = messages_for('recall', IndexedRecallResult, case['request'], views=[v.policy for v in catalog.views()])
    tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in dry_messages])
    print(json.dumps(dict(execute=args.execute, model=MODEL, version=VERSION, calls_limit=budget.calls_limit,
                         recall_input_tokens=tokens, output_limit=4096, context_window=32768,
                         total_input_limit=budget.total_input_limit, total_output_limit=budget.total_output_limit, wall_seconds=budget.wall_seconds,
                         cached_raw_count=len(cached_records), new_calls_limit=budget.calls_limit-len(cached_records),
                         recall_only=args.recall_only,
                         cost_usd=None, pricing_basis='Azure deployment rate unavailable; record actual usage'), ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    frozen = fingerprint(catalog, case)
    folder = TASK / '.local' / ('three-stage-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(parents=True, mode=0o700)
    def save(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)
    meta = dict(version=VERSION, model=MODEL, case_id=case['case_id'], frozen=frozen, sdk_retries=0,
                request=case['request'], recall_only=args.recall_only, custom_diagnostic=bool(args.request_file),
                temperature=1, top_p=1, seed=42, budget={k:v for k,v in vars(budget).items() if k != 'started'},
                cost_usd=None, pricing_basis='Azure deployment rate unavailable; tokens/calls/time bounded',
                started_at=datetime.now(timezone.utc).isoformat(), stopped=None, calls=0)
    meta.update(continued_from=str(args.continue_from) if args.continue_from else None,
                original_run_sha256=sha256((args.continue_from / 'run.json').read_bytes()).hexdigest() if args.continue_from else None,
                fixed_version_first_pass=not bool(cached_records))
    save('run.json', meta)
    def check_version():
        if fingerprint(SchemaCatalog('projects/retail'), case) != frozen:
            raise ValueError('frozen source/catalog/schema changed')
    def invoke(messages, schema):
        # Construct only after checking context/calls/time; no SQL or DB route.
        from evaluations.decomposition_runner import azure_planning_settings
        from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
        settings = replace(azure_planning_settings(Path('.env'), MODEL), max_output_tokens=budget.output_limit,
                           context_window=budget.context_window, context_safety_tokens=budget.safety,
                           request_timeout_seconds=budget.timeout_seconds)
        llm = bind_response_schema(get_llm_config(settings=settings), schema).bind(response_format={'type': 'json_object'})
        return llm.invoke(messages)
    continuation = Continuation(cached_records, invoke)
    try:
        response = run_pipeline(case['request'], catalog, continuation, save, budget, check_version, recall_only=args.recall_only)
        from evaluations.decomposition_grading import grade_decomposition
        from evaluations.planning_mvp import semantic_check
        # Oracle is deliberately outside runtime prompts and capability validation.
        if args.recall_only:
            save('diagnostic.json', dict(scope='recall only', status='structurally_valid', semantic_status='REQUIRES_REVIEW',
                                        requirements=len(response.requirements), source_mapping='NOT_EXECUTED'))
        else:
            save('score.json', dict(original=grade_decomposition(case, response, catalog), diagnostic=semantic_check(case, response, catalog)))
    except Exception as exc:
        meta['stopped'] = dict(error_type=type(exc).__name__, error=str(exc))
    finally:
        meta.update(budget.state(), finished_at=datetime.now(timezone.utc).isoformat())
        meta.update(cached_raw_replayed=continuation.cached_calls, new_provider_calls=continuation.live_calls)
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
        print(json.dumps(dict(folder=str(folder), calls=budget.calls, stopped=meta['stopped']), ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
