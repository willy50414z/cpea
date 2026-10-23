"""Approved evaluator-only cases. Never pass an oracle dictionary to a worker."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from evaluations.decomposition_cases import approved_for, case_sha256, load_decomposition_cases


def model_input(case: dict) -> dict:
    """The only case-derived fields permitted at the planning boundary."""
    return {'request': case['request'], 'case_id': case['case_id']}


def load_wrenai_cases(path: Path, catalog) -> list[dict]:
    cases = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not cases or any(not isinstance(c, dict) or not isinstance(c.get('case_id'), str) or not c['case_id'].strip() for c in cases):
        raise ValueError('cases require nonempty IDs')
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('duplicate case ID')
    ready = []
    for case in cases:
        if case.get('profile_id') != catalog.profile_id or case.get('contract_fingerprint') != catalog.fingerprint:
            raise ValueError('case profile/contract fingerprint mismatch')
        if case.get('case_sha256') != case_sha256(case):
            raise ValueError('case content fingerprint mismatch')
        if not approved_for(case, catalog):
            raise ValueError('case oracle is not approved for this catalog')
        if not isinstance(case.get('request'), str) or not case['request'].strip():
            raise ValueError('case requires a request')
        if case.get('expected_status') not in {'ready', 'unsupported', 'needs_clarification', 'error'}:
            raise ValueError('invalid expected status')
        if case['expected_status'] == 'ready':
            if not case.get('expected_tasks') or not isinstance(case.get('expected_integration'), dict):
                raise ValueError('ready oracle requires tasks and integration')
            integration = case['expected_integration']
            if integration.get('null_policy') not in {'preserve_null', 'zero_fill'}:
                raise ValueError('ready oracle requires an explicit null policy')
            if len(case['expected_tasks']) > 1 and not integration.get('edges'):
                raise ValueError('multi-source oracle requires preserve/cardinality edges')
            ready.append(case)
        elif case.get('expected_tasks') or case.get('expected_integration'):
            raise ValueError('nonready oracle must not require ready payloads')
    if ready:
        # The established loader owns field/aggregation/alternative validation.
        with tempfile.TemporaryDirectory(prefix='wrenai-oracles-') as directory:
            subset = Path(directory) / 'ready.jsonl'
            subset.write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in ready), encoding='utf-8')
            subset.chmod(0o600)
            load_decomposition_cases(subset, catalog)
    return cases
