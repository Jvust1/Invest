import unittest
from unittest.mock import patch

from invest.overfit_cv import combinatorial_purged_cv_plan


class FakeCV:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def split(self, X):
        yield [4, 5], [[0, 1], [2, 3]]
        yield [0, 1], [[2, 3], [4, 5]]


def sample_dates():
    return [f"2026-08-{day:02d}" for day in range(1, 7)]


class PurgedCVPlanTests(unittest.TestCase):
    def test_plan_is_auditable_and_development_only(self):
        with patch("invest.overfit_cv._load_skfolio_cpcv", return_value=(FakeCV, "1.4.9")):
            result = combinatorial_purged_cv_plan(
                sample_dates(), n_folds=3, n_test_folds=2, purged_size=0, embargo_size=0
            )
        self.assertEqual(result["status"], "DEVELOPMENT_MODEL_SELECTION_ONLY")
        self.assertEqual(result["backend_version"], "1.4.9")
        self.assertEqual(result["n_splits"], 2)
        self.assertEqual(len(result["plan_sha256"]), 64)
        for split in result["splits"]:
            self.assertFalse(set(split["train_indices"]) & set(split["test_indices"]))

    def test_same_input_produces_same_plan_identity(self):
        with patch("invest.overfit_cv._load_skfolio_cpcv", return_value=(FakeCV, "1.4.9")):
            left = combinatorial_purged_cv_plan(
                sample_dates(), n_folds=3, n_test_folds=2, purged_size=0, embargo_size=0
            )
            right = combinatorial_purged_cv_plan(
                sample_dates(), n_folds=3, n_test_folds=2, purged_size=0, embargo_size=0
            )
        self.assertEqual(left["plan_sha256"], right["plan_sha256"])

    def test_invalid_time_axis_and_fold_config_fail_closed(self):
        with self.assertRaises(ValueError):
            combinatorial_purged_cv_plan(list(reversed(sample_dates())))
        with self.assertRaises(ValueError):
            combinatorial_purged_cv_plan(sample_dates(), n_folds=3, n_test_folds=3)


if __name__ == "__main__":
    unittest.main()
