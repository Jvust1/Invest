"""Run with: python -m examples.duckdb_offline_replay

Synthetic-only end-to-end example. No provider package or network is used.
The temporary DuckDB file is closed and reopened read-only before research.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from invest.pipeline import run_a_share_sma_backtest
from invest.providers import DuckDBMarketCache, DuckDBReplayProvider
from invest.research_pipeline import run_a_share_research_bundle


class SyntheticHistory:
    """Fictional prices and dates; these are not exchange-session evidence."""

    def __init__(self):
        self.calls = 0

    def history(self, *, symbol, start_date, end_date, period, adjust):
        self.calls += 1
        index = pd.date_range("2024-01-01", periods=120, name="date")
        close = 10. + np.arange(120) * .02 + np.sin(np.arange(120) / 7) * .4
        return pd.DataFrame({"symbol": [symbol] * len(index), "open": close - .03,
                             "high": close + .15, "low": close - .15, "close": close,
                             "volume": np.full(len(index), 1000.)}, index=index)


def run_example() -> dict:
    request = {"symbol": "000001", "start_date": "20240101", "end_date": "20240430", "adjust": "qfq"}
    source_id = "synthetic-example/v1;prices=fictional-qfq;volume=fictional-units"
    upstream = SyntheticHistory()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.duckdb"
        with DuckDBMarketCache(path) as cache:
            refresh = DuckDBReplayProvider(cache, source_id=source_id, upstream=upstream, mode="refresh")
            recorded = refresh.history(**request)
            snapshot_id = refresh.last_snapshot["snapshot_id"]
        # There is deliberately no upstream attached to the reopened provider.
        with DuckDBMarketCache(path, read_only=True) as cache:
            replay = DuckDBReplayProvider(cache, source_id=source_id)
            bundle = run_a_share_research_bundle(replay, **request, fast=5, slow=20)
            baseline, summary = run_a_share_sma_backtest(**request, provider_instance=replay, fast=5, slow=20)
            assert_frame_equal(bundle.backtest, baseline)
            assert_frame_equal(recorded, bundle.market)
            assert summary == bundle.summary
            assert bundle.market.attrs["duckdb_replay"]["snapshot_id"] == snapshot_id
            assert upstream.calls == 1
            return {"data_kind": "synthetic_only", "provider_calls": upstream.calls,
                    "replayed_rows": len(bundle.market), "provenance": replay.last_snapshot,
                    "summary": summary,
                    "boundary": "Exploratory close-to-close research; not A-share execution or strategy validation"}


if __name__ == "__main__":
    print(json.dumps(run_example(), indent=2, ensure_ascii=False, allow_nan=False))
