"""Immutable v2-content rebinding with a complete outer evidence guard."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from evaluations import managed_node_diagnostics as base

ROOT = base.ROOT
VERSION = 'managed-node-diagnostics-rebind-1'
CONTENT_VERSION = 'kind-isolation-v2-rebind-1'
AUTHOR_TICKET = '098d0ce2e31f4254905064d4fd34c97b'
CONTENT_AUTHOR_TICKET = '4810e837bb3e44d5a05d9392d9140e84'
DEFAULT_MANIFEST = ROOT / 'evaluations/fixtures/kind_diagnostics_rebound/manifest.json'
CONTENT_MANIFEST = dict(path='evaluations/fixtures/kind_diagnostics_v2/manifest.json',
    sha256='33cf44c84c10842adb60bfb7cbfbb269bac6dfa136c124a43159efabd27d543f')
ADDITIONAL_SOURCES = ('evaluations/diagnostics/managed_node_diagnostics_v2.py',
    'tests/diagnostics/test_managed_node_diagnostics_v2.py',
    'evaluations/diagnostics/managed_node_diagnostics_rebound.py',
    'tests/diagnostics/test_managed_node_diagnostics_rebound.py')
LINEAGE = {
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/controller-check-evidence.log': '6a7dee2df6decc78d70dd3a9fcef13555f24ec05ef34f4d611783f4084b4e866',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/receipt.json': '205a6e2f4706d373f98dddaf32db0f0ea942ea89ebb6acf99074c25fa8297a3b',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/recovery-plan.json': '3b895e7a9592786d6621df03e6dc1110ae0a507242b9b8410a1b647f224c6e4d',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/review.json.late.raw.log': '0200cc20e8aa288580c0a5036d4056a144555a272b6b4afe64da357734118d6b',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/review.json.original.raw.log': 'aaa8b740cc30fbd1b8670fa45ce5b68280dc073b9ee5e662dc43eeb68b903dfa',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/semantic-review.log.late.raw.log': '3b7c9f3b51626a0634405b8e2c14efbcf730b600138aa60b067e74aceffca4f0',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/semantic-review.log.original.raw.log': 'fa3e4654447f56bef7cffe64220195c4e2817ba20838d2c3b27eaf893a28eaaa',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11/v2-expected-lineage-rejection.log': '6fc6fad47c0566b8004271cfe185c75d9a051175875b0c305c6e65442e0d4642',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-10-12/review.json': 'fe3becdeb0bd71518980174f1ba70bb30500822d563f713422b4391d78cd5517',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-10-12/recovery-analysis.json': 'b10d3fdfa8765f5e88cddd8796d8abe74ed6c5fd08c09c36200a08fb41126b0f',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-audit-10-12/recovery-plan.json': '3b895e7a9592786d6621df03e6dc1110ae0a507242b9b8410a1b647f224c6e4d',
    'evaluations/fixtures/kind_diagnostics_v1/manifest.json': '1749d09913e0f5d5a1caab4a4ede1bf4fa80fee260bb4e257f1f705634d934be',
    'evaluations/fixtures/kind_diagnostics_v2/manifest.json': '33cf44c84c10842adb60bfb7cbfbb269bac6dfa136c124a43159efabd27d543f',
}
prepare, evaluate, digest = base.prepare, base.evaluate, base.digest


def load_package(manifest=DEFAULT_MANIFEST):
    path = Path(manifest).resolve()
    if path != DEFAULT_MANIFEST.resolve():
        raise ValueError('only the fixed rebound manifest is supported')
    if any(digest(ROOT / name) != value for name, value in LINEAGE.items()):
        raise ValueError('immutable content/lineage drift')
    content = base.read_json(ROOT / CONTENT_MANIFEST['path'])
    # Interpret the historical late hashes through immutable copies only.
    recovery = ROOT / 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-evidence-recovery-11'
    for name, expected in content['lineage'].items():
        historical = recovery / (Path(name).name + '.late.raw.log') if 'loop-worker-diagnostic-semantics/' in name else ROOT / name
        if digest(historical) != expected:
            raise ValueError('historical v2 lineage correspondence differs')
    data = base.read_json(path)
    expected = deepcopy(content)
    expected.update(version=CONTENT_VERSION, runner_version=VERSION, author_ticket=AUTHOR_TICKET,
        content_author_ticket=CONTENT_AUTHOR_TICKET, content_manifest=CONTENT_MANIFEST,
        fixture_root='evaluations/fixtures/kind_diagnostics_v2', lineage=LINEAGE,
        samples=[dict(s, request_case=CONTENT_VERSION + ':ISOLATION:' + s['id'] + ':node') for s in content['samples']],
        bindings=data.get('bindings'))
    if data != expected or not isinstance(data.get('bindings'), dict):
        raise ValueError('fixed rebound design differs')
    package = dict(manifest=data, manifest_path=path, root=ROOT / data['fixture_root'],
        oracle=base.read_json(ROOT / data['fixture_root'] / 'oracle.json'))
    fixtures = {p.relative_to(package['root']).as_posix(): digest(p)
        for p in sorted(package['root'].rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    if fixtures != content['bindings']['fixtures']:
        raise ValueError('immutable v2 content fixtures differ')
    return package


def source_paths():
    return dict(base.source_paths(), **{name: digest(ROOT / name) for name in ADDITIONAL_SOURCES})


def bindings(package):
    result = base.bindings(package)
    result.update(sources=source_paths(), lineage={name: digest(ROOT / name) for name in LINEAGE},
        content_manifest=CONTENT_MANIFEST,
        historical_fixtures={p.relative_to(ROOT).as_posix(): digest(p)
            for p in sorted((ROOT / 'evaluations/fixtures/kind_diagnostics_v1').rglob('*')) if p.is_file()})
    return result


def _roles(package, review, loop):
    roles = {}
    for role, ticket, node in [
        ('content_author', package['manifest']['content_author_ticket'], 'kind_diagnostic_fixture_v2_correction'),
        ('binding_author', package['manifest']['author_ticket'], 'kind_diagnostic_evidence_rebinding'),
        ('reviewer', review['ticket'], 'kind_diagnostic_fixture_semantics')]:
        item = loop['tickets'].get(ticket)
        matches = [r for r in loop['rounds'] if isinstance(item, dict) and r.get('round') == item.get('round')
            and r.get('node') == node and r.get('producer') == item.get('platform_id') and r.get('result') == 'PASS']
        if (not isinstance(item, dict) or item.get('role') != 'worker' or item.get('node') != node
                or item.get('closed') is not True or not item.get('platform_id')
                or type(item.get('round')) is not int or len(matches) != 1):
            raise ValueError('review lacks completed three-role provenance')
        roles[role] = dict(ticket=ticket, **item, completion=matches[0])
    if len({r['ticket'] for r in roles.values()}) != 3 or len({r['platform_id'] for r in roles.values()}) != 3:
        raise ValueError('review lacks distinct three-role provenance')
    return roles


def _context_guard(package, contexts):
    if not contexts or len({c['sample']['id'] for c in contexts}) != len(contexts):
        raise ValueError('empty or duplicate diagnostic contexts')
    for context in contexts:
        fresh = prepare(package, context['sample']['id'])
        if (context['package'] != package or context['sample'] != fresh['sample']
                or context['input_tokens'] >= 32768 or context['input_tokens'] != fresh['input_tokens']
                or context['schema_json'] != fresh['schema_json'] or context['body'] != fresh['body']
                or context['schema'].model_json_schema() != fresh['schema_json']
                or base._body(context['messages'], context['schema']) != context['body']
                or context['request'] != fresh['request'] or context['upstream'] != fresh['upstream']
                or context['recall'].model_dump() != fresh['recall'].model_dump()
                or context['catalog'].fingerprint != fresh['catalog'].fingerprint
                or [c.model_dump() for c in context['coverages']] != [c.model_dump() for c in fresh['coverages']]):
            raise ValueError('context/schema/body/upstream drift')


def _version_guard(package, frozen, manifest_sha256):
    fresh = load_package(package['manifest_path'])
    if (fresh != package or digest(package['manifest_path']) != manifest_sha256
            or bindings(package) != frozen or frozen != package['manifest']['bindings']):
        raise ValueError('complete outer source/version/input drift')


def _review_guard(package, review):
    if (not isinstance(review, dict) or review.get('schema_version') != 1 or review.get('verdict') != 'ACCEPT'
            or review.get('reviewer_role') != 'fresh_fixture_semantics' or not review.get('ticket')
            or review.get('author_ticket') != package['manifest']['author_ticket']
            or review.get('content_author_ticket') != package['manifest']['content_author_ticket']
            or review.get('manifest_sha256') != digest(package['manifest_path'])
            or review.get('bindings') != package['manifest']['bindings']):
        raise ValueError('execute requires complete fresh ACCEPT fixture review')


def preflight(package, contexts, review, *, task_path=None):
    _review_guard(package, review)
    _version_guard(package, package['manifest']['bindings'], digest(package['manifest_path']))
    _context_guard(package, contexts)
    path = Path(task_path) if task_path is not None else ROOT / base.TASK / 'task.md'
    loop = json.loads(path.read_text(encoding='utf-8').split('---', 2)[1])['plan']['edd_loop']
    return dict(result='PASS', manifest_sha256=digest(package['manifest_path']),
        bindings_sha256=base.json_digest(package['manifest']['bindings']), review_sha256=base.json_digest(review),
        roles=_roles(package, review, loop))


def _execution_guard(ticket, stage, *, task_path=None):
    path = Path(task_path) if task_path is not None else ROOT / base.TASK / 'task.md'
    loop = json.loads(path.read_text(encoding='utf-8').split('---', 2)[1])['plan']['edd_loop']
    item = loop['tickets'].get(ticket); active = loop.get('active') or {}
    node = 'natural_kind_' + stage + '_isolation'
    if (loop.get('status') != 'RUNNING' or loop.get('audit_due') or loop.get('needs_research')
            or not item or item.get('role') != 'worker' or item.get('node') != node
            or item.get('closed') is not False or not item.get('platform_id')
            or active.get('node') != node or item.get('round') != active.get('round')):
        raise ValueError('execute requires active stage worker and completed audit')


def receipt_path(folder):
    folder = Path(folder)
    return folder.parent / (folder.name + '.outer.json')


def _save_receipt(folder, receipt):
    path = receipt_path(folder)
    base.write_json(path, receipt)
    base.write_json(path.with_suffix('.sha256.json'), dict(path=path.name, sha256=digest(path)))


def _read_receipt(folder):
    path = receipt_path(folder)
    if base.read_json(path.with_suffix('.sha256.json')) != dict(path=path.name, sha256=digest(path)):
        raise ValueError('outer receipt digest mismatch')
    return base.read_json(path)


def _authorization(package, review, authorization, mode, context, task_path):
    if mode == 'OFFLINE_CONTROL' and review is None and authorization is None:
        return dict(mode=mode, independent_semantic_approval='PENDING',
            manifest_sha256=digest(package['manifest_path']), bindings_sha256=base.json_digest(bindings(package)),
            review_sha256=None, roles=dict(content_author=CONTENT_AUTHOR_TICKET, binding_author=AUTHOR_TICKET, reviewer=None))
    fresh = preflight(package, [context], review, task_path=task_path)
    if mode != 'MANAGED_LOCAL_ISOLATION' or authorization != fresh:
        raise ValueError('outer authorization mismatch')
    return fresh


def record_sample(folder, context, invoke, *, mode='OFFLINE_CONTROL', identity=None, authorization=None,
                  context_window=32768, review=None, task_path=None):
    folder = Path(folder)
    if (folder.exists() and any(folder.iterdir())) or receipt_path(folder).exists():
        raise ValueError('sample folder and outer receipt must be empty; preserve every first raw')
    package = context['package']; frozen = bindings(package); manifest_hash = digest(package['manifest_path'])
    _version_guard(package, frozen, manifest_hash); _context_guard(package, [context])
    auth = _authorization(package, review, authorization, mode, context, task_path)
    receipt = dict(version=VERSION, content_version=CONTENT_VERSION, engine_version=base.VERSION,
        sample_folder=folder.name, sample=context['sample'], mode=mode, bindings=frozen,
        manifest_sha256=manifest_hash, review=review, authorization=auth,
        status='INTERRUPTED', stopped=dict(error_type='InterruptedRun', error='outer run did not reach completion'),
        started_at=datetime.now(timezone.utc).isoformat(), inner_hashes=None)
    folder.parent.mkdir(parents=True, exist_ok=True)
    _save_receipt(folder, receipt)
    def guarded_invoke(*args):
        if _read_receipt(folder) != receipt:
            raise ValueError('outer receipt changed before HTTP')
        _version_guard(package, frozen, manifest_hash); _context_guard(package, [context])
        if _authorization(package, review, authorization, mode, context, task_path) != auth:
            raise ValueError('outer authorization changed before HTTP')
        return invoke(*args)
    try:
        inner = base.record_sample(folder, context, guarded_invoke, mode=mode, identity=identity,
            authorization=auth, context_window=context_window)
        # Inner saves returned raw before this independent outer recheck.
        if _read_receipt(folder) != receipt:
            raise ValueError('outer receipt changed after HTTP')
        _version_guard(package, frozen, manifest_hash); _context_guard(package, [context])
        if _authorization(package, review, authorization, mode, context, task_path) != auth:
            raise ValueError('outer authorization changed after HTTP')
        base._verify_artifacts(folder, inner)
        if inner['authorization'] != auth:
            raise ValueError('inner authorization mismatch')
        receipt.update(status='FAIL' if inner['stopped'] else 'PASS', stopped=inner['stopped'])
    except Exception as exc:
        receipt.update(status='FAIL', stopped=base.error_record(exc))
    receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
        inner_hashes={p.name: digest(p) for p in folder.iterdir() if p.is_file()} if folder.exists() else {})
    _save_receipt(folder, receipt)
    return receipt


def replay(folder, package=None):
    folder = Path(folder); package = package or load_package(); path = receipt_path(folder)
    receipt = _read_receipt(folder)
    if receipt['status'] == 'INTERRUPTED':
        raise ValueError('outer receipt interrupted; never promote inner result')
    if (receipt['version'] != VERSION or receipt['content_version'] != CONTENT_VERSION
            or receipt['engine_version'] != base.VERSION or receipt['sample_folder'] != folder.name
            or receipt['status'] not in ['PASS', 'FAIL']
            or (receipt['status'] == 'PASS') != (receipt['stopped'] is None)):
        raise ValueError('outer receipt identity/result mismatch')
    _version_guard(package, receipt['bindings'], receipt['manifest_sha256'])
    context = prepare(package, receipt['sample']['id'])
    if context['sample'] != receipt['sample']:
        raise ValueError('outer receipt sample mismatch')
    auth = receipt['authorization']; review = receipt['review']
    if receipt['mode'] == 'OFFLINE_CONTROL':
        expected = _authorization(package, None, None, 'OFFLINE_CONTROL', context, None)
        if review is not None or auth != expected:
            raise ValueError('outer receipt offline authorization mismatch')
    else:
        _review_guard(package, review)
        roles = auth['roles']
        loop = dict(tickets={r['ticket']: {k: v for k, v in r.items() if k not in ['ticket', 'completion']} for r in roles.values()},
            rounds=[r['completion'] for r in roles.values()])
        expected = dict(result='PASS', manifest_sha256=digest(package['manifest_path']),
            bindings_sha256=base.json_digest(receipt['bindings']), review_sha256=base.json_digest(review), roles=_roles(package, review, loop))
        if receipt['mode'] != 'MANAGED_LOCAL_ISOLATION' or auth != expected:
            raise ValueError('outer receipt managed authorization mismatch')
    if receipt['inner_hashes'] != {p.name: digest(p) for p in folder.iterdir() if p.is_file()}:
        raise ValueError('outer receipt inner artifact mismatch')
    inner_meta = base.read_json(folder / 'run.json')
    if inner_meta['authorization'] != auth:
        raise ValueError('outer/inner authorization mismatch')
    inner = base.replay(folder, package=package)
    if receipt['status'] == 'PASS' and inner['stopped'] is not None:
        raise ValueError('outer PASS conflicts with inner first error')
    return dict(result=receipt['status'], replay_verification='PASS', stopped=receipt['stopped'],
        inner=inner, outer_receipt_sha256=digest(path), provider_calls=0, independent_semantic_approval='PENDING')


def freeze_sources(destination, package=None):
    package = package or load_package(); destination = Path(destination); bound = bindings(package)
    _version_guard(package, bound, digest(package['manifest_path']))
    destination.mkdir(parents=True, exist_ok=False)
    names = {**bound['sources'], **bound['lineage'], **bound['historical_fixtures']}
    names.update({(package['root'] / name).relative_to(ROOT).as_posix(): value for name, value in bound['fixtures'].items()})
    names[DEFAULT_MANIFEST.relative_to(ROOT).as_posix()] = digest(package['manifest_path'])
    for name, expected in names.items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target) != expected:
            raise ValueError('frozen full source/fixture/lineage differs')
    external = destination / '_external'; (external / 'edd').mkdir(parents=True)
    for source, target in [(base.LOOPCTL, external / 'loopctl.py'),
            (base.LOOPCTL.resolve().parents[3] / 'edd/scripts/ledger.py', external / 'edd/ledger.py')]:
        shutil.copyfile(source, target)
        if digest(target) != bound['external_sources'][str(source)]:
            raise ValueError('frozen external import differs')
    base.write_json(destination / 'freeze.json', dict(version=VERSION, engine_version=base.VERSION, bindings=bound,
        manifest_sha256=digest(package['manifest_path']), files=names,
        external_runtime='same installed .venv and bound uv.lock; external absolute loopctl/ledger hashes rechecked',
        replay_command='PYTHONPATH=<freeze>/src:<freeze> <repo>/.venv/bin/python -m evaluations.diagnostics.managed_node_diagnostics_rebound --replay <absolute-sample-folder>'))
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
        result = replay(args.replay, package); print(json.dumps(result, ensure_ascii=False))
        return int(result['result'] != 'PASS')
    contexts = [prepare(package, s['id']) for s in package['manifest']['samples'] if s['stage'] == args.stage]
    if not args.execute:
        print(json.dumps(dict(execute=False, version=VERSION, engine_version=base.VERSION,
            fixture_approval=package['manifest']['approval'], samples=[c['sample']['id'] for c in contexts],
            input_tokens={c['sample']['id']: c['input_tokens'] for c in contexts},
            bindings_match=bindings(package) == package['manifest']['bindings'], provider_calls=0), ensure_ascii=False))
        return 0
    if not args.ticket: raise ValueError('execute requires active controller worker ticket')
    review = base.read_json(args.review) if args.review else None
    authorization = preflight(package, contexts, review)
    _execution_guard(args.ticket, args.stage)
    settings = base.AssistantSettings.from_env(ROOT / '.env')
    if settings.llm_provider != 'ollama': raise ValueError('only local Ollama is authorized')
    os.environ['EDD_LOCAL_ENDPOINT'] = settings.llm_base_url.rstrip('/') + '/api/chat'
    identity = base.verify_model_identity(settings.llm_base_url)
    batch = ROOT / base.TASK / '.local' / (CONTENT_VERSION + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    batch.mkdir(mode=0o700); base.write_json(batch / 'fixture-review.json', review)
    freeze_sources(batch / 'frozen', package); results = []
    for context in contexts:
        preflight(package, [context], review)
        _execution_guard(args.ticket, args.stage)
        sid = context['sample']['id']; folder = batch / sid
        invoke = base.ManagedInvoke(folder, args.ticket, context['sample']['request_case'].removesuffix(':node'),
            lambda name, value, folder=folder: base.write_json(folder / name, value))
        receipt = record_sample(folder, context, invoke, mode='MANAGED_LOCAL_ISOLATION', identity=identity,
            authorization=authorization, review=review)
        results.append(dict(sample=sid, status=receipt['status'], stopped=receipt['stopped'], folder=str(folder),
            outer_receipt=receipt_path(folder).name, outer_receipt_sha256=digest(receipt_path(folder))))
        base.write_json(batch / 'outer-receipts.json', results)
        # Content errors finish the remaining preplanned independent coverage
        # controls. Identity/version/authorization/transport errors stop the batch.
        if ((folder / 'node-provider-error.json').exists() or not (folder / 'node-call.json').exists()
                or receipt['stopped'] != base.read_json(folder / 'run.json')['stopped']):
            break
    print(json.dumps(dict(batch=str(batch), results=results, independent_semantic_approval='PENDING'), ensure_ascii=False))
    return int(any(r['status'] != 'PASS' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
