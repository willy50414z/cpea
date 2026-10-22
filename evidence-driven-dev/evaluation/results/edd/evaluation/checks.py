import sys, unittest, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evidence-driven-dev/evaluation/fixtures'))
import cases
CATALOG=[{'view':'sales_view','aliases':['Revenue','SALES']},{'view':'stock_view','aliases':['Stock']}]
class Simple(unittest.TestCase):
 def test_upper(self): self.assertEqual(cases.bounded(10,0,10),10)
 def test_above(self): self.assertEqual(cases.bounded(25,0,10),10)
 def test_lower(self): self.assertEqual(cases.bounded(0,0,10),0)
 def test_below(self): self.assertEqual(cases.bounded(-5,0,10),0)
 def test_middle(self): self.assertEqual(cases.bounded(5,0,10),5)
 def test_negative_range(self): self.assertEqual(cases.bounded(-2,-5,-1),-2)
 def test_equal_bounds(self): self.assertEqual(cases.bounded(7,3,3),3)
 def test_float(self): self.assertEqual(cases.bounded(2.75,0,3),2.75)
 def test_invalid(self):
  with self.assertRaises(ValueError): cases.bounded(0,10,0)
class Retrieval(unittest.TestCase):
 def test_reported(self): self.assertEqual(cases.pipeline('revenue',CATALOG),'SELECT * FROM sales_view')
 def test_node(self): self.assertEqual(cases.retrieve({'question':'revenue'},CATALOG),['sales_view'])
 def test_case(self): self.assertEqual(cases.pipeline('rEVeNUe',CATALOG),'SELECT * FROM sales_view')
 def test_alias(self): self.assertEqual(cases.pipeline('sales',CATALOG),'SELECT * FROM sales_view')
 def test_other(self): self.assertEqual(cases.pipeline('stock',CATALOG),'SELECT * FROM stock_view')
 def test_missing(self):
  with self.assertRaises(ValueError): cases.pipeline('missing',CATALOG)
 def test_multi(self):
  with self.assertRaises(ValueError): cases.pipeline('revenue stock',CATALOG)
 def test_duplicate(self):
  cat=[{'view':'a','aliases':['same']},{'view':'b','aliases':['SAME']}]
  with self.assertRaises(ValueError): cases.pipeline('same',cat)
 def test_holdout(self): self.assertEqual(cases.pipeline('über', [{'view':'new_view','aliases':['ÜBER']}]),'SELECT * FROM new_view')
class Route(unittest.TestCase):
 def test_prefix_rejected(self): self.assertIsNone(cases.select_route(['sales','stock'],'s'))
 def test_unknown(self): self.assertIsNone(cases.select_route(['sales','stock'],'xyz'))
 def test_exact(self): self.assertEqual(cases.select_route(['sales','stock'],'sales'),'sales')
 def test_casefold(self): self.assertEqual(cases.select_route(['Straße'],'STRASSE'),'Straße')
 def test_trim(self): self.assertEqual(cases.select_route([' Sales '],' sales '),' Sales ')
 def test_duplicate(self): self.assertIsNone(cases.select_route(['Sales','sales'],'sales'))
 def test_empty_labels(self): self.assertIsNone(cases.select_route([],'sales'))
 def test_empty_query(self): self.assertIsNone(cases.select_route(['sales'],''))
 def test_blank_query(self): self.assertIsNone(cases.select_route([' '],' '))
 def test_holdout(self): self.assertEqual(cases.select_route(['Archive','receipt'],' RECEIPT '),'receipt')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('suite',choices=['simple','retrieval','route','all']);args=p.parse_args()
 suites={'simple':Simple,'retrieval':Retrieval,'route':Route}
 tests=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for k,c in suites.items() if args.suite in (k,'all'))
 result=unittest.TextTestRunner(verbosity=2).run(tests)
 sys.exit(not result.wasSuccessful())
