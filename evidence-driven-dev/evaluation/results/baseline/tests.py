import unittest
from cases import bounded, retrieve, compile_sql, pipeline, select_route

CATALOG = [
    {'view': 'sales_view', 'aliases': ['Revenue', 'SALES']},
    {'view': 'stock_view', 'aliases': ['Stock']},
]

class BoundsTests(unittest.TestCase):
    def test_upper_inclusive(self):
        self.assertEqual(bounded(10, 0, 10), 10)
    def test_above_upper(self):
        self.assertEqual(bounded(100, 0, 10), 10)
    def test_lower_inclusive(self):
        self.assertEqual(bounded(0, 0, 10), 0)
    def test_below_lower(self):
        self.assertEqual(bounded(-3, 0, 10), 0)
    def test_interior(self):
        self.assertEqual(bounded(5, 0, 10), 5)
    def test_single_point(self):
        self.assertEqual(bounded(4, 5, 5), 5)
    def test_fraction(self):
        self.assertEqual(bounded(1.5, 0, 2), 1.5)
    def test_negative_interval(self):
        self.assertEqual(bounded(-1, -10, -2), -2)
    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            bounded(1, 10, 0)

class RetrievalTests(unittest.TestCase):
    def test_single_node_replay(self):
        self.assertEqual(retrieve({'question': 'revenue'}, CATALOG), ['sales_view'])
    def test_full_pipeline(self):
        self.assertEqual(pipeline('revenue', CATALOG), 'SELECT * FROM sales_view')
    def test_case_metamorphic(self):
        for question in ['Revenue', 'REVENUE', ' sales ', 'SaLeS']:
            with self.subTest(question=question):
                self.assertEqual(pipeline(question, CATALOG), 'SELECT * FROM sales_view')
    def test_other_view(self):
        self.assertEqual(pipeline('stock', CATALOG), 'SELECT * FROM stock_view')
    def test_unknown_rejected(self):
        with self.assertRaises(ValueError):
            pipeline('unknown', CATALOG)
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            pipeline('', CATALOG)
    def test_multiple_rejected(self):
        with self.assertRaises(ValueError):
            pipeline('revenue stock', CATALOG)
    def test_conflicting_catalog_rejected(self):
        with self.assertRaises(ValueError):
            pipeline('revenue', CATALOG + [{'view': 'other', 'aliases': ['revenue']}])
    def test_compiler_contract(self):
        for candidates in [[], ['one', 'two']]:
            with self.subTest(candidates=candidates), self.assertRaises(ValueError):
                compile_sql({'candidates': candidates})
    def test_unseen_alias(self):
        self.assertEqual(pipeline('expenses', [{'view': 'costs', 'aliases': ['Expenses']}]), 'SELECT * FROM costs')

class RoutingTests(unittest.TestCase):
    def test_partial_rejected(self):
        self.assertIsNone(select_route(['sales', 'stock'], 's'))
    def test_exact(self):
        self.assertEqual(select_route(['sales', 'stock'], 'sales'), 'sales')
    def test_normalization(self):
        self.assertEqual(select_route(['Sales', 'stock'], '  SALES  '), 'Sales')
    def test_unknown(self):
        self.assertIsNone(select_route(['sales', 'stock'], 'unknown'))
    def test_empty_labels(self):
        self.assertIsNone(select_route([], 'sales'))
    def test_empty_query(self):
        self.assertIsNone(select_route(['sales'], ''))
    def test_blank_query(self):
        self.assertIsNone(select_route([''], '  '))
    def test_duplicate_exact(self):
        self.assertIsNone(select_route(['sales', 'sales'], 'sales'))
    def test_duplicate_normalized(self):
        self.assertIsNone(select_route(['Sales', ' sales '], 'sales'))
    def test_casefold(self):
        self.assertEqual(select_route(['Straße'], 'STRASSE'), 'Straße')
    def test_unseen_label(self):
        self.assertEqual(select_route(['invoices', 'payments'], ' PAYMENTS '), 'payments')

if __name__ == '__main__':
    unittest.main()
