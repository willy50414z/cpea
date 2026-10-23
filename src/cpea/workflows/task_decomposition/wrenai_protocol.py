"""Versioned, bounded JSONL boundary. Public errors contain fixed codes only."""
from __future__ import annotations
import json
from pathlib import Path

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_QUEUE = 128
WORKER_ERROR_CODES = frozenset({
    'context_budget_exceeded','invalid_selection_empty','invalid_selection_table',
    'invalid_selection_columns','invalid_selection_unknown_column','index_locked',
    'index_not_ready','index_drift','index_content_mismatch','manifest_identity_mismatch',
    'completion_not_finished','invalid_model_response','no_schema_candidates',
    'transport_error','rate_limit','replay_input_drift','replay_exhausted','worker_error',
})
TERMINAL = frozenset({'result','error','cancelled','unknown_outcome'})


class WorkerError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def _invalid_constant(value):
    raise ValueError('invalid JSON constant')


def decode_event(raw: bytes, *, max_line_bytes=MAX_LINE_BYTES) -> dict:
    if len(raw)>max_line_bytes:
        raise WorkerError('protocol_limit_exceeded')
    try:
        event = json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_invalid_constant)
    except (ValueError, UnicodeError):
        raise WorkerError('invalid_protocol') from None
    if not isinstance(event,dict) or type(event.get('protocol_version')) is not int or event.get('protocol_version') != PROTOCOL_VERSION or event.get('type') not in {
        'handshake','accepted','running',*TERMINAL}:
        raise WorkerError('invalid_protocol')
    for key in ('request_id','run_id','case_id'):
        if key in event and event[key] is not None and not isinstance(event[key],str):
            raise WorkerError('invalid_protocol')
    return event


def encode_plan(payload: dict, *, max_payload_bytes=MAX_PAYLOAD_BYTES) -> bytes:
    if payload.get('type')=='plan' and set(payload)-{
        'protocol_version','type','request_id','run_id','case_id','request',
        'catalog_fingerprint','schema','response_schema'}:
        raise WorkerError('invalid_payload')
    try:
        raw = json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8') + b'\n'
    except (TypeError,ValueError):
        raise WorkerError('invalid_payload') from None
    if len(raw)>max_payload_bytes:
        raise WorkerError('protocol_limit_exceeded')
    return raw


def verify_handshake(event: dict, expected_metadata: dict, import_root: Path | str) -> None:
    if event.get('type') != 'handshake' or not expected_metadata.get('upstream_sha'):
        raise WorkerError('worker_metadata_mismatch')
    if any(event.get(key)!=value for key,value in expected_metadata.items()):
        raise WorkerError('worker_metadata_mismatch')
    sources = event.get('import_sources')
    if not isinstance(sources,dict) or not sources:
        raise WorkerError('worker_metadata_mismatch')
    root = Path(import_root).resolve()
    for path in sources.values():
        if not isinstance(path,str) or not Path(path).is_absolute() or not Path(path).resolve().is_relative_to(root):
            raise WorkerError('worker_metadata_mismatch')
