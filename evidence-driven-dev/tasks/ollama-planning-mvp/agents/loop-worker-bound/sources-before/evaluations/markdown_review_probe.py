"""One Markdown planner call followed by a separate DeepSeek evidence review."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator
from cpea.application.models.decomposition import DecisionChainDecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import load_decomposition_cases, case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.decision_chain_probe import finish_chained, fingerprint
from evaluations.decision_summary_comparison import TASK
from evaluations.planning_mvp import semantic_check

MODEL = 'DeepSeek-V4.1-Flash'
PROMPT_VERSION = 'v3-md-priority-review-1'
PROMPTS = Path(__file__).resolve().parent / 'prompts'


class EvidenceCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requirement: str = Field(min_length=1, max_length=400)
    decision_step_ids: list[int] = Field(max_length=6)
    task_ids: list[str] = Field(max_length=8)
    contract_references: list[str] = Field(min_length=1, max_length=4)
    plan_references: list[str] = Field(min_length=1, max_length=4)
    status: Literal['supported', 'missing', 'contradicted', 'uncertain']
    missing_evidence: str = Field(max_length=600)


class EvidenceFinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    severity: Literal['blocking', 'advisory']
    requirement: str = Field(min_length=1, max_length=400)
    decision_step_ids: list[int] = Field(max_length=6)
    task_ids: list[str] = Field(max_length=8)
    plan_path: str = Field(min_length=1, max_length=200)
    observation: str = Field(min_length=1, max_length=600)
    required_evidence: str = Field(min_length=1, max_length=600)


class EvidenceReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['approve', 'reject', 'insufficient_evidence']
    checks: list[EvidenceCheck] = Field(min_length=1, max_length=16)
    findings: list[EvidenceFinding] = Field(max_length=12)
    summary: str = Field(min_length=1, max_length=800)

    @model_validator(mode='after')
    def approval_requires_supported_checks(self):
        if self.verdict == 'approve' and (
            any(check.status != 'supported' for check in self.checks)
            or any(f.severity == 'blocking' for f in self.findings)
        ):
            raise ValueError('approve cannot contain missing evidence or blocking findings')
        return self


def validate_review_references(review, draft):
    task_ids = {task.task_id for task in draft.tasks}
    step_ids = {record.step_id for record in draft.decision_chain}
    for item in [*review.checks, *review.findings]:
        if not set(item.task_ids) <= task_ids or not set(item.decision_step_ids) <= step_ids:
            raise ValueError('review references unknown task or decision step')
    return review


def planner_messages(request, catalog):
    return [SystemMessage(content=(PROMPTS / 'coverage_first_planner.md').read_text(encoding='utf-8')),
            HumanMessage(content=json.dumps({'request': request,
                'views': [{'view': v.name, **v.policy} for v in catalog.views()],
                'response_schema': DecisionChainDecompositionDraft.model_json_schema()}, ensure_ascii=False))]


def reviewer_messages(request, catalog, planner_output, prepared_requests):
    return [SystemMessage(content=(PROMPTS / 'evidence_reviewer.md').read_text(encoding='utf-8')),
            HumanMessage(content=json.dumps({'request': request,
                'views': [{'view': v.name, **v.policy} for v in catalog.views()],
                'planner_output': planner_output, 'prepared_requests': prepared_requests,
                'response_schema': EvidenceReview.model_json_schema()}, ensure_ascii=False))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    catalog = SchemaCatalog(Path('projects/retail'))
    case = next(c for c in load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'), catalog) if c['case_id'] == 'cross-view-11')
    approved = json.loads((TASK / 'agents/oracle-audit/review-manifest.json').read_text(encoding='utf-8'))
    assert approved['catalog_fingerprint'] == catalog.fingerprint
    assert next(c for c in approved['cases'] if c['case_id'] == case['case_id'])['case_sha256'] == case_sha256(case)
    frozen = fingerprint(catalog, case)
    prompt_hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in PROMPTS.glob('*.md')}
    schema_hashes = {cls.__name__: sha256(json.dumps(cls.model_json_schema(), sort_keys=True).encode()).hexdigest()
                     for cls in (DecisionChainDecompositionDraft, EvidenceReview)}
    counter = TiktokenCounter('cl100k_base')
    def budget(messages):
        tokens = counter.count_messages([(m.type, m.content) for m in messages])
        if tokens + 4096 + 1024 > 16384:
            raise ValueError('context budget exceeded before provider construction')
        return tokens
    planner_input = planner_messages(case['request'], catalog)
    tokens = budget(planner_input)
    print(json.dumps({'execute': args.execute, 'model': MODEL, 'calls_limit': 2,
                      'planner_input_tokens_estimated': tokens, 'reviewer_budget': 'checked after planner output',
                      'max_output_tokens': 4096, 'safety': 1024}, ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    folder = TASK / '.local' / ('markdown-review-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)
    def dump(name, value):
        p = folder / name
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        p.chmod(0o600)
    meta = {'model': MODEL, 'case_id': case['case_id'], 'prompt_version': PROMPT_VERSION,
            'calls': 0, 'completed': 0, 'stopped': None, 'sdk_retries': 0, 'temperature': 1, 'top_p': 1,
            'seed': 42, 'max_output_tokens': 4096, 'context_window': 16384, 'safety': 1024,
            'timeout_seconds': 300, 'wall_budget_seconds': 900, 'input_tokens_estimated': {'planner': tokens},
            'frozen': frozen, 'prompt_hashes': prompt_hashes, 'schema_hashes': schema_hashes,
            'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'started_at': datetime.now(timezone.utc).isoformat()}
    start = monotonic()
    dump('run.json', meta)
    draft = None
    response = None
    original_output = None
    try:
        for phase, schema in [('planner', DecisionChainDecompositionDraft), ('reviewer', EvidenceReview)]:
            if 900 - (monotonic()-start) < 300:
                meta['stopped'] = 'wall_budget'
                break
            assert fingerprint(catalog, case) == frozen
            assert prompt_hashes == {p.name: sha256(p.read_bytes()).hexdigest() for p in PROMPTS.glob('*.md')}
            messages = planner_input if phase == 'planner' else reviewer_messages(
                case['request'], catalog, original_output, [p.model_dump() for p in response.prepared_requests])
            meta['input_tokens_estimated'][phase] = budget(messages)
            settings = replace(azure_planning_settings(Path('.env'), MODEL), max_output_tokens=4096,
                               context_safety_tokens=1024, request_timeout_seconds=300)
            # Construct a fresh client: the reviewer has no planner chat history or oracle feedback.
            llm = bind_response_schema(get_llm_config(settings=settings), schema).bind(response_format={'type': 'json_object'})
            event = {'phase': phase, 'model': MODEL, 'messages': [{'role': m.type, 'content': m.content} for m in messages]}
            dump(phase + '-request.json', event)
            meta['calls'] += 1
            dump('run.json', meta)
            call_start = monotonic()
            try:
                raw = llm.invoke(messages)
            except Exception as exc:
                event.update(error_type=type(exc).__name__, error=str(exc))
                dump(phase + '-provider-error.json', event)
                error = folder / 'provider-error.txt'
                error.write_text(type(exc).__name__ + ': ' + str(exc), encoding='utf-8')
                error.chmod(0o600)
                meta['stopped'] = 'provider_error_no_retry'
                break
            event.update(response=raw.content, usage=getattr(raw, 'usage_metadata', None),
                         response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-call_start)
            dump(phase + '-call.json', event)
            result = {'phase': phase, 'parse_error': None}
            try:
                parsed = parse_model(raw, schema)
                if phase == 'planner':
                    original_output = json.loads(raw.content)
                    draft = parsed
                    response = finish_chained(draft, catalog)
                    result.update(response=response.model_dump(), score=grade_decomposition(case, response, catalog),
                                  diagnostic=semantic_check(case, response, catalog))
                else:
                    result['review'] = validate_review_references(parsed, draft).model_dump()
            except (ValueError, TypeError, KeyError) as exc:
                result['parse_error'] = str(exc)
                meta['stopped'] = 'parse_error_no_retry'
            dump(phase + '-result.json', result)
            meta['completed'] += 1
            dump('run.json', meta)
            print(json.dumps({'phase': phase, 'parse_error': result['parse_error'],
                              'status': result.get('response', {}).get('status'),
                              'verdict': result.get('review', {}).get('verdict')}, ensure_ascii=False), flush=True)
            if meta['stopped']:
                break
    finally:
        meta.update(elapsed_seconds=monotonic()-start, finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        dump('run.json', meta)
        print(json.dumps({'folder': str(folder), 'calls': meta['calls'], 'completed': meta['completed'], 'stopped': meta['stopped']}, ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
