#!/usr/bin/env python3
"""Probe actual Codex skill discovery without starting a model turn."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import queue
import re
import subprocess
import threading

WANTED = {'edd', 'edd-investigate', 'edd-verify', 'systematic-debugging', 'brainstorming',
          'writing-plans', 'test-driven-development', 'subagent-driven-development',
          'dispatching-parallel-agents', 'verification-before-completion', 'requesting-code-review'}


def plugin_skills(inventory, cache_root):
    """Reconcile installed CLI plugins with their versioned, declared skill roots.

    Cache presence alone is not installation. Keep this provenance distinct from
    skills/list: a standalone app-server may omit host-installed plugin skills.
    """
    items, errors = [], []
    if not isinstance(inventory, dict) or not isinstance(inventory.get('installed'), list):
        return [], ['Plugin 安裝清單必須包含 installed 清單']
    for plugin in inventory['installed']:
        if not isinstance(plugin, dict):
            errors.append('Plugin 安裝項目必須為物件')
            continue
        if plugin.get('installed') is not True or plugin.get('enabled') is not True:
            continue
        try:
            segments = [plugin.get(k) for k in ('marketplaceName', 'name', 'version')]
            if any(not isinstance(x, str) or x in {'.', '..'} or not re.fullmatch(r'[A-Za-z0-9_.+@-]+', x) for x in segments):
                raise ValueError('Plugin 名稱、市集或版本無效')
            package = Path(cache_root).joinpath(*segments).resolve()
            if not package.is_relative_to(Path(cache_root).resolve()):
                raise ValueError('Plugin cache 路徑越界')
            manifest_path = package / '.codex-plugin/plugin.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or manifest.get('name') != plugin['name'] or manifest.get('version') != plugin['version']:
                raise ValueError('Plugin manifest 與已安裝版本不一致')
            roots = manifest.get('skills', [])
            roots = [roots] if isinstance(roots, str) else roots
            if not isinstance(roots, list) or any(not isinstance(x, str) for x in roots):
                raise ValueError('Plugin skills roots 必須為路徑清單')
            paths = set()
            for rel in roots:
                declared = Path(rel)
                folder = (package / declared).resolve()
                if declared.is_absolute() or '..' in declared.parts or not folder.is_relative_to(package):
                    raise ValueError('Plugin skills root 路徑越界')
                paths.update(folder.rglob('SKILL.md'))
            for path in sorted(paths):
                if not path.resolve().is_relative_to(package):
                    raise ValueError('Plugin Skill symlink 路徑越界')
                content = path.read_text(encoding='utf-8')
                parts = content.split('---\n', 2)
                match = re.search(r'^name:\s*([a-z0-9-]+)\s*$', parts[1], re.M) if len(parts) == 3 and not parts[0] else None
                if not match:
                    raise ValueError('Plugin Skill name Frontmatter 無效：' + str(path))
                if match.group(1) not in WANTED:
                    continue
                items.append({'name': plugin['name'] + ':' + match.group(1), 'path': str(path),
                              'scope': 'plugin', 'enabled': True, 'readable': True,
                              'pluginId': plugin.get('pluginId'), 'version': plugin['version'],
                              'discovery': 'installed-plugin-manifest',
                              'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
                              'bytes': len(content.encode('utf-8'))})
        except (OSError, ValueError, TypeError) as e:
            errors.append(str(plugin.get('pluginId', plugin.get('name'))) + '：' + str(e))
    return items, errors


def discover(root):
    proc = subprocess.Popen(['codex', 'app-server', '--listen', 'stdio://'], cwd=root,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding='utf-8')
    messages = queue.Queue()
    def receive():
        for line in proc.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
    thread = threading.Thread(target=receive, daemon=True)
    thread.start()
    def send(value):
        proc.stdin.write(json.dumps(value) + '\n')
        proc.stdin.flush()
    def response(request_id):
        import time
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as e:
                raise RuntimeError('Codex app-server 回應逾時') from e
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(str(message['error']))
                return message['result']
        raise RuntimeError('Codex app-server 回應逾時')
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'edd-probe', 'version': '1.0.0'}}})
        response(1)
        send({'method': 'initialized'})
        send({'id': 2, 'method': 'skills/list', 'params': {'cwds': [str(root)], 'forceReload': True}})
        result = response(2)
        send({'id': 3, 'method': 'hooks/list', 'params': {'cwds': [str(root)]}})
        hook_result = response(3)
        entries = result.get('data', [])
        skills = []
        for entry in entries:
            for skill in entry.get('skills', []):
                if skill['name'].split(':')[-1] not in WANTED:
                    continue
                path = Path(skill['path'])
                item = {k: skill.get(k) for k in ('name', 'path', 'scope', 'enabled', 'pluginId')}
                item['readable'] = path.is_file()
                if path.is_file():
                    text = path.read_text(encoding='utf-8')
                    item['sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
                    item['bytes'] = len(text.encode('utf-8'))
                skills.append(item)
        plugin_errors = []
        try:
            inventory = json.loads(subprocess.check_output(['codex', 'plugin', 'list', '--json'],
                                   text=True, encoding='utf-8', timeout=25))
            codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
            extra, plugin_errors = plugin_skills(inventory, codex_home / 'plugins/cache')
            existing = {(s['name'], s['path']) for s in skills}
            skills.extend(s for s in extra if (s['name'], s['path']) not in existing)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            plugin_errors.append('Plugin 安裝探測無法完成：' + str(e))
        hooks = [{k: h.get(k) for k in ('eventName', 'sourcePath', 'enabled', 'trustStatus', 'timeoutSec')}
                 for entry in hook_result.get('data', []) for h in entry.get('hooks', [])
                 if str(h.get('sourcePath', '')) == str(root / '.codex/hooks.json')]
        return {'codex': subprocess.check_output(['codex', '--version'], text=True, encoding='utf-8').strip(),
                'skills': skills, 'errors': [e for entry in entries for e in entry.get('errors', [])],
                'hooks': hooks, 'hook_errors': [e for entry in hook_result.get('data', []) for e in entry.get('errors', [])],
                'plugin_errors': plugin_errors,
                'missing': sorted(WANTED - {s['name'].split(':')[-1] for s in skills if s['enabled'] and s['readable']}),
                'protocol': 'initialize → initialized → skills/list → hooks/list + codex plugin list --json 與已安裝版本 manifest；沒有啟動模型回合'}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        proc.stdin.close()
        proc.stdout.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(json.dumps(discover(args.root.resolve()), ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError) as e:
        print(json.dumps({'result': 'NOT_VERIFIED', 'error': str(e)}, ensure_ascii=False))
        raise SystemExit(1)
