import unittest
from contextlib import contextmanager

from invest.mlflow_tracking import MLflowExperimentTracker


class FakeMLflow:
    def __init__(self):
        self.experiment = None
        self.params = []
        self.metrics = []
        self.tags = []

    def set_experiment(self, name):
        self.experiment = name

    @contextmanager
    def start_run(self, run_name=None):
        yield {"run_name": run_name}

    def log_params(self, params):
        self.params.append(params)

    def log_metrics(self, metrics):
        self.metrics.append(metrics)

    def set_tags(self, tags):
        self.tags.append(tags)


class MLflowTrackingTests(unittest.TestCase):
    def test_tracker_logs_research_metadata(self):
        fake = FakeMLflow()
        run = MLflowExperimentTracker(fake, experiment_name="Invest-A-share").track(
            run_name="baseline",
            params={"fast": 20, "slow": 50},
            metrics={"sharpe": 1.2, "max_drawdown": -0.1},
            tags={"backend": "invest-core"},
        )
        self.assertEqual(fake.experiment, "Invest-A-share")
        self.assertEqual(run["run_name"], "baseline")
        self.assertEqual(fake.params[0]["fast"], 20)
        self.assertAlmostEqual(fake.metrics[0]["sharpe"], 1.2)
        self.assertEqual(fake.tags[0]["backend"], "invest-core")


if __name__ == "__main__":
    unittest.main()
