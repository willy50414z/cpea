from cases import retrieve, compile_sql
CATALOG = [{'view': 'sales_view', 'aliases': ['Revenue', 'SALES']}, {'view': 'stock_view', 'aliases': ['Stock']}]
state = {'question': 'revenue'}
state['candidates'] = retrieve(state, CATALOG)
print('baseline retrieval:', repr(state['candidates']))
assert state['candidates'] == []
try:
    compile_sql(state)
except ValueError as error:
    print('compiler correctly rejects bad retrieval:', error)

def experiment(question, catalog):
    terms = question.casefold().split()
    return [row['view'] for row in catalog
            if any(term in [alias.casefold() for alias in row['aliases']] for term in terms)]

for query, expected in [('revenue', ['sales_view']), ('stock', ['stock_view']), ('unknown', []), ('revenue stock', ['sales_view', 'stock_view'])]:
    actual = experiment(query, CATALOG)
    print('normalized alias experiment:', repr(query), repr(actual))
    assert actual == expected
print('minimal replay experiment PASS (4 comparisons)')
