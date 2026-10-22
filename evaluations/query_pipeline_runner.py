"""Isolated three-mode evaluation and offline regrading; never execute SQL."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.application.models.query import SQLGenerationResponse
from cpea.application.models.query_pipeline import QueryPipelineResponse
from cpea.application.ports.term_mappings import MappingScope
from cpea.application.services.query_pipeline import QueryPipelineService
from cpea.application.services.sql_generation import SQLGenerationService
from cpea.application.services.task_decomposition import TaskDecompositionService
from cpea.config.database import DatabaseSettings, SQLServerSettings
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.factory import get_llm_config
from cpea.infrastructure.terms_mapping import JsonTermMappingRepository
from cpea.workflows.query_pipeline.validation import validate_task_sql
from cpea.application.models.query_pipeline import TaskSQLInput
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT, DECOMPOSITION_PROMPT_VERSION
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from evaluations.metadata import git_workspace
from evaluations.query_pipeline_cases import approved_for, approved_planning, load_pipeline_cases
from evaluations.query_pipeline_grading import GRADER_VERSION, content_hash, grade_pipeline_case, summarize_pipeline


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def _update(path, value):
    with path.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def _new_output(root):
    output = Path(root) / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output / 'private').mkdir(mode=0o700)
    return output


def _source_hash(paths):
    root = Path(__file__).resolve().parents[1]
    return content_hash([(p.relative_to(root).as_posix(), sha256(p.read_bytes()).hexdigest()) for p in sorted(paths)])


def _versions(settings):
    package = Path(__file__).resolve().parents[1] / 'src/cpea'
    prompt = load_match_prompt()
    safe_keys = ('llm_provider', 'llm_model', 'temperature', 'top_p', 'seed', 'llm_reasoning',
        'context_window', 'max_output_tokens', 'context_safety_tokens', 'request_timeout_seconds',
        'max_rows', 'retrieval_mode', 'retrieval_k', 'reranker_enabled', 'token_count_encoding')
    safe = {key: getattr(settings, key) for key in safe_keys}
    common = list(package.rglob('*.py')) + list((package / 'workflows/text_to_sql/prompts').rglob('*.txt'))
    return {'settings': safe, 'dialect': settings.database_settings.resolved_dialect,
        'planning': {'prompt_version': DECOMPOSITION_PROMPT_VERSION,
            'prompt_sha256': sha256(DECOMPOSITION_PROMPT.encode('utf-8')).hexdigest(),
            'schema_sha256': content_hash(DecompositionDraft.model_json_schema()),
            'source_sha256': _source_hash(common + list((package / 'workflows/task_decomposition').glob('*.py')))},
        'sql': {'prompt_version': prompt.version,
            'prompt_sha256': content_hash([prompt.system_sha256, prompt.human_sha256]),
            'schema_sha256': content_hash([prompt.response_model.model_json_schema(), SQLGenerationResponse.model_json_schema()]),
            'source_sha256': _source_hash(common + list((package / 'workflows/text_to_sql').rglob('*.py'))
                                        + list((package / 'workflows/text_to_sql/prompts').rglob('*.txt')))},
        'pipeline_sha256': _source_hash(list((package / 'workflows/query_pipeline').glob('*.py'))),
        'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'grader_sha256': sha256(Path(__file__).with_name('query_pipeline_grading.py').read_bytes()).hexdigest()}


def _metadata(profile, cases_path, planner_settings, sql_settings, mode, runs, exploratory, kind):
    catalog = SchemaCatalog(profile)
    repo = git_workspace(profile)
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, capture_output=True, check=True).stdout
    planner, sql = _versions(planner_settings), _versions(sql_settings)
    return {'schema_version': 'query-pipeline-run-v1', 'mode': mode, 'kind': kind, 'runs': runs,
        'input_origin': {'planning': 'original_request', 'sql': 'approved_tasks', 'integrated': 'natural_planning'}[mode],
        'exploratory': exploratory, 'started_at': datetime.now(timezone.utc).isoformat(),
        'head': git('rev-parse', 'HEAD').decode('utf-8').strip(),
        'dirty_paths': git('status', '--porcelain').decode('utf-8').splitlines(),
        'dirty_diff_sha256': sha256(git('diff', 'HEAD', '--binary')).hexdigest(),
        'untracked_source_sha256': _source_hash(list((repo / 'src/cpea').rglob('*.py')) + list((repo / 'evaluations').glob('query_pipeline_*.py'))),
        'catalog_fingerprint': catalog.fingerprint,
        'casefile_sha256': sha256(Path(cases_path).read_bytes()).hexdigest(),
        'nodes': {'planning': {**planner['planning'], 'settings': planner['settings']},
                  'sql': {**sql['sql'], 'settings': sql['settings']}},
        'dialect': sql['dialect'], 'pipeline_sha256': sql['pipeline_sha256'],
        'runner_sha256': sql['runner_sha256'],
        'grader_version': GRADER_VERSION, 'grader_sha256': sql['grader_sha256'],
        'model_versions': {'planning': planner_settings.llm_model, 'sql': sql_settings.llm_model},
        'model_version_verified': False, 'model_calls': 0, 'sdk_retries': 0,
        'input_tokens': None, 'output_tokens': None, 'token_counter': 'provider_usage_or_unknown'}


class _RecordedModel:
    """Preserve model binding while recording private evidence, including first provider error."""
    def __init__(self, model, stage, journal):
        self.model, self.stage, self.journal = model, stage, journal

    def bind(self, **kwargs):
        return _RecordedModel(self.model.bind(**kwargs), self.stage, self.journal)

    def with_response_schema(self, schema):
        from langchain_ollama import ChatOllama
        if hasattr(self.model, 'with_response_schema'):
            model = self.model.with_response_schema(schema)
        elif isinstance(self.model, ChatOllama):
            model = self.model.bind(format=schema)
        else:
            model = self.model
        return _RecordedModel(model, self.stage, self.journal)

    def invoke(self, messages):
        if self.journal['stopped']:
            raise RuntimeError('provider already stopped; no retry')
        started = perf_counter()
        event = {'stage': self.stage, 'messages': [m.model_dump(mode='json') if hasattr(m, 'model_dump') else str(m) for m in messages]}
        try:
            result = self.model.invoke(messages)
            event.update(response=getattr(result, 'content', str(result)), usage=getattr(result, 'usage_metadata', None))
            return result
        except Exception as exc:
            event.update(error_type=type(exc).__name__, error=str(exc))
            self.journal['stopped'] = True
            self.journal['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            event['elapsed_ms'] = (perf_counter() - started) * 1000
            self.journal['calls'].append(event)


class _RecordedGenerator:
    def __init__(self, generator, journal):
        self.generator, self.journal = generator, journal
        self.workflow = getattr(generator, 'workflow', None)

    def generate(self, *args, **kwargs):
        try:
            return self.generator.generate(*args, **kwargs)
        except Exception as exc:
            self.journal.update(stopped=True, error=type(exc).__name__ + ': ' + str(exc))
            raise


class _RecordedPlanner:
    def __init__(self, planner, journal):
        self.planner, self.journal = planner, journal

    def plan(self, request):
        try:
            result = self.planner.plan(request)
            if getattr(result, 'code', None) == 'provider_error':
                self.journal.update(stopped=True, error=self.journal.get('error') or 'provider_error')
            return result
        except Exception as exc:
            self.journal.update(stopped=True, error=type(exc).__name__ + ': ' + str(exc))
            raise


def _isolated_settings(settings, mapping):
    return replace(settings, terms_mapping_path=str(mapping), integration_path=None, deployment_file=None,
        database=DatabaseSettings(dialect=settings.database_settings.resolved_dialect), sqlserver=SQLServerSettings())


def _safe_response(response):
    """Public summaries carry only fixed status/codes/counts, not model text or SQL."""
    if isinstance(response, DecompositionResponse):
        return {'status': response.status, 'code': response.code if response.code in {
            'provider_error', 'invalid_model_response', 'invalid_plan', 'context_budget_exceeded'} else None,
            'task_count': len(response.draft.tasks) if response.draft else 0}
    return {'status': response.status, 'task_statuses': [t.status for t in response.task_results],
        'skipped_count': len(response.skipped_task_ids),
        'issues': [{'stage': i.stage, 'code': i.code} for i in response.issues]}


def _write_trial(output, trial_id, response, events):
    base = output / 'private/trials' / trial_id
    _write(base / 'result.json', response.model_dump(mode='json'))
    planning = response if isinstance(response, DecompositionResponse) else response.planning
    _write(base / 'planning.json', planning.model_dump(mode='json') if planning else None)
    for index, event in enumerate(e for e in events if e.get('event') == 'task_finished'):
        safe_id = f'{index:04d}'
        # A model task_id is data only, never a path component.
        _write(base / 'tasks' / safe_id / 'input.json', event['task_input'])
        _write(base / 'tasks' / safe_id / 'generation.json',
               {**event['diagnostic'], 'candidate_generation': event.get('candidate_generation')})
    return str((base / 'result.json').relative_to(output))


def _write_reports(output, metadata, entries):
    summary = summarize_pipeline(entries, planned=metadata['planned'], runs=metadata['runs'],
                                 support_planned=metadata.get('support_planned'))
    metadata.update(summary, finished_at=datetime.now(timezone.utc).isoformat())
    _update(output / 'run.json', metadata)
    _update(output / 'result.json', entries)
    _write(output / 'grading.json', {'summary': summary, 'trials': [e.get('grading') for e in entries]})
    _write(output / 'planning.json', {'private_trial_references': [e.get('response_ref') for e in entries]})
    overview = ('# 查詢 Pipeline 評估\n\n'
        f"模式：{metadata['mode']}；來源：{metadata['kind']}。\n\n"
        f"規劃 {summary['planned']} 次、完成 {summary['completed']} 次、失敗 {summary['failed']} 次、略過 {summary['skipped']} 次。\n\n"
        f"自動檢查通過 {summary['automated_pass']} 次；已人工審核的自然成功 {summary['natural_success']} 次。\n\n"
        '本流程不執行 DB。sql_ready 僅代表 SQL 階段通過 gate；stub、replay 與未審核自然輸出均不等於業務驗收。\n')
    (output / 'overview.md').write_text(overview, encoding='utf-8')
    return {'output': str(output), 'model_calls': metadata['model_calls'], **summary}


def evaluate_query_pipeline(*, mode, profile, cases_path, env_file, planner_settings, sql_settings,
        runs=1, exploratory=False, output_root=None, planner_factory=None, generator_factory=None, live=False):
    if mode not in {'planning', 'sql', 'integrated'} or type(runs) is not int or runs < 1:
        raise ValueError('mode must be planning/sql/integrated and runs must be positive')
    if not live and ((mode != 'sql' and planner_factory is None) or (mode != 'planning' and generator_factory is None)):
        raise ValueError('real models require explicit --live; offline requires factories')
    catalog = SchemaCatalog(profile)
    cases = load_pipeline_cases(cases_path, catalog)
    cases = [c for c in cases if c['review_state'] != 'rejected']
    if not cases or (not exploratory and any(not approved_for(c, catalog) for c in cases)):
        raise ValueError('pending cases require --exploratory; no approved case panel')
    kind = 'natural' if planner_factory is None and generator_factory is None else 'stub'
    metadata = _metadata(profile, cases_path, planner_settings, sql_settings, mode, runs, exploratory, kind)
    metadata['planned'] = len(cases) * runs
    metadata['support_planned'] = sum(c['expected_stage_status'] == 'sql_ready' for c in cases) * runs
    output = _new_output(output_root or Path(profile) / 'artifacts/query_pipeline')
    _write(output / 'run.json', metadata)
    _write(output / 'result.json', [])
    entries, all_calls, mapping_hashes = [], [], []
    stopped = False
    stop_reason = 'provider_error'
    event_path = output / 'events.jsonl'
    with event_path.open('x', encoding='utf-8') as event_stream:
        for round_index in range(runs):
            for case in cases:
                trial_id = f'{len(entries):06d}'
                entry = {'case_id': case['case_id'], 'round': round_index, 'kind': kind,
                         'supported_case': case['expected_stage_status'] == 'sql_ready'}
                if stopped:
                    entries.append({**entry, 'status': 'skipped', 'reason': stop_reason})
                    _update(output / 'result.json', entries)
                    continue
                events, planning_events = [], []
                journal = {'calls': [], 'stopped': False, 'error': None}
                mapping = output / 'private/trials' / trial_id / 'terms_mapping.json'
                repository = JsonTermMappingRepository(mapping, MappingScope(profile_id=catalog.profile_id, datasource_id=sql_settings.datasource_id))
                mapping_hashes.append(content_hash(repository.read().model_dump(mode='json')))
                planner, generator = None, None
                started = perf_counter()
                try:
                    if mode != 'sql':
                        if planner_factory:
                            planner = planner_factory(catalog=catalog, settings=_isolated_settings(planner_settings, mapping), observer=planning_events.append)
                        else:
                            model = _RecordedModel(get_llm_config(settings=planner_settings), 'planning', journal)
                            planner = TaskDecompositionService(model, catalog, settings=_isolated_settings(planner_settings, mapping), observer=planning_events.append)
                        planner = _RecordedPlanner(planner, journal)
                    if mode != 'planning':
                        conf = _isolated_settings(sql_settings, mapping)
                        if generator_factory:
                            generator = generator_factory(catalog=catalog, settings=conf, repository=repository)
                        else:
                            model = _RecordedModel(get_llm_config(settings=conf), 'sql', journal)
                            generator = SQLGenerationService(model, catalog, settings=conf, repository=repository)
                        generator = _RecordedGenerator(generator, journal)
                    if mode == 'planning':
                        response = planner.plan(case['request'])
                    else:
                        pipeline = QueryPipelineService(planner, generator, catalog=catalog,
                            settings=_isolated_settings(sql_settings, mapping), observer=events.append)
                        response = (pipeline.generate_from_plan(case['request'], approved_planning(case, catalog))
                                    if mode == 'sql' else pipeline.invoke(case['request']))
                    entry['response_ref'] = _write_trial(output, trial_id, response, events)
                    score = grade_pipeline_case(case, response, mode=mode, catalog=catalog)
                    # Details contain only fixed diagnostics; task IDs and model text stay private.
                    _write(output / 'private/trials' / trial_id / 'grading.json', score)
                    entry.update(status='failed' if journal['stopped'] else 'completed',
                        response=_safe_response(response), grading={k: v for k, v in score.items() if k != 'issues'})
                except Exception as exc:
                    stop_reason = 'provider_error' if journal['stopped'] else 'evaluation_error'
                    journal.update(stopped=True, error=journal.get('error') or type(exc).__name__ + ': ' + str(exc))
                    entry.update(status='failed', reason=stop_reason, grading={'automated_pass': False,
                        'success': False, 'first_error_stage': 'evaluation' if stop_reason == 'evaluation_error' else
                        ('planning' if mode == 'planning' else 'sql_generation')})
                finally:
                    registry = getattr(getattr(generator, 'workflow', None), 'registry', None)
                    if registry is not None:
                        registry.close()
                entry['elapsed_ms'] = (perf_counter() - started) * 1000
                stopped = journal['stopped']
                if stopped:
                    entry.setdefault('reason', stop_reason)
                    private = output / 'private' / ('provider-error.txt' if stop_reason == 'provider_error' else 'evaluation-error.txt')
                    private.write_text(journal['error'] or 'provider_error', encoding='utf-8')
                    os.chmod(private, 0o600)
                _write(output / 'private/trials' / trial_id / 'calls.json', journal['calls'])
                _write(output / 'private/trials' / trial_id / 'planning-events.json', planning_events)
                _write(output / 'private/trials' / trial_id / 'events.json', events)
                for event in events:
                    safe = {k: event[k] for k in ('event', 'run_id', 'status') if k in event}
                    event_stream.write(json.dumps({'trial_id': trial_id, **safe}, ensure_ascii=False) + '\n')
                event_stream.flush()
                all_calls.extend(journal['calls'])
                entries.append(entry)
                _update(output / 'result.json', entries)
                metadata.update(summarize_pipeline(entries, planned=metadata['planned'], runs=runs,
                    support_planned=metadata['support_planned']))
                metadata['model_calls'] = len(all_calls)
                metadata['mapping_initial_sha256'] = mapping_hashes
                usage = [c.get('usage') for c in all_calls]
                for key in ('input_tokens', 'output_tokens'):
                    metadata[key] = sum(u[key] for u in usage) if usage and all(u and u.get(key) is not None for u in usage) else None
                _update(output / 'run.json', metadata)
    return _write_reports(output, metadata, entries)


def _read_reference(root, reference):
    path = (root / reference).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('artifact reference escapes run directory')
    return json.loads(path.read_text(encoding='utf-8'))


def replay_query_pipeline(run_dir, *, profile, cases_path, output_root=None, reviews_path=None):
    run_dir = Path(run_dir)
    original = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    catalog = SchemaCatalog(profile)
    cases = {c['case_id']: c for c in load_pipeline_cases(cases_path, catalog)}
    if reviews_path is not None:
        reviews = json.loads(Path(reviews_path).read_text(encoding='utf-8'))
        if not isinstance(reviews, dict) or not set(reviews) <= set(cases):
            raise ValueError('reviews must reference known cases')
        for case_id, decisions in reviews.items():
            if not isinstance(decisions, dict):
                raise ValueError('reviews must map response fingerprints to decisions')
            cases[case_id]['output_reviews'] = decisions
    if original['catalog_fingerprint'] != catalog.fingerprint or original['casefile_sha256'] != sha256(Path(cases_path).read_bytes()).hexdigest():
        raise ValueError('incompatible_replay: case or catalog drift')
    original_entries = json.loads((run_dir / 'result.json').read_text(encoding='utf-8'))
    output = _new_output(output_root or run_dir.parent)
    metadata = {**original, 'kind': 'replay', 'model_calls': 0, 'input_tokens': None, 'output_tokens': None,
        'replay_of': {'run': str(run_dir.resolve()), 'run_sha256': sha256((run_dir / 'run.json').read_bytes()).hexdigest()},
        'grader_version': GRADER_VERSION, 'grader_sha256': sha256(Path(__file__).with_name('query_pipeline_grading.py').read_bytes()).hexdigest()}
    if reviews_path is not None:
        metadata['reviewfile_sha256'] = sha256(Path(reviews_path).read_bytes()).hexdigest()
    current = _versions(AssistantSettings.from_env())
    metadata['source_drift'] = (current['runner_sha256'] != original.get('runner_sha256')
        or current['pipeline_sha256'] != original['pipeline_sha256']) or any(
        current[node][key] != original['nodes'][node][key]
        for node in ('planning', 'sql') for key in ('source_sha256', 'schema_sha256', 'prompt_sha256'))
    _write(output / 'run.json', metadata)
    entries = []
    for original_entry in original_entries:
        entry = {**original_entry, 'kind': 'replay'}
        if original_entry.get('response_ref'):
            data = _read_reference(run_dir, original_entry['response_ref'])
            response = (DecompositionResponse if original['mode'] == 'planning' else QueryPipelineResponse).model_validate(data)
            score = grade_pipeline_case(cases[entry['case_id']], response, mode=original['mode'], catalog=catalog)
            if response.status == 'sql_ready':
                # Revalidate recorded SQL with the original dialect and protection limit.
                conf = replace(AssistantSettings.from_env(), database=DatabaseSettings(dialect=original['dialect']),
                    max_rows=original['nodes']['sql']['settings']['max_rows'])
                tasks = {t.task_id: t for t in response.planning.draft.tasks}
                errors = [i for r in response.task_results for i in validate_task_sql(
                    TaskSQLInput(original_request=cases[entry['case_id']]['request'], task=tasks[r.task_id],
                        contract_fingerprint=response.contract_fingerprint), r.generation, catalog=catalog, settings=conf)]
                if errors:
                    score.update(automated_pass=False, success=False, first_error_stage='sql_validation', task_to_plan_and_sql_policy=False)
            entry['grading'] = {k: v for k, v in score.items() if k != 'issues'}
            entry['response_ref'] = _write_trial(output, f'{len(entries):06d}', response, [])
        entries.append(entry)
    (output / 'events.jsonl').write_text('', encoding='utf-8')
    return _write_reports(output, metadata, entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['planning', 'sql', 'integrated'], required=True)
    parser.add_argument('--profile', type=Path, default=Path('projects/retail'))
    parser.add_argument('--cases', type=Path, default=Path('projects/retail/evaluations/query_pipeline_cases.jsonl'))
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--planner-provider', choices=['ollama', 'azure', 'llamacpp', 'gcp'], default='ollama')
    parser.add_argument('--planner-model', default='qwen3.8:27b')
    parser.add_argument('--sql-provider', choices=['ollama', 'azure', 'llamacpp', 'gcp'], default='ollama')
    parser.add_argument('--sql-model', default='qwen3.8:27b')
    parser.add_argument('--ollama-base-url', help='Explicit Ollama endpoint for either Ollama node')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--exploratory', action='store_true')
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--reviews', type=Path, help='Human output reviews for offline regrading')
    args = parser.parse_args(argv)
    if args.replay:
        result = replay_query_pipeline(args.replay, profile=args.profile, cases_path=args.cases,
            output_root=args.output_root, reviews_path=args.reviews)
    else:
        if not args.live:
            parser.error('real models require explicit --live')
        base = AssistantSettings.from_env(args.env_file if args.env_file.is_file() else None)
        def node_settings(provider, model):
            if provider == 'azure':
                from evaluations.decomposition_runner import azure_planning_settings
                return azure_planning_settings(args.env_file, model)
            return replace(base, llm_provider=provider, llm_model=model,
                llm_base_url=(args.ollama_base_url or (base.llm_base_url if base.llm_provider == 'ollama' else 'http://localhost:11434'))
                    if provider == 'ollama' else base.llm_base_url,
                token_count_endpoint=None)
        result = evaluate_query_pipeline(mode=args.mode, profile=args.profile, cases_path=args.cases,
            env_file=args.env_file, planner_settings=node_settings(args.planner_provider, args.planner_model),
            sql_settings=node_settings(args.sql_provider, args.sql_model), runs=args.runs,
            exploratory=args.exploratory, output_root=args.output_root, live=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['failed'] or result['skipped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
