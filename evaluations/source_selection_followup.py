"""Request brief retrospective source justifications, without changing original plans."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field
from cpea.infrastructure.llm.context_budget import TiktokenCounter
from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_runner import azure_planning_settings
from evaluations.decision_summary_comparison import TASK, MODELS


BASE = TASK / '.local/decision-chain-20261020T153804Z-eea260'
QUESTION = '請針對上一份規劃中你選擇的銷售來源，提供簡短、可核對的選擇理由：哪些需求與View契約支持此選擇？v_sales_detail與v_product_monthly的適用差異為何？所選來源能否滿足指定線上通路條件？如有不足請明說。僅說明原選擇，不重做規劃或修改原輸出；不要求私有逐步思維鏈。'


class SourceSelectionReason(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    originally_selected_sales_view: str = Field(min_length=1, max_length=160)
    selection_reason: str = Field(min_length=1, max_length=800)
    contract_evidence: list[str] = Field(min_length=1, max_length=6)
    alternative_comparison: str = Field(min_length=1, max_length=800)
    fulfills_online_condition: bool
    limitation: str = Field(min_length=1, max_length=800)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def messages_for(model):
    original = read(BASE / (model + '-call.json'))
    context = json.loads(original['messages'][1]['content'])
    context['response_schema'] = SourceSelectionReason.model_json_schema()
    context['previous_model_response'] = json.loads(original['response'])
    context['followup_question'] = QUESTION
    return [SystemMessage(content='你正在對既有規劃作事後說明。依提供的需求、完整View契約與你的上一份輸出，填寫指定JSON schema，以繁體中文提供簡短的決策理由與契約依據。承認不滿足的條件，不虛構欄位。這不是原始內部推理紀錄，也不要產出新計畫。'),
            HumanMessage(content=json.dumps(context, ensure_ascii=False))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    baseline = read(BASE / 'run.json')
    for name, digest in baseline['artifact_hashes'].items():
        assert sha256((BASE / name).read_bytes()).hexdigest() == digest
    counter = TiktokenCounter('cl100k_base')
    token_counts = {model: counter.count_messages([(m.type, m.content) for m in messages_for(model)]) for model in MODELS}
    print(json.dumps({'execute': args.execute, 'input_tokens_estimated': token_counts, 'max_output': 1536, 'safety': 1024}, ensure_ascii=False), flush=True)
    if any(n + 1536 + 1024 > 16384 for n in token_counts.values()):
        raise ValueError('context budget exceeded')
    if not args.execute:
        return 0
    folder = TASK / '.local' / ('source-reasons-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)
    def dump(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)
    meta = {'models': list(MODELS), 'base_folder': str(BASE), 'calls': 0, 'completed': 0,
            'purpose': 'retrospective_source_justification', 'question': QUESTION,
            'temperature': 1, 'top_p': 1, 'seed': 42, 'max_output_tokens': 1536,
            'sdk_retries': 0, 'context_window': 16384, 'timeout_seconds': 300,
            'input_tokens_estimated': token_counts, 'stopped': None,
            'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'base_run_sha256': sha256((BASE / 'run.json').read_bytes()).hexdigest(),
            'started_at': datetime.now(timezone.utc).isoformat()}
    started = monotonic()
    dump('run.json', meta)
    try:
        for model in MODELS:
            if monotonic() - started > 600:
                meta['stopped'] = 'wall_budget'
                break
            settings = replace(azure_planning_settings(Path('.env'), model), max_output_tokens=1536,
                               context_safety_tokens=1024, request_timeout_seconds=300)
            llm = bind_response_schema(get_llm_config(settings=settings), SourceSelectionReason).bind(response_format={'type': 'json_object'})
            messages = messages_for(model)
            event = {'model': model, 'messages': [{'role': m.type, 'content': m.content} for m in messages]}
            dump(model + '-request.json', event)
            meta['calls'] += 1
            dump('run.json', meta)
            call_start = monotonic()
            try:
                raw = llm.invoke(messages)
            except Exception as exc:
                event.update(error_type=type(exc).__name__, error=str(exc))
                dump(model + '-provider-error.json', event)
                (folder / 'provider-error.txt').write_text(type(exc).__name__ + ': ' + str(exc), encoding='utf-8')
                (folder / 'provider-error.txt').chmod(0o600)
                meta['stopped'] = 'provider_error_no_retry'
                break
            event.update(response=raw.content, usage=getattr(raw, 'usage_metadata', None),
                         response_metadata=getattr(raw, 'response_metadata', None), elapsed_seconds=monotonic()-call_start)
            dump(model + '-call.json', event)
            result = {'model': model, 'reason': None, 'parse_error': None}
            try:
                result['reason'] = parse_model(raw, SourceSelectionReason).model_dump()
            except (ValueError, TypeError) as exc:
                result['parse_error'] = str(exc)
            dump(model + '-result.json', result)
            meta['completed'] += 1
            dump('run.json', meta)
            print(json.dumps({'model': model, 'parse_error': result['parse_error']}, ensure_ascii=False), flush=True)
    finally:
        meta.update(elapsed_seconds=monotonic()-started, finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        dump('run.json', meta)
        print(json.dumps({'folder': str(folder), 'calls': meta['calls'], 'completed': meta['completed'], 'stopped': meta['stopped']}, ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
