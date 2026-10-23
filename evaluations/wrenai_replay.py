"""Private recorded artifacts: regrade locally or rerun the isolated native graph."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.workflows.task_decomposition.validation import prepare_requests, validate_decomposition
from evaluations.wrenai_oracles import grade_wrenai_run


IDENTITY_KEYS = ('upstream_sha', 'patch_sha', 'lock_sha256', 'python_version', 'model',
                 'embedding_model', 'tokenizer', 'prompt_sha256', 'schema_sha256',
                 'input_sha256', 'catalog_fingerprint', 'index_identity', 'configuration_sha256')


def _fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _read(root, name):
    target = root / name
    if not isinstance(name, str) or Path(name).name != name or target.is_symlink():
        raise ValueError('unsafe_artifact_reference')
    target.chmod(0o600)
    return json.loads(target.read_text(encoding='utf-8'))


def _write(root, name, value):
    target = root / name
    if target.is_symlink():
        raise ValueError('unsafe_artifact_reference')
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _artifacts(run_dir):
    root = Path(run_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid_run_directory')
    root = root.resolve()
    root.chmod(0o700)
    metadata = _read(root, 'runtime.json')
    payload = _read(root, 'input.json')
    if not isinstance(payload, dict) or set(payload) - {
        'protocol_version', 'type', 'request_id', 'run_id', 'case_id', 'request',
        'catalog_fingerprint', 'schema', 'response_schema'}:
        raise ValueError('invalid_recorded_model_input')
    ledger = _read(root, 'ledger.json')
    identity = metadata.get('identity', {})
    if any(identity.get(key) is None for key in IDENTITY_KEYS):
        raise ValueError('incomplete_recorded_identity')
    if identity['input_sha256'] != _fingerprint(payload):
        raise ValueError('input_identity_mismatch')
    if identity['schema_sha256'] != _fingerprint(payload['response_schema']):
        raise ValueError('schema_identity_mismatch')
    if identity['catalog_fingerprint'] != payload.get('catalog_fingerprint'):
        raise ValueError('catalog_identity_mismatch')
    names = ledger.get('calls')
    if not isinstance(names, list) or len(set(names)) != len(names):
        raise ValueError('invalid_call_ledger')
    if set(names) != {path.name for path in root.glob('call-*.json')}:
        raise ValueError('incomplete_call_ledger')
    calls = [_read(root, name) for name in names]
    for call in calls:
        if call.get('attempt') != 1 or any(key not in call for key in ('run_id', 'case_id', 'node_id', 'call_id', 'batch_id')):
            raise ValueError('invalid_attempt_record')
        if call.get('request_fingerprint') != _fingerprint(call.get('request')):
            raise ValueError('transport_request_identity_mismatch')
        if any(key in payload and call.get(key) != payload[key] for key in ('run_id', 'case_id')):
            raise ValueError('transport_run_identity_mismatch')
    return root, metadata, payload, calls


def _response(recorded, catalog):
    if 'response' in recorded:
        return recorded
    if 'contract_fingerprint' in recorded:
        return {'response': recorded}
    draft = DecompositionDraft.model_validate(recorded['draft'])
    errors = validate_decomposition(draft, catalog) if draft.status == 'ready' else []
    status = 'error' if errors else draft.status
    response = DecompositionResponse(
        status=status, code='invalid_plan' if errors else None, draft=draft,
        prepared_requests=prepare_requests(draft, catalog) if status == 'ready' else [],
        validation_errors=errors, contract_fingerprint=catalog.fingerprint,
        context_tokens=recorded.get('context_tokens', 0), token_counter=recorded.get('token_counter', ''))
    return {'response': response.model_dump(), 'nodes': recorded.get('nodes', {})}


def _native_nodes(root, payload):
    nodes = {}
    if (root / 'intent.json').exists():
        nodes['intent'] = _read(root, 'intent.json')
    mapping = payload.get('schema', {}).get('model_to_view', {})
    retrieval = {}
    if (root / 'retrieval_schema-raw.json').exists():
        raw = _read(root, 'retrieval_schema-raw.json')
        selected = {}
        for row in raw.get('results', []):
            view = mapping.get(row['table_name'], row['table_name'])
            if view in selected:
                raise ValueError('duplicate_recorded_selection')
            selected[view] = row['table_contents']['columns']
        retrieval['raw_selection'] = selected
    if (root / 'retrieval-rendered.json').exists():
        rendered = _read(root, 'retrieval-rendered.json')
        selected = {}
        for row in rendered.get('retrieval_results', []):
            view = mapping.get(row['table_name'], row['table_name'])
            if view in selected:
                raise ValueError('duplicate_rendered_selection')
            # Parse only the pinned renderer's four adapter types. Do not derive
            # rendered columns from the raw selection (that would hide drift).
            ddl = re.sub(r'/\*.*?\*/|--[^\n]*', '', row['table_ddl'], flags=re.DOTALL)
            selected[view] = re.findall(r'^\s*"?([A-Za-z_][A-Za-z0-9_]*)"?\s+(?:NUMERIC|VARCHAR|DATE|BOOLEAN)\b', ddl, re.MULTILINE)
        retrieval['rendered_columns'] = selected
    if retrieval:
        nodes['retrieval'] = retrieval
    return nodes


def regrade(run_dir: Path, case: dict, catalog) -> dict:
    root, metadata, payload, calls = _artifacts(run_dir)
    if payload.get('case_id') != case['case_id'] or payload.get('catalog_fingerprint') != catalog.fingerprint:
        raise ValueError('case_or_catalog_identity_mismatch')
    if payload.get('request') != case['request']:
        raise ValueError('case_request_identity_mismatch')
    run = _response(_read(root, 'response.json'), catalog)
    run['nodes'] = {**run.get('nodes', {}), **_native_nodes(root, payload)}
    score = grade_wrenai_run(case, run, catalog)
    spends = [call.get('spend', call.get('money', {})) for call in calls]
    complete = all(s.get('status') in {'known', 'complete'} and isinstance(s.get('amount'), (int, float)) for s in spends)
    currencies = {s.get('currency') for s in spends}
    complete = complete and len(currencies) <= 1 and all(c.get('status') == 'response' for c in calls)
    score.update(cost_complete=complete, spend=sum(s['amount'] for s in spends) if complete else None,
                 calls=len(calls), fixture_source=metadata.get('fixture_source', 'unknown'))
    _write(root, 'regrade.json', score)
    return score


def replay(run_dir: Path, *, runtime_identity: dict, allow_drift: bool = False) -> dict:
    root, metadata, payload, calls = _artifacts(run_dir)
    if any(runtime_identity.get(key) is None for key in IDENTITY_KEYS):
        raise ValueError('incomplete_runtime_identity')
    drift = [key for key in IDENTITY_KEYS if metadata['identity'][key] != runtime_identity[key]]
    if drift and not allow_drift:
        raise ValueError('runtime_identity_mismatch:' + ','.join(drift))
    if any(c.get('status') != 'response' or c.get('raw_response') is None for c in calls):
        raise ValueError('replay_requires_complete_transport_responses')
    repo = Path(__file__).resolve().parents[1]
    runtime = Path(runtime_identity.get('runtime_root', repo / 'integrations/wrenai/.runtime')).resolve()
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(repo / 'integrations/wrenai')
    environment.update(LANGFUSE_ENABLED='false', HAYSTACK_TELEMETRY_ENABLED='false',
                       LITELLM_LOCAL_MODEL_COST_MAP='true')
    command = [str(runtime / 'env/bin/python'), '-m', 'native_worker.replay', str(root)]
    if allow_drift:
        command.append('--allow-drift')
    process = subprocess.run(command, cwd=runtime / 'upstream/wren-ai-service', env=environment,
                             text=True, encoding='utf-8', capture_output=True, timeout=180)
    _write(root, 'replay-process.json', {'returncode': process.returncode, 'stderr': process.stderr, 'stdout': process.stdout})
    if process.returncode:
        raise RuntimeError('native_replay_failed')
    result = json.loads(process.stdout)
    if not isinstance(result, dict) or 'draft' not in result:
        raise ValueError('invalid_native_replay_result')
    result.update(identity_drift=drift, exact_reproduction=not drift and not allow_drift,
                  drift_allowed=allow_drift,
                  fixture_source=metadata.get('fixture_source', 'unknown'), replay_mode='native_graph')
    _write(root, 'replay-result.json', result)
    return result
