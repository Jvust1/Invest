"""Synthetic-only, executable train/test isolation and production-path tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sklearn.model_selection import TimeSeriesSplit

from invest.data import dataset_identity, demo_dataset
from invest.engine import backtest
from invest.experiments import run_study
from invest.walkforward import plan_folds
from invest.workspace import Workspace


def specification(**configuration):
    return {'symbol': '600000.SH', 'cost_model_acknowledged': True,
            'walk_forward': {'n_splits': 3, 'gap': 5, **configuration}}


class WalkForwardTests(unittest.TestCase):
    def setUp(self):
        self.dataset = demo_dataset()

    def test_actual_upstream_splitter_contract(self):
        bars = [b for b in self.dataset['bars'] if b['symbol'] == '600000.SH']
        config, folds = plan_folds(bars, 30, {'n_splits': 3, 'gap': 4, 'max_train_size': 20})
        days = [bar['date'] for bar in bars[30:]]
        for fold, (train, test) in zip(folds, TimeSeriesSplit(**config).split(days)):
            self.assertEqual(fold['train']['start'], days[train[0]])
            self.assertEqual(fold['train']['end'], days[train[-1]])
            self.assertEqual(fold['test']['start'], days[test[0]])
            self.assertEqual(fold['test']['end'], days[test[-1]])
            self.assertLess(fold['train']['end'], fold['test']['start'])
            self.assertEqual(test[0] - train[-1] - 1, 4)
            self.assertEqual(len(train), 20)

    def test_existing_study_path_replays_and_persists_complete_report(self):
        report = run_study(self.dataset, specification())
        self.assertEqual(report, run_study(self.dataset, specification()))
        self.assertEqual(report['summary'], {'planned': 9, 'succeeded': 9, 'failed': 0,
            'below_buy_hold': sum(r['excess_vs_buy_hold'] < 0 for r in report['results']),
            'training_runs': 18})
        self.assertFalse(report['protocol']['frozen_holdout_opened'])
        self.assertEqual(report['protocol']['splitter'], 'sklearn.model_selection.TimeSeriesSplit')
        self.assertEqual(report['protocol']['parameter_budget'], 27)
        for row in report['results']:
            self.assertLess(row['selected_on_or_before'], row['test_window']['start'])
            self.assertEqual(row['result']['evaluation_start'], row['test_window']['start'])
            self.assertEqual(row['replay']['status'], 'PASS')
            scores = [r['excess_vs_buy_hold'] for r in row['training']]
            best = scores.index(max(scores))
            self.assertEqual(row['candidate'], row['training'][best]['candidate'])
            self.assertEqual(row['training_score'], scores[best])
            self.assertTrue(all(r['replay']['status'] == 'PASS' for r in row['training']))
        json.dumps(report, allow_nan=False)
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp) / 'state.sqlite')
            saved = workspace.put('study', report)
            self.assertEqual(workspace.get(saved['id'])['payload'], report)
            self.assertEqual(workspace.put('study', report)['id'], saved['id'])

    def test_future_price_changes_cannot_choose_an_earlier_candidate(self):
        before = run_study(self.dataset, specification())
        cutoff = before['protocol']['folds'][0]['train']['end']
        changed = copy.deepcopy(self.dataset)
        for bar in changed['bars']:
            if bar['date'] > cutoff:
                for field in ('open', 'high', 'low', 'close', 'up_limit', 'down_limit'):
                    bar[field] = round(bar[field] * 2, 2)
        changed['id'] = dataset_identity(changed)
        after = run_study(changed, specification())
        for old, new in zip(before['results'][:3], after['results'][:3]):
            self.assertEqual(old['candidate'], new['candidate'])
            self.assertEqual(old['training_score'], new['training_score'])
            self.assertEqual([r['result']['metrics'] for r in old['training']],
                             [r['result']['metrics'] for r in new['training']])
        self.assertNotEqual(before['protocol_id'], after['protocol_id'])

    def test_no_test_backtest_is_run_before_training_selection(self):
        calls = []

        def observe(dataset, params):
            calls.append((params['fast'], params['slow'], params['start_date'], params['end_date']))
            return backtest(dataset, params)

        with patch('invest.engine.backtest', side_effect=observe):
            report = run_study(self.dataset, specification())
        self.assertEqual(len(calls), 27)
        for offset, row in enumerate(report['results']):
            group = calls[offset * 3:offset * 3 + 3]
            self.assertEqual([c[2:] for c in group[:2]],
                             [(row['train_window']['start'], row['train_window']['end'])] * 2)
            self.assertEqual(group[2][2:], (row['test_window']['start'], row['test_window']['end']))

    def test_failed_training_candidate_blocks_selection_and_retains_evidence(self):
        def fail_one(dataset, params):
            if params['fast'] == 5:
                raise ValueError('synthetic failed candidate')
            return backtest(dataset, params)

        with patch('invest.engine.backtest', side_effect=fail_one) as engine:
            report = run_study(self.dataset, specification())
        self.assertEqual(engine.call_count, 18)
        self.assertEqual(report['summary']['failed'], 9)
        for row in report['results']:
            self.assertIsNone(row['candidate'])
            self.assertNotIn('result', row)
            self.assertEqual(row['training'][0]['reason'], 'synthetic failed candidate')
            self.assertEqual(row['training'][1]['status'], 'PASS')

    def test_ties_use_declared_order(self):
        spec = specification()
        spec['candidates'] = [{'name': 'first', 'fast': 5, 'slow': 20},
                              {'name': 'second', 'fast': 5, 'slow': 20}]
        report = run_study(self.dataset, spec)
        self.assertEqual({row['candidate'] for row in report['results']}, {'first'})

    def test_fixed_test_and_rolling_training_windows(self):
        report = run_study(self.dataset, specification(test_size=15, max_train_size=20))
        for fold in report['protocol']['folds']:
            self.assertEqual(fold['train']['sessions'], 20)
            self.assertEqual(fold['test']['sessions'], 15)
        for left, right in zip(report['protocol']['folds'], report['protocol']['folds'][1:]):
            self.assertLess(left['test']['end'], right['test']['start'])

    def test_invalid_settings_fail_closed(self):
        for config in (None, True, {'gap': True}, {'gap': -1}, {'gap': 61},
                       {'n_splits': 1}, {'n_splits': 6}, {'n_splits': 3.0},
                       {'test_size': 9}, {'test_size': 5000}, {'max_train_size': 0},
                       {'holdout': True}, {'random_state': 7}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_study(self.dataset, {**specification(), 'walk_forward': config})

    def test_too_short_fold_and_oversized_history_rejected(self):
        bars = [b for b in self.dataset['bars'] if b['symbol'] == '600000.SH']
        for configuration in ({'n_splits': 5, 'gap': 60}, {'test_size': 40}):
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                plan_folds(bars, 30, configuration)
        with self.assertRaises(ValueError):
            plan_folds([{'date': f'{i:08d}'} for i in range(2600)], 30, {})

    def test_dataset_identity_cost_and_holdout_gates_unchanged(self):
        forged = copy.deepcopy(self.dataset)
        forged['bars'][0]['close'] += 1
        with self.assertRaises(ValueError):
            run_study(forged, specification())
        for extra in ({'cost_model_acknowledged': False}, {'holdout': True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                run_study(self.dataset, {**specification(), **extra})

    def test_default_study_remains_chronological_comparison(self):
        report = run_study(self.dataset, {'symbol': '600000.SH', 'cost_model_acknowledged': True})
        self.assertEqual(report['protocol']['mode'], 'EXPLORATORY_CHRONOLOGICAL_SLICES')
        self.assertEqual(report['summary']['planned'], 18)
        self.assertNotIn('training', report['results'][0])


if __name__ == '__main__':
    unittest.main()
