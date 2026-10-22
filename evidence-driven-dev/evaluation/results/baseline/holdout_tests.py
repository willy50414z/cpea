import itertools
import random
import unittest
from cases import bounded, pipeline, select_route

class HoldoutTests(unittest.TestCase):
    def test_bounded_general_intervals(self):
        generator = random.Random(27)
        for _ in range(100):
            low = generator.uniform(-50, 50)
            high = low + generator.uniform(0, 50)
            value = generator.uniform(-100, 100)
            with self.subTest(low=low, high=high, value=value):
                result = bounded(value, low, high)
                self.assertTrue(low <= result <= high)
                self.assertEqual(result, low if value < low else high if value > high else value)
    def test_retrieval_unseen_casefold_aliases(self):
        for alias in ['Straße', 'Invoices', 'Δείγμα']:
            catalog = [{'view': 'unseen_view', 'aliases': [alias]}]
            with self.subTest(alias=alias):
                self.assertEqual(pipeline(alias.upper(), catalog), 'SELECT * FROM unseen_view')
                self.assertEqual(pipeline(alias.lower(), catalog), 'SELECT * FROM unseen_view')
    def test_routing_permutation_and_legacy_threshold(self):
        for labels in itertools.permutations([' Invoices ', 'Archive', 'Sales']):
            for threshold in [0.0, 0.3, 0.6, 0.9, 1.1]:
                with self.subTest(labels=labels, threshold=threshold):
                    self.assertEqual(select_route(labels, 'INVOICES', threshold), ' Invoices ')
                    self.assertIsNone(select_route(labels, 'i', threshold))
                    self.assertIsNone(select_route([*labels, 'invoices'], 'INVOICES', threshold))

if __name__ == '__main__':
    unittest.main()
