"""Small Qlib interoperability bridge; Qlib remains an optional dependency."""
from __future__ import annotations
import pandas as pd

def to_qlib_frame(history: pd.DataFrame, instrument: str = "unknown") -> pd.DataFrame:
    """Convert OHLCV rows into Qlib's (instrument, datetime) index shape."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "datetime"
    frame["instrument"] = instrument
    frame = frame.reset_index().set_index(["instrument", "datetime"]).sort_index()
    return frame[["open", "high", "low", "close", "volume"]]

def load_qlib_features(instruments, fields, start_time, end_time, provider_uri=None):
    """Read features through Qlib's data API when pyqlib is installed."""
    try:
        import qlib
        from qlib.data import D
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Qlib is optional; install the 'qlib' extra to load features") from exc
    if provider_uri:
        from qlib.config import REG_CN
        qlib.init(provider_uri=provider_uri, region=REG_CN)
    return D.features(instruments, fields, start_time, end_time)


class QlibMarketProvider:
    """Expose Qlib's D.features API behind Invest's normalized history contract."""

    name = "qlib"

    def __init__(self, data_api, *, instrument_prefix: str | None = None):
        if not callable(getattr(data_api, "features", None)):
            raise TypeError("data_api must provide features()")
        self._data = data_api
        self.instrument_prefix = instrument_prefix

    @staticmethod
    def normalize_instrument(symbol: str) -> str:
        raw = str(symbol).strip().upper()
        if raw.startswith(("SH", "SZ")) and len(raw) == 8:
            return raw
        digits = "".join(ch for ch in raw if ch.isdigit()).zfill(6)
        if len(digits) != 6:
            raise ValueError("symbol must contain a six-digit A-share code")
        prefix = "SH" if digits.startswith(("5", "6", "9")) else "SZ"
        return prefix + digits

    def history(
        self,
        symbol: str,
        *,
        start_date: str = "2000-01-01",
        end_date: str = "2050-01-01",
        adjust: str = "",
    ) -> pd.DataFrame:
        instrument = self.normalize_instrument(symbol)
        fields = ["$open", "$high", "$low", "$close", "$volume"]
        frame = self._data.features(
            [instrument],
            fields,
            start_time=start_date,
            end_time=end_date,
            freq="day",
        )
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Qlib D.features must return pandas.DataFrame")
        if frame.empty:
            return frame
        result = frame.copy()
        if isinstance(result.index, pd.MultiIndex):
            try:
                result = result.xs(instrument, level=0)
            except Exception:
                pass
        result = result.rename(columns={
            "$open": "open",
            "$high": "high",
            "$low": "low",
            "$close": "close",
            "$volume": "volume",
        })
        required = ["open", "high", "low", "close", "volume"]
        missing = [name for name in required if name not in result.columns]
        if missing:
            raise ValueError(f"Qlib features missing normalized columns: {missing}")
        result = result[required].copy()
        result.index = pd.to_datetime(result.index)
        result.index.name = "date"
        for name in required:
            result[name] = pd.to_numeric(result[name], errors="coerce")
        return result.sort_index()


def create_qlib_market_provider(*, provider_uri=None):
    """Initialize Qlib lazily and return a provider compatible with Invest research pipelines."""
    try:
        import qlib
        from qlib.config import REG_CN
        from qlib.data import D
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Qlib is optional; install the 'qlib' extra before enabling it") from exc
    kwargs = {"region": REG_CN}
    if provider_uri is not None:
        kwargs["provider_uri"] = provider_uri
    qlib.init(**kwargs)
    return QlibMarketProvider(D)
