"""Versioned coordination for fixed v2 diagnostics; all contract execution is v1."""
from __future__ import annotations

from copy import deepcopy
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from langchain_core.messages import AIMessage

from evaluations import managed_node_diagnostics as base

ROOT = base.ROOT
VERSION = 'managed-node-diagnostics-2'
DEFAULT_MANIFEST = ROOT / 'evaluations/fixtures/kind_diagnostics_v2/manifest.json'
ADDITIONAL_SOURCES = ('evaluations/diagnostics/managed_node_diagnostics_v2.py',
                      'tests/diagnostics/test_managed_node_diagnostics_v2.py')
LINEAGE = {
    'evaluations/fixtures/kind_diagnostics_v1/manifest.json': '1749d09913e0f5d5a1caab4a4ede1bf4fa80fee260bb4e257f1f705634d934be',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-diagnostic-semantics/review.json': '0200cc20e8aa288580c0a5036d4056a144555a272b6b4afe64da357734118d6b',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-diagnostic-semantics/semantic-review.log': '3b7c9f3b51626a0634405b8e2c14efbcf730b600138aa60b067e74aceffca4f0',
}
# These functions use the supplied package/context, with no v1 version gate.
prepare, evaluate, digest = base.prepare, base.evaluate, base.digest


def load_package(manifest=DEFAULT_MANIFEST):
    path = Path(manifest).resolve()
    if path != DEFAULT_MANIFEST.resolve():
        raise ValueError('only the fixed kind_diagnostics_v2 manifest is supported')
    data = base.read_json(path)
    old = base.read_json(ROOT / 'evaluations/fixtures/kind_diagnostics_v1/manifest.json')
    expected_samples = [dict(s, request_case='kind-isolation-v2:ISOLATION:' + s['id'] + ':node') for s in old['samples']]
    if (data.get('schema_version') != 1 or data.get('version') != 'kind-isolation-v2'
            or data.get('candidate') != base.contract.VERSION or data.get('runner_version') != VERSION
            or data.get('samples') != expected_samples or data.get('upstream_injected') is not True
            or data.get('approval') != 'PENDING_FRESH_INDEPENDENT_REVIEW'
            or data.get('lineage') != LINEAGE
            or any(digest(ROOT / name) != value for name, value in LINEAGE.items())):
        raise ValueError('fixed v2 diagnostic design/lineage differs')
    return dict(manifest=data, manifest_path=path, root=path.parent, oracle=base.read_json(path.parent / 'oracle.json'))


def source_paths():
    return dict(base.source_paths(), **{name: digest(ROOT / name) for name in ADDITIONAL_SOURCES})


def bindings(package):
    result = base.bindings(package)
    result['sources'] = source_paths()
    result['lineage'] = {name: digest(ROOT / name) for name in LINEAGE}
    return result


def _controller_loop(task_path=None):
    path = Path(task_path) if task_path is not None else ROOT / base.TASK / 'task.md'
    return json.loads(path.read_text(encoding='utf-8').split('---', 2)[1])['plan']['edd_loop']


def _review_provenance(package, review, task_path=None):
    loop = _controller_loop(task_path)
    tickets = loop['tickets']; author_id = package['manifest']['author_ticket']
    author, reviewer = tickets.get(author_id), tickets.get(review['ticket'])
    def completed(item, node):
        return (isinstance(item, dict) and item.get('role') == 'worker' and item.get('node') == node
            and item.get('closed') is True and bool(item.get('platform_id'))
            and type(item.get('round')) is int
            and any(r.get('round') == item['round'] and r.get('node') == node
                and r.get('producer') == item['platform_id'] and r.get('result') == 'PASS' for r in loop['rounds']))
    if (not completed(author, 'kind_diagnostic_fixture_v2_correction')
            or not completed(reviewer, 'kind_diagnostic_fixture_semantics')
            or author['platform_id'] == reviewer['platform_id']):
        raise ValueError('review lacks fresh completed author/semantic-parent provenance')


