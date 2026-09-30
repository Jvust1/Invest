import unittest
import pandas as pd

from invest.optuna_walkforward import optimize_sma_walkforward


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


if __name__ == "__main__":
    unittest.main()
