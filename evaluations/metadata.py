"""Non-secret run identity. Evaluation outputs are private artifacts, not an audit store."""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
import cpea

def run_metadata(runtime, cases, *, kind='real-model'):
    values = asdict(runtime.settings)
    keys = ['llm_provider', 'llm_model', 'llm_reasoning', 'temperature', 'top_p', 'seed', 'context_window',
            'max_output_tokens', 'context_safety_tokens', 'request_timeout_seconds',
            'embedding_provider', 'embedding_model', 'retrieval_mode', 'retrieval_k',
            'reranker_enabled', 'reranker_provider', 'reranker_model', 'rerank_top_k',
            'history_token_budget', 'history_recent_turns', 'max_rows', 'sql_generation_mode',
            'token_count_encoding', 'gcp_project', 'gcp_location']
    settings = {key: values[key] for key in keys}
    canonical = [case.model_dump() if hasattr(case, 'model_dump') else case for case in cases]
    digest = sha256()
    package = Path(cpea.__file__).parent
    for file in sorted(package.rglob('*.py')):
        digest.update(file.relative_to(package).as_posix().encode() + b'\0' + file.read_bytes())
    return {'run_id': uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat(),
            'kind': kind, 'product_version': cpea.__version__, 'source_fingerprint': digest.hexdigest(),
            'model': runtime.settings.llm_model, 'provider': runtime.settings.llm_provider,
            'settings': settings, 'settings_fingerprint': sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
            'profile_id': runtime.catalog.profile_id, 'contract_version': runtime.catalog.contract_version,
            'contract_fingerprint': runtime.catalog.fingerprint,
            'dataset_fingerprint': sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}

def default_output(metadata, label):
    return Path('artifacts/evaluations') / metadata['run_id'] / f'{label}.jsonl'

def write_jsonl(path, records):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as output:
        for record in records:
            value = record.model_dump(mode='json') if hasattr(record, 'model_dump') else record
            output.write(json.dumps(value, ensure_ascii=False, default=str) + '\n')
