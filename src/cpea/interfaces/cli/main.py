"""Installed-package CLI for the existing generation, execution and answer modes."""
import argparse
import json
import sys
from cpea.bootstrap import AssistantRuntime
from cpea.application.errors import DependencyUnavailable

def compact_generation(result):
    return {key: getattr(result, key) for key in ('supported', 'sql', 'selected_views', 'explanation', 'limitations')}

def main(argv=None, *, runtime: AssistantRuntime | None = None):
    parser = argparse.ArgumentParser(description='CPEA governed single-view SQL assistant')
    parser.add_argument('--request', default='請查詢 ZX100 目前各倉庫庫存數量')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--answer', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--env-file', help='Explicit env file; no ancestor search')
    args = parser.parse_args(argv)
    if args.answer and not args.execute:
        parser.error('--answer requires --execute')
    try:
        runtime = runtime if runtime is not None else AssistantRuntime.from_env(args.env_file)
        if args.execute:
            runtime.require_execution()
            execution = runtime.execute(args.request)
            result = execution.generation
            print(json.dumps(result.model_dump() if args.verbose else compact_generation(result), ensure_ascii=False, default=str))
            print(json.dumps({'execution_attempts': execution.attempts, 'repaired': execution.repaired,
                'columns': execution.columns, 'rows': execution.rows, 'rows_truncated': execution.rows_truncated}, ensure_ascii=False, default=str))
            if args.answer:
                print(runtime.answer_service().synthesize(args.request, execution).model_dump_json())
            return 0
        result = runtime.generate(args.request)
        print(json.dumps(result.model_dump() if args.verbose else compact_generation(result), ensure_ascii=False, default=str))
        return 0 if result.supported and result.sql else 2
    except DependencyUnavailable as exc:
        print(f'{exc.code}: {exc}', file=sys.stderr)
        return 3
    except Exception as exc:
        print(f'CPEA command failed: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
