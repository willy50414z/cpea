"""Explicit, reviewed scripts for HILP evaluation; never guess a user's choice."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cpea.application.models.confirmation import ConfirmationRequest
from cpea.application.ports.term_mappings import TermMapping, normalize_term

Status = Literal['ready', 'needs_confirmation', 'unsupported', 'cancelled', 'error']


class ConfirmationStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['confirm', 'cancel']
    choices: dict[str, str] = Field(default_factory=dict)
    expected_status: Status
    expected_source: Literal['confirmed_this_request', 'reused_confirmation'] | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.action == 'cancel' and self.choices or self.action == 'confirm' and not self.choices:
            raise ValueError('confirmation script must contain explicit choices, or cancel without choices')
        return self


class HilpCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_kind: Literal['hilp']
    case_format_version: Literal[1] = 1
    case_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    profile_id: str
    contract_fingerprint: str = Field(min_length=64, max_length=64)
    question: str
    expected_initial_status: Status
    expected_columns: list[str] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)
    initial_mappings: list[TermMapping] = Field(default_factory=list)
    steps: list[ConfirmationStep] = Field(default_factory=list)
    verify_reuse: bool = False
    review_status: Literal['pending', 'approved', 'rejected'] = 'pending'
    reviewer: str | None = None
    reviewed_at: str | None = None
    reviewed_case_sha256: str | None = None
    reviewed_contract_fingerprint: str | None = None

    def content_sha256(self):
        payload = self.model_dump(mode='json', exclude={'review_status', 'reviewer', 'reviewed_at',
            'reviewed_case_sha256', 'reviewed_contract_fingerprint'})
        return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

    def approved_for(self, fingerprint):
        return (self.review_status == 'approved' and bool(self.reviewer and self.reviewed_at)
                and self.reviewed_case_sha256 == self.content_sha256()
                and self.contract_fingerprint == self.reviewed_contract_fingerprint == fingerprint)


def run_hilp_case(runtime, case):
    """Run in an isolated repository created by the evaluator, without DB work."""
    if case.initial_mappings:
        runtime.generation_service().workflow.repository.commit(case.initial_mappings, used=[], replacements={})
    initial = generation = runtime.generate(case.question)
    phases = [{'status': generation.status, 'expected_status': case.expected_initial_status}]
    failures = []
    if generation.status != case.expected_initial_status:
        failures.append('initial_status_mismatch')
    if generation.status == 'ready' and case.expected_initial_status != 'ready':
        failures.append('semantic_false_accept')
    if generation.status == 'needs_confirmation' and case.expected_initial_status == 'ready':
        failures.append('unnecessary_confirmation')
    if case.expected_terms and (not generation.clarification or
            {item.term for item in generation.clarification.items} != set(case.expected_terms)):
        failures.append('confirmation_terms_mismatch')
    for step in case.steps:
        if generation.status != 'needs_confirmation':
            failures.append('script_expected_confirmation')
            break
        clarification = generation.clarification
        decisions = []
        if step.action == 'confirm':
            supplied = {normalize_term(k): v for k, v in step.choices.items()}
            if supplied.keys() != {normalize_term(i.term) for i in clarification.items}:
                failures.append('script_terms_mismatch')
                break
            for item in clarification.items:
                option = next((o for o in item.options if o.column == supplied[normalize_term(item.term)]), None)
                if option is None:
                    failures.append('script_column_not_offered')
                    break
                decisions.append({'item_id': item.id, 'option_id': option.id})
            if len(decisions) != len(clarification.items):
                break
        generation = runtime.confirm(ConfirmationRequest(confirmation_id=clarification.confirmation_id,
            action=step.action, decisions=decisions if step.action == 'confirm' else None))
        phases.append({'status': generation.status, 'expected_status': step.expected_status})
        if generation.status != step.expected_status:
            failures.append('resume_status_mismatch')
        if step.expected_source and not any(r.source == step.expected_source for r in generation.term_mapping_reasoning):
            failures.append('reasoning_source_mismatch')
    if case.expected_columns and (not generation.query_plan or generation.query_plan.select_columns != case.expected_columns):
        failures.append('final_columns_mismatch')
    if case.verify_reuse:
        previous = generation
        generation = runtime.generate(case.question)
        phases.append({'status': generation.status, 'expected_status': 'ready'})
        if generation.status != 'ready' or not generation.term_mapping_reasoning or any(
                r.source != 'reused_confirmation' for r in generation.term_mapping_reasoning):
            failures.append('reuse_mismatch')
        if {r.mapping_id for r in previous.term_mapping_reasoning} != {r.mapping_id for r in generation.term_mapping_reasoning}:
            failures.append('reuse_mapping_id_mismatch')
    return generation, phases, failures
