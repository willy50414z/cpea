import json
import tiktoken


def validate_selection(raw, mdl):
    allowed = {m['name']:{c['name'] for c in m['columns']} for m in mdl['models']}
    results = raw['results']
    if not isinstance(results, list) or not results:
        raise ValueError('invalid_selection_empty')
    seen = set()
    for table in results:
        name = table['table_name']
        if name not in allowed or name in seen:
            raise ValueError('invalid_selection_table')
        seen.add(name)
        cols = table['table_contents']['columns']
        if not isinstance(cols, list) or not cols or len(set(cols)) != len(cols):
            raise ValueError('invalid_selection_columns')
        if any(c not in allowed[name] for c in cols):
            raise ValueError('invalid_selection_unknown_column')
    return raw


class Budget:
    def __init__(self, *, context_window, output_reserve, safety, encoding):
        if min(context_window, output_reserve) <= 0 or safety < 0:
            raise ValueError('invalid_context_configuration')
        self.context_window, self.output_reserve, self.safety = context_window, output_reserve, safety
        self.encoding = tiktoken.get_encoding(encoding)
        self.counter = f'tiktoken:{encoding}:serialized_messages_schema_plus_16_per_message'

    def check(self, messages, kwargs):
        # Explicit conservative accounting; provider-reported usage remains separate.
        payload = json.dumps({'messages':messages,'response_format':kwargs.get('response_format')}, ensure_ascii=False)
        count = len(self.encoding.encode(payload)) + 16 * len(messages)
        if count + self.output_reserve + self.safety > self.context_window:
            raise ValueError('context_budget_exceeded')
        return count
