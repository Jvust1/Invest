"""Explicit native-price, local-only Qlib interoperability (optional SDK)."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from importlib import metadata
from pathlib import Path
import re

import numpy as np
import pandas as pd

QLIB_VERSION = "0.9.7"
MLFLOW_VERSION = "3.16.1"
OHLCV = ("open", "high", "low", "close", "volume")
FIELDS = tuple("$" + name for name in OHLCV)
MAX_ROWS = 20_000
WORKER_TIMEOUT = 45
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def to_qlib_frame(history: pd.DataFrame, instrument: str = "unknown") -> pd.DataFrame:
    """Convert OHLCV rows into Qlib's (instrument, datetime) index shape."""
    missing = set(OHLCV).difference(history.columns)
    if missing:
        raise ValueError(f"history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "datetime"
    frame["instrument"] = instrument
    frame = frame.reset_index().set_index(["instrument", "datetime"]).sort_index()
    return frame[list(OHLCV)]


def _date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})", value):
        raise ValueError(f"{label} must be YYYYMMDD or YYYY-MM-DD")
    try:
        return pd.Timestamp(datetime.strptime(value, "%Y%m%d" if len(value) == 8 else "%Y-%m-%d"))
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a valid daily date") from exc


def _window(start, end):
    start, end = _date(start, "start_date"), _date(end, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    try:
        span = (end - start).days + 1
    except (ValueError, OverflowError) as exc:
        raise ValueError("Qlib date window is out of supported bounds") from exc
    if span > MAX_ROWS:
        raise ValueError(f"Qlib request exceeds the {MAX_ROWS}-day limit")
    return start, end


def _local_directory(provider_uri):
    if not isinstance(provider_uri, (str, Path)) or not str(provider_uri):
        raise ValueError("provider_uri must be an explicit existing local Qlib directory")
    raw = str(provider_uri)
    if raw.startswith(("//", "\\\\")) or "://" in raw or (":" in raw and not re.match(r"^[A-Za-z]:[\\/]", raw)):
        raise ValueError("Qlib provider_uri must be a local directory, not a URL, UNC or NFS URI")
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("provider_uri must be an absolute existing local Qlib directory")
    root = path.resolve(strict=True)
    if str(root).startswith(("//", "\\\\")):
        raise ValueError("network directories are not supported")
    for relative in ("calendars/day.txt", "instruments/all.txt"):
        _local_file(root, relative)
    if not (root / "features").is_dir() or (root / "features").is_symlink():
        raise ValueError("Qlib dataset requires a local features directory")
    return root


def _local_file(root, relative):
    path = root / relative
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Qlib dataset is missing a confined local file: {relative}")
    if any(item.is_symlink() for item in (path, *path.parents) if item != root and root in item.parents):
        raise ValueError("Qlib dataset files must not be symlinks")
    if path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ValueError("Qlib dataset file exceeds the bounded local reader limit")
    return path


def _check_sdk_versions():
    for package, expected in (("pyqlib", QLIB_VERSION), ("mlflow", MLFLOW_VERSION)):
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError("Qlib is optional; install Invest's 'qlib' extra") from exc
        if actual != expected:
            raise RuntimeError(f"local Qlib reader requires {package}=={expected}; found {actual}")


class _LocalQlibDataAPI:
    """Every read gets an isolated SDK singleton; no parent Qlib/MLflow imports."""

    def __init__(self, root):
        self.root = root

    def features(self, instruments, fields, start_time, end_time, freq="day"):
        import json
        import os
        import subprocess
        import sys
        import tempfile

        if getattr(sys, "frozen", False):
            raise RuntimeError("local Qlib reader requires source Python, not the frozen executable")
        _check_sdk_versions()
        if freq != "day" or not isinstance(instruments, (list, tuple)) or not 1 <= len(instruments) <= 16:
            raise ValueError("local Qlib reader requires 1–16 explicit daily instruments")
        normalized = [QlibMarketProvider.normalize_instrument(item) for item in instruments]
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate instruments are not supported")
        if not isinstance(fields, (list, tuple)) or not fields or len(set(fields)) != len(fields) or any(item not in FIELDS for item in fields):
            raise ValueError("local Qlib reader supports only direct native $open/$high/$low/$close/$volume fields")
        start, end = _window(start_time, end_time)
        if len(normalized) * ((end - start).days + 1) > MAX_ROWS:
            raise ValueError("Qlib request exceeds the bounded total-row limit")
        root = _local_directory(self.root)
        request = {"root": str(root), "instruments": normalized, "fields": list(fields),
                   "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")}
        env = {key: value for key, value in os.environ.items() if not key.startswith(("MLFLOW_", "QLIB_"))}
        env.update(MLFLOW_DISABLE_TELEMETRY="true", DO_NOT_TRACK="true", MLFLOW_ENABLE_ASYNC_LOGGING="false",
                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        bootstrap = (
            "import sys\n"
            "def deny_network(event, args):\n"
            "    if event in {'socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.sendto','socket.bind'}:\n"
            "        raise RuntimeError('network disabled for the local Qlib reader')\n"
            "sys.addaudithook(deny_network)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from invest.qlib_local import worker_main\n"
            "worker_main()\n"
        )
        try:
            # The SDK cannot leave mlruns, caches or relative files in the caller's cwd.
            with tempfile.TemporaryDirectory(prefix="invest-qlib-") as temporary:
                completed = subprocess.run(
                    [sys.executable, "-I", "-c", bootstrap, str(Path(__file__).resolve().parent.parent)],
                    input=json.dumps(request).encode(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env=env, cwd=temporary, timeout=WORKER_TIMEOUT, check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("local Qlib data read timed out") from exc
        if completed.returncode or len(completed.stdout) > MAX_RESPONSE_BYTES:
            raise RuntimeError("local Qlib data worker failed or exceeded its output limit")
        try:
            result = json.loads(completed.stdout)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("local Qlib data worker returned an invalid response") from exc
        if result.get("status") != "ok":
            raise ValueError("local Qlib data unavailable: " + result.get("reason", "unknown error"))
        rows = result["rows"]
        index = pd.MultiIndex.from_tuples([(row[0], pd.Timestamp(row[1])) for row in rows], names=["instrument", "datetime"])
        frame = pd.DataFrame([row[2:] for row in rows], columns=fields, index=index)
        frame.attrs["market_data"] = result["metadata"]
        return frame


def load_qlib_features(instruments, fields, start_time, end_time, provider_uri=None):
    """Read bounded native OHLCV fields from an explicit local dataset, never global D.

    Arbitrary expressions, market aliases, remote sources and implicit defaults are
    deliberately unsupported. Returned values retain the dataset's native basis.
    """
    root = _local_directory(provider_uri)
    return _LocalQlibDataAPI(root).features(instruments, fields, start_time, end_time)


class QlibMarketProvider:
    """Adapt native Qlib values for exploratory return research, not cash execution.

    ``adjust='qlib'`` is required: native values may be first-day-normalized and
    adjusted by the data author. This adapter cannot claim raw, qfq or CNY units.
    Injected data APIs are caller-owned; use the factory for isolated local reads.
    """

    name = "qlib"

    def __init__(self, data_api, *, instrument_prefix: str | None = None):
        if not callable(getattr(data_api, "features", None)):
            raise TypeError("data_api must provide features()")
        if instrument_prefix is not None:
            raise ValueError("instrument_prefix is unsupported; specify the exchange in the symbol")
        self._data = data_api
        self.instrument_prefix = None

    @staticmethod
    def normalize_instrument(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a six-digit string, SH/SZ prefix, or .SH/.SZ suffix")
        raw = symbol.strip().upper()
        if re.fullmatch(r"(?:SH|SZ)[0-9]{6}", raw):
            return raw
        match = re.fullmatch(r"([0-9]{6})\.(SH|SZ)", raw)
        if match:
            return match[2] + match[1]
        if not re.fullmatch(r"[0-9]{6}", raw):
            raise ValueError("symbol must be a six-digit code with at most one explicit SH/SZ exchange")
        return ("SH" if raw.startswith(("5", "6", "9")) else "SZ") + raw

    def history(self, symbol: str, *, start_date: str = "2000-01-01", end_date: str = "2050-01-01", adjust: str = "", period: str = "daily") -> pd.DataFrame:
        if period != "daily":
            raise ValueError("Qlib supports only period='daily'")
        if adjust != "qlib":
            raise ValueError("Qlib supports only adjust='qlib' (native data basis); raw/qfq/hfq conversion is unavailable")
        instrument = self.normalize_instrument(symbol)
        start, end = _window(start_date, end_date)
        frame = self._data.features([instrument], list(FIELDS), start_time=start.strftime("%Y-%m-%d"),
                                    end_time=end.strftime("%Y-%m-%d"), freq="day")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Qlib D.features must return pandas.DataFrame")
        if frame.empty:
            raise ValueError(f"Qlib returned no data for {instrument}")
        if len(frame) > MAX_ROWS or not frame.columns.is_unique:
            raise ValueError("Qlib feature rows exceed the limit or columns are duplicated")
        if not isinstance(frame.index, pd.MultiIndex) or frame.index.nlevels != 2 or set(frame.index.names) != {"instrument", "datetime"}:
            raise ValueError("Qlib features must identify both instrument and datetime index levels")
        if set(frame.index.get_level_values("instrument")) != {instrument}:
            raise ValueError("Qlib features contain a missing or unexpected instrument")
        missing = set(FIELDS).difference(frame.columns)
        if missing:
            raise ValueError(f"Qlib features missing columns: {sorted(missing)}")
        result = frame.xs(instrument, level="instrument")[list(FIELDS)].copy()
        dates = result.index
        if not isinstance(dates, pd.DatetimeIndex) or dates.hasnans or dates.tz is not None:
            raise ValueError("Qlib datetime index must contain valid timezone-naive daily timestamps")
        if not dates.equals(dates.normalize()) or dates.has_duplicates or not dates.is_monotonic_increasing:
            raise ValueError("Qlib dates must be unique, chronological daily timestamps")
        if dates.min() < start or dates.max() > end:
            raise ValueError("Qlib features contain dates outside the requested inclusive window")
        for column in FIELDS:
            dtype = result[column].dtype
            if not pd.api.types.is_numeric_dtype(dtype) or pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_complex_dtype(dtype):
                raise ValueError("Qlib OHLCV values must be real numbers, not coerced strings or booleans")
        values = result.to_numpy(dtype="float64", na_value=np.nan)
        if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
            raise ValueError("Qlib OHLCV requires finite positive prices and nonnegative volume; missing/suspended rows are unsupported")
        if (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any() or (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any():
            raise ValueError("Qlib OHLC prices are inconsistent")
        result.columns = list(OHLCV)
        result.index.name = "date"
        source = deepcopy(frame.attrs.get("market_data", {}))
        source.update(provider="qlib", adjustment="qlib", price_basis="qlib_native_unconverted",
                      volume_basis="qlib_native_unconverted", price_unit="dataset_defined_unverified",
                      volume_unit="dataset_defined_unverified", instrument=instrument,
                      start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))
        source.setdefault("source_kind", "injected_qlib_data_api_unverified")
        result.attrs["market_data"] = source
        return result


def create_qlib_market_provider(*, provider_uri=None):
    """Create an isolated, local-only SDK reader; requires an explicit directory."""
    root = _local_directory(provider_uri)
    _check_sdk_versions()
    return QlibMarketProvider(_LocalQlibDataAPI(root))
