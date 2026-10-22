import json
import subprocess
import sys
import unittest
from pathlib import Path
from test_ledger import LedgerTests
from ledger import EddError, Ledger, read_document
from helpers import complete, plan


class LifecycleTests(LedgerTests):
    # Use the same setup without running inherited test methods twice.
    def test_complete_and_archive_preserve_all_records(self):
        ev = complete(self.l)
        self.assertEqual(self.l.validate('example'), [])
        dest = self.l.archive('example')
        self.assertEqual(read_document(dest / 'task.md')[0]['status'], 'ARCHIVED')
        self.assertTrue((dest / ev['path']).exists())
        self.assertTrue((dest / 'experiments/EXP-001.md').exists())
        self.assertFalse(self.l.task_path('example').exists())
        with self.assertRaises(EddError):
            self.l.init('example', 'bugfix', 'again', ['x'], 'moderate')

    def test_archive_collision_does_not_destroy_task(self):
        complete(self.l)
        import datetime
        dest = self.l.home / 'archive' / (datetime.date.today().isoformat() + '-example')
        dest.mkdir(parents=True)
        (dest / 'keep').write_text('keep', encoding='utf-8')
        with self.assertRaises(EddError):
            self.l.archive('example')
        self.assertTrue(self.l.task_path('example').exists())
        self.assertEqual((dest / 'keep').read_text(encoding='utf-8'), 'keep')

    def test_multiple_tasks_require_explicit_selection(self):
        self.l.init('second', 'feature', 'other', ['x'], 'moderate')
        with self.assertRaises(EddError):
            self.l.resolve()
        self.l.bind('example', 'session-a')
        self.l.bind('second', 'session-b')
        self.assertEqual(self.l.resolve(session_id='session-a'), 'example')
        self.assertEqual(self.l.resolve(session_id='session-b'), 'second')

    def test_three_failures_stop_same_hypothesis_and_preserve_results(self):
        for i in range(3):
            exp = self.l.experiment('example', 'H1', '原假設', 'pass', 'fail', True)
            ev = self.l.run('example', [sys.executable, '-c', 'raise SystemExit(1)'], 'experiment')
            self.l.conclude('example', exp['id'], 'REFUTED', [ev['path']], '實質修正仍失敗')
        self.assertTrue(self.l.failure_review_required(self.l.load('example')))
        with self.assertRaises(EddError):
            self.l.experiment('example', 'H1', 'again', 'pass', 'fail', True)
        self.assertEqual(len(list((self.l.task_path('example') / 'experiments').glob('*.md'))), 3)
        with self.assertRaises(EddError):
            self.l.conclude('example', 'EXP-001', 'SUPPORTED', [ev['path']], 'overwrite')

    def test_agents_writer_ownership_and_structured_handoff(self):
        before = (self.l.task_path('example') / 'task.md').read_bytes()
        for a in ('cause', 'oracle'):
            self.l.register_agent('example', a, '獨立唯讀研究', ['fixture'], 'platform-' + a)
        main_before = (self.l.task_path('example') / 'task.md').read_bytes()
        agent = Ledger(self.root, actor='cause')
        agent.handoff('example', 'cause', {'status': 'DONE', 'summary': '已定位邊界', 'evidence': ['fixture:line1'],
                                         'next_step': 'Main 審核', 'risks': [], 'diff_reference': 'base'})
        self.assertEqual(main_before, (self.l.task_path('example') / 'task.md').read_bytes())
        with self.assertRaises(EddError):
            agent.handoff('example', 'oracle', {'status': 'DONE', 'summary': 'x', 'next_step': 'x'})
        self.l.integrate('example', 'cause')
        self.assertTrue(self.l.load('example')['agents'][0]['integrated'])
        Ledger(self.root, actor='oracle').handoff('example', 'oracle', {'status': 'BLOCKED', 'summary': '缺 fixture',
                            'next_step': '請提供', 'blockers': ['input missing']})
        with self.assertRaises(EddError):
            self.l.integrate('example', 'oracle')
        self.l.integrate('example', 'oracle', '保留 BLOCKED，改由主 Agent 處理 input')
        self.assertEqual(self.l.load('example')['agents'][1]['status'], 'BLOCKED')

    def test_cli_roundtrip_and_error_exit_codes(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/edd.py'
        def run(*args):
            return subprocess.run([sys.executable, str(cli), '--root', str(self.root), *args], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run('validate', '--id', 'example').returncode, 0)
        self.assertNotEqual(run('init', '--id', 'example').returncode, 0)
        result = run('run', '--id', 'example', '--kind', 'focused', '--', sys.executable, '-c', 'print("hi")')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['exit_code'], 0)


# unittest loads inherited methods; suppress duplicate inherited entries in this module.
for _name in list(LedgerTests.__dict__):
    if _name.startswith('test_'):
        setattr(LifecycleTests, _name, None)
del LedgerTests

if __name__ == '__main__':
    unittest.main()
