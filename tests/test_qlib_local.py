"""Actual pyqlib 0.9.7 data-only integration; no market download or broker."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from examples.qlib_local_research import write_synthetic_dataset
from invest.pipeline import run_a_share_sma_backtest
from invest.qlib_bridge import create_qlib_market_provider, load_qlib_features
from invest.research_pipeline import run_a_share_research_bundle

SDK = importlib.util.find_spec("qlib") is not None and importlib.util.find_spec("mlflow") is not None
sdk = pytest.mark.skipif(not SDK, reason="optional real pyqlib/MLflow SDKs not installed")


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "dataset"
    expected = write_synthetic_dataset(root)
    return root, expected


def arguments(expected):
    return {"start_date": expected.index[0].strftime("%Y-%m-%d"), "end_date": expected.index[-1].strftime("%Y-%m-%d"),
            "adjust": "qlib", "fast": 5, "slow": 20}


@sdk
def test_actual_sdk_both_pipelines_hostile_environment_and_no_parent_imports(dataset, monkeypatch, tmp_path):
    root, expected = dataset
    for key, value in {"MLFLOW_TRACKING_URI": "https://remote.invalid/tracking", "MLFLOW_REGISTRY_URI": "https://remote.invalid/registry",
                       "MLFLOW_DISABLE_TELEMETRY": "false", "QLIB_PROVIDER_URI": "remote:/data", "QLIB_MLFLOW_URI": "https://remote.invalid"}.items():
        monkeypatch.setenv(key, value)
    before_env, before_modules = dict(os.environ), set(sys.modules)
    before_files = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    provider = create_qlib_market_provider(provider_uri=root)
    result, summary = run_a_share_sma_backtest("000001.SH", provider_instance=provider, **arguments(expected))
    bundle = run_a_share_research_bundle(provider, "SH000001", **arguments(expected))
    assert len(result) == len(expected) == 120
    pd.testing.assert_frame_equal(result, bundle.backtest)
    np.testing.assert_allclose(bundle.market["close"], expected["close"], rtol=1e-6)
    assert summary == bundle.summary
    source = result.attrs["market_data"]
    assert source == bundle.market.attrs["market_data"]
    assert source["instrument"] == "SH000001"  # Never silently switches to Shenzhen.
    assert source["runtime_version"] == "0.9.7"
    assert source["mlflow_runtime_version"] == "3.16.1"
    assert source["tracking"] == source["network"] == "disabled"
    assert source["source_kind"] == "local_qlib_dataset_unverified"
    assert len(source["dataset_sha256"]) == 64
    assert not ({"qlib", "mlflow", "torch"} - before_modules) & set(sys.modules)
    assert dict(os.environ) == before_env
    assert before_files == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not (tmp_path / "mlruns").exists()


@sdk
def test_actual_d_features_tracking_disabled_and_global_state_isolation(dataset, tmp_path):
    root, expected = dataset
    other = tmp_path / "other"
    write_synthetic_dataset(other, scale=3)
    script = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
network_attempts = []
def deny(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto", "socket.bind"}:
        network_attempts.append((event, args[1] if event == "socket.bind" else None))
        raise AssertionError("unexpected network access")
sys.addaudithook(deny)
os.environ['MLFLOW_DISABLE_TELEMETRY'] = 'true'
os.environ['DO_NOT_TRACK'] = 'true'
import mlflow
from mlflow.telemetry.client import get_telemetry_client
assert get_telemetry_client() is None
# urllib3 probes local IPv6 at import; the guard denies that harmless bind too.
assert all(event == 'socket.bind' and address == ('::1', 0) for event, address in network_attempts)
network_attempts.clear()
clients = []
def no_client(*args, **kwargs):
    clients.append(True)
    raise AssertionError('data-only use must never create an MLflow client')
mlflow.tracking.MlflowClient = no_client
mlflow.MlflowClient = no_client
from invest.qlib_local import read_local
request = {'root':sys.argv[2], 'instruments':['SH000001'], 'fields':['$close'], 'start':'2025-01-02', 'end':'2025-06-18'}
first = read_local(request)
from qlib.config import C
from qlib.data import D
from qlib.workflow import R
assert C.kernels == 1 and C.auto_mount is False
assert C.dataset_cache is None and C.expression_cache is None
assert C.exp_manager['class'].__name__ == 'DataOnlyExperimentManager'
try:
    R.start_exp(experiment_name='must-not-start')
except RuntimeError as error:
    assert 'disabled' in str(error)
else:
    raise AssertionError('tracking was enabled')
raw_before = D.features(['SH000001'], ['$close'], '2025-01-02', '2025-06-18', freq='day')
config_before = str(C)
from invest.qlib_bridge import create_qlib_market_provider
other = create_qlib_market_provider(provider_uri=sys.argv[3])
frame = other.history('000001.SH', start_date='20250102', end_date='20250618', adjust='qlib')
assert abs(float(frame.iloc[0]['close']) - 3.0) < 1e-6
raw_after = D.features(['SH000001'], ['$close'], '2025-01-02', '2025-06-18', freq='day')
assert raw_before.equals(raw_after) and str(C) == config_before
assert float(raw_before.iloc[0, 0]) == 1.0
assert mlflow.active_run() is None and get_telemetry_client() is None
assert not clients and not network_attempts, repr((clients, network_attempts))
assert 'torch' not in sys.modules
print('actual D.features, telemetry, tracking, network and singleton isolation passed')
'''
    env = dict(os.environ, MLFLOW_DISABLE_TELEMETRY="true", DO_NOT_TRACK="true", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    completed = subprocess.run([sys.executable, "-I", "-c", script, str(Path(__file__).resolve().parents[1]), str(root), str(other)],
                               env=env, cwd=tmp_path, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "singleton isolation passed" in completed.stdout
    assert not (tmp_path / "mlruns").exists()


@sdk
@pytest.mark.parametrize("corruption", ["wrong_instrument", "duplicate_calendar", "invalid_calendar", "unsorted_calendar", "missing_field", "truncated_binary", "invalid_offset", "nan", "negative", "outside_features", "lifetime"])
def test_actual_local_dataset_corruption_fails(dataset, corruption):
    root, expected = dataset
    calendar = root / "calendars/day.txt"
    field = root / "features/sh000001/close.day.bin"
    if corruption == "wrong_instrument":
        path = root / "instruments/all.txt"
        path.write_text(path.read_text().replace("SH000001", "SZ000001"))
    elif corruption in {"duplicate_calendar", "invalid_calendar", "unsorted_calendar"}:
        lines = calendar.read_text().splitlines()
        if corruption == "duplicate_calendar": lines[1] = lines[0]
        elif corruption == "invalid_calendar": lines[0] = "2025-02-30"
        else: lines = lines[::-1]
        calendar.write_text("\n".join(lines) + "\n")
    elif corruption == "lifetime":
        path = root / "instruments/all.txt"
        path.write_text(path.read_text().replace("2025-01-02", "2025-01-03"))
    elif corruption == "missing_field": field.unlink()
    elif corruption == "truncated_binary": field.write_bytes(field.read_bytes() + b'x')
    elif corruption == "outside_features":
        outside = root.parent / "outside.bin"
        outside.write_bytes(field.read_bytes())
        field.unlink()
        try: field.symlink_to(outside)
        except OSError: pytest.skip("symlink privilege unavailable")
    else:
        values = np.fromfile(field, dtype="<f4")
        if corruption == "invalid_offset": values[0] = .5
        elif corruption == "nan": values[2] = np.nan
        else: values[2] = -1
        values.tofile(field)
    provider = create_qlib_market_provider(provider_uri=root)
    options = arguments(expected)
    with pytest.raises(ValueError):
        provider.history("SH000001", **{key:value for key,value in options.items() if key not in {"fast", "slow"}})


@sdk
def test_generic_loader_native_only_and_durable_source_changes(dataset):
    root, expected = dataset
    before = load_qlib_features(["000001.SH"], ["$close"], "20250102", "20250618", provider_uri=root)
    assert before.index.names == ["instrument", "datetime"]
    assert before.attrs["market_data"]["price_basis"] == "qlib_native_unconverted"
    field = root / "features/sh000001/close.day.bin"
    values = np.fromfile(field, dtype="<f4")
    values[1:] *= 2
    values.tofile(field)
    after = load_qlib_features(["SH000001"], ["$close"], "20250102", "20250618", provider_uri=root)
    assert float(after.iloc[0,0]) == 2 * float(before.iloc[0,0])
    assert before.attrs["market_data"]["dataset_sha256"] != after.attrs["market_data"]["dataset_sha256"]


def test_expression_market_alias_and_version_rejection_precedes_worker(dataset, monkeypatch):
    root, _ = dataset
    monkeypatch.setattr("invest.qlib_bridge._check_sdk_versions", lambda: None)
    spawn = Mock(side_effect=AssertionError("must not launch"))
    monkeypatch.setattr(subprocess, "run", spawn)
    for instruments, fields in [("csi300", ["$close"]), (["SH000001"], ["Ref($close, -1)"]),
                                (["SH000001", "000001.SH"], ["$close"]), (["SH000001"], ["$close", "$close"])]:
        with pytest.raises(ValueError):
            load_qlib_features(instruments, fields, "20250102", "20250618", provider_uri=root)
    spawn.assert_not_called()


def test_version_is_pinned_before_sdk_import(dataset, monkeypatch):
    root, _ = dataset
    monkeypatch.setattr("importlib.metadata.version", lambda package: "0.0.0")
    with pytest.raises(RuntimeError, match="requires pyqlib==0.9.7"):
        create_qlib_market_provider(provider_uri=root)


def test_timeout_and_worker_failure_are_explicit(dataset, monkeypatch):
    root, _ = dataset
    monkeypatch.setattr("invest.qlib_bridge._check_sdk_versions", lambda: None)
    for failure in [subprocess.TimeoutExpired("python", 45), Mock(returncode=1, stdout=b""), Mock(returncode=0, stdout=b"garbage")]:
        mock = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
        monkeypatch.setattr(subprocess, "run", mock)
        with pytest.raises(RuntimeError):
            create_qlib_market_provider(provider_uri=root).history("SH000001", adjust="qlib")


def test_worker_rechecks_untrusted_request_before_sdk(tmp_path, monkeypatch):
    from invest.qlib_local import read_local
    check = Mock(side_effect=AssertionError("SDK should not be reached"))
    monkeypatch.setattr("invest.qlib_bridge._check_sdk_versions", check)
    base = {"root": str(tmp_path), "instruments": ["SH000001"], "fields": ["$close"], "start": "20250102", "end": "20250618"}
    for update in [{"instruments": ["../escape"]}, {"fields": ["__import__('os')"]}, {"start": "oops"}, {"instruments": []}]:
        with pytest.raises(ValueError):
            read_local({**base, **update})
    check.assert_not_called()
