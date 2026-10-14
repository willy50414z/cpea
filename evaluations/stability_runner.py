"""Recorded small-model probes and bounded repeat-run workflow evaluations."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate

from cpea.bootstrap import AssistantRuntime
from cpea.infrastructure.llm.factory import get_llm_config, bind_response_schema
from cpea.infrastructure.llm.parsing import parse_model
from cpea.domain.models import SchemaLink
from cpea.domain.models import QueryFilter, QueryPlan
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping
from cpea.workflows.text_to_sql.sql_generation import unmapped_request_literals
from evaluations.metadata import run_metadata
from evaluations.runners.query_reliability import QueryReliabilityCase, evaluate_cases


def append(path: Path, record: dict) -> None:
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')


def check_mapping(mapping, question, view, catalog, case=None):
    """Assess raw model semantics without retrieval, compilation, or DB calls."""
    failures = []
    supported = mapping.table is not None and not isinstance(mapping.table, list)
    expected_supported = case is None or (case.expected_supported and case.expected_view in {None, view})
    if case is not None and supported != expected_supported:
        failures.append('support_mismatch')
    if not supported:
        return failures if case is not None and not expected_supported else ['candidate_rejected']
    if mapping.table.view != view:
        failures.append('view_mismatch')
    if mapping.table.text and mapping.table.text != view and mapping.table.text not in question:
        failures.append('table_text_not_grounded')
    if not mapping.fields:
        failures.append('empty_fields')
    columns = catalog.columns(view)
    for item in [*mapping.fields, *mapping.criteria, *mapping.group, *mapping.order]:
        if not item.text or item.text not in question:
            failures.append('text_not_grounded')
        if item.column not in columns:
            failures.append('unknown_column')
    grouped = {item.column for item in mapping.group}
    for item in mapping.fields:
        error = catalog.validate_link(SchemaLink(
            fact_text=item.text, view=view, column=item.column,
            role='dimension' if item.column in grouped else 'metric',
            aggregation=item.aggregation), {view})
        if error:
            failures.append(error)
    for item in mapping.criteria:
        error = catalog.validate_link(SchemaLink(
            fact_text=item.text, view=view, column=item.column, role='filter',
            operator=item.operator, value=item.value), {view})
        if error:
            failures.append(error)
    missing = unmapped_request_literals(question, mapping, catalog, view)
    if missing:
        failures.append('unmapped request literals: ' + ', '.join(missing))
    if not failures:
        try:
            plan = QueryPlan(supported=True, source_views=[view],
                select_columns=list(dict.fromkeys(i.column for i in [*mapping.fields, *mapping.group])),
                group_by=list(dict.fromkeys(i.column for i in mapping.group)),
                order_by=[i.column for i in mapping.order],
                filters=[QueryFilter(column=i.column, operator=i.operator, value=i.value) for i in mapping.criteria],
                aggregations={i.column: i.aggregation for i in mapping.fields if i.aggregation})
            compile_single_view(plan, catalog, request=question)
        except ValueError as exc:
            failures.append(str(exc))
    if case is not None:
        selected = {item.column for item in mapping.fields}
        failures.extend('select_mismatch:' + c for c in case.expected_select_columns if c not in selected)
        for column, value in case.expected_filters.items():
            if not any(item.column == column and str(item.value) == value for item in mapping.criteria):
                failures.append('filter_mismatch:' + column)
        if not case.allow_extra_filters:
            failures.extend('unexpected_filter:' + item.column for item in mapping.criteria
                            if item.column not in case.expected_filters)
        for column, operator in case.expected_filter_operators.items():
            if not any(item.column == column and item.operator == operator for item in mapping.criteria):
                failures.append('filter_operator_mismatch:' + column)
        for column in case.forbidden_filters:
            if any(item.column == column for item in mapping.criteria):
                failures.append('forbidden_filter:' + column)
        if case.expected_group_by is not None and [i.column for i in mapping.group] != case.expected_group_by:
            failures.append('group_by_mismatch')
        if case.expected_order_by is not None and [i.column for i in mapping.order] != case.expected_order_by:
            failures.append('order_by_mismatch')
        for column, aggregation in case.expected_aggregations.items():
            if not any(i.column == column and i.aggregation == aggregation for i in mapping.fields):
                failures.append('aggregation_mismatch:' + column)
    return failures


class RecordedModel:
    """Reserve before invoking; SDK retries must be disabled by the caller."""
    def __init__(self, model, provider, model_name, output, ledger):
        self.model, self.provider, self.model_name = model, provider, model_name
        self.output, self.ledger = output, ledger
        self.context: dict[str, Any] = {}
        self.blocked: Exception | None = None
        self.fallback = None
        self.response_schema = None

    def with_response_schema(self, schema):
        self.response_schema = schema
        return self

    def invoke(self, messages):
        if self.blocked is not None:
            raise RuntimeError('provider paused after an API error; inspect the recorded error') from self.blocked
        # Lock the shared ledger across processes, including in-flight calls.
        with self.ledger.open('a+', encoding='utf-8') as stream:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            count = sum(json.loads(line)['provider'] == self.provider
                        for line in stream if line.strip())
            if self.provider in {'azure', 'gcp'} and count >= 500:
                if self.fallback is None:
                    raise RuntimeError('cloud_call_cap_reached: switch to ollama')
                append(self.output, {'event': 'provider_switch', 'from': self.provider,
                                     'to': 'ollama', 'reason': 'cloud_call_cap_reached'})
                self.model, self.model_name = self.fallback()
                self.provider = 'ollama'
            call_id = uuid4().hex
            stream.write(json.dumps({'call_id': call_id, 'provider': self.provider,
                                     'model': self.model_name,
                                     'created_at': datetime.now(timezone.utc).isoformat()}) + '\n')
            stream.flush()
        record = {'event': 'request', 'call_id': call_id, 'provider': self.provider,
                  'model': self.model_name, **self.context,
                  'messages': [{'role': m.type, 'content': m.content} for m in messages]}
        append(self.output, record)
        started = time.perf_counter()
        try:
            driver = self.model
            if self.provider == 'ollama' and self.response_schema is not None:
                driver = driver.bind(format=self.response_schema)
            raw = driver.invoke(messages)
            append(self.output, {'event': 'response', 'call_id': call_id,
                                'elapsed_seconds': time.perf_counter() - started,
                                'response': raw.model_dump(mode='json')})
            return raw
        except Exception as exc:
            self.blocked = exc
            append(self.output, {'event': 'error', 'call_id': call_id,
                                'elapsed_seconds': time.perf_counter() - started,
                                'error': f'{type(exc).__name__}: {exc}'})
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['mvp', 'workflow'])
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--provider', choices=['azure', 'gcp', 'ollama'], required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--ledger', default='artifacts/stability/cloud-calls.jsonl')
    parser.add_argument('--dataset', default='evaluations/datasets/query_reliability.jsonl')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--prompt-file')
    parser.add_argument('--view', help='Candidate for an isolated MVP probe')
    parser.add_argument('--question', help='Original request for an isolated MVP probe')
    parser.add_argument('--gcp-credentials', help='Explicit service-account ADC file')
    parser.add_argument('--ollama-model', default='gemma4:26b', help='Cloud-cap fallback model')
    parser.add_argument('--ollama-base-url', help='Local model endpoint; defaults to Ollama embedding endpoint')
    parser.add_argument('--native-schema', action='store_true', help='Probe cloud schema binding before adopting it')
    parser.add_argument('--plain-json', action='store_true', help='Probe Ollama JSON mode without grammar constraints')
    parser.add_argument('--retrieval-mode', choices=['lexical', 'vector'])
    parser.add_argument('--full-contract', action='store_true', help='Probe all approved schema constraints')
    parser.add_argument('--all-candidates', action='store_true', help='Probe joint candidate selection before changing the workflow')
    parser.add_argument('--feedback-file', help='Probe generic validation feedback without workflow changes')
    parser.add_argument('--reasoning', action=argparse.BooleanOptionalAction, default=None,
                        help='Override explicit Ollama thinking mode')
    parser.add_argument('--max-output-tokens', type=int, help='Probe a bounded reasoning/output budget')
    parser.add_argument('--constrain-names', action='store_true', help='Probe contract-derived name enums')
    parser.add_argument('--execute', action='store_true', help='Also run approved SQL on configured DB')
    args = parser.parse_args(argv)
    if args.runs < 3:
        parser.error('LLM stability evaluation requires at least 3 runs')
    if args.phase == 'mvp' and (not args.view or not args.question):
        parser.error('MVP requires view and question')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    ledger = Path(args.ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    base = AssistantRuntime.from_env(args.env_file)
    settings = replace(base.settings, llm_provider=args.provider, llm_model=args.model)
    if args.retrieval_mode:
        settings = replace(settings, retrieval_mode=args.retrieval_mode)
    if args.reasoning is not None:
        settings = replace(settings, llm_reasoning=args.reasoning)
    if args.max_output_tokens is not None:
        if args.max_output_tokens < 1:
            parser.error('max-output-tokens must be positive')
        settings = replace(settings, max_output_tokens=args.max_output_tokens)
    if args.provider == 'ollama':
        settings = replace(settings, llm_base_url=args.ollama_base_url or settings.embedding_base_url,
                           llm_api_key='not-needed', temperature=0.0)
    elif args.provider == 'gcp':
        from dotenv import dotenv_values
        values = dotenv_values(args.env_file, encoding='utf-8')
        if args.gcp_credentials:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path(args.gcp_credentials).resolve())
        settings = replace(settings, llm_api_key=os.environ.get('CPEA_GCP_LLM_API_KEY') or values.get('CPEA_GCP_LLM_API_KEY') or 'not-needed',
                           temperature=0.0)
    elif args.provider == 'azure':
        from dotenv import dotenv_values
        values = dotenv_values(args.env_file, encoding='utf-8', interpolate=False)
        if base.settings.llm_provider != 'azure':
            endpoint = os.environ.get('CPEA_AZURE_LLM_BASE_URL') or values.get('CPEA_AZURE_LLM_BASE_URL')
            key = os.environ.get('CPEA_AZURE_LLM_API_KEY') or values.get('CPEA_AZURE_LLM_API_KEY')
            if not endpoint or not key:
                parser.error('Azure evaluation requires its dedicated endpoint and key when switching providers')
            endpoint = endpoint.rstrip('/')
            if not endpoint.endswith('/openai/v1'):
                endpoint += '/openai/v1'
            settings = replace(settings, llm_base_url=endpoint, llm_api_key=key)
        settings = replace(settings, temperature=1.0 if args.model.startswith('gpt-') else 0.0)
    llm = get_llm_config(settings=settings)
    if hasattr(llm, 'max_retries'):
        llm.max_retries = 0
    # Bind before wrapping so isinstance-based provider dispatch still works.
    llm = bind_response_schema(llm, SQLClauseMapping)
    if args.plain_json and args.provider == 'ollama':
        llm = llm.bind(format='json')
    if args.native_schema and args.provider == 'gcp':
        llm = llm.bind(response_mime_type='application/json',
                       response_json_schema=SQLClauseMapping.model_json_schema())
    recorded = RecordedModel(llm, args.provider, args.model, output / 'calls.jsonl', ledger)
    def fallback():
        local = replace(base.settings, llm_provider='ollama', llm_model=args.ollama_model,
                        llm_base_url=args.ollama_base_url or base.settings.embedding_base_url,
                        llm_api_key='not-needed', temperature=0.0)
        return bind_response_schema(get_llm_config(settings=local), SQLClauseMapping), args.ollama_model
    recorded.fallback = fallback
    runtime = AssistantRuntime(settings, catalog=base.catalog, llm=recorded)
    cases = [QueryReliabilityCase.model_validate_json(line) for line in
             Path(args.dataset).read_text(encoding='utf-8').splitlines() if line.strip()]
    import cpea.workflows.text_to_sql.sql_generation as workflow
    prompt = Path(args.prompt_file).read_text(encoding='utf-8') if args.prompt_file else workflow.MATCH_PROMPT
    if len(prompt) > 2000:
        parser.error('MATCH_PROMPT exceeds 2000 characters')
    workflow.MATCH_PROMPT = prompt
    metadata = run_metadata(runtime, cases)
    metadata.update(phase=args.phase, prompt=prompt, prompt_chars=len(prompt),
                    prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
                    execute=args.execute, source_module=workflow.__file__,
                    native_schema=args.native_schema, plain_json=args.plain_json,
                    reasoning=settings.llm_reasoning,
                    runner_fingerprint=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'run.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    records = []
    if args.phase == 'mvp':
        definition = next(v for v in runtime.catalog.views() if v.name == args.view)
        contracts = ([workflow.candidate_schema(v) for v in runtime.catalog.views()]
                     if args.all_candidates else [workflow.candidate_schema(definition)])
        schema = {'candidates': contracts}
        if args.constrain_names:
            from cpea.infrastructure.llm.factory import response_schema_for
            constrained = response_schema_for(SQLClauseMapping,
                column_names={c for contract in contracts for c in contract['columns']},
                view_names={contract['view'] for contract in contracts})
            schema['response_schema'] = constrained
            recorded.with_response_schema(constrained)
        messages = ChatPromptTemplate.from_messages([
            ('system', prompt), ('human', '需求: {request} table定義: {schema_context}')
        ]).invoke({'request': args.question, 'schema_context': json.dumps(schema, ensure_ascii=False)}).to_messages()
        if args.feedback_file:
            from langchain_core.messages import HumanMessage
            messages.append(HumanMessage(content='前次輸出未通過檢查：' +
                Path(args.feedback_file).read_text(encoding='utf-8') +
                '\n請依需求原文與候選契約更正，只回傳完整 JSON，不新增需求。'))
        for repetition in range(1, args.runs + 1):
            recorded.context = {'question': args.question, 'repetition': repetition}
            try:
                raw = recorded.invoke(messages)
                mapping = parse_model(raw, SQLClauseMapping)
                case = next((c for c in cases if c.question == args.question), None)
                failures = check_mapping(mapping, args.question, args.view, runtime.catalog, case)
                record = {'run': repetition, 'parsed': True, 'passed': not failures,
                          'failure_reasons': failures, 'mapping': mapping.model_dump(mode='json')}
            except Exception as exc:
                record = {'run': repetition, 'parsed': False, 'passed': False,
                          'error': f'{type(exc).__name__}: {exc}'}
            records.append(record)
            append(output / 'results.jsonl', record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if recorded.blocked is not None:
                break  # Infrastructure/auth/rate errors are never retried here.
    else:
        service = runtime.generation_service()
        agent = runtime.execution_agent() if args.execute else None
        repetitions = {}

        class EvaluatedService:
            def generate(self, question):
                repetitions[question] = repetitions.get(question, 0) + 1
                recorded.context = {'question': question, 'repetition': repetitions[question]}
                result = service.generate(question)
                if agent and result.supported:
                    started = time.perf_counter()
                    try:
                        execution = agent.execute_generation(result, runtime.datasource_id, request=question)
                    except Exception as exc:
                        append(output / 'execution.jsonl', {'question': question, 'sql': result.sql,
                               'repetition': repetitions[question], 'passed': False,
                               'elapsed_seconds': time.perf_counter() - started,
                               'error_type': type(exc).__name__, 'error': str(exc)})
                        raise
                    append(output / 'execution.jsonl', {'question': question, 'sql': result.sql,
                           'repetition': repetitions[question], 'passed': True,
                           'elapsed_seconds': time.perf_counter() - started,
                           'columns': execution.columns, 'row_count': len(execution.rows),
                           'rows_truncated': execution.rows_truncated})
                    result = execution.generation
                return result

        def emit(record):
            record.update(provider=recorded.provider, model=recorded.model_name)
            append(output / 'results.jsonl', record)
            print(json.dumps({k: record.get(k) for k in ('question', 'run', 'passed', 'failure_reasons', 'rejection_stage')}, ensure_ascii=False), flush=True)

        records = evaluate_cases(cases, EvaluatedService(), runs=args.runs, max_failures=3, on_record=emit)
    summary = {'phase': args.phase, 'total': len(records),
               'passed': sum(r.get('passed', r.get('parsed', False)) for r in records),
               'stopped_early': len(records) < (args.runs if args.phase == 'mvp' else args.runs * len(cases))}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return int(summary['stopped_early'] or summary['passed'] != summary['total'])


if __name__ == '__main__':
    raise SystemExit(main())
