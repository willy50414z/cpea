"""Fixed upstream-injected node diagnostics; default dry-run, offline replay."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from importlib.metadata import version as distribution_version
import json
import os
from pathlib import Path
import shutil
import sys
from time import monotonic
from uuid import uuid4

from langchain_core.messages import AIMessage

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from evaluations import kind_mapping_managed_contract as contract
from evaluations.managed_three_stage_runner import (
    LOOPCTL, MODEL, MODEL_DIGEST, MODEL_OPTIONS, ManagedInvoke, read_json,
    verify_model_identity, write_json,
)
from evaluations.three_stage_view_selection import MISSING_POLICIES, finish_selection
from evaluations.three_stage_view_selection_runner import (
    TASK, RecordedProviderError, _verify_artifacts, error_record,
)

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'managed-node-diagnostics-1'
FIXTURES = ROOT / 'evaluations/fixtures/kind_diagnostics_v1'
DEFAULT_MANIFEST = FIXTURES / 'manifest.json'
SAMPLE_IDS = ['SEL-ISO-v1-01', 'COV-ISO-v1-01', 'COV-ISO-v1-02', 'COV-ISO-v1-03']


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def json_digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def load_package(manifest=DEFAULT_MANIFEST):
    path = Path(manifest).resolve()
    if path != DEFAULT_MANIFEST.resolve():
        raise ValueError('only the fixed kind_diagnostics_v1 manifest is supported')
    data = read_json(path)
    if (data['version'] != 'kind-isolation-v1' or data['candidate'] != contract.VERSION
            or data['runner_version'] != VERSION or [s['id'] for s in data['samples']] != SAMPLE_IDS
            or any(s['count'] != 1 or s['role'] != 'ISOLATION' for s in data['samples'])
            or data['upstream_injected'] is not True):
        raise ValueError('fixed diagnostic design differs')
    return dict(manifest=data, manifest_path=path, root=path.parent,
                oracle=read_json(path.parent / 'oracle.json'))


def _fixture(package, name):
    path = (package['root'] / name).resolve()
    if not path.is_relative_to(package['root'].resolve()):
        raise ValueError('fixture path escapes package')
    return path


def _body(messages, schema):
    roles = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
    return dict(model=MODEL, messages=[dict(role=roles[m.type], content=m.content) for m in messages],
                stream=False, think=True, options=deepcopy(MODEL_OPTIONS), format=schema.model_json_schema())


def prepare(package, sample_id):
    sample = next((s for s in package['manifest']['samples'] if s['id'] == sample_id), None)
    if sample is None:
        raise ValueError('sample is not in fixed manifest')
    request = _fixture(package, sample['request']).read_bytes().decode('utf-8')
    profile = ROOT / sample['profile'] if sample['profile'] == 'projects/retail' else _fixture(package, sample['profile'])
    catalog = SchemaCatalog(profile)
    recall_data = read_json(_fixture(package, sample['recall']))
    recall = contract.materialize_recall(contract.RecallWire.model_validate(recall_data), request, catalog)
    requirements = [r.model_dump() for r in recall.requirements]
    views = [v.policy for v in catalog.views()]
    coverages = []
    if sample['stage'] == 'selection':
        if recall.model_dump() != read_json(_fixture(package, 'recall-original-normalized.json')):
            raise ValueError('fixed normalized recall differs')
        wires = read_json(_fixture(package, sample['coverage']))
        if set(wires) != {v['view'] for v in views}:
            raise ValueError('fixed coverage must contain every admitted View')
        covschema = contract.coverage_schema(recall)
        coverages = [contract.materialize_coverage(covschema.model_validate(wires[v['view']]),
            recall, request, catalog, v) for v in views]
        if [c.model_dump() for c in coverages] != read_json(_fixture(package, 'coverage-selection-normalized.json')):
            raise ValueError('fixed normalized coverage differs')
        schema = contract.SelectionWire
        messages = contract.messages('selection', schema, request, requirements=requirements,
            coverages=[c.model_dump() for c in coverages], views=views, missing_policy_options=MISSING_POLICIES)
    else:
        schema = contract.coverage_schema(recall)
        policy = next(v for v in views if v['view'] == sample['view'])
        messages = contract.messages('coverage', schema, request, requirements=requirements, view=policy)
    tokens = TiktokenCounter('cl100k_base').count_messages([(m.type, m.content) for m in messages])
    context = dict(package=package, sample=deepcopy(sample), request=request, catalog=catalog,
        recall=recall, coverages=coverages, schema=schema, schema_json=schema.model_json_schema(),
        messages=messages, body=_body(messages, schema), input_tokens=tokens,
        upstream=dict(recall=recall.model_dump(), coverages=[c.model_dump() for c in coverages],
            profile_id=catalog.profile_id, catalog_fingerprint=catalog.fingerprint))
    for suffix, value in [('messages', [dict(role=m.type, content=m.content) for m in messages]),
                          ('schema', context['schema_json']), ('body', context['body']),
                          ('upstream', context['upstream'])]:
        frozen = _fixture(package, 'inputs/' + sample_id + '-' + suffix + '.json')
        if frozen.exists() and read_json(frozen) != value:
            raise ValueError('fixed input ' + suffix + ' differs')
    return context


def source_paths():
    # Superset of the complete repo import closure, plus original tests/prompts/lock.
    paths = [*sorted((ROOT / 'src/cpea').rglob('*.py')),
             *sorted((ROOT / 'evaluations').glob('*.py')),
             *sorted((ROOT / 'evaluations/prompts').rglob('*.md')),
             *sorted((ROOT / 'tests/unit').glob('*.py')),
             *sorted((ROOT / 'projects/retail').rglob('*.yaml')),
             ROOT / 'pyproject.toml', ROOT / 'uv.lock']
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}


def bindings(package):
    contexts = [prepare(package, sid) for sid in SAMPLE_IDS]
    external = [LOOPCTL, LOOPCTL.resolve().parents[3] / 'edd/scripts/ledger.py']
    return dict(sources=source_paths(), external_sources={str(p): digest(p) for p in external},
        fixtures={p.relative_to(package['root']).as_posix(): digest(p)
                  for p in sorted(package['root'].rglob('*')) if p.is_file() and p.name != 'manifest.json'},
        samples={c['sample']['id']: dict(body=json_digest(c['body']), schema=json_digest(c['schema_json']),
            upstream=json_digest(c['upstream']), messages=json_digest([dict(role=m.type, content=m.content) for m in c['messages']]),
            profile_id=c['catalog'].profile_id, catalog=c['catalog'].fingerprint,
            input_tokens=c['input_tokens']) for c in contexts},
        model=dict(name=MODEL, digest=MODEL_DIGEST, think=True, options=MODEL_OPTIONS,
            HTTP_timeout_seconds=None, outer_timeout_seconds=None, tokenizer='cl100k_base', context_window=32768),
        runtime=dict(venv='.venv', python=sys.version, executable=sys.executable,
            packages={name: distribution_version(name) for name in ['pydantic','langchain-core','tiktoken','PyYAML']},
            external_dependencies='same installed environment with uv.lock; not vendored'))


def _review_provenance(package, review):
    # The fresh semantic reviewer is a different controller-bound worker, not
    # an author assertion or a review copied from another task/node/version.
    task = json.loads(TASK.joinpath('task.md').read_text(encoding='utf-8').split('---', 2)[1])
    loop = task['plan']['edd_loop']
    tickets = loop['tickets']
    author = tickets.get(package['manifest']['author_ticket'])
    reviewer = tickets.get(review['ticket'])
    if (not author or not reviewer or reviewer.get('role') != 'worker'
            or reviewer.get('node') != 'kind_diagnostic_fixture_semantics'
            or reviewer.get('closed') is not True
            or not reviewer.get('platform_id') or reviewer['platform_id'] == author.get('platform_id')
            or not any(r.get('round') == reviewer.get('round') and r.get('result') == 'PASS'
                       and r.get('node') == 'kind_diagnostic_fixture_semantics'
                       and r.get('producer') == reviewer['platform_id'] for r in loop['rounds'])):
        raise ValueError('review lacks fresh completed controller-bound semantic provenance')


def preflight(package, contexts, review):
    if (not isinstance(review, dict) or review.get('schema_version') != 1 or review.get('verdict') != 'ACCEPT'
            or review.get('reviewer_role') != 'fresh_fixture_semantics' or not review.get('ticket')
            or review['ticket'] == package['manifest']['author_ticket']
            or review.get('author_ticket') != package['manifest']['author_ticket']):
        raise ValueError('execute requires fresh ACCEPT fixture review')
    if (read_json(package['manifest_path']) != package['manifest']
            or review.get('manifest_sha256') != digest(package['manifest_path'])
            or review.get('bindings') != package['manifest']['bindings']
            or bindings(package) != package['manifest']['bindings']):
        raise ValueError('review/manifest/fixture/source/model/input hash drift')
    for context in contexts:
        fresh = prepare(package, context['sample']['id'])
        if (context['input_tokens'] >= 32768 or context['input_tokens'] != fresh['input_tokens']
                or context['schema_json'] != fresh['schema_json'] or context['body'] != fresh['body']
                or context['schema'].model_json_schema() != fresh['schema_json']
                or _body(context['messages'], context['schema']) != context['body']
                or context['request'] != fresh['request']
                or context['recall'].model_dump() != fresh['recall'].model_dump()
                or context['catalog'].fingerprint != fresh['catalog'].fingerprint
                or context['upstream'] != fresh['upstream']
                or [c.model_dump() for c in context['coverages']] != [c.model_dump() for c in fresh['coverages']]):
            raise ValueError('context/schema/body/upstream preflight drift')
    _review_provenance(package, review)
    return dict(result='PASS', manifest_sha256=digest(package['manifest_path']), review_sha256=json_digest(review))


def _date_equivalent(actual, expected):
    if not expected or any('operator' not in m for m in expected):
        return False
    if len(expected) != 2 or {m['operator'] for m in expected} != {'>=', '<'}:
        return False
    start = next(m for m in expected if m['operator'] == '>=')
    end = next(m for m in expected if m['operator'] == '<')
    inclusive = dict(end, operator='<=', value=(date.fromisoformat(end['value']) - timedelta(days=1)).isoformat())
    return sorted(map(json_digest, actual)) in [sorted(map(json_digest, [start, end])), sorted(map(json_digest, [start, inclusive]))]


def _coverage_semantics(context, parsed):
    expected = context['package']['oracle']['positive_outputs'][context['sample']['id']]['entries']
    actual = parsed['entries']; findings = []
    for rid, target in expected.items():
        row = actual[rid]
        statuses = ['unsupported', 'uncertain'] if target['status'] == 'unsupported' else [target['status']]
        if row['status'] not in statuses or row['own_gap'] != target['own_gap']:
            findings.append(dict(requirement_id=rid, aspect='status/own_gap', expected=target, actual=row))
        mapping_equal = sorted(map(json_digest, row['mappings'])) == sorted(map(json_digest, target['mappings']))
        if not mapping_equal and not _date_equivalent(row['mappings'], target['mappings']):
            findings.append(dict(requirement_id=rid, aspect='necessary mappings/predicates', expected=target['mappings'], actual=row['mappings']))
        if row.get('contract_path') != target.get('contract_path'):
            # A different true evidence path needs explicit semantic review;
            # it is never silently approved by the author checker.
            findings.append(dict(requirement_id=rid, aspect='contract_path requires review', expected=target.get('contract_path'), actual=row.get('contract_path')))
    return findings


def _selection_semantics(context, parsed):
    target = context['package']['oracle']['selection_requirements']; draft = parsed['draft']; findings = []
    def check(ok, aspect, actual):
        if not ok: findings.append(dict(aspect=aspect, actual=actual))
    check(draft['status'] == 'ready', 'required ready', draft['status'])
    tasks = {t['view']: t for t in draft['tasks']}
    expected_views = {target['inventory_view'], target['sales_view']}
    check(set(tasks) == expected_views and len(draft['tasks']) == 2, 'two source responsibilities', list(tasks))
    if set(tasks) != expected_views or draft['integration'] is None:
        return findings
    inventory, sales = tasks[target['inventory_view']], tasks[target['sales_view']]
    keys = target['keys']
    for task, metrics in [(inventory, target['inventory_metrics']), (sales, target['sales_metrics'])]:
        check(task['metrics'] == metrics and not task['conditional_metrics'], 'typed sum responsibilities', task)
        check(set(task['group_by']) == set(keys) and set(task['output_grain']) == set(keys), 'task store/product grain', task)
        check(not task['attributes'] and not task['depends_on'] and not task['unbound_inputs'], 'no extra data obligations', task)
    check(inventory['filters'] == [], 'inventory no sales scope or status restriction', inventory['filters'])
    check(inventory['metadata_collections'] == target['inventory_metadata'], 'snapshot metadata', inventory['metadata_collections'])
    check(not sales['metadata_collections'], 'sales no snapshot metadata', sales['metadata_collections'])
    filters = sales['filters']; channel = [f for f in filters if f['column'] == 'sales_channel']
    period = [f for f in filters if f['column'] == 'order_date']
    expected_period = [dict(column='order_date', operator='>=', value=target['sales_month'][0]),
                       dict(column='order_date', operator='<', value=target['sales_month'][1])]
    check(channel == [dict(column='sales_channel', operator='=', value=target['channel'])]
          and len(filters) == 3 and _date_equivalent(period, expected_period), 'same-task whole month and online', filters)
    integration = draft['integration']
    check(integration['anchor_task'] == inventory['task_id'] and set(integration['output_grain']) == set(keys), 'inventory anchor/grain', integration)
    edges = integration['edges']
    check(len(edges) == 1 and edges[0]['left_task'] == inventory['task_id'] and edges[0]['right_task'] == sales['task_id']
          and edges[0]['mode'] == 'left' and edges[0]['preserve_task'] == inventory['task_id']
          and edges[0]['cardinality'] == 'one_to_one' and edges[0]['left_keys'] == edges[0]['right_keys']
          and set(edges[0]['left_keys']) == set(keys), 'left preserve paired keys', edges)
    check(integration['missing_data_policy'] == MISSING_POLICIES[0], 'no unproven zero fill', integration['missing_data_policy'])
    assigned = {a['requirement_id']: a for a in parsed['assignments']}
    for requirement in context['recall'].requirements:
        task = inventory if requirement.kind in ['grain', 'population', 'metadata'] or requirement.requirement_id == 'MET-001' else sales
        a = assigned.get(requirement.requirement_id)
        check(a is not None and a['view'] == task['view'] and a['task_id'] == task['task_id'], 'assignment ' + requirement.requirement_id, a)
    return findings


def _presence(value, path=''):
    rows = []
    if isinstance(value, dict):
        rows.append(dict(path=path, keys=list(value)))
        for key, item in value.items():
            rows += _presence(item, path + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, item in enumerate(value): rows += _presence(item, path + '/' + str(i))
    return rows


def evaluate(context, raw, save=lambda name, value: None):
    # Presence records raw JSON before Pydantic adds any defaults. Strict wire
    # parsing still rejects duplicate keys/NaN; presence is never a repair path.
    try:
        object_keys = []
        def pairs(items):
            object_keys.append([key for key, _ in items])
            return dict(items)
        raw_json = json.loads(raw, object_pairs_hook=pairs)
        save('node-presence.json', dict(objects=_presence(raw_json), object_key_sequences_in_parse_order=object_keys,
            note='raw JSON key sequences include duplicates; strict parser verdict recorded separately'))
    except (ValueError, TypeError):
        save('node-presence.json', dict(objects=None, note='not parseable JSON'))
    parsed_model = contract.parse_wire(AIMessage(content=raw), context['schema'])
    parsed = parsed_model.model_dump(by_alias=True)
    save('node-parsed.json', parsed)
    save('node-refs.json', dict(requirements=[dict(requirement_id=r.requirement_id, scope_ids=r.scope_ids,
        grain_binding=r.grain_binding, grain_requirement_ids=r.grain_requirement_ids) for r in context['recall'].requirements], wire=parsed))
    response = None
    if context['sample']['stage'] == 'coverage':
        compiled = contract.compile_coverage(parsed_model, context['recall']).model_dump(by_alias=True)
        save('node-compiled.json', compiled)
        policy = next(v.policy for v in context['catalog'].views() if v.name == context['sample']['view'])
        normalized = contract.materialize_coverage(parsed_model, context['recall'], context['request'], context['catalog'], policy)
        findings = _coverage_semantics(context, parsed)
    else:
        save('node-compiled.json', dict(applicable=False, reason='selection materializes using original contract; no answer compilation'))
        normalized = contract.materialize_selection(parsed_model, context['recall'], context['coverages'], context['request'], context['catalog'])
        response_model = finish_selection(normalized, context['recall'], context['coverages'], context['request'], context['catalog'])
        response = response_model.model_dump()
        save('response.json', response)
        findings = _selection_semantics(context, parsed)
    normalized = normalized.model_dump()
    save('node-normalized.json', normalized)
    semantic = dict(machine_verdict='FAIL' if findings else 'PASS', classification='SEMANTIC_REJECT' if findings else 'MACHINE_CHECKS_ONLY',
        findings=findings, independent_semantic_approval='PENDING',
        free_text_review='PENDING: all raw/normalized text, tasks.request, preparation, notes, policies, assignment/exclusion refs and remaining claims require independent semantic review',
        fixture_approval=context['package']['oracle']['approval'])
    save('semantic-review.json', semantic)
    return dict(parsed=parsed, normalized=normalized, response=response, semantic=semantic)


def _run(context, invoke, save, check_version, context_window):
    sample = context['sample']; raw = None; usage = dict(calls=0, input_tokens_actual=0, output_tokens_actual=0, usage_missing_calls=0)
    try:
        check_version()
        save('node-request.json', dict(sample=sample, upstream_injected=True, input_tokens_estimated=context['input_tokens'],
            messages=[dict(role=m.type, content=m.content) for m in context['messages']], response_schema=context['schema_json']))
        save('node-body.json', context['body'])
        save('upstream.json', context['upstream'])
        save('usage.json', dict(usage))
        if context['input_tokens'] >= context_window:
            raise ValueError('input cannot fit model context')
        usage['calls'] = 1
        save('usage.json', dict(usage))
        started = monotonic()
        try:
            raw = invoke('node', context['messages'], context['schema'])
        except Exception as exc:
            save('node-provider-error.json', dict(**error_record(exc), elapsed_seconds=monotonic()-started))
            raise
        actual = getattr(raw, 'usage_metadata', None)
        save('node-call.json', dict(response=raw.content, usage=actual,
            response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-started))
        if actual:
            usage['input_tokens_actual'], usage['output_tokens_actual'] = actual['input_tokens'], actual['output_tokens']
        else: usage['usage_missing_calls'] = 1
        save('usage.json', dict(usage))
        check_version()
        result = evaluate(context, raw.content, save)
        if result['semantic']['machine_verdict'] != 'PASS':
            raise ValueError('fixed diagnostic semantic checks failed')
        return result
    except Exception as exc:
        save('node-error.json', dict(**error_record(exc), raw_saved=raw is not None))
        raise


def record_sample(folder, context, invoke, *, mode='OFFLINE_CONTROL', identity=None, authorization=None, context_window=32768):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(folder.iterdir()): raise ValueError('sample folder must be empty; preserve every first raw')
    package = context['package']; frozen = bindings(package)
    save = lambda name, value: write_json(folder / name, value)
    meta = dict(version=VERSION, candidate=contract.VERSION, sample=context['sample'], mode=mode,
        upstream_injected=True, injection_sources={name: digest(_fixture(package, name)) for name in
            [context['sample']['request'], context['sample']['recall'], *([context['sample']['coverage']] if 'coverage' in context['sample'] else [])]},
        frozen=frozen, manifest_sha256=digest(package['manifest_path']), model_identity=identity,
        authorization=authorization, context_window=context_window,
        started_at=datetime.now(timezone.utc).isoformat(), stopped=dict(error_type='InterruptedRun', error='run did not reach completion'))
    save('run.json', meta)
    def check_version():
        if digest(package['manifest_path']) != meta['manifest_sha256'] or bindings(package) != frozen:
            raise ValueError('source/version/input changed during sample')
    try:
        _run(context, invoke, save, check_version, context_window)
        check_version()
        meta['stopped'] = None
    except Exception as exc:
        meta['stopped'] = error_record(exc)
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        meta['artifact_hashes'] = {p.name: digest(p) for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
    return meta


def replay(folder, package=None):
    folder = Path(folder); package = package or load_package(); meta = read_json(folder / 'run.json')
    _verify_artifacts(folder, meta)
    if meta['version'] != VERSION or digest(package['manifest_path']) != meta['manifest_sha256'] or bindings(package) != meta['frozen']:
        raise ValueError('replay version/input mismatch')
    context = prepare(package, meta['sample']['id'])
    if context['sample'] != meta['sample']:
        raise ValueError('replay sample mismatch')
    saved = {}
    def invoke(name, messages, schema):
        if read_json(folder / 'node-body.json') != _body(messages, schema):
            raise ValueError('replay request/body mismatch')
        if (folder / 'node-provider-error.json').exists():
            raise RecordedProviderError(read_json(folder / 'node-provider-error.json'))
        call = read_json(folder / 'node-call.json')
        return AIMessage(content=call['response'], usage_metadata=call['usage'], response_metadata=call['response_metadata'] or {})
    stopped = None
    try: _run(context, invoke, saved.__setitem__, lambda: None, meta['context_window'])
    except Exception as exc: stopped = error_record(exc)
    if stopped != meta['stopped']: raise ValueError('replay first error differs')
    for name, value in saved.items():
        original = read_json(folder / name)
        if name.endswith(('-call.json', '-provider-error.json')):
            original.pop('elapsed_seconds', None); value.pop('elapsed_seconds', None)
        if original != value: raise ValueError('replay artifact differs: ' + name)
    external = {'node-managed.json', 'node-provider-response.json'}
    if set(meta['artifact_hashes']) - external != set(saved):
        raise ValueError('replay artifact set differs')
    return dict(result='PASS', raw_replays=int('node-call.json' in saved), stopped=stopped,
                upstream_injected=True, provider_calls=0)


def freeze_sources(destination, package=None):
    package = package or load_package(); destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, expected in source_paths().items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != expected: raise ValueError('frozen source differs')
    shutil.copytree(package['root'], destination / 'evaluations/fixtures/kind_diagnostics_v1')
    external = destination / '_external'; external.mkdir()
    shutil.copyfile(LOOPCTL, external / 'loopctl.py')
    (external / 'edd').mkdir()
    shutil.copyfile(LOOPCTL.resolve().parents[3] / 'edd/scripts/ledger.py', external / 'edd/ledger.py')
    write_json(destination / 'freeze.json', dict(version=VERSION, bindings=bindings(package),
        manifest_sha256=digest(package['manifest_path']), external_runtime='same .venv/uv.lock, external dependencies not vendored',
        replay_command='PYTHONPATH=<freeze>/src:<freeze> <repo>/.venv/bin/python -m evaluations.managed_node_diagnostics --replay <absolute-run>'))
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true'); group.add_argument('--replay', type=Path)
    parser.add_argument('--stage', choices=['selection', 'coverage'], default='selection')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--review', type=Path); parser.add_argument('--ticket')
    args = parser.parse_args(argv); package = load_package(args.manifest)
    if args.replay:
        print(json.dumps(replay(args.replay, package), ensure_ascii=False)); return 0
    contexts = [prepare(package, s['id']) for s in package['manifest']['samples'] if s['stage'] == args.stage]
    if not args.execute:
        print(json.dumps(dict(execute=False, version=VERSION, candidate=contract.VERSION, upstream_injected=True,
            fixture_approval=package['manifest']['approval'], samples=[c['sample']['id'] for c in contexts],
            input_tokens={c['sample']['id']: c['input_tokens'] for c in contexts},
            manifest_sha256=digest(package['manifest_path']), bindings_match=bindings(package) == package['manifest']['bindings'],
            provider_calls=0), ensure_ascii=False)); return 0
    if not args.ticket: raise ValueError('execute requires active controller worker ticket')
    review = read_json(args.review) if args.review else None
    authorization = preflight(package, contexts, review)
    settings = AssistantSettings.from_env(ROOT / '.env')
    if settings.llm_provider != 'ollama': raise ValueError('only configured local Ollama provider is authorized')
    os.environ['EDD_LOCAL_ENDPOINT'] = settings.llm_base_url.rstrip('/') + '/api/chat'
    identity = verify_model_identity(settings.llm_base_url)
    batch = TASK / '.local' / ('kind-isolation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    batch.mkdir(mode=0o700)
    write_json(batch / 'fixture-review.json', review)
    freeze_sources(batch / 'frozen', package)
    results = []
    for context in contexts:
        preflight(package, [context], review)
        sid = context['sample']['id']; folder = batch / sid
        invoke = ManagedInvoke(folder, args.ticket, 'kind-isolation-v1:ISOLATION:' + sid,
            lambda name, value, folder=folder: write_json(folder / name, value))
        meta = record_sample(folder, context, invoke, mode='MANAGED_LOCAL_ISOLATION', identity=identity, authorization=authorization)
        results.append(dict(sample=sid, stopped=meta['stopped'], folder=str(folder)))
        # Content errors are independent controls. Invalid/safety/provider state
        # cannot establish a sample and therefore stops the entire batch.
        if (folder / 'node-provider-error.json').exists() or (meta['stopped'] and not (folder / 'node-call.json').exists()):
            break
    print(json.dumps(dict(batch=str(batch), results=results, independent_semantic_approval='PENDING'), ensure_ascii=False))
    return int(any(r['stopped'] for r in results) or len(results) != len(contexts))


if __name__ == '__main__':
    raise SystemExit(main())
