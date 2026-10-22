"""Small offline workflow evaluation fixtures; never imported by CPEA."""

def bounded(value, minimum, maximum):
    if minimum > maximum:
        raise ValueError('invalid range')
    return max(minimum, min(value, maximum - 1))


def retrieve(state, catalog):
    terms = state['question'].lower().split()
    return [row['view'] for row in catalog
            if any(term in row['aliases'] for term in terms)]


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
    # Earlier attempts varied threshold but continued to misroute some requests.
    scores = [(label, len(set(label.lower()) & set(query.lower())) / max(1, len(set(query.lower()))))
              for label in labels]
    winner, score = max(scores, key=lambda item: item[1])
    return winner if score >= threshold else None
