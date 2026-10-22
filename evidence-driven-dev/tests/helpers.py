"""Build an evidence-backed lifecycle in an isolated test repository."""
import sys
from ledger import atomic_text, now


def plan(l, task_id='example'):
    d = l.load(task_id)
    if d['status'] == 'CREATED':
        l.transition(task_id, 'INVESTIGATING')
    l.update(task_id, {'problem': {'description': 'replay fixture', 'expected': '契約成立', 'actual': '契約違反',
             'evidence': ['fixture replay'], 'hypotheses': [{'id': 'H1', 'claim': 'boundary mapping', 'status': 'UNCONFIRMED'}]}})
    l.transition(task_id, 'PLANNING')
    solutions = []
    for size in ('S', 'M', 'L'):
        solutions.append(dict(id=size, hypothesis='mapping defect', root_cause='boundary', benefit='correct result',
                              scope='fixture', complexity=size, cost='local CPU', risks='oracle ambiguity',
                              verification='fixture assertions', falsification='replay still fails', rollback='revert fixture'))
    l.update(task_id, {'plan': {'solutions': solutions, 'selected_solution': 'S', 'success': 'assertions pass',
                               'failure': 'assertions fail', 'regression': ['fixture cases'], 'approval_required': False}})
    return l.experiment(task_id, 'H1', 'boundary mapping', 'assertions pass', 'assertions fail')


def complete(l, task_id='example'):
    exp = plan(l, task_id)
    l.transition(task_id, 'EXPERIMENTING')
    ev = l.run(task_id, [sys.executable, '-c', 'assert 1 + 1 == 2'], 'experiment')
    l.conclude(task_id, exp['id'], 'SUPPORTED', [ev['path']], '隔離 fixture 契約成立')
    l.transition(task_id, 'IMPLEMENTING')
    l.update(task_id, {'changes': {'scope': ['fixture'], 'revision': l.revision(), 'diff_fingerprint': l.fingerprint(), 'tests': [ev['path']]}})
    l.transition(task_id, 'VERIFYING')
    reg = l.run(task_id, [sys.executable, '-c', 'assert all(x + 0 == x for x in [-1, 0, 1, 10])'], 'regression')
    l.decision(task_id, '採用最小修正', ['S', 'M', 'L'], 'replay 足以區分假設', '僅本地 fixture', '新證據出現', [exp['id']])
    l.update(task_id, {'acceptance': [{'id': 'AC-1', 'description': 'fixture assertions', 'status': 'PASS', 'evidence': [ev['path']]}],
             'verification': {'result': 'PASS', 'reviewer': 'independent-test-oracle', 'method': 'fresh subprocess assertions',
                              'verified_at': now(), 'revision': l.revision(), 'diff_fingerprint': l.fingerprint(),
                              'tests': [ev['path']], 'regression': [reg['path']], 'unverified': [], 'warnings': [], 'blocking_issues': []},
             'completion_summary': '測試 fixture 完成；非產品效能證明'})
    l.transition(task_id, 'COMPLETED')
    atomic_text(l.task_path(task_id) / 'final-report.md', '# 測試報告\n\n實際執行隔離 fixture 與 regression。\n')
    return ev
