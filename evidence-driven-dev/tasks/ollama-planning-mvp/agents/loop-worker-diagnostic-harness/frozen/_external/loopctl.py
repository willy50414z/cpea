"""Bounded EDD coordination and one-at-a-time managed HTTP model attempts."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import base64
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'edd/scripts'))
from ledger import Ledger


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Controller:
    def __init__(self, root, task_id):
        self.ledger = Ledger(root)
        self.root = self.ledger.root
        self.task_id = task_id

    def _target(self, task):
        return dict(goal=task['goal'], acceptance=[dict(id=a['id'], description=a['description'])
                                                   for a in task['acceptance']])

    def _task_gate(self, task):
        if task['status'] in ('WAITING_USER', 'BLOCKED'):
            return dict(action='needs_user', reason='parent task is ' + task['status'])
        if task['status'] in ('COMPLETED', 'ARCHIVED', 'CANCELLED'):
            return dict(action='stop', reason='parent task is ' + task['status'])
        return None

    def _require_active_task(self, task):
        gate = self._task_gate(task)
        if gate:
            raise ValueError(gate['reason'] + '; no new work or model calls permitted')

    def _read(self):
        task = self.ledger.load(self.task_id)
        state = task['plan'].get('edd_loop')
        if state is None:
            raise ValueError('loop not initialized')
        if state['target'] != self._target(task):
            raise ValueError('approved target changed; obtain user decision before continuing')
        return state

    @contextmanager
    def _edit(self, initializing=False):
        with self.ledger.lock():
            task = self.ledger.load(self.task_id)
            state = task['plan'].get('edd_loop')
            if not initializing and (state is None or state['target'] != self._target(task)):
                raise ValueError('loop missing or approved target changed')
            yield task, state
            state = task['plan']['edd_loop']
            action = self._task_gate(task) or self._action(state)
            projection = dict(kind='edd-loop-progress', goal=task['goal'], action=action,
                rounds=f"{len(state['rounds'])}/{state['config']['max_rounds']}", used=state['used'],
                nodes=[dict(id=n['id'], parent=n['parent'], status=n['status']) for n in state['nodes'].values()])
            task['progress'] = [p for p in task['progress'] if p.get('kind') != 'edd-loop-progress'] + [projection]
            label = {'research': '委派獨立研究與分階段測試計畫', 'work': '派遣節點實作及驗證',
                     'wait': '等待當前節點完成', 'audit': '委派獨立方向審核',
                     'verify_final': '委派根目標最終驗收', 'done': '迴圈驗收通過，依EDD完成Task',
                     'needs_user': '等待使用者決策', 'stop': '停止迴圈'}[action['action']]
            location = ' → '.join(action.get('active_path', []))
            task['checkpoint']['current_action'] = f"EDD loop {projection['rounds']}：{label}" + (f"；{location}" if location else '')
            task['checkpoint']['next_action'] = action.get('reason') or label
            if state['rounds']:
                last = state['rounds'][-1]
                task['checkpoint']['last_completed'] = f"EDD loop 第{last['round']}輪 {last['node']}：{last['result']}"
            errors = self.ledger.schema_errors(task)
            if errors:
                raise ValueError('; '.join(errors))
            self.ledger.save(task)

    def initialize(self, config):
        required = {'max_rounds', 'max_model_retries_per_case', 'max_cloud_calls', 'max_local_calls',
                    'max_agent_dispatches', 'review_every', 'request_timeout_seconds', 'phase'}
        if not required <= set(config) or set(config) - required - {'endpoint_envs'}:
            raise ValueError('configuration requires exactly: ' + ', '.join(sorted(required)))
        for key in required - {'request_timeout_seconds', 'phase'}:
            if type(config[key]) is not int or config[key] < 0:
                raise ValueError('budget must be a nonnegative integer: ' + key)
        if not 1 <= config['review_every'] <= config['max_rounds'] or config['max_agent_dispatches'] < 4:
            raise ValueError('require 1 <= review_every <= max_rounds and >=4 agent slots')
        timeout = config['request_timeout_seconds']
        if timeout is not None and (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('request timeout must be null or positive')
        if config['phase'] not in ('feasibility', 'optimization'):
            raise ValueError('phase must be feasibility or optimization')
        endpoints = {}
        supplied = config.get('endpoint_envs', {})
        if not isinstance(supplied, dict) or set(supplied) - {'cloud', 'local'}:
            raise ValueError('endpoint_envs must map cloud/local to environment variable names')
        for provider, names in supplied.items():
            if not isinstance(names, list):
                raise ValueError('endpoint environment names must be a list')
            for name in names:
                if not isinstance(name, str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', name) or name in endpoints:
                    raise ValueError('endpoint environment names must be unique and explicit')
                value = os.environ.get(name, '')
                parsed = urlsplit(value)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError('endpoint environment is missing or invalid: ' + name)
                endpoints[name] = dict(provider=provider, url_sha256=sha256(value.encode('utf-8')).hexdigest())
        with self._edit(initializing=True) as (task, old):
            self._require_active_task(task)
            if old is not None:
                raise ValueError('loop already exists; never reset consumed budgets on resume')
            if task['status'] in ('COMPLETED', 'ARCHIVED', 'CANCELLED') or not task['acceptance']:
                raise ValueError('require an unfinished task with explicit acceptance criteria')
            task['plan']['edd_loop'] = dict(id=uuid4().hex, target=self._target(task), config=copy.deepcopy(config),
                status='RUNNING', nodes={}, endpoints=endpoints, needs_research=True, active=None, rounds=[], reviews=[],
                last_review=0, failure_streak=0, audit_due=False, tickets={}, requests={}, plan_evidence=[],
                used=dict(agent_dispatches=0, cloud_calls=0, local_calls=0, model_retries=0), started_at=stamp())
        return self.status()

    def _children(self, state, identifier):
        return [n for n in state['nodes'].values() if n['parent'] == identifier]

    def _choose(self, state, identifier='root'):
        node = state['nodes'][identifier]
        for child in self._children(state, identifier):
            if child['status'] != 'passed':
                return self._choose(state, child['id'])
        return identifier if node['status'] != 'passed' else None

    def _path(self, state, identifier):
        path = []
        while identifier is not None:
            path.append(identifier)
            identifier = state['nodes'][identifier]['parent']
        return list(reversed(path))

    def _action(self, state):
        if state['status'] != 'RUNNING':
            return dict(action={'ACCEPTED': 'done', 'NEEDS_USER': 'needs_user'}.get(state['status'], 'stop'),
                        reason=state.get('stop_reason', state['status']))
        if state['active']:
            return dict(action='wait', node=state['active']['node'], active_path=self._path(state, state['active']['node']))
        if state['audit_due']:
            return dict(action='audit', reviewed_rounds=list(range(state['last_review'] + 1, len(state['rounds']) + 1)))
        if state['nodes'] and state['nodes']['root']['status'] == 'passed':
            return dict(action='verify_final', reviewed_rounds=list(range(state['last_review'] + 1, len(state['rounds']) + 1)))
        at_budget = (len(state['rounds']) >= state['config']['max_rounds']
                     or state['used']['agent_dispatches'] >= state['config']['max_agent_dispatches'] - 2)
        if at_budget and state['last_review'] < len(state['rounds']):
            return dict(action='audit', reason='budget boundary; review completed work before stopping',
                        reviewed_rounds=list(range(state['last_review'] + 1, len(state['rounds']) + 1)))
        if len(state['rounds']) >= state['config']['max_rounds']:
            return dict(action='stop', reason='round budget exhausted; target not accepted')
        if state['used']['agent_dispatches'] >= state['config']['max_agent_dispatches'] - 2:
            return dict(action='stop', reason='agent budget reserved for review; no more worker/research dispatch')
        if state['needs_research']:
            return dict(action='research')
        identifier = self._choose(state)
        return dict(action='work', node=identifier, active_path=self._path(state, identifier),
                    kind='verify_parent' if self._children(state, identifier) else 'leaf')

    def status(self):
        state = self._read()
        action = self._task_gate(self.ledger.load(self.task_id)) or self._action(state)
        return dict(loop_id=state['id'], **action, used=state['used'], limits=state['config'],
                    rounds=len(state['rounds']), remaining_cloud_calls=state['config']['max_cloud_calls'] - state['used']['cloud_calls'])

    def amend_limits(self, updates, authorization):
        allowed = {'max_rounds', 'max_model_retries_per_case', 'max_cloud_calls', 'max_local_calls',
                   'max_agent_dispatches', 'review_every'}
        if (not authorization.strip() or not updates or set(updates) - allowed
                or any(type(v) is not int or v < 0 for v in updates.values())):
            raise ValueError('explicit user authorization and integer budget changes required')
        with self._edit() as (_, state):
            config = dict(state['config'], **updates)
            if (not 1 <= config['review_every'] <= config['max_rounds']
                    or config['max_rounds'] < len(state['rounds']) + bool(state['active'])
                    or config['max_agent_dispatches'] < max(4, state['used']['agent_dispatches'])
                    or any(config['max_' + k] < state['used'][k] for k in ('cloud_calls', 'local_calls'))
                    or config['max_model_retries_per_case'] < max((r['retry_number'] for r in state['requests'].values()), default=0)):
                raise ValueError('new limits cannot erase consumed resources or invalidate the active round')
            state.setdefault('budget_changes', []).append(dict(before=state['config'], after=config,
                                                               authorization=authorization, at=stamp()))
            state['config'] = config
            if state['active'] is None and len(state['rounds']) - state['last_review'] >= config['review_every']:
                state['audit_due'] = True
        return self.status()

    def resume(self, authorization):
        if not authorization.strip():
            raise ValueError('explicit user resolution required')
        with self._edit() as (task, state):
            self._require_active_task(task)
            if (state['status'] not in ('NEEDS_USER', 'STOPPED') or state['active']
                    or any(r['status'] == 'inflight' for r in state['requests'].values())):
                raise ValueError('settle active work and requests before resuming a stopped loop')
            state.setdefault('resolutions', []).append(dict(authorization=authorization, at=stamp()))
            state['status'] = 'RUNNING'
        return self.status()

    def _proof(self, paths):
        if not paths:
            raise ValueError('fresh evidence files are required')
        result = []
        for value in paths:
            path = (self.root / value).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError('evidence must exist inside the repository')
            result.append(dict(path=str(path.relative_to(self.root)), sha256=digest(path)))
        return result

    def _ticket(self, state, identifier, roles):
        ticket = state['tickets'].get(identifier)
        if not ticket or ticket['role'] not in roles or not ticket['platform_id'] or ticket['closed']:
            raise ValueError('require a bound agent ticket with role ' + '/'.join(roles))
        return ticket

    def reserve_agent(self, role, node=None):
        with self._edit() as (task, state):
            self._require_active_task(task)
            action = self._action(state)['action']
            allowed = ((role == 'research' and action == 'research')
                or (role == 'worker' and state['active'] and node == state['active']['node'])
                or (role == 'auditor' and action == 'audit')
                or (role == 'verifier' and action == 'verify_final'))
            if state['status'] != 'RUNNING' or not allowed:
                raise ValueError('agent role is not currently eligible')
            limit = state['config']['max_agent_dispatches'] - (0 if role in ('auditor', 'verifier') else 2)
            if state['used']['agent_dispatches'] >= limit:
                raise ValueError('agent dispatch budget exhausted or reserved for review')
            round_number = len(state['rounds']) + bool(state['active'])
            if any(t['role'] == role and t['round'] == round_number and not t['closed'] for t in state['tickets'].values()):
                raise ValueError('agent for this role/round is still outstanding; wait rather than duplicate dispatch')
            identifier = uuid4().hex
            ticket = dict(id=identifier, role=role, node=node, round=round_number,
                          platform_id=None, closed=False, reserved_at=stamp())
            state['tickets'][identifier] = ticket
            state['used']['agent_dispatches'] += 1
        return copy.deepcopy(ticket)

    def bind_agent(self, identifier, platform_id):
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError('actual platform agent ID required')
        with self._edit() as (_, state):
            ticket = state['tickets'].get(identifier)
            if not ticket or ticket['platform_id'] is not None:
                raise ValueError('ticket absent or already bound')
            if any(t['platform_id'] == platform_id for t in state['tickets'].values()):
                raise ValueError('fresh agent identity required; do not reuse context for independent review')
            ticket['platform_id'] = platform_id
        return self.status()

    def set_plan(self, ticket_id, nodes, evidence):
        proof = self._proof(evidence)
        with self._edit() as (task, state):
            self._require_active_task(task)
            ticket = self._ticket(state, ticket_id, ('research',))
            if ticket['round'] != len(state['rounds']):
                raise ValueError('fresh research context required for this round')
            if self._action(state)['action'] != 'research':
                raise ValueError('research is not currently due')
            proposed = {}
            for node in nodes:
                if (set(node) != {'id', 'parent', 'goal', 'acceptance'} or not node['goal']
                        or not isinstance(node['id'], str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+', node['id'])
                        or not isinstance(node['acceptance'], list) or not node['acceptance']
                        or any(not isinstance(a, str) or not a.strip() for a in node['acceptance'])
                        or node['id'] in proposed):
                    raise ValueError('nodes require unique id, parent, goal and nonempty acceptance list')
                proposed[node['id']] = dict(node, status='pending')
            root = proposed.get('root')
            if (not root or root['parent'] is not None or root['goal'] != state['target']['goal']
                    or root['acceptance'] != [a['description'] for a in state['target']['acceptance']]):
                raise ValueError('root must preserve approved task goal and acceptance criteria')
            for node in proposed.values():
                seen, current = set(), node['id']
                while current is not None:
                    if current in seen or current not in proposed:
                        raise ValueError('plan contains cycle or missing parent')
                    seen.add(current)
                    current = proposed[current]['parent']
                if 'root' not in seen:
                    raise ValueError('all nodes must descend from root')
            for identifier, old in state['nodes'].items():
                new = proposed.get(identifier)
                if not new or any(new[k] != old[k] for k in ('parent', 'goal', 'acceptance')):
                    raise ValueError('do not delete existing nodes or weaken their approved tests')
                new['status'] = old['status']
                if old['status'] == 'passed':
                    before = {n['id'] for n in self._children(state, identifier)}
                    after = {n['id'] for n in proposed.values() if n['parent'] == identifier}
                    if before != after:
                        raise ValueError('passed parent requires an explicit reopening decision')
            state['nodes'] = proposed
            state['needs_research'] = False
            state['plan_evidence'].extend(proof)
            ticket['closed'] = True
        return self.status()

    def begin_round(self, node):
        with self._edit() as (task, state):
            self._require_active_task(task)
            action = self._action(state)
            if action.get('action') != 'work' or action.get('node') != node:
                raise ValueError('next work item or review gate does not permit this round')
            state['active'] = dict(round=len(state['rounds']) + 1, node=node, started_at=stamp())
            state['nodes'][node]['status'] = 'active'
        return self.status()

    def complete_round(self, ticket_id, result, evidence, summary):
        if result not in ('PASS', 'FAIL') or not isinstance(summary, str) or not summary.strip():
            raise ValueError('round result and factual summary required')
        proof = self._proof(evidence)
        with self._edit() as (_, state):
            ticket = self._ticket(state, ticket_id, ('worker',))
            active = state['active']
            if not active or ticket['node'] != active['node'] or ticket['round'] != active['round']:
                raise ValueError('worker does not own the active round')
            if any(r['status'] == 'inflight' for r in state['requests'].values()):
                raise ValueError('model request still in flight; cannot finish or restart the round')
            children = self._children(state, active['node'])
            if result == 'PASS' and any(n['status'] != 'passed' for n in children):
                raise ValueError('parent cannot pass before its children')
            node = state['nodes'][active['node']]
            node['status'] = 'passed' if result == 'PASS' else 'failed'
            state['rounds'].append(dict(**active, result=result, evidence=proof, summary=summary,
                                       producer=ticket['platform_id'], finished_at=stamp()))
            state['active'] = None
            ticket['closed'] = True
            state['failure_streak'] = 0 if result == 'PASS' else state['failure_streak'] + 1
            state['needs_research'] = result == 'FAIL'
            state['audit_due'] = (len(state['rounds']) - state['last_review'] >= state['config']['review_every']
                                  or state['failure_streak'] >= 3)
            parent = node['parent']
            if parent and all(n['status'] == 'passed' for n in self._children(state, parent)):
                state['nodes'][parent]['status'] = 'verify_parent'
        return self.status()

    def _check_evidence(self, state):
        proofs = list(state['plan_evidence'])
        for record in state['rounds'] + state['reviews']:
            proofs.extend(record['evidence'])
        for item in proofs:
            path = (self.root / item['path']).resolve()
            if not path.is_relative_to(self.root) or not path.is_file() or digest(path) != item['sha256']:
                raise ValueError('evidence missing or changed: ' + item['path'])

    def check_evidence(self):
        self._check_evidence(self._read())
        return dict(result='PASS', scope='file provenance only; not semantic approval')

    def review(self, ticket_id, verdict, reviewed_rounds, evidence, summary):
        if verdict not in ('CONTINUE', 'REPLAN', 'NEEDS_USER', 'STOP', 'ACCEPT') or not summary.strip():
            raise ValueError('review verdict and summary required')
        proof = self._proof(evidence)
        with self._edit() as (task, state):
            ticket = self._ticket(state, ticket_id, ('auditor', 'verifier'))
            if verdict in ('ACCEPT', 'CONTINUE', 'REPLAN'):
                self._require_active_task(task)
            if ticket['round'] != len(state['rounds']):
                raise ValueError('fresh review context required for this review interval')
            action = self._action(state)['action']
            expected = list(range(state['last_review'] + 1, len(state['rounds']) + 1))
            if action not in ('audit', 'verify_final') or reviewed_rounds != expected:
                raise ValueError('review must cover every unreviewed round, not only the latest success')
            if ticket['platform_id'] in {r['producer'] for r in state['rounds']}:
                raise ValueError('implementer cannot independently approve own direction or result')
            self._check_evidence(state)
            if verdict == 'ACCEPT' and (not state['nodes'] or state['nodes']['root']['status'] != 'passed'):
                raise ValueError('whole root task and parent integrations must pass before acceptance')
            state['reviews'].append(dict(verdict=verdict, reviewed_rounds=reviewed_rounds, evidence=proof,
                                         summary=summary, reviewer=ticket['platform_id'], at=stamp()))
            state['last_review'] = len(state['rounds'])
            ticket['closed'] = True
            state['audit_due'] = False
            state['failure_streak'] = 0
            if verdict == 'REPLAN':
                state['needs_research'] = True
            if verdict in ('NEEDS_USER', 'STOP', 'ACCEPT'):
                state['status'] = {'NEEDS_USER': 'NEEDS_USER', 'STOP': 'STOPPED', 'ACCEPT': 'ACCEPTED'}[verdict]
                state['stop_reason'] = summary
        return self.status()

    def reserve_request(self, ticket_id, provider, case_key, request_sha, retry_of=None):
        if provider not in ('cloud', 'local') or not case_key or not request_sha:
            raise ValueError('provider, stable case key and request fingerprint required')
        with self._edit() as (task, state):
            self._require_active_task(task)
            ticket = self._ticket(state, ticket_id, ('worker',))
            if (state['status'] != 'RUNNING' or not state['active'] or state['audit_due']
                    or ticket['node'] != state['active']['node'] or ticket['round'] != state['active']['round']):
                raise ValueError('model calls require the current worker round')
            if any(r['status'] == 'inflight' for r in state['requests'].values()):
                raise ValueError('previous model request still in flight; wait before any new case')
            key = provider + '_calls'
            if state['used'][key] >= state['config']['max_' + key]:
                raise ValueError(provider + ' model-call budget exhausted before request')
            previous = [r for r in state['requests'].values()
                        if r['provider'] == provider and r['case_key'] == case_key and r['request_sha'] == request_sha]
            retries = 0
            if retry_of:
                old = state['requests'].get(retry_of)
                if (not old or old not in previous or old['status'] not in ('transport_error', 'timeout', 'retryable_error')
                        or old['ticket_id'] != ticket_id):
                    raise ValueError('retry requires the same worker and an actual transient failed attempt')
                retries = max(r['retry_number'] for r in previous) + 1
                if retries > state['config']['max_model_retries_per_case']:
                    raise ValueError('per-case model retry budget exhausted')
            elif previous:
                raise ValueError('identical request already attempted; do not relabel a retry as a new test')
            identifier = uuid4().hex
            item = dict(id=identifier, ticket_id=ticket_id, provider=provider, case_key=case_key,
                        request_sha=request_sha, retry_number=retries, retry_of=retry_of,
                        status='inflight', round=state['active']['round'], reserved_at=stamp())
            state['requests'][identifier] = item
            state['used'][key] += 1
            state['used']['model_retries'] += bool(retry_of)
        return copy.deepcopy(item)

    def settle_request(self, identifier, status, **details):
        if status not in ('ok', 'transport_error', 'timeout', 'retryable_error', 'http_error', 'rate_limited', 'unknown'):
            raise ValueError('unknown request result')
        with self._edit() as (_, state):
            item = state['requests'].get(identifier)
            if not item or item['status'] != 'inflight':
                raise ValueError('request missing or already settled')
            item.update(status=status, finished_at=stamp(), details=details)
            if status == 'rate_limited':
                state['status'] = 'NEEDS_USER'
                state['stop_reason'] = 'provider rate/quota limit; resolve before spending remaining calls'
        return self.status()

    def request(self, ticket_id, provider, case_key, request_file, url_env, auth_env=None,
                auth_header='Authorization', auth_prefix='Bearer ', retry_of=None):
        url = os.environ[url_env]
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('absolute HTTP endpoint without inline credentials required')
        endpoint = self._read()['endpoints'].get(url_env)
        if (not endpoint or endpoint['provider'] != provider
                or endpoint['url_sha256'] != sha256(url.encode('utf-8')).hexdigest()):
            raise ValueError('endpoint/provider not authorized or endpoint changed since loop setup')
        payload = Path(request_file).read_text(encoding='utf-8')
        body = json.loads(payload)
        if not isinstance(body, dict) or body.get('stream') is True:
            raise ValueError('request must be a JSON object with streaming disabled')
        headers = {'Content-Type': 'application/json'}
        if auth_env:
            token = os.environ[auth_env]
            if not re.fullmatch(r'[A-Za-z0-9-]+', auth_header) or '\n' in token + auth_prefix or '\r' in token + auth_prefix:
                raise ValueError('invalid authorization header')
            headers[auth_header] = auth_prefix + token
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        item = self.reserve_request(ticket_id, provider, case_key, sha256(encoded).hexdigest(), retry_of)
        folder = self.ledger.task_path(self.task_id) / '.local/edd-loop/requests'
        if not folder.resolve().is_relative_to(self.ledger.task_path(self.task_id).resolve()):
            self.settle_request(item['id'], 'unknown', reason='unsafe output directory')
            raise ValueError('private output directory escapes task')
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        saved_request = folder / (item['id'] + '.request.json')
        saved_request.write_text(encoded.decode('utf-8') + '\n', encoding='utf-8')
        saved_request.chmod(0o600)
        outcome, code, response = 'ok', None, b''
        try:
            request = Request(url, data=encoded, headers=headers, method='POST')
            with build_opener(NoRedirect).open(request, timeout=self._read()['config']['request_timeout_seconds']) as result:
                code, response = result.status, result.read()
        except HTTPError as exc:
            code = exc.code
            outcome = 'rate_limited' if code == 429 else ('retryable_error' if code in (408, 500, 502, 503, 504) else 'http_error')
            try:
                response = exc.read()
            except OSError:
                response = b''
        except (TimeoutError, URLError, OSError) as exc:
            outcome = 'timeout' if isinstance(exc, TimeoutError) else 'transport_error'
            response = json.dumps(dict(error_type=type(exc).__name__), ensure_ascii=False).encode('utf-8')
        output = folder / (item['id'] + '.response.txt')
        try:
            text = response.decode('utf-8')
        except UnicodeDecodeError:
            text = json.dumps(dict(non_utf8_body_base64=base64.b64encode(response).decode('ascii')))
        output.write_text(text, encoding='utf-8')
        output.chmod(0o600)
        self.settle_request(item['id'], outcome, http_status=code,
                            response_path=str(output.relative_to(self.root)), response_sha256=digest(output))
        return dict(request_id=item['id'], result=outcome, http_status=code,
                    response_path=str(output), calls_charged=1, automatic_retries=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--id', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('init'); p.add_argument('--config', type=Path, required=True)
    p = sub.add_parser('amend'); p.add_argument('--file', type=Path, required=True); p.add_argument('--authorization', required=True)
    p = sub.add_parser('resume'); p.add_argument('--authorization', required=True)
    sub.add_parser('status'); sub.add_parser('check-evidence')
    p = sub.add_parser('plan'); p.add_argument('--ticket', required=True); p.add_argument('--file', type=Path, required=True)
    p = sub.add_parser('begin'); p.add_argument('--node', required=True)
    p = sub.add_parser('dispatch'); p.add_argument('--role', choices=['research', 'worker', 'auditor', 'verifier'], required=True); p.add_argument('--node')
    p = sub.add_parser('bind'); p.add_argument('--ticket', required=True); p.add_argument('--platform-id', required=True)
    p = sub.add_parser('finish'); p.add_argument('--file', type=Path, required=True)
    p = sub.add_parser('review'); p.add_argument('--file', type=Path, required=True)
    p = sub.add_parser('abandon-request'); p.add_argument('--request-id', required=True); p.add_argument('--reason', required=True)
    p = sub.add_parser('request')
    for flag in ('ticket', 'provider', 'case', 'url-env'):
        p.add_argument('--' + flag, required=True)
    p.add_argument('--file', type=Path, required=True)
    p.add_argument('--auth-env'); p.add_argument('--auth-header', default='Authorization'); p.add_argument('--auth-prefix', default='Bearer ')
    p.add_argument('--retry-of')
    args = parser.parse_args()
    control = Controller(args.root, args.id)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    if args.action == 'init': result = control.initialize(read(args.config))
    elif args.action == 'amend': result = control.amend_limits(read(args.file), args.authorization)
    elif args.action == 'resume': result = control.resume(args.authorization)
    elif args.action == 'status': result = control.status()
    elif args.action == 'check-evidence': result = control.check_evidence()
    elif args.action == 'plan':
        data = read(args.file); result = control.set_plan(args.ticket, data['nodes'], data['evidence'])
    elif args.action == 'begin': result = control.begin_round(args.node)
    elif args.action == 'dispatch': result = control.reserve_agent(args.role, args.node)
    elif args.action == 'bind': result = control.bind_agent(args.ticket, args.platform_id)
    elif args.action == 'finish':
        data = read(args.file); result = control.complete_round(data['ticket'], data['result'], data['evidence'], data['summary'])
    elif args.action == 'review':
        data = read(args.file); result = control.review(data['ticket'], data['verdict'], data['reviewed_rounds'], data['evidence'], data['summary'])
    elif args.action == 'abandon-request':
        result = control.settle_request(args.request_id, 'unknown', reason=args.reason)
    else:
        result = control.request(args.ticket, args.provider, args.case, args.file, args.url_env,
                                 args.auth_env, args.auth_header, args.auth_prefix, args.retry_of)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('result') in ('transport_error', 'timeout', 'retryable_error', 'http_error', 'rate_limited') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps(dict(result='ERROR', error=str(exc)), ensure_ascii=False))
        raise SystemExit(2)