def preflight(package, contexts, review, *, task_path=None):
    if (not isinstance(review, dict) or review.get('schema_version') != 1 or review.get('verdict') != 'ACCEPT'
            or review.get('reviewer_role') != 'fresh_fixture_semantics' or not review.get('ticket')
            or review['ticket'] == package['manifest']['author_ticket']
            or review.get('author_ticket') != package['manifest']['author_ticket']):
        raise ValueError('execute requires fresh ACCEPT fixture review')
    fresh_package = load_package(package['manifest_path'])
    if (fresh_package['manifest'] != package['manifest'] or fresh_package['oracle'] != package['oracle']
            or review.get('manifest_sha256') != digest(package['manifest_path'])
            or review.get('bindings') != package['manifest']['bindings']
            or bindings(package) != package['manifest']['bindings']):
        raise ValueError('review/manifest/fixture/source/model/input hash drift')
    if not contexts or len({c['sample']['id'] for c in contexts}) != len(contexts):
        raise ValueError('empty or duplicate diagnostic contexts')
    for context in contexts:
        fresh = prepare(fresh_package, context['sample']['id'])
        if (context['sample'] != fresh['sample'] or context['package'] != package
                or context['input_tokens'] >= 32768 or context['input_tokens'] != fresh['input_tokens']
                or context['schema_json'] != fresh['schema_json'] or context['body'] != fresh['body']
                or context['schema'].model_json_schema() != fresh['schema_json']
                or base._body(context['messages'], context['schema']) != context['body']
                or context['request'] != fresh['request']
                or context['recall'].model_dump() != fresh['recall'].model_dump()
                or context['catalog'].fingerprint != fresh['catalog'].fingerprint
                or context['upstream'] != fresh['upstream']
                or [c.model_dump() for c in context['coverages']] != [c.model_dump() for c in fresh['coverages']]):
            raise ValueError('context/schema/body/upstream preflight drift')
    _review_provenance(package, review, task_path)
    return dict(result='PASS', manifest_sha256=digest(package['manifest_path']), review_sha256=base.json_digest(review))


