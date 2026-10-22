def exact(labels,query):
 normalized=query.casefold().strip()
 if not normalized: return None
 matches=[label for label in labels if label.casefold().strip()==normalized]
 return matches[0] if len(matches)==1 else None
assert exact(['sales','stock'],'s') is None
assert exact([],'s') is None
assert exact(['Sales','sales'],'sales') is None
assert exact(['Straße'],'STRASSE')=='Straße'
assert exact([' Sales '],' sales ')==' Sales '
print('5 independent contract checks passed')
