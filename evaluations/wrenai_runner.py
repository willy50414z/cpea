"""Offline-only evaluator CLI. It never loads .env or constructs a live provider."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='WrenAI 離線評估：regrade / replay；live 尚未授權且不提供。')
    commands = parser.add_subparsers(dest='mode', required=True)
    grade_parser = commands.add_parser('regrade', help='只重評儲存結果，零模型呼叫')
    grade_parser.add_argument('run_dir', type=Path)
    grade_parser.add_argument('--profile', type=Path, required=True)
    grade_parser.add_argument('--cases', type=Path, required=True)
    grade_parser.add_argument('--case-id', required=True)
    replay_parser = commands.add_parser('replay', help='以錄製 completion/embedding 重跑隔離 native graph')
    replay_parser.add_argument('run_dir', type=Path)
    replay_parser.add_argument('--runtime-identity', type=Path, required=True)
    replay_parser.add_argument('--allow-drift', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'regrade':
            from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
            from evaluations.wrenai_cases import load_wrenai_cases
            from evaluations.wrenai_replay import regrade
            catalog = SchemaCatalog(args.profile)
            cases = load_wrenai_cases(args.cases, catalog)
            case = next(c for c in cases if c['case_id'] == args.case_id)
            result = regrade(args.run_dir, case, catalog)
            summary = {key: result[key] for key in ('automated_pass', 'cost_complete', 'spend', 'calls', 'fixture_source')}
        else:
            from evaluations.wrenai_replay import replay
            identity = json.loads(args.runtime_identity.read_text(encoding='utf-8'))
            result = replay(args.run_dir, runtime_identity=identity, allow_drift=args.allow_drift)
            summary = {key: result[key] for key in ('identity_drift', 'drift_allowed', 'exact_reproduction', 'fixture_source', 'replay_mode')}
            summary['draft_sha256'] = sha256(json.dumps(result['draft'], sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception:
        # Exception messages may contain provider credentials, prompts or paths.
        print(json.dumps({'status': 'error', 'code': 'offline_evaluation_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
