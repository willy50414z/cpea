#!/usr/bin/env python3
"""Small explicit CLI; no command strings are read from ledger documents."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from ledger import EddError, Ledger, STATES


def parser():
    p = argparse.ArgumentParser(description='EDD 檔案式任務與證據管理')
    p.add_argument('--root', type=Path, help='Repository 路徑；預設使用目前 Git Worktree')
    p.add_argument('--actor', default='main-agent', help='合作契約身分；不是安全認證')
    subs = p.add_subparsers(dest='command', required=True)
    commands = ['init', 'status', 'resume', 'validate', 'archive', 'update', 'transition', 'checkpoint',
                'run', 'ask', 'answer', 'decision', 'experiment', 'conclude', 'agent', 'handoff', 'integrate', 'bind', 'agent-map', 'hooks-mode']
    for name in commands:
        s = subs.add_parser(name)
        if name not in {'status', 'hooks-mode'}:
            s.add_argument('--id', required=True)
        if name == 'init':
            s.add_argument('--type', default='bugfix', choices=['bugfix', 'feature', 'architecture', 'research'])
            s.add_argument('--goal')
            s.add_argument('--scope', action='append', default=[])
            s.add_argument('--complexity', choices=['moderate', 'complex'], default='moderate')
        if name in {'update', 'handoff'}:
            s.add_argument('--data-file', type=Path, required=True, help='UTF-8 JSON，不執行內容')
        if name == 'validate':
            s.add_argument('--portable', action='store_true', help='只驗證可攜紀錄一致性，不宣稱目前 checkout 已通過測試')
        if name == 'transition':
            s.add_argument('--to', required=True, choices=sorted(STATES - {'ARCHIVED'}))
            s.add_argument('--reason', default='')
        if name == 'checkpoint':
            s.add_argument('--last', required=True)
            s.add_argument('--current', required=True)
            s.add_argument('--next', required=True)
            s.add_argument('--input', action='append', default=[])
        if name == 'run':
            s.add_argument('--kind', required=True, choices=['baseline', 'focused', 'regression', 'negative', 'boundary', 'holdout', 'metamorphic', 'experiment', 'review'])
            s.add_argument('--timeout', type=float, default=60)
            s.add_argument('argv', nargs=argparse.REMAINDER)
        if name in {'ask', 'answer'}:
            s.add_argument('--question-id', required=True)
        if name == 'ask':
            s.add_argument('--source', default='main-agent')
            s.add_argument('--question', required=True)
            s.add_argument('--context', required=True)
            s.add_argument('--option', action='append', default=[])
            s.add_argument('--recommendation', default='')
            s.add_argument('--impact', required=True)
        if name == 'answer':
            s.add_argument('--answer', required=True)
            s.add_argument('--evidence', required=True)
        if name == 'decision':
            s.add_argument('--summary', required=True)
            s.add_argument('--alternative', action='append', required=True)
            s.add_argument('--reason', required=True)
            s.add_argument('--risks', required=True)
            s.add_argument('--revisit', required=True)
            s.add_argument('--ref', action='append', default=[])
        if name == 'experiment':
            s.add_argument('--hypothesis-id', required=True)
            s.add_argument('--hypothesis', required=True)
            s.add_argument('--success', required=True)
            s.add_argument('--failure', required=True)
            s.add_argument('--substantive-fix', action='store_true')
        if name == 'conclude':
            s.add_argument('--experiment-id', required=True)
            s.add_argument('--conclusion', choices=['SUPPORTED', 'REFUTED', 'INCONCLUSIVE'], required=True)
            s.add_argument('--evidence', action='append', required=True)
            s.add_argument('--interpretation', required=True)
        if name in {'agent', 'handoff', 'integrate', 'agent-map'}:
            s.add_argument('--agent-id', required=True)
        if name == 'agent':
            s.add_argument('--assignment', required=True)
            s.add_argument('--scope', action='append', required=True)
            s.add_argument('--platform-id')
            s.add_argument('--worktree')
        if name == 'integrate':
            s.add_argument('--disposition', default='')
        if name == 'bind':
            s.add_argument('--session-id', required=True)
        if name == 'agent-map':
            s.add_argument('--platform-id', required=True)
        if name == 'hooks-mode':
            s.add_argument('--mode', choices=['advisory', 'enforce'], required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = args.root or Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True, encoding='utf-8').strip())
        l = Ledger(root, args.actor)
        c = args.command
        if c == 'init':
            out = l.init(args.id, args.type, args.goal, args.scope, args.complexity)
        elif c == 'status':
            out = l.list_tasks()
        elif c == 'resume':
            out = l.resume(args.id)
        elif c == 'validate':
            errors = l.validate(args.id, portable=args.portable)
            print(json.dumps({'result': 'FAIL' if errors else 'PASS', 'errors': errors}, ensure_ascii=False, indent=2))
            return bool(errors)
        elif c == 'archive':
            out = {'archive': str(l.archive(args.id))}
        elif c == 'update':
            out = l.update(args.id, json.loads(args.data_file.read_text(encoding='utf-8')))
        elif c == 'transition':
            out = l.transition(args.id, args.to, args.reason)
        elif c == 'checkpoint':
            out = l.checkpoint(args.id, args.last, args.current, args.next, args.input)
        elif c == 'run':
            command = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            out = l.run(args.id, command, args.kind, args.timeout)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0 if out['exit_code'] == 0 and out['source_unchanged'] else 1
        elif c == 'ask':
            out = l.ask(args.id, args.question_id, args.source, args.question, args.context, args.option, args.recommendation, args.impact)
        elif c == 'answer':
            out = l.answer(args.id, args.question_id, args.answer, args.evidence)
        elif c == 'decision':
            out = l.decision(args.id, args.summary, args.alternative, args.reason, args.risks, args.revisit, args.ref)
        elif c == 'experiment':
            out = l.experiment(args.id, args.hypothesis_id, args.hypothesis, args.success, args.failure, args.substantive_fix)
        elif c == 'conclude':
            out = l.conclude(args.id, args.experiment_id, args.conclusion, args.evidence, args.interpretation)
        elif c == 'agent':
            out = l.register_agent(args.id, args.agent_id, args.assignment, args.scope, args.platform_id, args.worktree)
        elif c == 'handoff':
            out = l.handoff(args.id, args.agent_id, json.loads(args.data_file.read_text(encoding='utf-8')))
        elif c == 'integrate':
            out = l.integrate(args.id, args.agent_id, args.disposition)
        elif c == 'bind':
            l.bind(args.id, args.session_id)
            out = {'bound': args.id, 'session_id': args.session_id}
        elif c == 'agent-map':
            l.map_agent(args.id, args.agent_id, args.platform_id)
            out = {'agent': args.agent_id, 'platform_id': args.platform_id}
        elif c == 'hooks-mode':
            l.hooks_mode(args.mode)
            out = {'hooks_mode': args.mode}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if c == 'resume' and out['errors']:
            return 1
        if c == 'status' and any('error' in x for x in out):
            return 1
        return 0
    except (EddError, OSError, ValueError, subprocess.SubprocessError) as e:
        print(json.dumps({'result': 'ERROR', 'error': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