def record_sample(folder, context, invoke, *, mode='OFFLINE_CONTROL', identity=None, authorization=None, context_window=32768):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(folder.iterdir()): raise ValueError('sample folder must be empty; preserve every first raw')
    package = context['package']; frozen = bindings(package)
    save = lambda name, value: base.write_json(folder / name, value)
    meta = dict(version=VERSION, candidate=base.contract.VERSION, sample=context['sample'], mode=mode,
        upstream_injected=True, injection_sources={name: digest(base._fixture(package, name)) for name in
            [context['sample']['request'], context['sample']['recall'], *([context['sample']['coverage']] if 'coverage' in context['sample'] else [])]},
        frozen=frozen, manifest_sha256=digest(package['manifest_path']), model_identity=identity,
        authorization=authorization, context_window=context_window,
        started_at=datetime.now(timezone.utc).isoformat(), stopped=dict(error_type='InterruptedRun', error='run did not reach completion'))
    save('run.json', meta)
    def check_version():
        if digest(package['manifest_path']) != meta['manifest_sha256'] or bindings(package) != frozen:
            raise ValueError('source/version/input changed during sample')
    try:
        base._run(context, invoke, save, check_version, context_window)
        check_version()
        meta['stopped'] = None
    except Exception as exc:
        meta['stopped'] = base.error_record(exc)
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        meta['artifact_hashes'] = {p.name: digest(p) for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
    return meta


def replay(folder, package=None):
    folder = Path(folder); package = package or load_package(); meta = base.read_json(folder / 'run.json')
    base._verify_artifacts(folder, meta)
    if (meta['version'] != VERSION or digest(package['manifest_path']) != meta['manifest_sha256']
            or bindings(package) != meta['frozen']):
        raise ValueError('replay version/input mismatch')
    context = prepare(package, meta['sample']['id'])
    if context['sample'] != meta['sample']: raise ValueError('replay sample mismatch')
    saved = {}
    def invoke(name, messages, schema):
        if base.read_json(folder / 'node-body.json') != base._body(messages, schema):
            raise ValueError('replay request/body mismatch')
        if (folder / 'node-provider-error.json').exists():
            raise base.RecordedProviderError(base.read_json(folder / 'node-provider-error.json'))
        call = base.read_json(folder / 'node-call.json')
        return AIMessage(content=call['response'], usage_metadata=call['usage'], response_metadata=call['response_metadata'] or {})
    stopped = None
    try: base._run(context, invoke, saved.__setitem__, lambda: None, meta['context_window'])
    except Exception as exc: stopped = base.error_record(exc)
    if stopped != meta['stopped']: raise ValueError('replay first error differs')
    for name, value in saved.items():
        original = base.read_json(folder / name)
        if name.endswith(('-call.json', '-provider-error.json')):
            original.pop('elapsed_seconds', None); value.pop('elapsed_seconds', None)
        if original != value: raise ValueError('replay artifact differs: ' + name)
    if set(meta['artifact_hashes']) - {'node-managed.json', 'node-provider-response.json'} != set(saved):
        raise ValueError('replay artifact set differs')
    return dict(result='PASS', raw_replays=int('node-call.json' in saved), stopped=stopped, upstream_injected=True, provider_calls=0)


def freeze_sources(destination, package=None):
    package = package or load_package(); destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, expected in source_paths().items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != expected: raise ValueError('frozen source differs')
    for version in ['kind_diagnostics_v1', 'kind_diagnostics_v2']:
        shutil.copytree(ROOT / 'evaluations/fixtures' / version, destination / 'evaluations/fixtures' / version)
    for name, expected in LINEAGE.items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != expected: raise ValueError('frozen lineage differs')
    external = destination / '_external'; external.mkdir(); (external / 'edd').mkdir()
    shutil.copyfile(base.LOOPCTL, external / 'loopctl.py')
    shutil.copyfile(base.LOOPCTL.resolve().parents[3] / 'edd/scripts/ledger.py', external / 'edd/ledger.py')
    base.write_json(destination / 'freeze.json', dict(version=VERSION, bindings=bindings(package),
        manifest_sha256=digest(package['manifest_path']), external_runtime='same .venv/uv.lock, external dependencies not vendored',
        replay_command='PYTHONPATH=<freeze>/src:<freeze> <repo>/.venv/bin/python -m evaluations.diagnostics.managed_node_diagnostics_v2 --replay <absolute-run>'))
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
        print(json.dumps(dict(execute=False, version=VERSION, candidate=base.contract.VERSION, upstream_injected=True,
            fixture_approval=package['manifest']['approval'], samples=[c['sample']['id'] for c in contexts],
            input_tokens={c['sample']['id']: c['input_tokens'] for c in contexts},
            manifest_sha256=digest(package['manifest_path']), bindings_match=bindings(package) == package['manifest']['bindings'], provider_calls=0), ensure_ascii=False)); return 0
    if not args.ticket: raise ValueError('execute requires active controller worker ticket')
    review = base.read_json(args.review) if args.review else None
    authorization = preflight(package, contexts, review)
    settings = base.AssistantSettings.from_env(ROOT / '.env')
    if settings.llm_provider != 'ollama': raise ValueError('only configured local Ollama provider is authorized')
    os.environ['EDD_LOCAL_ENDPOINT'] = settings.llm_base_url.rstrip('/') + '/api/chat'
    identity = base.verify_model_identity(settings.llm_base_url)
    batch = ROOT / base.TASK / '.local' / ('kind-isolation-v2-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    batch.mkdir(mode=0o700)
    base.write_json(batch / 'fixture-review.json', review)
    freeze_sources(batch / 'frozen', package)
    results = []
    for context in contexts:
        preflight(package, [context], review)
        sid = context['sample']['id']; folder = batch / sid
        # ManagedInvoke appends ':node' itself. The manifest fixes the full case.
        invoke = base.ManagedInvoke(folder, args.ticket, context['sample']['request_case'].removesuffix(':node'),
            lambda name, value, folder=folder: base.write_json(folder / name, value))
        meta = record_sample(folder, context, invoke, mode='MANAGED_LOCAL_ISOLATION', identity=identity, authorization=authorization)
        results.append(dict(sample=sid, stopped=meta['stopped'], folder=str(folder)))
        if (folder / 'node-provider-error.json').exists() or (meta['stopped'] and not (folder / 'node-call.json').exists()):
            break
    print(json.dumps(dict(batch=str(batch), results=results, independent_semantic_approval='PENDING'), ensure_ascii=False))
    return int(any(r['stopped'] for r in results) or len(results) != len(contexts))


if __name__ == '__main__':
    raise SystemExit(main())
