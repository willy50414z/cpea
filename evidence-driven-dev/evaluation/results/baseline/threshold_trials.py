from cases import select_route
import json
import sys
threshold = float(sys.argv[1])
actual = select_route(['sales', 'stock'], 's', threshold=threshold)
print(json.dumps({'threshold': threshold, 'input': {'labels': ['sales', 'stock'], 'query': 's'}, 'expected': None, 'actual': actual}, ensure_ascii=False))
assert actual is None, 'partial query violates exact-match contract'
