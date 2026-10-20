"""Installed-package CLI for the existing generation, execution and answer modes."""
import argparse
import json
import sys
from cpea.bootstrap import AssistantRuntime
from cpea.application.errors import DependencyUnavailable
from cpea.application.models.query import SQLGenerationResponse
from cpea.application.models.confirmation import ConfirmationRequest

def compact_generation(result):
    return result.model_dump(include={'status', 'code', 'supported', 'sql', 'selected_views', 'explanation', 'limitations', 'clarification', 'term_mapping_reasoning'})

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
        value = runtime.execute(args.request) if args.execute else runtime.generate(args.request)
        while isinstance(value, SQLGenerationResponse) and value.status == 'needs_confirmation':
            if not sys.stdin.isatty():
                print(value.model_dump_json())
                return 4
            clarification = value.clarification
            decisions = []
            cancel = False
            for item in clarification.items:
                print(f'{item.term}：{item.reason}')
                for index, option in enumerate(item.options, 1):
                    print(f'  {index}. {item.view}.{option.column} {option.description}' if option.column else f'  {index}. {option.description}')
                while True:
                    try:
                        choice = input('請選擇編號（0 取消）：').strip()
                    except (EOFError, KeyboardInterrupt):
                        choice = '0'
                    if choice.isdigit() and 0 <= int(choice) <= len(item.options):
                        break
                if choice == '0' or item.options[int(choice) - 1].column is None:
                    cancel = True
                    break
                decisions.append({'item_id': item.id, 'option_id': item.options[int(choice) - 1].id})
            payload = ConfirmationRequest(confirmation_id=clarification.confirmation_id,
                action='cancel' if cancel else 'confirm', decisions=None if cancel else decisions)
            value = runtime.confirm(payload, mode='execute' if args.execute else 'sql')
        if isinstance(value, SQLGenerationResponse):
            print(json.dumps(value.model_dump() if args.verbose else compact_generation(value), ensure_ascii=False, default=str))
            return 0 if value.status == 'ready' else 2
        execution = value
        result = execution.generation
        print(json.dumps(result.model_dump() if args.verbose else compact_generation(result), ensure_ascii=False, default=str))
        print(json.dumps({'execution_attempts': execution.attempts, 'repaired': execution.repaired,
            'columns': execution.columns, 'rows': execution.rows, 'rows_truncated': execution.rows_truncated}, ensure_ascii=False, default=str))
        if args.answer:
            print(runtime.answer_service().synthesize(args.request, execution).model_dump_json())
        return 0
    except DependencyUnavailable as exc:
        print(f'{exc.code}: {exc}', file=sys.stderr)
        return 3
    except Exception as exc:
        print('CPEA command failed；請檢查設定後重新提問。', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
