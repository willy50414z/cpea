"""Data-only Codex lifecycle adapters. Never execute commands from hook input."""
import json
from pathlib import Path
import re
import sys

from ledger import EddError, Ledger, confined, read_document

CLAIM = re.compile(r'\[EDD-COMPLETE:([a-z0-9][a-z0-9_-]{0,79})\]')


def warning(message):
    return {'systemMessage': 'EDD：' + message[:3000]}


def decision(message, enforce, reentry):
    if enforce and not reentry:
        return {'decision': 'block', 'reason': 'EDD：' + message[:3000]}
    return warning(message)


def handle(root, expected, event):
    if not isinstance(event, dict) or event.get('hook_event_name') != expected:
        return warning('事件格式／類型錯誤；安全降級，未修改 Task。')
    l = Ledger(root)
    if not isinstance(event.get('cwd'), str) or not Path(event['cwd']).is_absolute() or not Path(event['cwd']).resolve().is_relative_to(l.root):
        return warning('事件 cwd 不屬於本 Hook Repository；未處理。')
    try:
        config_path = confined(l.home, 'config.yaml')
        config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
        if not isinstance(config, dict):
            raise EddError('config.yaml 必須是 JSON-subset YAML 物件')
        enforce = config.get('hooks_mode') == 'enforce'
        reentry = event.get('stop_hook_active') is True
        text = event.get('last_assistant_message') or ''
        if not isinstance(text, str):
            raise EddError('last_assistant_message 必須是字串或 null')
        claim = CLAIM.search(text) if expected == 'Stop' else None
        # Stop is deliberately declaration-based: ordinary answers do not inherit old completion checks.
        if expected == 'Stop' and claim is None:
            return {}
        task_id = l.resolve(claim.group(1) if claim else None, event.get('session_id'))
        if not task_id:
            return {}
        d = l.load(task_id)
        if expected == 'SessionStart':
            snapshot = l.resume(task_id)
            # Metadata is context, not executable instructions; cap output and avoid raw logs.
            context = {'instruction': '先讀取指定 Task 與 Checkpoint；核對 Git 與證據，不自動重跑副作用。',
                       'path': str(l.task_path(task_id) / 'task.md'), 'status': d['status'],
                       'checkpoint': d['checkpoint'], 'pending_questions': [q for q in d['questions'] if q.get('status') == 'WAITING_USER'],
                       'errors': snapshot['errors'], 'agents': d['agents']}
            return {'hookSpecificOutput': {'hookEventName': 'SessionStart',
                    'additionalContext': json.dumps(context, ensure_ascii=False)[:7500]}}
        if expected == 'Stop':
            if d['status'] in {'WAITING_USER', 'BLOCKED', 'CANCELLED'}:
                return warning('任務仍為 ' + d['status'] + '；請提供階段／阻塞報告，不宣稱完成。')
            errors = l.validate(task_id, completion=True)
            if d['status'] != 'COMPLETED':
                errors.append('請由 Main Agent 完成驗收後 transition COMPLETED')
            if errors:
                return decision('完成宣稱缺少必要證據：' + '; '.join(errors) + '。修正紀錄或重新執行必要驗證；不要盲目重跑全部測試。', enforce, reentry)
            return {}
        if expected == 'SubagentStop':
            platform_id = event.get('agent_id')
            matches = [a for a in d['agents'] if platform_id and a.get('platform_id') == platform_id]
            if len(matches) != 1:
                return warning('沒有唯一 platform agent_id 對應；請 Main 使用 agent-map 指定 Task／Agent，不猜測 Report。')
            item = dict(matches[0])
            try:
                report, _ = read_document(confined(l.task_path(task_id), item['report']))
            except EddError as e:
                return decision(str(e) + '；請寫入指定 Report。', enforce, reentry)
            item['status'] = report.get('status')
            errors = l.agent_errors(task_id, item)
            if report.get('status') == 'IN_PROGRESS':
                errors.append('停止前必須保存結構化 Handoff，不能只在回覆寫 DONE')
            if report.get('status') in {'NEEDS_USER_DECISION', 'BLOCKED', 'NEEDS_CONTEXT', 'FAILED'}:
                return warning('請 Main 處理 ' + item['id'] + ' 的 ' + str(report.get('status')) +
                               '，閱讀 Report、保存問題／處置；不要求 Subagent 自行批准。' + '; '.join(errors))
            if errors:
                return decision('; '.join(errors) + '；請修正自己的 Handoff。', enforce, reentry)
            return warning('Handoff 已存在；Main 仍需審核證據並執行 integrate：' + item['id'])
        return {}
    except (EddError, OSError, ValueError, KeyError, TypeError) as e:
        return warning('Hook 資料無法驗證，安全降級：' + str(e))


def main(root, expected):
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise EddError('Hook 輸入超過 1 MiB')
        event = json.loads(raw.decode('utf-8'))
        result = handle(root, expected, event)
    except (EddError, OSError, ValueError, TypeError) as e:
        result = warning('Hook 輸入無效，安全降級：' + str(e))
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + '\n')
    return 0
