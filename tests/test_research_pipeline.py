import unittest
import importlib.util
import numpy as np
from unittest.mock import patch

import pandas as pd

from invest.research_pipeline import run_a_share_research_bundle
from invest.optuna_walkforward import OptimizationResult


class Provider:
    def history(self, **kwargs):
        idx = pd.date_range("2026-01-01", periods=8)
        return pd.DataFrame(
            {
                "high": [10,11,12,13,14,15,16,17],
                "low": [8,9,10,11,12,13,14,15],
                "close": [9,10,11,12,13,14,15,16],
            },
            index=idx,
        )


class Features:
    def transform(self, frame):
        result = frame.copy()
        result["ta_rsi_14"] = 50.0
        return result


class ResearchBundleTests(unittest.TestCase):
    def test_provider_features_and_backtest_are_fused(self):
        bundle = run_a_share_research_bundle(
            Provider(), "000001", feature_engineer=Features(), fast=2, slow=3
        )
        self.assertIn("ta_rsi_14", bundle.market.columns)
        self.assertIn("equity", bundle.backtest.columns)
        self.assertIn("max_drawdown", bundle.summary)
        self.assertIsNone(bundle.optimization)
        self.assertIsNone(bundle.research_split)

    def test_bad_feature_engineer_fails_closed(self):
        with self.assertRaises(TypeError):
            run_a_share_research_bundle(
                Provider(), "000001", feature_engineer=object(), fast=2, slow=3
            )


class LongProvider:
    def __init__(self):
        self.calls = 0
        self.frame = pd.DataFrame({'close': 100 + np.cumsum(np.random.default_rng(8).normal(.1, .5, 240))},
                                  index=pd.date_range('2025-01-01', periods=240, freq='B'))

    def history(self, **kwargs):
        self.calls += 1
        return self.frame.copy()


class OptimizedResearchBundleTests(unittest.TestCase):
    def test_fraction_cutoff_is_not_one_row_early_from_float_rounding(self):
        provider = LongProvider()
        provider.frame = pd.DataFrame({'close': np.linspace(100, 120, 360)})
        selected = OptimizationResult({'fast': 5, 'slow': 12}, .4, (.3, .4, .5))
        with patch('invest.optuna_walkforward.optimize_sma_walkforward', return_value=selected):
            bundle = run_a_share_research_bundle(provider, '000001', optimization_trials=5)
        self.assertEqual(bundle.research_split['training_observations'], 252)
        self.assertEqual(len(bundle.backtest), 108)

    def test_provider_to_search_to_later_evaluation_is_wired(self):
        provider = LongProvider()
        selected = OptimizationResult({'fast': 5, 'slow': 12}, .4, (.3, .4, .5))
        with patch('invest.optuna_walkforward.optimize_sma_walkforward', return_value=selected) as search:
            bundle = run_a_share_research_bundle(provider, '000001', optimization_trials=5)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(search.call_args.args[0]), 168)
        self.assertEqual(search.call_args.args[0].index[-1], provider.frame.index[167])
        self.assertEqual(bundle.backtest.index[0], provider.frame.index[168])
        self.assertEqual(len(bundle.backtest), 72)
        self.assertEqual(bundle.optimization, selected)
        self.assertFalse(bundle.research_split['frozen_holdout_opened'])
        self.assertAlmostEqual(bundle.summary['total_return'],
                               float((1 + bundle.backtest.strategy_return).prod() - 1))
        self.assertAlmostEqual(bundle.backtest.equity.iloc[-1], 1 + bundle.summary['total_return'])

    @unittest.skipUnless(importlib.util.find_spec('optuna'), 'optional Optuna not installed')
    def test_real_optimizer_never_sees_changed_future_prices(self):
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        provider = LongProvider()
        before = run_a_share_research_bundle(provider, '000001', optimization_trials=4, optimization_seed=9)
        provider.frame.iloc[168:, 0] *= np.linspace(1, 2, 72)
        after = run_a_share_research_bundle(provider, '000001', optimization_trials=4, optimization_seed=9)
        self.assertEqual(before.optimization, after.optimization)
        self.assertNotEqual(before.summary, after.summary)
        self.assertEqual(provider.calls, 2)

    def test_invalid_split_settings_and_unused_study_rejected(self):
        for fraction in [True, 0, 1, float('nan'), .99]:
            with self.subTest(fraction=fraction), self.assertRaises(ValueError):
                run_a_share_research_bundle(LongProvider(), '000001', optimization_trials=1,
                                           training_fraction=fraction)
        with self.assertRaisesRegex(ValueError, 'requires optimization_trials'):
            run_a_share_research_bundle(LongProvider(), '000001', optimization_study=object())


if __name__ == "__main__":
    unittest.main()
