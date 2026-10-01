import unittest
import importlib.util
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from unittest.mock import patch

from invest.optuna_walkforward import _walkforward_score, optimize_sma_walkforward
from invest.pipeline import moving_average_signal, run_backtest


class Trial:
    number = 0
    params = {"fast": 5, "slow": 12}
    value = None

    def suggest_int(self, name, low, high):
        return self.params[name]


class Study:
    def __init__(self):
        self.best_trial = Trial()

    def optimize(self, objective, n_trials):
        self.best_trial.value = objective(self.best_trial)


class OptunaWalkForwardTests(unittest.TestCase):
    def test_injected_study_runs_without_optuna_dependency(self):
        close = pd.Series([100 + i * 0.2 for i in range(120)])
        result = optimize_sma_walkforward(close, n_trials=1, splits=3, study=Study())
        self.assertEqual(result.params, {"fast": 5, "slow": 12})
        self.assertEqual(len(result.fold_scores), 3)

    def test_too_short_history_fails_closed(self):
        with self.assertRaises(ValueError):
            optimize_sma_walkforward(pd.Series(range(12)), n_trials=1, splits=3, study=Study())

    def test_fold_scores_use_only_validation_returns(self):
        close = pd.Series([100 + i * 0.2 for i in range(120)])
        score, folds = _walkforward_score(close, fast=5, slow=12, fee_bps=5, splits=3)
        expected = []
        for train, test in TimeSeriesSplit(n_splits=3).split(close):
            window = close.iloc[:test[-1] + 1]
            run = run_backtest(window, moving_average_signal(window, 5, 12), fee_bps=5)
            returns = run.iloc[test]['strategy_return']
            total = float((1 + returns).prod() - 1)
            volatility = float(returns.std(ddof=1) * np.sqrt(252))
            expected.append(float(returns.mean()) * 252 / volatility if volatility else 0)
        np.testing.assert_allclose(folds, expected)
        self.assertAlmostEqual(score, sum(expected) / len(expected))

    def test_invalid_history_fails_before_optimizer_runs(self):
        good = pd.Series([100 + i * .2 for i in range(120)])
        cases = [good.iloc[::-1], pd.Series(good.to_numpy(), index=[0] * len(good))]
        for value in [float('nan'), float('inf'), 0.0, -1.0]:
            bad = good.copy(); bad.iloc[50] = value; cases.append(bad)
        for close in cases:
            study = Study()
            with self.subTest(kind=str(close.index[:2])), patch.object(study, 'optimize') as optimize:
                with self.assertRaises(ValueError):
                    optimize_sma_walkforward(close, n_trials=1, study=study)
                optimize.assert_not_called()

    def test_invalid_budget_fees_and_seed_rejected(self):
        close = pd.Series([100 + i * .2 for i in range(120)])
        cases = [{'n_trials': True}, {'n_trials': 101}, {'splits': 1}, {'splits': 6},
                 {'fee_bps': float('nan')}, {'fee_bps': float('inf')}, {'fee_bps': 10000},
                 {'fee_bps': -1}, {'fee_bps': True}, {'seed': -1}, {'seed': True}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                optimize_sma_walkforward(close, study=Study(), **kwargs)

    def test_completed_trials_retained_and_injected_seed_not_claimed(self):
        result = optimize_sma_walkforward(pd.Series([100 + i * .2 for i in range(120)]),
                                         n_trials=1, splits=3, study=Study())
        self.assertEqual(len(result.trials), 1)
        self.assertEqual(result.trials[0]['params'], result.params)
        self.assertEqual(result.trials[0]['score'], result.score)
        self.assertIsNone(result.seed)

    def test_prior_unbound_trials_rejected(self):
        study = Study(); study.trials = [object()]
        with self.assertRaisesRegex(ValueError, 'fresh study'):
            optimize_sma_walkforward(pd.Series([100 + i * .2 for i in range(120)]), study=study)

    @unittest.skipUnless(importlib.util.find_spec('optuna'), 'optional Optuna not installed')
    def test_real_optuna_sampler_is_seeded_and_space_has_warmup(self):
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        close = pd.Series(100 + np.cumsum(np.random.default_rng(11).normal(.1, .8, 120)))
        a = optimize_sma_walkforward(close, n_trials=12, splits=3, seed=12)
        b = optimize_sma_walkforward(close, n_trials=12, splits=3, seed=12)
        self.assertEqual(a, b)
        self.assertEqual(a.seed, 12)
        self.assertEqual(len(a.trials), 12)
        self.assertEqual(a.optimizer_version, optuna.__version__)
        self.assertEqual(len(a.training_fingerprint), 64)
        self.assertTrue(all(t['params']['slow'] <= 30 for t in a.trials))


if __name__ == "__main__":
    unittest.main()
