#!/usr/bin/env python3
"""Validate authored assets, UTF-8, local reference links and EDD hook configuration."""
import json
from pathlib import Path
import re
import sys


def check(root):
    errors = []
    folders = [root / '.agents/skills' / name for name in ('edd', 'edd-investigate', 'edd-verify')]
    paths = [root / 'AGENTS.md', root / 'evidence-driven-dev/README.md', root / '.codex/hooks.json']
    for folder in folders:
        paths.extend(p for p in folder.rglob('*') if p.is_file())
    for folder in [root / 'evidence-driven-dev/scripts', root / 'evidence-driven-dev/templates', root / '.codex/hooks']:
        paths.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for path in paths:
        try:
            raw = path.read_bytes()
            if raw.startswith(b'\xef\xbb\xbf'):
                errors.append(str(path) + ': BOM')
            text = raw.decode('utf-8')
            if path.suffix == '.md':
                for target in re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', text):
                    if '://' not in target and not target.startswith('#'):
                        if not (path.parent / target.split('#')[0]).exists():
                            errors.append(str(path) + ': 連結不存在 ' + target)
        except (OSError, UnicodeError) as e:
            errors.append(str(e))
    for folder in folders:
        path = folder / 'SKILL.md'
        try:
            text = path.read_text(encoding='utf-8')
            head = text.split('---\n', 2)[1]
            if not re.search(r'^name: ' + re.escape(folder.name) + r'$', head, re.M) or not re.search(r'^description: .+', head, re.M):
                errors.append(str(path) + ': Skill Frontmatter 無效')
        except (OSError, IndexError) as e:
            errors.append(str(e))
    try:
        config = json.loads((root / '.codex/hooks.json').read_text(encoding='utf-8'))
        if set(config['hooks']) != {'SessionStart', 'SubagentStop', 'Stop'}:
            errors.append('Hook events 不符合 v1')
        for groups in config['hooks'].values():
            for group in groups:
                for h in group['hooks']:
                    if h['type'] != 'command' or h['timeout'] != 10:
                        errors.append('Hook handler 需要 command 與 10 秒逾時')
    except (OSError, ValueError, KeyError, TypeError) as e:
        errors.append('Hook 設定無效：' + str(e))
    return errors


if __name__ == '__main__':
    errors = check(Path(__file__).resolve().parents[2])
    print(json.dumps({'result': 'FAIL' if errors else 'PASS', 'errors': errors}, ensure_ascii=False, indent=2))
    sys.exit(bool(errors))
