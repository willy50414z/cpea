"""核對本次全域 EDD skill 更新，記錄外部檔案指紋，不呼叫模型。"""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path('/home/willy/.codex/skills')
TASK = Path(__file__).resolve().parents[1]
validator = ROOT / '.system/skill-creator/scripts/quick_validate.py'
spec = importlib.util.spec_from_file_location('skill_quick_validate', validator)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for name in ('edd', 'edd-investigate', 'edd-verify'):
    valid, message = module.validate_skill(ROOT / name)
    assert valid, (name, message)
files = ['edd/SKILL.md', 'edd-investigate/SKILL.md', 'edd-verify/SKILL.md',
         'edd-investigate/references/model-decision-comparison.md']
hashes = {}
for name in files:
    path = ROOT / name
    data = path.read_bytes()
    assert not data.startswith(b'\xef\xbb\xbf') and b'\r\n' not in data
    text = data.decode('utf-8')
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if '://' not in target and not target.startswith('#'):
            assert (path.parent / target.split('#')[0]).exists(), (name, target)
    hashes[str(path)] = sha256(data).hexdigest()
result = {'result': 'PASS', 'skill_frontmatter': '3/3', 'utf8_no_bom_and_preserved_lf': '4/4',
          'local_links': 'PASS', 'external_skill_sha256': hashes,
          'behavioral_review': {
              'baseline_agent': '/root/edd_reason_baseline',
              'baseline_observation': '原技能下已主動提出理由比較；但規劃四次呼叫、每次塞入六題，未先停在單一失敗案例的最小比較。不是證明原技能完全不會比較理由。',
              'forward_agent': '/root/edd_reason_forward',
              'forward_observation': '改後先選一題兩次呼叫，足以決定實驗即停止；已有理由時零新診斷呼叫；辨識粒度便利不能取代online必要條件，保留首次與事後證據。',
              'scope': '一次修改前與一次修改後的獨立情境測試，後者含兩種情境；不代表統計穩定性或產品正確率提升。',
          }, 'new_planner_provider_calls': 0, 'product_changes_this_turn': False}
(TASK / 'reports/edd-model-decision-flow.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
