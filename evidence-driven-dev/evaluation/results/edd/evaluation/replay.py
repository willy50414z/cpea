from checks import cases, CATALOG
state={'question':'revenue'}
original=cases.retrieve(state,CATALOG)
assert original==[],original
assert cases.compile_sql({'candidates':['sales_view']})=='SELECT * FROM sales_view'
normalized=[row['view'] for row in CATALOG if any(term in {alias.casefold() for alias in row['aliases']} for term in state['question'].casefold().split())]
assert normalized==['sales_view'], normalized
print({'baseline_candidates':original,'prototype_candidates':normalized,'compiler_with_valid_candidate':'PASS','formal_code_changed':False})
