"""Optional MLflow tracking bridge for reproducible Invest research.

Upstream: mlflow/mlflow @
7faf28476bddcebb68ee8b08cdcba1bee7ad6109 (Apache-2.0).
"""
from __future__ import annotations

from typing import Any, Mapping


class MLflowExperimentTracker:
    def __init__(self, mlflow_module: Any, *, experiment_name: str = "Invest") -> None:
        for name in ("set_experiment", "start_run", "log_params", "log_metrics", "set_tags"):
            if not callable(getattr(mlflow_module, name, None)):
                raise TypeError(f"mlflow module must provide {name}()")
        self._mlflow = mlflow_module
        self.experiment_name = str(experiment_name).strip() or "Invest"

    def track(
        self,
        *,
        run_name: str,
        params: Mapping[str, Any] | None = None,
        metrics: Mapping[str, float] | None = None,
        tags: Mapping[str, Any] | None = None,
    ) -> Any:
        self._mlflow.set_experiment(self.experiment_name)
        with self._mlflow.start_run(run_name=str(run_name).strip() or None) as run:
            if params:
                self._mlflow.log_params(dict(params))
            if metrics:
                self._mlflow.log_metrics({str(k): float(v) for k, v in metrics.items()})
            if tags:
                self._mlflow.set_tags({str(k): str(v) for k, v in tags.items()})
            return run


def create_mlflow_tracker(*, experiment_name: str = "Invest") -> MLflowExperimentTracker:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow is optional; install Invest with the 'mlflow' extra before enabling tracking"
        ) from exc
    return MLflowExperimentTracker(mlflow, experiment_name=experiment_name)
