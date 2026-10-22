"""Two fresh diagnostic nodes for the explicit inventory-snapshot request."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from langchain_core.messages import AIMessage
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.three_stage_view_selection import RecallResult, ViewCoverage, validate_recall, validate_coverage
from evaluations.three_stage_view_selection_runner import Budget, MODEL, TASK, messages_for, fingerprint, _verify_artifacts

REQUEST = '對照各店各商品的盤點庫存件數與 2026 年 9 月線上通路的折扣金額及淨銷售額，並顯示庫存盤點日期，準備促銷後補貨評估；保留所有庫存商品。'
CASE = {'case_id': 'cross-view-11-explicit-snapshot', 'request': REQUEST}
VIEW = 'demo_retail.v_inventory_status'


def frozen(catalog):
    return dict(base=fingerprint(catalog, CASE), probe_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def execute(catalog, invoke, save, budget, check_version):
    recall = None
    for phase, schema in [('recall', RecallResult), ('inventory', ViewCoverage)]:
        started = monotonic()
        raw = None
        try:
            check_version()
            if phase == 'recall':
                messages = messages_for('recall', schema, REQUEST, views=[v.policy for v in catalog.views()])
            else:
                messages = messages_for('coverage', schema, REQUEST,
                    requirements=[r.model_dump() for r in recall.requirements],
                    view=next(v.policy for v in catalog.views() if v.name == VIEW))
            estimated = budget.begin(messages)
            save(phase + '-request.json', dict(messages=[dict(role=m.type, content=m.content) for m in messages],
                                              schema=schema.__name__, input_tokens_estimated=estimated))
            save('budget.json', budget.state())
            try:
                raw = invoke(messages, schema)
            except Exception as exc:
                save(phase + '-provider-error.json', dict(error_type=type(exc).__name__, error=str(exc)))
                raise
            save(phase + '-call.json', dict(response=raw.content, usage=raw.usage_metadata,
                response_metadata=raw.response_metadata, elapsed_seconds=monotonic()-started))
            budget.record_usage(raw.usage_metadata, estimated)
            parsed = parse_model(raw, schema)
            if phase == 'recall':
                recall = validate_recall(parsed, REQUEST, catalog)
            else:
                if parsed.view != VIEW:
                    raise ValueError('inventory probe returned another view')
                validate_coverage(parsed, recall, REQUEST, catalog)
            save(phase + '-result.json', parsed.model_dump())
        except Exception as exc:
            save(phase + '-error.json', dict(error_type=type(exc).__name__, error=str(exc), raw_saved=raw is not None))
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true')
    group.add_argument('--replay', type=Path)
    args = parser.parse_args(argv)
    catalog = SchemaCatalog('projects/retail')
    budget = Budget(calls_limit=2, total_input_limit=30000, total_output_limit=8192, wall_seconds=900)
    freeze = frozen(catalog)
    if args.replay:
        folder = args.replay
        meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
        assert meta['frozen'] == freeze, 'replay source/catalog/schema mismatch'
        _verify_artifacts(folder, meta)
        names = iter([p for p in ('recall', 'inventory') if (folder / (p + '-call.json')).exists()])
        saved = {}
        def invoke(messages, schema):
            phase = next(names)
            original_input = json.loads((folder / (phase + '-request.json')).read_text(encoding='utf-8'))
            assert original_input['messages'] == [dict(role=m.type, content=m.content) for m in messages]
            call = json.loads((folder / (phase + '-call.json')).read_text(encoding='utf-8'))
            return AIMessage(content=call['response'], usage_metadata=call['usage'], response_metadata=call['response_metadata'])
        stopped = None
        try:
            execute(catalog, invoke, saved.__setitem__, budget, lambda: None)
        except Exception as exc:
            stopped = dict(error_type=type(exc).__name__, error=str(exc))
        assert stopped == meta['stopped'], 'replay stopped differently'
        assert budget.calls == meta['calls']
        for name, value in saved.items():
            if name.endswith(('-result.json', '-error.json')):
                assert value == json.loads((folder / name).read_text(encoding='utf-8'))
        print(json.dumps(dict(result='PASS', raw_replays=len(list(folder.glob('*-call.json'))), stopped=stopped), ensure_ascii=False))
        return 0
    print(json.dumps(dict(execute=args.execute, case=CASE['case_id'], request=REQUEST,
                         model=MODEL, max_calls=2, max_input_tokens=30000, max_output_reserve=8192,
                         scope='fresh recall then inventory mapping only; no final selection'), ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    folder = TASK / '.local' / ('snapshot-inventory-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    folder.mkdir(mode=0o700)
    def save(name, value):
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)
    meta = dict(case=CASE, frozen=freeze, model=MODEL, max_calls=2, sdk_retries=0,
                temperature=1, top_p=1, seed=42, context_window=32768, output_limit=4096,
                safety=1024, timeout_seconds=300, wall_seconds=900, cost_usd=None,
                started_at=datetime.now(timezone.utc).isoformat(), stopped=None,
                oracle_status='diagnostic reference; not independently approved benchmark',
                scope='recall and inventory mapping only; no SQL/DB/Ollama/final selection')
    save('run.json', meta)
    def check_version():
        if frozen(SchemaCatalog('projects/retail')) != freeze:
            raise ValueError('frozen version changed')
    def invoke(messages, schema):
        from evaluations.decomposition_runner import azure_planning_settings
        from cpea.infrastructure.llm.factory import bind_response_schema, get_llm_config
        settings = replace(azure_planning_settings(Path('.env'), MODEL), context_window=32768,
            max_output_tokens=4096, context_safety_tokens=1024, request_timeout_seconds=300)
        return bind_response_schema(get_llm_config(settings=settings), schema).bind(response_format={'type': 'json_object'}).invoke(messages)
    try:
        execute(catalog, invoke, save, budget, check_version)
    except Exception as exc:
        meta['stopped'] = dict(error_type=type(exc).__name__, error=str(exc))
    finally:
        meta.update(budget.state(), finished_at=datetime.now(timezone.utc).isoformat())
        meta['artifact_hashes'] = {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name != 'run.json'}
        save('run.json', meta)
        print(json.dumps(dict(folder=str(folder), calls=meta['calls'], stopped=meta['stopped']), ensure_ascii=False), flush=True)
    return 1 if meta['stopped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
