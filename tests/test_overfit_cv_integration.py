import importlib.util
import unittest

from invest.overfit_cv import combinatorial_purged_cv_plan


@unittest.skipUnless(importlib.util.find_spec("skfolio"), "skfolio optional dependency absent")
class SkfolioPurgedCVIntegrationTests(unittest.TestCase):
    def test_real_cpcv_has_disjoint_train_test_sets(self):
        dates = [f"2026-07-{day:02d}" for day in range(1, 31)]
        result = combinatorial_purged_cv_plan(
            dates,
            n_folds=5,
            n_test_folds=2,
            purged_size=1,
            embargo_size=1,
        )
        self.assertEqual(result["backend"], "skfolio.CombinatorialPurgedCV")
        self.assertGreater(result["n_splits"], 1)
        for split in result["splits"]:
            self.assertFalse(set(split["train_indices"]) & set(split["test_indices"]))


if __name__ == "__main__":
    unittest.main()
