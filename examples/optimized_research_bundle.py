"""Offline Optuna integration demo. Run after pip install -e '.[optuna]'."""
from dataclasses import asdict
import json

import numpy as np
import pandas as pd

from invest.research_pipeline import run_a_share_research_bundle


class SyntheticProvider:
    """No network, API credentials or real market data."""
    def history(self, **kwargs):
        generator = np.random.default_rng(17)
        return pd.DataFrame(
            {'close': 100 * np.exp(np.cumsum(generator.normal(0, 0.01, 360)))},
            index=pd.date_range('2024-01-01', periods=360, freq='B'),
        )


if __name__ == '__main__':
    bundle = run_a_share_research_bundle(
        SyntheticProvider(), 'SYNTHETIC', optimization_trials=12,
        optimization_splits=3, training_fraction=0.7, optimization_seed=7,
    )
    print(json.dumps({'source': 'SYNTHETIC_NOT_REAL_MARKET_DATA',
                      'summary': bundle.summary, 'split': bundle.research_split,
                      'optimization': asdict(bundle.optimization)},
                     indent=2, allow_nan=False))
