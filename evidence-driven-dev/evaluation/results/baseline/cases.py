"""Small offline workflow evaluation fixtures; never imported by CPEA."""

def bounded(value, minimum, maximum):
    if minimum > maximum:
        raise ValueError('invalid range')
    return max(minimum, min(value, maximum))


def retrieve(state, catalog):
    terms = state['question'].casefold().split()
    return [row['view'] for row in catalog
            if any(term in [alias.casefold() for alias in row['aliases']] for term in terms)]


def compile_sql(state):
    candidates = state['candidates']
    if len(candidates) != 1:
        raise ValueError('ambiguous or missing view')
    return 'SELECT * FROM ' + candidates[0]


def pipeline(question, catalog):
    state = {'question': question}
    state['candidates'] = retrieve(state, catalog)
    return compile_sql(state)


def select_route(labels, query, threshold=0.5):
    # Retain the legacy argument for callers; exact matching has no score cutoff.
    normalized_query = query.casefold().strip()
    if not normalized_query:
        return None
    matches = [label for label in labels
               if label.casefold().strip() == normalized_query]
    return matches[0] if len(matches) == 1 else None
