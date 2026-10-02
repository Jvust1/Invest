"""Bounded child-process implementation for native local Qlib data reads."""
from __future__ import annotations


class DataOnlyExperimentManager:
    """Qlib initialization hook: no MLflow client, experiment or recorder writes."""

    active_experiment = None

    def end_exp(self, *args, **kwargs):
        pass  # Qlib installs an atexit cleanup even for data-only use.

    def __getattr__(self, name):
        raise RuntimeError("Qlib experiment tracking is disabled in the local data reader")


def read_local(request):
    """Called only in a fresh worker after the network and telemetry guards."""
    import hashlib
    import json
    import os
    import sys

    import numpy as np
    import pandas as pd

    from .qlib_bridge import FIELDS, MAX_ROWS, QLIB_VERSION, MLFLOW_VERSION, QlibMarketProvider, _check_sdk_versions, _local_directory, _local_file, _date, _window

    if "qlib" in sys.modules:
        raise RuntimeError("local Qlib reader requires a fresh SDK process")
    if not isinstance(request, dict) or set(request) != {"root", "instruments", "fields", "start", "end"}:
        raise ValueError("invalid local Qlib request")
    names, fields = request["instruments"], request["fields"]
    if (not isinstance(names, list) or not 1 <= len(names) <= 16
            or any(not isinstance(name, str) or QlibMarketProvider.normalize_instrument(name) != name for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("local Qlib request requires unique canonical instruments")
    if (not isinstance(fields, list) or not fields or any(field not in FIELDS for field in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError("local Qlib request requires direct native OHLCV fields")
    start, end = _window(request["start"], request["end"])
    if len(names) * ((end - start).days + 1) > MAX_ROWS:
        raise ValueError("local Qlib request exceeds the total-row limit")
    _check_sdk_versions()
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["DO_NOT_TRACK"] = "true"
    root = _local_directory(request["root"])
    files = [_local_file(root, "calendars/day.txt"), _local_file(root, "instruments/all.txt")]
    calendar = [_date(item, "calendar date") for item in files[0].read_text(encoding="utf-8").splitlines()]
    if not calendar or len(calendar) > MAX_ROWS or len(set(calendar)) != len(calendar) or calendar != sorted(calendar):
        raise ValueError("local Qlib calendar must be nonempty, unique, chronological and bounded")
    instruments = {}
    for line in files[1].read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError("invalid local Qlib instrument manifest")
        start, end = _date(parts[1], "instrument start"), _date(parts[2], "instrument end")
        if start > end:
            raise ValueError("invalid local Qlib instrument lifetime")
        instruments.setdefault(parts[0], []).append((start, end))
    for instrument in request["instruments"]:
        if instrument not in instruments:
            raise ValueError("requested instrument is absent from the local Qlib manifest")
        for field in request["fields"]:
            path = _local_file(root, f"features/{instrument.lower()}/{field[1:]}.day.bin")
            if path.stat().st_size % 4 or path.stat().st_size > (MAX_ROWS + 1) * 4:
                raise ValueError("invalid local Qlib binary byte length")
            data = np.fromfile(path, dtype="<f4")
            if len(data) < 2 or not np.isfinite(data[0]) or data[0] < 0 or data[0] != int(data[0]) or int(data[0]) + len(data) - 1 > len(calendar):
                raise ValueError("invalid local Qlib binary calendar offset or length")
            files.append(path)

    def fingerprint():
        values = [(str(path.relative_to(root)).replace("\\", "/"), hashlib.sha256(path.read_bytes()).hexdigest()) for path in files]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()

    before = fingerprint()
    import qlib
    from qlib.config import REG_CN
    from qlib.data import D
    qlib.init(provider_uri=str(root), region=REG_CN, auto_mount=False, kernels=1, joblib_backend="threading",
              expression_cache=None, dataset_cache=None, calendar_cache=None, default_disk_cache=0,
              logging_config=None, exp_manager={"class": DataOnlyExperimentManager})
    frame = D.features(request["instruments"], request["fields"], start_time=request["start"], end_time=request["end"], freq="day", disk_cache=0)
    if before != fingerprint():
        raise ValueError("local Qlib input files changed during the read")
    if frame.empty or len(frame) > MAX_ROWS or not isinstance(frame.index, pd.MultiIndex):
        raise ValueError("empty, invalid or oversized Qlib feature response")
    if frame.index.names != ["instrument", "datetime"] or frame.index.has_duplicates:
        raise ValueError("Qlib response must identify unique instrument/date rows")
    if set(frame.index.get_level_values("instrument")) != set(request["instruments"]):
        raise ValueError("Qlib response is missing a requested instrument or contains an unexpected one")
    days = frame.index.get_level_values("datetime")
    if (not isinstance(days, pd.DatetimeIndex) or days.hasnans or days.tz is not None
            or not days.equals(days.normalize()) or days.min() < pd.Timestamp(request["start"])
            or days.max() > pd.Timestamp(request["end"])):
        raise ValueError("Qlib response contains invalid or out-of-window daily dates")
    for field in request["fields"]:
        values = frame[field].to_numpy(dtype="float64")
        if not np.isfinite(values).all() or (values < 0 if field == "$volume" else values <= 0).any():
            raise ValueError("Qlib native features require finite positive prices and nonnegative volume; missing/suspended data is unsupported")
    rows = []
    for (instrument, day), values in frame.iterrows():
        if not any(start <= day <= end for start, end in instruments[instrument]):
            raise ValueError("Qlib response contains dates outside the declared instrument lifetime")
        rows.append([instrument, day.strftime("%Y-%m-%d"), *map(float, values)])
    return {"status": "ok", "rows": rows, "metadata": {
        "provider": "qlib", "source_kind": "local_qlib_dataset_unverified", "dataset_sha256": before,
        "runtime_version": QLIB_VERSION, "mlflow_runtime_version": MLFLOW_VERSION,
        "frequency": "day", "adjustment": "qlib", "price_basis": "qlib_native_unconverted",
        "volume_basis": "qlib_native_unconverted", "price_unit": "dataset_defined_unverified",
        "volume_unit": "dataset_defined_unverified", "tracking": "disabled", "network": "disabled",
    }}


def worker_main():
    import contextlib
    import json
    import os
    import sys

    from .qlib_bridge import MAX_RESPONSE_BYTES

    def deny_network(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto", "socket.bind"}:
            raise RuntimeError("network disabled for the local Qlib reader")

    sys.addaudithook(deny_network)  # Defense in depth, not an OS security sandbox.
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError("Qlib request exceeds the bounded input limit")
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            result = read_local(json.loads(raw))
        output = json.dumps(result, allow_nan=False, separators=(",", ":"))
        if len(output.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("Qlib response exceeds the bounded output limit")
    except (ValueError, FileNotFoundError) as exc:
        output = json.dumps({"status": "failed", "reason": str(exc)[:200]})
    except Exception:
        output = json.dumps({"status": "failed", "reason": "SDK initialization or local feature read failed"})
    sys.stdout.write(output)
