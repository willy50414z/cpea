import json
import subprocess
import sys
import unittest
from pathlib import Path
from test_ledger import LedgerTests
from ledger import Ledger, atomic_text
from hook_runtime import handle
from helpers import complete


class HookTests(LedgerTests):
    def setUp(self):
        super().setUp()
        atomic_text(self.l.home / 'config.yaml', json.dumps({'schema_version': 1, 'hooks_mode': 'enforce'}))

    def event(self, name, **kwargs):
        return dict(hook_event_name=name, cwd=str(self.root), session_id='test-session', stop_hook_active=False, **kwargs)

    def test_stop_blocks_unverified_claim_once(self):
        e = self.event('Stop', last_assistant_message='已完成 [EDD-COMPLETE:example]')
        self.assertEqual(handle(self.root, 'Stop', e)['decision'], 'block')
        e['stop_hook_active'] = True
        self.assertNotIn('decision', handle(self.root, 'Stop', e))

    def test_advisory_does_not_block(self):
        self.l.hooks_mode('advisory')
        out = handle(self.root, 'Stop', self.event('Stop', last_assistant_message='[EDD-COMPLETE:example]'))
        self.assertIn('systemMessage', out)
        self.assertNotIn('decision', out)

    def test_unrelated_and_stage_reports_unaffected(self):
        for text in ('一般聊天', '先報告目前進度', '測試完成，仍待驗收'):
            self.assertEqual(handle(self.root, 'Stop', self.event('Stop', last_assistant_message=text)), {})

    def test_waiting_user_and_blocked_allow_stop(self):
        self.l.ask('example', 'Q-001', 'main-agent', 'Oracle?', 'ambiguity', ['A', 'B'], 'A', 'scope')
        e = self.event('Stop', last_assistant_message='[EDD-COMPLETE:example]')
        self.assertNotIn('decision', handle(self.root, 'Stop', e))
        self.l.answer('example', 'Q-001', 'A', '測試使用者事件')
        self.l.update('example', {'blockers': ['缺少外部 fixture；提供後恢復']})
        self.l.transition('example', 'BLOCKED')
        self.assertNotIn('decision', handle(self.root, 'Stop', e))

    def test_complete_with_evidence_and_stale_detection(self):
        complete(self.l)
        e = self.event('Stop', last_assistant_message='[EDD-COMPLETE:example]')
        self.assertEqual(handle(self.root, 'Stop', e), {})
        (self.root / 'changed.py').write_text('v=2\n', encoding='utf-8')
        self.assertEqual(handle(self.root, 'Stop', e)['decision'], 'block')
        self.assertTrue(self.l.resume('example')['errors'])

    def test_session_multiple_tasks_requires_id(self):
        self.l.init('other', 'feature', 'other', ['x'], 'moderate')
        e = self.event('SessionStart', source='resume')
        self.assertIn('systemMessage', handle(self.root, 'SessionStart', e))
        self.l.bind('example', 'test-session')
        out = handle(self.root, 'SessionStart', e)['hookSpecificOutput']
        self.assertEqual(out['hookEventName'], 'SessionStart')
        self.assertIn('checkpoint', out['additionalContext'])

    def test_subagent_missing_handoff_and_unknown_id(self):
        self.l.register_agent('example', 'cause', 'read only', ['fixture'], 'platform-1')
        e = self.event('SubagentStop', agent_id='platform-1')
        self.assertEqual(handle(self.root, 'SubagentStop', e)['decision'], 'block')
        e['agent_id'] = 'unknown'
        self.assertNotIn('decision', handle(self.root, 'SubagentStop', e))

    def test_subagent_question_goes_to_main_and_never_loops(self):
        self.l.register_agent('example', 'cause', 'read only', ['fixture'], 'platform-1')
        Ledger(self.root, actor='cause').handoff('example', 'cause', {'status': 'NEEDS_USER_DECISION', 'summary': 'Oracle ambiguity',
            'next_step': 'Main 詢問使用者', 'question': {'question_id': 'Q-001', 'question': 'A or B?', 'context': 'two contracts',
            'source_agent': 'cause', 'options': ['A', 'B'], 'recommendation': 'B', 'impact': 'result', 'status': 'WAITING_USER', 'answer': None}})
        out = handle(self.root, 'SubagentStop', self.event('SubagentStop', agent_id='platform-1'))
        self.assertIn('Main', out['systemMessage'])
        self.assertNotIn('decision', out)

    def test_malformed_and_foreign_cwd_fail_open(self):
        self.assertIn('systemMessage', handle(self.root, 'Stop', []))
        e = self.event('Stop', last_assistant_message='[EDD-COMPLETE:../escape]')
        self.assertEqual(handle(self.root, 'Stop', e), {})
        e['cwd'] = '/another/repo'
        self.assertNotIn('decision', handle(self.root, 'Stop', e))
        atomic_text(self.l.home / 'config.yaml', 'broken json')
        self.assertNotIn('decision', handle(self.root, 'Stop', self.event('Stop', last_assistant_message='[EDD-COMPLETE:example]')))

    def test_valid_json_wrong_types_always_fail_open(self):
        e = self.event('Stop', last_assistant_message='[EDD-COMPLETE:example]')
        for value in ('[]', 'null', '1', '"text"'):
            atomic_text(self.l.home / 'config.yaml', value)
            self.assertIn('systemMessage', handle(self.root, 'Stop', e))
        e['cwd'] = []
        self.assertNotIn('decision', handle(self.root, 'Stop', e))

    def test_wrappers_always_emit_json_on_bad_input(self):
        root = Path(__file__).resolve().parents[2]
        for name in ('edd_session', 'edd_subagent_stop', 'edd_stop'):
            r = subprocess.run([sys.executable, str(root / '.codex/hooks' / (name + '.py'))],
                               input='not-json', capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('systemMessage', json.loads(r.stdout))

for _name in list(LedgerTests.__dict__):
    if _name.startswith('test_'):
        setattr(HookTests, _name, None)
del LedgerTests

if __name__ == '__main__':
    unittest.main()
