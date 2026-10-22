"""EDD v1: a file-backed ledger. JSON frontmatter is a strict subset of YAML 1.2."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


class EddError(ValueError):
    pass


STATES = {'CREATED', 'INVESTIGATING', 'PLANNING', 'EXPERIMENTING', 'IMPLEMENTING',
          'VERIFYING', 'WAITING_USER', 'BLOCKED', 'CANCELLED', 'COMPLETED', 'ARCHIVED'}
ACTIVE = STATES - {'CANCELLED', 'COMPLETED', 'ARCHIVED'}
EDGES = {'CREATED': {'INVESTIGATING'}, 'INVESTIGATING': {'PLANNING'},
         'PLANNING': {'EXPERIMENTING', 'INVESTIGATING'},
         'EXPERIMENTING': {'IMPLEMENTING', 'INVESTIGATING', 'PLANNING'},
         'IMPLEMENTING': {'VERIFYING', 'INVESTIGATING', 'PLANNING'},
         'VERIFYING': {'COMPLETED', 'INVESTIGATING', 'PLANNING'},
         'COMPLETED': {'ARCHIVED', 'VERIFYING'}, 'ARCHIVED': set(), 'CANCELLED': set()}
AGENT_STATES = {'IN_PROGRESS', 'DONE', 'DONE_WITH_CONCERNS', 'BLOCKED', 'NEEDS_CONTEXT',
                'NEEDS_USER_DECISION', 'FAILED'}
VERIFY_RESULTS = {'PASS', 'PASS_WITH_WARNINGS', 'FAIL', 'BLOCKED', 'NOT_VERIFIED'}
ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,79}\Z')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise EddError('識別碼只允許小寫英數、底線、連字號，長度 1–80')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')


def confined(root, relative):
    root = Path(root).absolute()
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise EddError(f'禁止越界路徑：{relative}')
    target = root / p
    current = root
    if root.is_symlink():
        raise EddError(f'禁止 symlink：{root}')
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise EddError(f'禁止 symlink：{current}')
    if not target.resolve().is_relative_to(root.resolve()):
        raise EddError(f'禁止越界路徑：{relative}')
    return target


def atomic_text(path, text):
    path = Path(path)
    if path.is_symlink():
        raise EddError(f'禁止寫入 symlink：{path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    newline = '\r\n' if path.exists() and b'\r\n' in path.read_bytes() else '\n'
    text = text.replace('\r\n', '\n').replace('\n', newline)
    fd, name = tempfile.mkstemp(prefix='.edd-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_document(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
        parts = text.split('---\n', 2)
        if len(parts) != 3 or parts[0]:
            raise EddError(f'{path}：缺少 Frontmatter')
        meta = json.loads(parts[1])
        if not isinstance(meta, dict):
            raise EddError(f'{path}：Frontmatter 必須是物件')
        return meta, parts[2]
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise EddError(f'{path}：無法讀取 UTF-8 / JSON-subset YAML：{e}') from e


def write_document(path, meta, body):
    atomic_text(path, '---\n' + json.dumps(meta, ensure_ascii=False, indent=2) + '\n---\n' + body)


def task_body(d):
    def show(v):
        return json.dumps(v, ensure_ascii=False, indent=2)
    sections = [
        ('目標', d['goal']), ('問題定義（預期／實際／證據／未確認假設）', show(d['problem'])),
        ('範圍', '\n'.join('- ' + s for s in d['scope'])), ('限制', show(d['constraints'])),
        ('驗收標準', show(d['acceptance'])), ('工作進度', show(d['progress'])),
        ('Subagent Registry', show(d['agents'])), ('實驗', show(d['experiments'])),
        ('決策', '詳見 [decisions.md](decisions.md)。\n' + show(d['decisions'])),
        ('待使用者回答問題', show(d['questions'])), ('阻礙', show(d['blockers'])),
        ('Recovery Checkpoint', show(d['checkpoint'])), ('最終驗證', show(d['verification'])),
        ('完成摘要', d['completion_summary'])]
    return '# 任務：' + d['id'] + '\n\n' + '\n\n'.join('## ' + h + '\n\n' + v for h, v in sections) + '\n'


class Ledger:
    def __init__(self, root, actor='main-agent'):
        self.root = Path(root).resolve()
        self.home = confined(self.root, 'evidence-driven-dev')
        self.actor = actor

    def main_only(self):
        if self.actor != 'main-agent':
            raise EddError('只有 Main Agent 可以寫入主 Task；actor 是合作契約，不是 OS 安全邊界')

    @contextlib.contextmanager
    def lock(self):
        self.home.mkdir(parents=True, exist_ok=True)
        p = confined(self.home, '.edd.lock')
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as e:
            raise EddError('Ledger 正在寫入；若程序已中斷，確認無 writer 後手動移除 .edd.lock') from e
        try:
            os.write(fd, f'{os.getpid()}\n'.encode('utf-8'))
            yield
        finally:
            os.close(fd)
            p.unlink()

    def git(self, *args, binary=False):
        r = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, timeout=20)
        if r.returncode:
            raise EddError('Git 命令失敗：' + ' '.join(args))
        return r.stdout if binary else r.stdout.decode('utf-8').strip()

    def revision(self):
        return self.git('rev-parse', 'HEAD')

    def fingerprint(self):
        # Ledger outputs are excluded: recording evidence must not invalidate itself.
        h = hashlib.sha256()
        h.update(self.revision().encode('utf-8'))
        raw = self.git('ls-files', '--cached', '--others', '--exclude-standard', '-z', binary=True)
        for name in sorted(set(raw.split(b'\0')) - {b''}):
            rel = os.fsdecode(name)
            if (rel.startswith(('evidence-driven-dev/tasks/', 'evidence-driven-dev/archive/',
                                'evidence-driven-dev/.local/', 'evidence-driven-dev/reports/'))
                    or rel == 'evidence-driven-dev/.edd.lock'):
                continue
            p = self.root / rel
            h.update(name + b'\0')
            if p.is_symlink():
                h.update(b'link:' + os.fsencode(os.readlink(p)))
            elif p.is_file():
                h.update(str(p.stat().st_mode & 0o111).encode('ascii'))
                with p.open('rb') as f:
                    for block in iter(lambda: f.read(1024 * 1024), b''):
                        h.update(block)
            elif p.is_dir():
                child = Ledger(p)
                if child.git('rev-parse', '--show-toplevel') != str(p.resolve()):
                    raise EddError('未初始化或無法辨識的 Git 子目錄：' + rel)
                h.update(b'git-directory:' + child.fingerprint().encode('ascii'))
            else:
                h.update(b'deleted')
        return h.hexdigest()

    def task_path(self, task_id):
        return confined(self.home, 'tasks/' + identifier(task_id))

    def load(self, task_id):
        return read_document(confined(self.task_path(task_id), 'task.md'))[0]

    def save(self, d):
        d['updated_at'] = now()
        write_document(confined(self.task_path(d['id']), 'task.md'), d, task_body(d))

    def init(self, task_id, task_type='bugfix', goal=None, scope=None, complexity='moderate'):
        self.main_only()
        identifier(task_id)
        if task_type not in {'bugfix', 'feature', 'architecture', 'research'} or complexity not in {'moderate', 'complex'}:
            raise EddError('無效任務類型或複雜度；Trivial 使用輕量驗證即可')
        with self.lock():
            p = self.task_path(task_id)
            if p.exists() or any((self.home / 'archive').glob('*-' + task_id)):
                raise EddError('Task ID 已存在（包含歸檔）；請使用新識別碼')
            sha = self.revision()
            d = dict(schema_version=1, id=task_id, type=task_type, complexity=complexity,
                     status='CREATED', phase='INITIALIZATION', owner='main-agent',
                     base_git_sha=sha, branch=self.git('branch', '--show-current'), worktree=str(self.root),
                     openspec_change=None, updated_at=now(), goal=goal or task_id,
                     problem={'description': goal or task_id, 'expected': '', 'actual': '', 'evidence': [], 'hypotheses': []},
                     scope=scope or [], constraints=[], acceptance=[], progress=[], agents=[], experiments=[], decisions=[],
                     questions=[], blockers=[], waiting=None, paused_from=None,
                     checkpoint={'last_completed': '', 'current_action': '調查問題', 'next_action': '建立重現與基準',
                                 'required_inputs': [], 'unresolved_questions': []},
                     plan={}, changes={}, verification={}, completion_summary='',
                     history=[{'from': None, 'to': 'CREATED', 'at': now(), 'reason': '初始化'}])
            p.mkdir(parents=True)
            (p / 'experiments').mkdir()
            (p / 'agents').mkdir()
            atomic_text(p / 'decisions.md', '# 技術決策\n\n尚未採納方案；不得以備用程式碼代替決策紀錄。\n')
            self.save(d)
            return d

    def update(self, task_id, patch):
        self.main_only()
        allowed = {'phase', 'goal', 'problem', 'scope', 'constraints', 'acceptance', 'progress', 'plan',
                   'changes', 'verification', 'completion_summary', 'openspec_change', 'blockers'}
        if not isinstance(patch, dict) or set(patch) - allowed:
            raise EddError('patch 含受保護或未知欄位；狀態請用 transition')
        with self.lock():
            d = self.load(task_id)
            if d['status'] in {'ARCHIVED', 'CANCELLED'}:
                raise EddError('終止任務不可更新')
            d.update(patch)
            errors = self.schema_errors(d)
            if errors:
                raise EddError('; '.join(errors))
            self.save(d)
        return d

    def checkpoint(self, task_id, last, current, next_action, inputs):
        self.main_only()
        with self.lock():
            d = self.load(task_id)
            d['checkpoint'] = {'last_completed': last, 'current_action': current, 'next_action': next_action,
                               'required_inputs': inputs, 'unresolved_questions': [q['question_id'] for q in d['questions'] if q['status'] == 'WAITING_USER']}
            self.save(d)
        return d

    def schema_errors(self, d):
        errors = []
        required = {'schema_version': int, 'id': str, 'type': str, 'complexity': str, 'status': str, 'phase': str,
                    'owner': str, 'base_git_sha': str, 'branch': str, 'worktree': str, 'updated_at': str,
                    'goal': str, 'problem': dict, 'scope': list, 'constraints': list, 'acceptance': list,
                    'progress': list, 'agents': list, 'experiments': list, 'decisions': list, 'questions': list,
                    'blockers': list, 'checkpoint': dict, 'plan': dict, 'changes': dict, 'verification': dict,
                    'completion_summary': str, 'history': list}
        for key, typ in required.items():
            if key not in d or type(d[key]) is not typ:
                errors.append(f'Schema：{key} 必須是 {typ.__name__}')
        if errors:
            return errors
        if d['schema_version'] != 1 or d['status'] not in STATES or d['owner'] != 'main-agent':
            errors.append('Schema：版本、狀態或 Owner 無效')
        identifier(d['id'])
        if not re.fullmatch('[0-9a-f]{40,64}', d['base_git_sha']):
            errors.append('Schema：base_git_sha 無效')
        if d['type'] not in {'bugfix', 'feature', 'architecture', 'research'} or d['complexity'] not in {'moderate', 'complex'}:
            errors.append('Schema：type / complexity 無效')
        for key in ('description', 'expected', 'actual'):
            if not isinstance(d['problem'].get(key), str):
                errors.append('Schema：problem.' + key)
        for key in ('evidence', 'hypotheses'):
            if not isinstance(d['problem'].get(key), list):
                errors.append('Schema：problem.' + key)
        for key in ('last_completed', 'current_action', 'next_action'):
            if not isinstance(d['checkpoint'].get(key), str):
                errors.append('Schema：checkpoint.' + key)
        for key in ('required_inputs', 'unresolved_questions'):
            if not isinstance(d['checkpoint'].get(key), list):
                errors.append('Schema：checkpoint.' + key)
        if any(not isinstance(x, str) for x in d['scope']):
            errors.append('Schema：scope 必須為字串清單')
        for key in ('agents', 'experiments', 'questions', 'decisions', 'progress', 'acceptance'):
            if any(not isinstance(x, dict) for x in d[key]):
                errors.append('Schema：' + key + ' 必須為物件清單')
        hypotheses = d['problem'].get('hypotheses')
        for h in hypotheses if isinstance(hypotheses, list) else []:
            if not isinstance(h, dict) or not h.get('id') or not h.get('claim') or not isinstance(h.get('status'), str) or h.get('status') not in {'UNCONFIRMED', 'CONFIRMED', 'REFUTED'}:
                errors.append('Schema：根因假設需 id、claim 與合法 status')
        for c in d['acceptance']:
            if isinstance(c, dict) and (not c.get('id') or not isinstance(c.get('status'), str) or c.get('status') not in {'PENDING', 'PASS', 'FAIL'} or not isinstance(c.get('evidence', []), list)):
                errors.append('Schema：acceptance 項目格式錯誤')
        for group, keys in [('verification', ('tests', 'regression', 'warnings', 'unverified', 'blocking_issues')),
                            ('changes', ('scope', 'tests')), ('plan', ('solutions', 'regression', 'mvp'))]:
            for key in keys:
                if key in d[group] and not isinstance(d[group][key], list):
                    errors.append(f'Schema：{group}.{key} 必須為清單')
        if 'result' in d['verification'] and (not isinstance(d['verification']['result'], str) or d['verification']['result'] not in VERIFY_RESULTS):
            errors.append('Schema：verification.result 無效')
        solutions = d['plan'].get('solutions', [])
        if isinstance(solutions, list) and any(not isinstance(s, dict) for s in solutions):
            errors.append('Schema：plan.solutions 必須為物件清單')
        if 'reassessment' in d['plan']:
            errors.extend(self.reassessment_errors(d))
        try:
            dt.datetime.fromisoformat(d['updated_at'])
        except ValueError:
            errors.append('Schema：updated_at 必須是 ISO8601')
        return errors

    def edge_allowed(self, old, new, d):
        if old in {'WAITING_USER', 'BLOCKED'}:
            return new == d.get('paused_from') or new == 'CANCELLED'
        if old in ACTIVE and new in {'WAITING_USER', 'BLOCKED', 'CANCELLED'} and new != old:
            return True
        return new in EDGES.get(old, set())

    def gate_errors(self, d, target, current=True):
        errors = []
        def need(ok, reason):
            if not ok:
                errors.append(reason)
        p = d['problem']
        if target == 'INVESTIGATING':
            need(p.get('description') and d['scope'] and d['owner'], '問題、Scope 與 Owner 必須存在')
        if target == 'PLANNING':
            need(p.get('expected') and p.get('actual') and p.get('evidence') and p.get('hypotheses'), '必須定義預期／實際、觀察證據與根因假設')
            for h in p.get('hypotheses', []):
                need(isinstance(h, dict) and h.get('status') in {'UNCONFIRMED', 'CONFIRMED', 'REFUTED'} and h.get('claim'), '假設格式錯誤')
                if isinstance(h, dict) and h.get('status') == 'CONFIRMED':
                    need(h.get('evidence'), 'confirmed 根因必須有證據')
        if target == 'EXPERIMENTING':
            plan = d['plan']
            solutions = plan.get('solutions', [])
            need(isinstance(solutions, list) and len(solutions) >= 2, '至少比較兩個候選方案；S/M/L 不適用時記錄原因')
            fields = {'id', 'hypothesis', 'root_cause', 'benefit', 'scope', 'complexity', 'cost', 'risks', 'verification', 'falsification', 'rollback'}
            need(all(isinstance(s, dict) and fields <= s.keys() and all(s[k] for k in fields) for s in solutions), '候選方案必要欄位不完整')
            need(plan.get('success') and plan.get('failure') and d['experiments'], '必須定義成功、失敗與最小實驗')
            need(not plan.get('approval_required') or plan.get('approval'), '必要 User Gate 未通過')
            if plan.get('approval_required'):
                need(any(x.get('id') == plan.get('approval') and x.get('source') == 'user' for x in d['decisions']), '核准必須連結實際使用者決策')
            need(not self.failure_review_required(d) or plan.get('reassessment'), '同假設已三次失敗；先重新評估問題與 Oracle')
        if target == 'IMPLEMENTING':
            supported = []
            for item in d['experiments']:
                exp, _ = read_document(confined(self.task_path(d['id']), 'experiments/' + item['id'] + '.md'))
                if exp.get('conclusion') == 'SUPPORTED' and exp.get('evidence'):
                    errors.extend(self.evidence_errors(d['id'], exp['evidence']))
                    supported.append(exp)
            need(supported and d['plan'].get('selected_solution') and d['plan'].get('regression'), '必須有支持實驗、選定方案及 Regression 計畫')
            need(not self.failure_review_required(d) or d['plan'].get('reassessment'), '三次實質失敗後必須重新審查')
        if target == 'VERIFYING':
            c = d['changes']
            need(c.get('scope') and c.get('revision') and c.get('diff_fingerprint') and c.get('tests'), '需保存變更範圍、版本、Diff 與已執行測試')
            if c.get('tests'):
                errors.extend(self.evidence_errors(d['id'], c['tests'], fresh=current,
                              expected_revision=c.get('revision'), expected_fingerprint=c.get('diff_fingerprint')))
            if current:
                need(c.get('revision') == self.revision() and c.get('diff_fingerprint') == self.fingerprint(), '變更版本與目前工作樹不一致')
        if target in {'COMPLETED', 'ARCHIVED'}:
            errors.extend(self.gate_errors(d, 'INVESTIGATING'))
            for item in d['agents']:
                errors.extend(self.agent_errors(d['id'], item))
            v = d['verification']
            need(v.get('result') in {'PASS', 'PASS_WITH_WARNINGS'}, '缺少通過的最終驗證')
            need(v.get('reviewer') and v.get('method') and v.get('verified_at'), '需獨立驗證者／方法／時間')
            need('unverified' in v and 'warnings' in v, '需揭露未驗證項目與風險')
            need(not v.get('blocking_issues') and not d['blockers'], '仍有 Blocking Issues')
            need(not any(q.get('status') == 'WAITING_USER' for q in d['questions']), '仍有待回答 User Gate')
            need(d['acceptance'] and all(c.get('status') == 'PASS' and c.get('evidence') for c in d['acceptance']), '驗收標準未全部驗證')
            for criterion in d['acceptance']:
                if criterion.get('evidence'):
                    errors.extend(self.evidence_errors(d['id'], criterion['evidence'], fresh=target != 'ARCHIVED' and current,
                                  expected_revision=v.get('revision'), expected_fingerprint=v.get('diff_fingerprint')))
            need(v.get('tests') and v.get('regression'), '必要測試與 Regression 不可缺少')
            errors.extend(self.evidence_errors(d['id'], v.get('tests', []) + v.get('regression', []), fresh=target != 'ARCHIVED' and current,
                          expected_revision=v.get('revision'), expected_fingerprint=v.get('diff_fingerprint')))
            if target == 'COMPLETED' and current:
                need(v.get('revision') == self.revision() and v.get('diff_fingerprint') == self.fingerprint(), '最終驗證已過期，請重新驗證')
            if v.get('unverified') or v.get('warnings'):
                need(v.get('result') == 'PASS_WITH_WARNINGS', '有未驗證或警告時不得標為 PASS')
            need(d['decisions'] and d['completion_summary'], '需更新決策與完成摘要')
            for a in d['agents']:
                need(a.get('integrated') is True, 'Subagent Handoff 尚未整合：' + str(a.get('id')))
                need(a.get('status') in {'DONE', 'DONE_WITH_CONCERNS'} or a.get('disposition'), '未完成 Subagent 需明確處置')
            if target == 'ARCHIVED':
                need(confined(self.task_path(d['id']), 'final-report.md').is_file(), '歸檔前需 Final Report')
        return errors

    def transition(self, task_id, target, reason='', **extra):
        self.main_only()
        with self.lock():
            d = self.load(task_id)
            self._transition(d, target, reason, **extra)
            self.save(d)
        return d

    def _transition(self, d, target, reason='', **extra):
        errors = self.schema_errors(d)
        if errors:
            raise EddError('; '.join(errors))
        if target not in STATES or not self.edge_allowed(d['status'], target, d):
            raise EddError(f'不允許轉移：{d["status"]} → {target}')
        if target == 'ARCHIVED':
            raise EddError('歸檔請使用 archive')
        if target == 'WAITING_USER' and not d.get('waiting'):
            raise EddError('WAITING_USER 請使用 ask，保存問題與恢復條件')
        if target == 'BLOCKED' and not d['blockers']:
            raise EddError('BLOCKED 必須記錄阻礙與恢復條件')
        errors = self.gate_errors(d, target)
        for required in ('decisions.md', 'experiments', 'agents'):
            if not confined(self.task_path(d['id']), required).exists():
                errors.append('缺少必要紀錄：' + required)
        if errors:
            raise EddError('; '.join(errors))
        old = d['status']
        if target in {'WAITING_USER', 'BLOCKED'}:
            d['paused_from'] = old
        d['status'] = target
        d['phase'] = target
        d['history'].append({'from': old, 'to': target, 'at': now(), 'reason': reason,
                             'paused_from': d.get('paused_from')})
        if old in {'WAITING_USER', 'BLOCKED'} and target not in {'WAITING_USER', 'BLOCKED'}:
            d['paused_from'] = None

    def list_tasks(self):
        folder = confined(self.home, 'tasks')
        if not folder.exists():
            return []
        results = []
        for p in sorted(folder.iterdir()):
            if p.is_dir():
                try:
                    d = self.load(p.name)
                    results.append({'id': d['id'], 'status': d['status'], 'phase': d['phase'],
                                    'blockers': d['blockers'], 'questions': d['questions'], 'checkpoint': d['checkpoint']})
                except (EddError, KeyError) as e:
                    results.append({'id': p.name, 'error': str(e)})
        return results

    def resolve(self, task_id=None, session_id=None):
        if task_id:
            self.load(task_id)
            return task_id
        if session_id:
            binding = confined(self.home, '.local/bindings.json')
            if binding.exists():
                data = json.loads(binding.read_text(encoding='utf-8'))
                if session_id in data:
                    task_id = data[session_id]
                    self.load(task_id)
                    return task_id
        active = [d for d in self.list_tasks() if d.get('status') in ACTIVE]
        matches = [d for d in active if self.load(d['id']).get('worktree') == str(self.root)
                   and self.load(d['id']).get('branch') == self.git('branch', '--show-current')]
        if len(matches) == 1:
            return matches[0]['id']
        if active:
            raise EddError('無法唯一判斷 Active Task；請指定 --id 或 bind session：' + ', '.join(d['id'] for d in active))
        return None

    def bind(self, task_id, session_id):
        self.main_only()
        with self.lock():
            self.load(task_id)
            p = confined(self.home, '.local/bindings.json')
            d = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
            d[session_id] = task_id
            atomic_text(p, json.dumps(d, ensure_ascii=False, indent=2) + '\n')

    def validate(self, task_id, completion=False, portable=False):
        try:
            d = self.load(task_id)
            errors = self.schema_errors(d)
            if errors:
                return errors
            if d['id'] != task_id:
                errors.append('Task ID 與目錄不一致')
            if d['status'] == 'ARCHIVED':
                errors.append('歸檔中斷：ARCHIVED 仍位於 tasks；確認目標後重新執行 archive')
            if not portable and d['worktree'] != str(self.root):
                errors.append('Worktree 與建立任務時不同；先確認原始未提交變更是否存在')
            if not portable and d['branch'] != self.git('branch', '--show-current'):
                errors.append('Branch 與建立任務時不同；需核對版本後再恢復')
            p = self.task_path(task_id)
            for name in ('decisions.md', 'experiments', 'agents'):
                if not confined(p, name).exists():
                    errors.append('缺少必要紀錄：' + name)
            history = d['history']
            previous = None
            for i, h in enumerate(history):
                if not isinstance(h, dict) or h.get('from') != previous:
                    errors.append('轉移歷史不連續')
                    break
                target = h.get('to')
                if i == 0:
                    if target != 'CREATED':
                        errors.append('歷史必須起於 CREATED')
                elif target == 'ARCHIVED' and previous == 'COMPLETED':
                    pass
                elif not self.edge_allowed(previous, target, h):
                    errors.append(f'歷史包含非法轉移：{previous} → {target}')
                previous = target
            if not history or previous != d['status']:
                errors.append('目前狀態與轉移歷史不一致')
            if d['status'] == 'WAITING_USER':
                w = d.get('waiting') or {}
                for key in ('previous_status', 'question_id', 'source', 'impact', 'resume_condition'):
                    if not w.get(key):
                        errors.append('WAITING_USER 缺少：' + key)
                if not any(q.get('question_id') == w.get('question_id') and q.get('status') == 'WAITING_USER' for q in d['questions']):
                    errors.append('WAITING_USER 問題不存在')
            for a in d['agents']:
                errors.extend(self.agent_errors(task_id, a))
            for item in d['experiments']:
                exp, _ = read_document(confined(p, 'experiments/' + item['id'] + '.md'))
                if exp.get('status') == 'FINISHED':
                    errors.extend(self.evidence_errors(task_id, exp.get('evidence', []), require_pass=False))
                    if not exp.get('evidence') or exp.get('conclusion') not in {'SUPPORTED', 'REFUTED', 'INCONCLUSIVE'}:
                        errors.append('實驗結果缺少證據／結論：' + item['id'])
            if d['status'] in {'PLANNING', 'EXPERIMENTING', 'IMPLEMENTING', 'VERIFYING', 'COMPLETED', 'ARCHIVED'}:
                errors.extend(self.gate_errors(d, d['status'], current=not portable))
            if completion and d['status'] not in {'COMPLETED', 'ARCHIVED'}:
                errors.extend(self.gate_errors(d, 'COMPLETED', current=not portable))
            return list(dict.fromkeys(errors))
        except (EddError, OSError, KeyError, TypeError, ValueError) as e:
            return ['紀錄無效：' + str(e)]

    def resume(self, task_id):
        d = self.load(task_id)
        return {'task': d, 'errors': self.validate(task_id), 'git': {'revision': self.revision(),
                'branch': self.git('branch', '--show-current'), 'worktree': str(self.root)},
                'warning': '只恢復上下文；不會重跑命令或自動重啟 Subagent。版本／檔案不一致必須重新驗證。'}

    def run(self, task_id, command, kind, timeout=60):
        self.main_only()
        if not command or not all(isinstance(c, str) for c in command):
            raise EddError('必須提供明確 argv；不從 Markdown 執行命令')
        self.load(task_id)
        revision, fingerprint = self.revision(), self.fingerprint()
        evidence_id = 'EV-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        p = self.task_path(task_id)
        raw = confined(p, '.local/' + evidence_id + '.log')
        raw.parent.mkdir(exist_ok=True)
        started = now()
        try:
            with raw.open('w', encoding='utf-8') as out:
                proc = subprocess.Popen(command, cwd=self.root, stdout=out, stderr=subprocess.STDOUT,
                                        text=True, encoding='utf-8', start_new_session=True)
                try:
                    code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    code = 124
        except OSError as e:
            atomic_text(raw, str(e) + '\n')
            code = 127
        after = self.fingerprint()
        record = {'id': evidence_id, 'kind': kind, 'command': command, 'cwd': str(self.root),
                  'started_at': started, 'finished_at': now(), 'exit_code': code,
                  'revision': revision, 'diff_fingerprint': fingerprint, 'post_fingerprint': after,
                  'source_unchanged': after == fingerprint, 'output_sha256': digest(raw.read_bytes()),
                  'raw_output': str(raw.relative_to(p)), 'output_policy': '原始輸出僅保留於 Git 忽略目錄；分享前審查敏感資料'}
        record['digest'] = digest(canonical(record))
        rel = 'evidence/' + evidence_id + '.json'
        with self.lock():
            atomic_text(confined(p, rel), json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        return {'path': rel, **record}

    def evidence_errors(self, task_id, refs, fresh=False, require_pass=True, expected_revision=None, expected_fingerprint=None):
        errors = []
        if not isinstance(refs, list):
            return ['證據參照必須為清單']
        for ref in refs:
            try:
                p = confined(self.task_path(task_id), ref)
                ev = json.loads(p.read_text(encoding='utf-8'))
                if not isinstance(ev, dict):
                    raise EddError('證據 JSON 必須為物件')
                stored = ev.pop('digest', None)
                if stored != digest(canonical(ev)):
                    errors.append('證據摘要不符：' + ref)
                if require_pass and ev.get('exit_code') != 0:
                    errors.append('測試未通過：' + ref)
                if not ev.get('source_unchanged'):
                    errors.append('測試過程改變程式版本，結果不能驗收：' + ref)
                if not all(k in ev for k in ('command', 'finished_at', 'revision', 'diff_fingerprint', 'output_sha256')):
                    errors.append('證據欄位不完整：' + ref)
                if fresh and (ev.get('revision') != self.revision() or ev.get('diff_fingerprint') != self.fingerprint()):
                    errors.append('測試證據已過期：' + ref)
                if expected_revision and ev.get('revision') != expected_revision:
                    errors.append('證據與宣告的 Git Revision 不一致：' + ref)
                if expected_fingerprint and ev.get('diff_fingerprint') != expected_fingerprint:
                    errors.append('證據與宣告的 Diff Fingerprint 不一致：' + ref)
                raw = confined(self.task_path(task_id), ev.get('raw_output', '.local/missing'))
                if raw.exists() and digest(raw.read_bytes()) != ev.get('output_sha256'):
                    errors.append('原始輸出摘要不符：' + ref)
            except (EddError, OSError, ValueError, TypeError) as e:
                errors.append('證據無法讀取：' + str(e))
        return errors

    def ask(self, task_id, question_id, source, question, context, options, recommendation, impact):
        self.main_only()
        if not re.fullmatch(r'Q-\d{3,}', question_id) or not all((source, question, context, impact)):
            raise EddError('問題必須有 Q-NNN、來源、問題、證據脈絡與影響')
        with self.lock():
            d = self.load(task_id)
            if d['status'] in {'WAITING_USER', 'BLOCKED', 'CANCELLED', 'COMPLETED', 'ARCHIVED'}:
                raise EddError('請先處理目前暫停／終止狀態；不要覆蓋等待資訊')
            if any(q['question_id'] == question_id for q in d['questions']):
                raise EddError('問題 ID 已存在')
            q = dict(question_id=question_id, source_agent=source, question=question, context=context,
                     options=options, recommendation=recommendation, impact=impact, status='WAITING_USER', answer=None)
            d['questions'].append(q)
            d['waiting'] = {'previous_status': d['status'], 'question_id': question_id, 'source': source,
                            'impact': impact, 'resume_condition': 'Main Agent 記錄使用者答案並轉交原 Agent'}
            d['checkpoint']['unresolved_questions'].append(question_id)
            self._transition(d, 'WAITING_USER', question_id)
            self.save(d)
        return q

    def answer(self, task_id, question_id, answer, evidence):
        self.main_only()
        if not answer or not evidence:
            raise EddError('必須記錄實際答案與使用者訊息來源')
        with self.lock():
            d = self.load(task_id)
            if d['status'] != 'WAITING_USER' or d['waiting']['question_id'] != question_id:
                raise EddError('目前未等待此問題')
            q = next(q for q in d['questions'] if q['question_id'] == question_id)
            q.update(status='ANSWERED', answer=answer, answer_evidence=evidence)
            dec = {'id': 'DEC-' + str(len(d['decisions']) + 1).zfill(3), 'source': 'user', 'question_id': question_id,
                   'summary': answer, 'evidence': evidence, 'at': now()}
            d['decisions'].append(dec)
            target = d['waiting']['previous_status']
            self._transition(d, target, '使用者已回答 ' + question_id)
            self._decision_text(d, dec)
            d['waiting'] = None
            d['checkpoint']['unresolved_questions'] = [x for x in d['checkpoint']['unresolved_questions'] if x != question_id]
            self.save(d)
        return d

    def _decision_text(self, d, dec):
        p = confined(self.task_path(d['id']), 'decisions.md')
        previous = p.read_text(encoding='utf-8')
        atomic_text(p, previous + '\n## ' + dec['id'] + '\n\n```json\n' + json.dumps(dec, ensure_ascii=False, indent=2) + '\n```\n')

    def decision(self, task_id, summary, alternatives, reason, risks, revisit, refs):
        self.main_only()
        with self.lock():
            d = self.load(task_id)
            dec = dict(id='DEC-' + str(len(d['decisions']) + 1).zfill(3), status='ACCEPTED', source='main-agent',
                       summary=summary, alternatives=alternatives, reason=reason, risks=risks, revisit=revisit, references=refs, at=now())
            self._decision_text(d, dec)
            d['decisions'].append(dec)
            self.save(d)
        return dec

    def failure_review_required(self, d):
        return any(n >= 3 for n in self.failure_streaks(d).values())

    def failure_streaks(self, d):
        streaks = {}
        for item in d['experiments']:
            exp, _ = read_document(confined(self.task_path(d['id']), 'experiments/' + item['id'] + '.md'))
            h = exp.get('hypothesis_id')
            if exp.get('status') != 'FINISHED' or not exp.get('substantive_fix'):
                continue
            streaks[h] = streaks.get(h, 0) + 1 if exp.get('conclusion') == 'REFUTED' else 0
        return streaks

    def reassessment_errors(self, d):
        review = d['plan'].get('reassessment')
        keys = {'experiments', 'rejected_hypothesis', 'oracle_review', 'problem_review', 'new_direction', 'new_hypothesis_id'}
        if not isinstance(review, dict) or not keys <= review.keys() or not all(review[k] for k in keys):
            return ['reassessment 需結構化記錄三次實驗、否定假設、Oracle／問題重查與新方向／新假設']
        ids = {x['id'] for x in d['experiments']}
        if (not isinstance(review['experiments'], list) or any(not isinstance(x, str) for x in review['experiments'])
                or len(set(review['experiments'])) < 3 or not set(review['experiments']) <= ids):
            return ['reassessment 必須引用至少三個既有實驗']
        if review['new_hypothesis_id'] == review['rejected_hypothesis']:
            return ['重新評估必須改變方向，不能繼續相同被否定假設']
        return []

    def experiment(self, task_id, hypothesis_id, hypothesis, success, failure, substantive_fix=False):
        self.main_only()
        if not all((hypothesis_id, hypothesis, success, failure)):
            raise EddError('最小實驗必須定義假設、成功與失敗標準')
        with self.lock():
            d = self.load(task_id)
            if self.failure_review_required(d):
                errors = self.reassessment_errors(d)
                if errors or self.failure_streaks(d).get(hypothesis_id, 0) >= 3:
                    raise EddError('三次實質失敗：停止同假設調整；先記錄有效 reassessment 與新假設。' + '; '.join(errors))
                if hypothesis_id != d['plan']['reassessment']['new_hypothesis_id']:
                    raise EddError('新實驗需對應重新評估的新假設')
            eid = 'EXP-' + str(len(d['experiments']) + 1).zfill(3)
            p = confined(self.task_path(task_id), 'experiments/' + eid + '.md')
            if p.exists():
                raise EddError('實驗檔已存在，不可覆蓋')
            exp = dict(id=eid, hypothesis_id=hypothesis_id, hypothesis=hypothesis, success=success, failure=failure,
                       substantive_fix=substantive_fix, status='PLANNED', conclusion=None, evidence=[],
                       git_sha=self.revision(), diff_fingerprint=self.fingerprint(), created_at=now())
            body = '# ' + eid + '\n\n' + '\n\n'.join('## ' + s + '\n\n待執行後記錄。' for s in
                   ['支持假設的證據', 'Baseline', 'Input Snapshot', '環境與設定（Model／Provider／Prompt／Dataset／Token／Latency）',
                    '測試命令', '預期結果', '實際結果', 'Metrics', 'Interpretation', '下一步']) + '\n'
            write_document(p, exp, body)
            d['experiments'].append({'id': eid, 'hypothesis_id': hypothesis_id})
            self.save(d)
        return exp

    def conclude(self, task_id, experiment_id, conclusion, refs, interpretation):
        self.main_only()
        if conclusion not in {'SUPPORTED', 'REFUTED', 'INCONCLUSIVE'} or not refs or not interpretation:
            raise EddError('必須提供結論、實際證據與解釋')
        with self.lock():
            d = self.load(task_id)
            if experiment_id not in [x['id'] for x in d['experiments']]:
                raise EddError('實驗不在 Registry')
            p = confined(self.task_path(task_id), 'experiments/' + experiment_id + '.md')
            exp, body = read_document(p)
            if exp['status'] == 'FINISHED':
                raise EddError('歷史實驗不可覆蓋；建立新實驗')
            errors = self.evidence_errors(task_id, refs, require_pass=conclusion == 'SUPPORTED')
            if errors:
                raise EddError('; '.join(errors))
            exp.update(status='FINISHED', conclusion=conclusion, evidence=refs, interpretation=interpretation, finished_at=now())
            write_document(p, exp, body + '\n## 執行結論\n\n' + interpretation + '\n')
            d['checkpoint']['last_completed'] = experiment_id + ' ' + conclusion
            self.save(d)
        return exp

    def agent_errors(self, task_id, item):
        p = confined(self.task_path(task_id), 'agents/' + identifier(item['id']) + '/task.md')
        a, body = read_document(p)
        errors = []
        if a.get('agent_id') != item['id'] or a.get('parent_task') != task_id or a.get('status') != item.get('status'):
            errors.append('Subagent Registry / Report 不一致：' + item['id'])
        if a.get('status') not in AGENT_STATES or not a.get('base_git_sha') or not a.get('allowed_scope'):
            errors.append('Subagent Schema 錯誤：' + item['id'])
        if a.get('status') != 'IN_PROGRESS':
            handoff = a.get('handoff', {})
            if not handoff.get('summary') or not handoff.get('next_step') or handoff.get('status') != a['status']:
                errors.append('缺少結構化 Handoff：' + item['id'])
            if a['status'] in {'DONE', 'DONE_WITH_CONCERNS'} and not handoff.get('evidence'):
                errors.append('DONE 缺少證據：' + item['id'])
            if a['status'] == 'NEEDS_USER_DECISION' and not a.get('question'):
                errors.append('缺少需轉交的問題：' + item['id'])
            if a['status'] == 'BLOCKED' and not a.get('blockers'):
                errors.append('BLOCKED 缺少阻礙：' + item['id'])
        return errors

    def register_agent(self, task_id, agent_id, assignment, scope, platform_id=None, worktree=None):
        self.main_only()
        identifier(agent_id)
        if not assignment or not scope:
            raise EddError('Agent 必須有明確任務與允許範圍')
        with self.lock():
            d = self.load(task_id)
            if any(a['id'] == agent_id or (platform_id and a.get('platform_id') == platform_id) for a in d['agents']):
                raise EddError('Agent ID / platform ID 重複')
            p = confined(self.task_path(task_id), 'agents/' + agent_id + '/task.md')
            if p.exists():
                raise EddError('Agent Report 已存在')
            a = dict(parent_task=task_id, agent_id=agent_id, role='subagent', status='IN_PROGRESS',
                     base_git_sha=self.revision(), assignment=assignment, allowed_scope=scope,
                     worktree=worktree or str(self.root), platform_id=platform_id, handoff={}, blockers=[], question=None)
            headings = ['任務', '允許範圍', '禁止事項', '輸入', '調查', '假設', '實驗', '發現', '變更檔案', '待釐清問題', 'Handoff']
            write_document(p, a, '# Subagent 任務\n\n禁止修改主 task.md、其他 Agent 紀錄、驗收標準或擴大範圍。\n\n' +
                           '\n\n'.join('## ' + h for h in headings) + '\n')
            d['agents'].append({'id': agent_id, 'status': 'IN_PROGRESS', 'report': 'agents/' + agent_id + '/task.md',
                                'platform_id': platform_id, 'integrated': False})
            self.save(d)
        return a

    def map_agent(self, task_id, agent_id, platform_id):
        self.main_only()
        if not platform_id:
            raise EddError('必須提供實際平台 Agent ID')
        with self.lock():
            d = self.load(task_id)
            item = next((a for a in d['agents'] if a['id'] == agent_id), None)
            if item is None or any(a['id'] != agent_id and a.get('platform_id') == platform_id for a in d['agents']):
                raise EddError('未知 Agent 或重複平台 ID')
            item['platform_id'] = platform_id
            p = confined(self.task_path(task_id), item['report'])
            a, body = read_document(p)
            a['platform_id'] = platform_id
            write_document(p, a, body)
            self.save(d)

    def hooks_mode(self, mode):
        self.main_only()
        if mode not in {'advisory', 'enforce'}:
            raise EddError('Hook mode 必須是 advisory 或 enforce')
        with self.lock():
            p = confined(self.home, 'config.yaml')
            d = json.loads(p.read_text(encoding='utf-8'))
            d['hooks_mode'] = mode
            atomic_text(p, json.dumps(d, ensure_ascii=False, indent=2) + '\n')

    def handoff(self, task_id, agent_id, report):
        if self.actor != agent_id:
            raise EddError('只能由對應 Agent 寫入自己的 Handoff')
        with self.lock():
            p = confined(self.task_path(task_id), 'agents/' + identifier(agent_id) + '/task.md')
            a, body = read_document(p)
            if report.get('status') not in AGENT_STATES - {'IN_PROGRESS'} or not report.get('summary') or not report.get('next_step'):
                raise EddError('Handoff 需有合法終止狀態、摘要與下一步')
            a.update(status=report['status'], handoff=report, blockers=report.get('blockers', []), question=report.get('question'))
            write_document(p, a, body)
        return a

    def integrate(self, task_id, agent_id, disposition=''):
        self.main_only()
        with self.lock():
            d = self.load(task_id)
            item = next((a for a in d['agents'] if a['id'] == agent_id), None)
            if not item:
                raise EddError('未知 Agent')
            a, _ = read_document(confined(self.task_path(task_id), item['report']))
            item['status'] = a['status']
            errors = self.agent_errors(task_id, item)
            if errors or a['status'] == 'IN_PROGRESS':
                raise EddError('; '.join(errors) or 'Agent 尚未交接')
            if a['status'] not in {'DONE', 'DONE_WITH_CONCERNS'} and not disposition:
                raise EddError('非 DONE 必須由 Main Agent 說明處置，不可當成成功')
            if a['status'] == 'NEEDS_USER_DECISION':
                question_id = a.get('question', {}).get('question_id')
                if not any(q.get('question_id') == question_id and q.get('status') == 'ANSWERED' for q in d['questions']):
                    raise EddError('必須由 Main 真正取得並記錄使用者答案後才能整合 NEEDS_USER_DECISION')
            item.update(integrated=True, disposition=disposition, integrated_at=now())
            d['checkpoint']['last_completed'] = '已審核 Handoff：' + agent_id
            self.save(d)
        return a

    def archive(self, task_id):
        self.main_only()
        with self.lock():
            d = self.load(task_id)
            recovering = d['status'] == 'ARCHIVED'
            if d['status'] not in {'COMPLETED', 'ARCHIVED'}:
                raise EddError('只有 COMPLETED 可以歸檔')
            errors = [e for e in self.validate(task_id, portable=True) if not (recovering and e.startswith('歸檔中斷：'))]
            errors += self.gate_errors(d, 'ARCHIVED', current=False)
            if errors:
                raise EddError('; '.join(errors))
            dest = confined(self.home, 'archive/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d') + '-' + task_id)
            if dest.exists():
                raise EddError('同名 Archive 已存在，不會覆蓋')
            dest.parent.mkdir(exist_ok=True)
            original = (self.task_path(task_id) / 'task.md').read_text(encoding='utf-8')
            if not recovering:
                d['status'] = 'ARCHIVED'
                d['phase'] = 'ARCHIVED'
                d['history'].append({'from': 'COMPLETED', 'to': 'ARCHIVED', 'at': now(), 'reason': '歸檔'})
                self.save(d)
            try:
                os.rename(self.task_path(task_id), dest)
            except OSError:
                atomic_text(self.task_path(task_id) / 'task.md', original)
                raise
        return dest
