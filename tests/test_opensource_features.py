import importlib.util
import json
import math
import unittest
from unittest.mock import patch

from invest.opensource.common import validated_series
from invest.opensource.features import run


SERIES = [100 + i * .1 + math.sin(i * .7) for i in range(64)]


class InputTests(unittest.TestCase):
    def test_strict_bounded_input(self):
        for value in [True, '1', None, float('nan'), float('inf'), 10**1000, -1000001]:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                validated_series({'values': [1.] * 7 + [value]})
        for payload in [{'values': [1] * 7}, {'values': [1] * 5001}, {'values': [1]*8, 'sql': 'select 1'}, {'path': '/tmp/x'}, [], None]:
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(ValueError):
                validated_series(payload)

    def test_input_not_mutated(self):
        payload = {'values': list(range(8))}
        before = json.dumps(payload)
        self.assertEqual(validated_series(payload), list(map(float, range(8))))
        self.assertEqual(json.dumps(payload), before)

    def test_no_dynamic_backend_import(self):
        with patch('importlib.import_module') as importer:
            with self.assertRaises(ValueError):
                run('os.system', {'values': SERIES})
            importer.assert_not_called()

    def test_missing_backend_no_fallback(self):
        with patch('invest.opensource.common.importlib.import_module', side_effect=ModuleNotFoundError):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                run('ffn', {'values': SERIES})


@unittest.skipUnless(importlib.util.find_spec('ta'), 'optional ta not installed')
class TATests(unittest.TestCase):
    def test_known_linear_series(self):
        r = run('ta', {'values': list(range(1, 33))})
        self.assertAlmostEqual(r['rsi_14'], 100)
        self.assertAlmostEqual(r['sma_20'], 22.5)
        self.assertFalse(r['warmup_filled'])

    def test_short_and_nonpositive_rejected(self):
        for values in [[1.] * 8, [0.] * 32, [-1.] * 32]:
            with self.assertRaises(ValueError): run('ta', {'values': values})


@unittest.skipUnless(importlib.util.find_spec('ffn'), 'optional ffn not installed')
class FFNTests(unittest.TestCase):
    def test_known_drawdown(self):
        r = run('ffn', {'values': [100, 120, 90, 99, 100, 100, 100, 110]})
        self.assertAlmostEqual(r['total_return'], .1)
        self.assertAlmostEqual(r['max_drawdown'], -.25)
        self.assertEqual(r['simple_returns_count'], 7)

    def test_constant_and_invalid(self):
        self.assertEqual(run('ffn', {'values': [2.] * 8})['max_drawdown'], 0)
        with self.assertRaises(ValueError): run('ffn', {'values': [0.] * 8})


@unittest.skipUnless(importlib.util.find_spec('networkx'), 'optional networkx not installed')
class NetworkTests(unittest.TestCase):
    def test_state_graph_counts(self):
        r = run('networkx', {'values': [1, 2, 1, 2, 1, 2, 1, 2]})
        self.assertEqual(r['nodes'], ['down', 'up'])
        self.assertEqual(sum(x['count'] for x in r['transitions']), 6)
        self.assertAlmostEqual(sum(r['pagerank'].values()), 1)

    def test_constant_graph(self):
        r = run('networkx', {'values': [1.] * 8})
        self.assertEqual(r['pagerank'], {'flat': 1.})


@unittest.skipUnless(importlib.util.find_spec('plotly'), 'optional plotly not installed')
class PlotlyTests(unittest.TestCase):
    def test_json_figure_preserves_input(self):
        r = run('plotly', {'values': SERIES})
        self.assertEqual(r['figure']['data'][0]['y'], SERIES)
        self.assertEqual(r['figure']['data'][0]['x'], list(range(64)))
        self.assertFalse(r['external_resources_requested'])
        self.assertNotIn('<script', json.dumps(r))


@unittest.skipUnless(importlib.util.find_spec('sklearn'), 'optional sklearn not installed')
class SklearnTests(unittest.TestCase):
    def test_chronology_and_finite_mae(self):
        r = run('sklearn', {'values': SERIES})
        self.assertEqual(len(r['folds']), 3)
        for f in r['folds']:
            self.assertLess(f['train_target_last_index'] + 1, f['test_target_first_index'])
            self.assertGreaterEqual(f['ridge_mae'], 0)
            self.assertTrue(math.isfinite(f['ridge_mae']))

    def test_constant_and_short(self):
        r = run('sklearn', {'values': [2.] * 40})
        self.assertTrue(all(f['ridge_mae'] == f['persistence_mae'] == 0 for f in r['folds']))
        with self.assertRaises(ValueError): run('sklearn', {'values': [1.] * 8})

    def test_later_values_cannot_change_first_fold(self):
        original = run('sklearn', {'values': SERIES})
        altered = SERIES[:]
        altered[-1] = 10000
        result = run('sklearn', {'values': altered})
        self.assertEqual(original['folds'][0], result['folds'][0])
