import json
import sys
import unittest
from test_ledger import LedgerTests
from ledger import EddError, Ledger, write_document, read_document
from helpers import complete, plan


class GuardTests(LedgerTests):
    def test_pause_chain_is_rejected_without_losing_original_state(self):
        self.l.transition('example', 'INVESTIGATING')
        self.l.ask('example', 'Q-001', 'main-agent', 'A?', 'contract', ['A', 'B'], 'A', 'scope')
        self.l.update('example', {'blockers': ['missing input']})
        with self.assertRaises(EddError):
            self.l.transition('example', 'BLOCKED')
        self.l.answer('example', 'Q-001', 'A', '測試事件')
        self.assertEqual(self.l.load('example')['status'], 'INVESTIGATING')

    def test_failed_answer_does_not_append_orphan_decision(self):
        self.l.transition('example', 'INVESTIGATING')
        self.l.ask('example', 'Q-001', 'main-agent', 'A?', 'contract', ['A', 'B'], 'A', 'scope')
        self.l.update('example', {'scope': []})
        before = (self.l.task_path('example') / 'decisions.md').read_bytes()
        with self.assertRaises(EddError):
            self.l.answer('example', 'Q-001', 'A', '測試事件')
        self.assertEqual(before, (self.l.task_path('example') / 'decisions.md').read_bytes())

    def test_transition_rejects_missing_report_before_completion(self):
        complete(self.l)
        self.l.transition('example', 'VERIFYING')
        self.l.register_agent('example', 'review', 'independent review', ['fixture'])
        Ledger(self.root, actor='review').handoff('example', 'review', {'status': 'DONE', 'summary': 'review', 'evidence': ['fixture'], 'next_step': 'integrate'})
        self.l.integrate('example', 'review')
        (self.l.task_path('example') / 'agents/review/task.md').unlink()
        with self.assertRaises(EddError):
            self.l.transition('example', 'COMPLETED')

    def test_empty_scope_and_owner_cannot_complete(self):
        complete(self.l)
        self.l.transition('example', 'VERIFYING')
        self.l.update('example', {'scope': []})
        with self.assertRaises(EddError):
            self.l.transition('example', 'COMPLETED')

    def test_malformed_nested_schema_is_rejected(self):
        for patch in ({'verification': {'tests': 'not-list'}}, {'acceptance': [{'id': 'x', 'status': True}]},
                      {'plan': {'solutions': [None]}}, {'problem': {'description': 'x', 'expected': '', 'actual': '', 'evidence': [], 'hypotheses': ['not-object']}}):
            with self.assertRaises(EddError, msg=str(patch)):
                self.l.update('example', patch)

    def test_failed_hypothesis_cannot_be_retried_with_one_word_review(self):
        for _ in range(3):
            exp = self.l.experiment('example', 'H1', 'same', 'pass', 'fail', True)
            ev = self.l.run('example', [sys.executable, '-c', 'raise SystemExit(1)'], 'experiment')
            self.l.conclude('example', exp['id'], 'REFUTED', [ev['path']], 'failed')
        with self.assertRaises(EddError):
            self.l.update('example', {'plan': {'reassessment': 'reviewed'}})
        self.l.update('example', {'plan': {'reassessment': {'experiments': ['EXP-001', 'EXP-002', 'EXP-003'],
            'rejected_hypothesis': 'H1', 'oracle_review': 'contract is exact match', 'problem_review': 'threshold not cause',
            'new_direction': 'exact normalization', 'new_hypothesis_id': 'H2'}}})
        with self.assertRaises(EddError):
            self.l.experiment('example', 'H1', 'same again', 'pass', 'fail', True)
        self.l.experiment('example', 'H2', 'new contract', 'pass', 'fail', True)

    def test_invalid_nested_types_do_not_crash_schema_validation(self):
        patches = [
            {'problem': {'description': 'x', 'expected': '', 'actual': '', 'evidence': [], 'hypotheses': None}},
            {'verification': {'result': []}}, {'acceptance': [{'id': 'x', 'status': {}}]},
            {'plan': {'solutions': None}}, {'plan': {'solutions': 'bad'}}]
        for patch in patches:
            with self.subTest(patch=patch), self.assertRaises(EddError):
                self.l.update('example', patch)

    def test_portable_validation_does_not_claim_current_checkout_passes(self):
        complete(self.l)
        (self.root / 'source.py').write_text('new=1\n', encoding='utf-8')
        self.assertTrue(self.l.validate('example'))
        self.assertEqual(self.l.validate('example', portable=True), [])
        self.assertTrue(self.l.resume('example')['errors'])

    def test_interrupted_archive_is_detected_and_resumable(self):
        complete(self.l)
        d = self.l.load('example')
        d.update(status='ARCHIVED', phase='ARCHIVED')
        from ledger import now
        d['history'].append({'from': 'COMPLETED', 'to': 'ARCHIVED', 'at': now(), 'reason': 'simulated interruption'})
        write_document(self.l.task_path('example') / 'task.md', d, '')
        self.assertTrue(any('歸檔中斷' in x for x in self.l.resume('example')['errors']))
        dest = self.l.archive('example')
        archived, _ = read_document(dest / 'task.md')
        self.assertEqual(len(archived['history']), len(d['history']))
        self.assertFalse(self.l.task_path('example').exists())

    def test_archive_io_failure_preserves_completed_state(self):
        from unittest.mock import patch
        complete(self.l)
        before = (self.l.task_path('example') / 'task.md').read_bytes()
        with patch('ledger.os.rename', side_effect=OSError('simulated disk error')):
            with self.assertRaises(OSError):
                self.l.archive('example')
        self.assertEqual(before, (self.l.task_path('example') / 'task.md').read_bytes())
        self.assertEqual(self.l.load('example')['status'], 'COMPLETED')
        self.l.archive('example')

    def test_gitlink_source_changes_invalidate_evidence(self):
        import subprocess
        vendor = self.root / 'vendor'
        subprocess.run(['git', 'init', '-q', str(vendor)], check=True)
        (vendor / 'code.py').write_text('x=1\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(vendor), 'add', 'code.py'], check=True)
        subprocess.run(['git', '-C', str(vendor), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '-qm', 'vendor'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'vendor'], check=True, capture_output=True)
        first = self.l.fingerprint()
        (vendor / 'code.py').write_text('x=2\n', encoding='utf-8')
        self.assertNotEqual(first, self.l.fingerprint())

    def test_evidence_wrong_json_shape_is_diagnostic(self):
        p = self.l.task_path('example') / 'bad.json'
        p.write_text('null', encoding='utf-8')
        self.assertTrue(self.l.evidence_errors('example', ['bad.json']))

    def test_actual_git_worktree_ledgers_are_isolated(self):
        import subprocess
        child = self.root / 'isolated-worktree'
        subprocess.run(['git', '-C', str(self.root), 'worktree', 'add', '--detach', str(child), 'HEAD'], check=True, capture_output=True)
        other = Ledger(child)
        other.init('example', 'research', 'separate task', ['fixture'], 'moderate')
        other.checkpoint('example', 'isolated baseline', 'work', 'verify', [])
        self.assertNotEqual(other.load('example')['worktree'], self.l.load('example')['worktree'])
        self.assertEqual(self.l.load('example')['checkpoint']['last_completed'], '')
        self.assertEqual(other.resume('example')['errors'], [])

    def test_worktree_mismatch_is_visible_in_resume(self):
        d = self.l.load('example')
        d['worktree'] = '/missing/worktree'
        write_document(self.l.task_path('example') / 'task.md', d, '')
        self.assertTrue(any('Worktree' in x for x in self.l.resume('example')['errors']))

    def test_non_done_agent_question_cannot_be_silently_integrated(self):
        self.l.register_agent('example', 'cause', 'research', ['fixture'])
        Ledger(self.root, actor='cause').handoff('example', 'cause', {'status': 'NEEDS_USER_DECISION', 'summary': 'ambiguous',
            'next_step': 'ask user', 'question': {'question_id': 'Q-001', 'source_agent': 'cause', 'question': 'A or B?',
            'context': 'contract', 'options': ['A', 'B'], 'recommendation': 'B', 'impact': 'result', 'status': 'WAITING_USER', 'answer': None}})
        with self.assertRaises(EddError):
            self.l.integrate('example', 'cause', 'ignore question')

for _name in list(LedgerTests.__dict__):
    if _name.startswith('test_'):
        setattr(GuardTests, _name, None)
del LedgerTests

if __name__ == '__main__':
    unittest.main()
