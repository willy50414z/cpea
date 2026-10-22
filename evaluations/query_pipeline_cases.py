"""Versioned evaluation inputs; approved oracles never enter natural services."""
from __future__ import annotations

import json
from pathlib import Path

from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.workflows.task_decomposition.validation import prepare_requests, validate_decomposition
from evaluations.query_pipeline_grading import content_hash

CASE_SCHEMA_VERSION = 'query-pipeline-cases-v1'


def case_sha256(case):
    return content_hash({k: v for k, v in case.items() if k not in {
        'case_sha256', 'review_state', 'reviewer', 'reviewed_at', 'reviewed_case_sha256',
        'reviewed_contract_fingerprint', 'output_reviews'}})


def approved_for(case, catalog):
    return (case.get('review_state') == 'approved' and bool(case.get('reviewer'))
        and bool(case.get('reviewed_at')) and case.get('reviewed_case_sha256') == case_sha256(case)
        and case.get('reviewed_contract_fingerprint') == catalog.fingerprint)


def load_pipeline_cases(path: Path, catalog):
    text = Path(path).read_text(encoding='utf-8')
    cases = json.loads(text) if Path(path).suffix == '.json' else [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(cases, list) or not cases or len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('cases require nonempty unique IDs')
    for case in cases:
        if (case.get('schema_version') != CASE_SCHEMA_VERSION or case.get('profile_id') != catalog.profile_id
                or case.get('contract_fingerprint') != catalog.fingerprint):
            raise ValueError('case schema/profile/contract drift')
        if case.get('case_sha256') != case_sha256(case):
            raise ValueError('case content drift')
        if not isinstance(case.get('request'), str) or not case['request'].strip() or len(case['request']) > 4000:
            raise ValueError('case request must be 1..4000 characters')
        if case.get('expected_stage_status') not in {'sql_ready', 'needs_clarification', 'needs_confirmation', 'unsupported', 'error'}:
            raise ValueError('invalid expected stage status')
        if case.get('review_state') not in {'pending', 'approved', 'rejected'}:
            raise ValueError('invalid review state')
        if not case.get('requirements') or not isinstance(case.get('required_capabilities'), list):
            raise ValueError('requirements and capabilities required')
        for value in case.get('approved_plans', []):
            draft = DecompositionDraft.model_validate(value)
            # Unsupported envelopes may intentionally contain unresolved inputs. Keep them for preflight.
            errors = validate_decomposition(draft, catalog)
            if errors and case['expected_stage_status'] == 'sql_ready':
                raise ValueError('positive oracle fails planning validation')
        if case['expected_stage_status'] == 'sql_ready' and not case.get('approved_plans'):
            raise ValueError('positive cases require a complete oracle')
        if case.get('review_state') == 'approved' and not approved_for(case, catalog):
            raise ValueError('case approval drift')
    return cases


def approved_planning(case, catalog):
    plans = case.get('approved_plans', [])
    if not plans:
        return DecompositionResponse(status=case.get('expected_planning_status', 'unsupported'),
                                     contract_fingerprint=catalog.fingerprint)
    draft = DecompositionDraft.model_validate(plans[0])
    # Preflight must also see unsupported-but-unserializable capabilities, rather than a fabricated ready request.
    try:
        prepared = prepare_requests(draft, catalog)
    except ValueError:
        prepared = []
    return DecompositionResponse(status=draft.status, draft=draft, prepared_requests=prepared,
                                 contract_fingerprint=catalog.fingerprint)
