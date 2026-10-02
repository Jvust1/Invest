"""Synthetic-only Qlib binary data -> real SDK -> both Invest research pipelines.

Run: python -m examples.qlib_local_research
Never downloads market data. Values are fictional, native normalized units.
"""
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from invest.pipeline import run_a_share_sma_backtest
from invest.qlib_bridge import create_qlib_market_provider
from invest.research_pipeline import run_a_share_research_bundle


def write_synthetic_dataset(root: Path, *, scale: float = 1.0) -> pd.DataFrame:
    """Write the documented Qlib calendar/manifest/float32 binary layout.

    This is Invest-authored fixture construction, not downloaded market data.
    Each binary begins with its little-endian float32 calendar-start offset,
    followed by one little-endian float32 value per calendar date.
    """
    root.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2025-01-02", periods=120)
    close = scale * (1.0 + np.arange(len(dates)) * 0.002 + np.sin(np.arange(len(dates)) / 7) * 0.03)
    frame = pd.DataFrame({"open": close * 0.998, "high": close * 1.01,
                          "low": close * 0.99, "close": close, "volume": np.arange(len(dates)) + 1000.0}, index=dates)
    (root / "calendars").mkdir()
    (root / "instruments").mkdir()
    (root / "features" / "sh000001").mkdir(parents=True)
    (root / "calendars" / "day.txt").write_text("\n".join(dates.strftime("%Y-%m-%d")) + "\n", encoding="utf-8")
    (root / "instruments" / "all.txt").write_text(f"SH000001\t{dates[0]:%Y-%m-%d}\t{dates[-1]:%Y-%m-%d}\n", encoding="utf-8")
    for field in frame:
        np.r_[0.0, frame[field]].astype("<f4").tofile(root / "features" / "sh000001" / f"{field}.day.bin")
    return frame


def main():
    with tempfile.TemporaryDirectory(prefix="invest-synthetic-qlib-") as directory:
        root = Path(directory)
        expected = write_synthetic_dataset(root)
        provider = create_qlib_market_provider(provider_uri=root)
        arguments = {"start_date": expected.index[0].strftime("%Y-%m-%d"),
                     "end_date": expected.index[-1].strftime("%Y-%m-%d"),
                     "adjust": "qlib", "fast": 5, "slow": 20}
        result, summary = run_a_share_sma_backtest("000001.SH", provider_instance=provider, **arguments)
        bundle = run_a_share_research_bundle(provider, "SH000001", **arguments)
        pd.testing.assert_frame_equal(result, bundle.backtest)
        assert summary == bundle.summary
        assert result.attrs["market_data"]["dataset_sha256"] == bundle.market.attrs["market_data"]["dataset_sha256"]
        print(f"Synthetic-only Qlib {len(result)} rows -> both research pipelines verified")
        print(f"Basis: {result.attrs['market_data']['price_basis']}; tracking disabled; no market download")


if __name__ == "__main__":
    main()
