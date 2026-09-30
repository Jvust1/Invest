"""Fail-closed Qlib normalization without importing the optional SDK."""
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from invest.pipeline import run_a_share_sma_backtest
from invest.qlib_bridge import QlibMarketProvider, create_qlib_market_provider, load_qlib_features
from invest.research_pipeline import run_a_share_research_bundle


def feature_frame():
    index = pd.MultiIndex.from_product([["SH000001"], pd.date_range("2025-01-01", periods=4)], names=["instrument", "datetime"])
    return pd.DataFrame({"$open": [1., 2., 3., 4.], "$high": [2., 3., 4., 5.],
                         "$low": [.5, 1., 2., 3.], "$close": [1.5, 2.5, 3.5, 4.5], "$volume": [100., 0., 120., 130.]}, index=index)


def provider(frame=None):
    api = Mock()
    api.features.return_value = feature_frame() if frame is None else frame
    return QlibMarketProvider(api), api


def read(value, **kwargs):
    return value.history("000001.SH", start_date="20250101", end_date="2025-01-04", adjust="qlib", **kwargs)


@pytest.mark.parametrize(("symbol", "expected"), [("000001", "SZ000001"), ("600000", "SH600000"),
    ("SH000001", "SH000001"), ("000001.SH", "SH000001"), ("000001.SZ", "SZ000001"),
    (" sz000001 ", "SZ000001"), ("sh600000", "SH600000"), ("600000.SZ", "SZ600000")])
def test_exchange_identity_is_preserved(symbol, expected):
    assert QlibMarketProvider.normalize_instrument(symbol) == expected


@pytest.mark.parametrize("symbol", ["garbage", "SHABCDEF", "", "1", "00001", "1234567", "foo000001bar", "SH000001.SZ",
    "SZ000001.SH", "000001.BJ", "BJ000001", "SH 000001", "000001/SH", "٠٠٠٠٠١", None, 1, True])
def test_invalid_symbols_never_call_sdk(symbol):
    value, api = provider()
    with pytest.raises(ValueError):
        value.history(symbol, adjust="qlib")
    api.features.assert_not_called()


@pytest.mark.parametrize("adjust", ["", "qfq", "hfq", "raw", "QLIB", None])
def test_unsupported_adjustment_fails_before_sdk(adjust):
    value, api = provider()
    with pytest.raises(ValueError, match="adjust='qlib'"):
        value.history("SH000001", adjust=adjust)
    api.features.assert_not_called()


def test_period_daily_is_explicit_and_others_fail_before_sdk():
    value, api = provider()
    assert len(read(value, period="daily")) == 4
    api.reset_mock()
    for period in ["weekly", "monthly", "day", None]:
        with pytest.raises(ValueError, match="daily"):
            read(value, period=period)
    api.features.assert_not_called()


@pytest.mark.parametrize(("start", "end"), [("20250230", "20250301"), ("20250105", "20250101"),
    ("2025-01-01T00:00:00", "20250104"), ("2025/01/01", "20250104"), ("10000101", "99991231"), (20250101, "20250104")])
def test_bad_window_fails_before_sdk(start, end):
    value, api = provider()
    with pytest.raises((ValueError, OverflowError)):
        value.history("SH000001", adjust="qlib", start_date=start, end_date=end)
    api.features.assert_not_called()


@pytest.mark.parametrize("kind", ["wrong_asset", "extra_asset", "missing_identity", "unnamed_identity", "nat", "duplicate",
    "unsorted", "timezone", "intraday", "date_string", "out_of_window", "missing_column", "duplicate_column", "empty"])
def test_invalid_identity_dates_and_schema_fail(kind):
    frame = feature_frame()
    days = frame.index.get_level_values("datetime")
    if kind == "wrong_asset":
        frame.index = pd.MultiIndex.from_product([["SZ000001"], days], names=frame.index.names)
    elif kind == "extra_asset":
        extra = frame.iloc[:1].copy()
        extra.index = pd.MultiIndex.from_tuples([("SZ000001", days[0])], names=frame.index.names)
        frame = pd.concat([frame, extra])
    elif kind == "missing_identity":
        frame.index = days
    elif kind == "unnamed_identity":
        frame.index.names = [None, None]
    elif kind in {"nat", "duplicate", "timezone", "intraday", "date_string", "out_of_window"}:
        if kind == "nat": days = [*days[:3], pd.NaT]
        elif kind == "duplicate": days = [days[0], days[0], *days[2:]]
        elif kind == "timezone": days = days.tz_localize("UTC")
        elif kind == "intraday": days = days + pd.Timedelta(hours=1)
        elif kind == "date_string": days = days.astype(str)
        else: days = days - pd.Timedelta(days=1)
        frame.index = pd.MultiIndex.from_product([["SH000001"], days], names=frame.index.names)
    elif kind == "unsorted": frame = frame.iloc[::-1]
    elif kind == "missing_column": frame = frame.drop(columns="$close")
    elif kind == "duplicate_column": frame = pd.concat([frame, frame[["$close"]]], axis=1)
    elif kind == "empty": frame = frame.iloc[:0]
    value, _ = provider(frame)
    with pytest.raises(ValueError): read(value)


@pytest.mark.parametrize("field", ["$open", "$high", "$low", "$close", "$volume"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, -1.0, "oops", "1.5", True, 1j])
def test_bad_ohlcv_is_never_coerced_or_filled(field, bad):
    frame = feature_frame()
    frame[field] = frame[field].astype(object)
    frame.loc[frame.index[0], field] = bad
    value, _ = provider(frame)
    with pytest.raises(ValueError): read(value)


@pytest.mark.parametrize(("field", "bad"), [("$open", 0.), ("$close", 0.), ("$high", .2), ("$low", 2.)])
def test_zero_or_inconsistent_prices_fail(field, bad):
    frame = feature_frame()
    frame.loc[frame.index[0], field] = bad
    value, _ = provider(frame)
    with pytest.raises(ValueError): read(value)


def test_both_pipelines_preserve_native_metadata_and_defaults_stay_qfq():
    frame = feature_frame()
    frame.attrs["market_data"] = {"source_kind": "synthetic_test", "dataset_sha256": "a" * 64}
    value, api = provider(frame)
    result, _ = run_a_share_sma_backtest("SH000001", provider_instance=value, fast=1, slow=2, adjust="qlib")
    class DropsAttrs:
        def transform(self, market):
            market.attrs = {}
            return market
    bundle = run_a_share_research_bundle(value, "SH000001", fast=1, slow=2, adjust="qlib", feature_engineer=DropsAttrs())
    assert result.attrs["market_data"] == bundle.market.attrs["market_data"] == bundle.backtest.attrs["market_data"]
    assert result.attrs["market_data"]["price_unit"] == "dataset_defined_unverified"
    assert result.attrs["market_data"]["instrument"] == "SH000001"
    assert frame.attrs["market_data"] == {"source_kind": "synthetic_test", "dataset_sha256": "a" * 64}
    api.reset_mock()
    with pytest.raises(ValueError, match="adjust='qlib'"):
        run_a_share_sma_backtest("SH000001", provider_instance=value)
    with pytest.raises(ValueError, match="adjust='qlib'"):
        run_a_share_research_bundle(value, "SH000001")
    api.features.assert_not_called()
    fake = Mock()
    fake.history.return_value = pd.DataFrame({"close": [1., 2.]})
    run_a_share_sma_backtest("000001", provider_instance=fake, fast=1, slow=2)
    assert fake.history.call_args.kwargs["adjust"] == "qfq"
    run_a_share_research_bundle(fake, "000001", fast=1, slow=2)
    assert fake.history.call_args.kwargs["adjust"] == "qfq"


@pytest.mark.parametrize("uri", [None, "", "relative", "https://host/data", "host:/data", "//host/data", "\\\\host\\data", {}])
def test_factory_rejects_implicit_remote_or_missing_directory_before_sdk(uri, monkeypatch):
    check = Mock(side_effect=AssertionError("SDK should not be reached"))
    monkeypatch.setattr("invest.qlib_bridge._check_sdk_versions", check)
    with pytest.raises(ValueError): create_qlib_market_provider(provider_uri=uri)
    check.assert_not_called()


def test_factory_requires_layout_and_confined_files(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="calendars/day.txt"):
        create_qlib_market_provider(provider_uri=tmp_path)
    (tmp_path / "calendars").mkdir()
    (tmp_path / "calendars/day.txt").write_text("2025-01-01\n")
    with pytest.raises(ValueError, match="instruments/all.txt"):
        create_qlib_market_provider(provider_uri=tmp_path)


def test_ignored_prefix_now_fails_explicitly():
    with pytest.raises(ValueError, match="instrument_prefix"):
        QlibMarketProvider(Mock(), instrument_prefix="SH")


@pytest.mark.parametrize("field", ["$open", "$high", "$low", "$close", "$volume"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, -1.])
def test_numeric_dtype_invalid_values_fail(field, bad):
    frame = feature_frame()
    frame.loc[frame.index[0], field] = bad
    value, _ = provider(frame)
    with pytest.raises(ValueError, match="finite positive prices"):
        read(value)


def test_exact_upstream_provenance_and_runtime_pins():
    import hashlib
    import json
    from pathlib import Path
    import configparser

    root = Path(__file__).resolve().parents[1]
    raw = (root / "third_party/qlib/LICENSE").read_bytes()
    assert hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == "9e841e7a26e4eb057b24511e7b92d42b257a80e5"
    assert "third_party/qlib/LICENSE -text" in (root / ".gitattributes").read_text(encoding="utf-8")
    registry = json.loads((root / "invest/upstream_registry.json").read_text(encoding="utf-8"))
    item = next(item for item in registry["projects"] if item["repo"] == "microsoft/qlib")
    assert item["target"] == "invest.qlib_bridge"
    assert item["runtime_revision"] == "da920b7f954f48ab1bb64117c976710de198373e"
    assert item["license"] == "MIT" and item["license_path"] == "third_party/qlib/LICENSE"
    assert item["runtime_package"] == "pyqlib==0.9.7"
    # This section uses simple one-line JSON-compatible TOML arrays. Keep the
    # proof stdlib-only on Python 3.10, where tomllib is not yet available.
    project = configparser.ConfigParser(interpolation=None)
    project.read_string((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project.optional-dependencies"]
    assert set(json.loads(extras["qlib"])) == {"pyqlib==0.9.7", "mlflow==3.16.1"}
    assert json.loads(extras["mlflow"]) == ["mlflow==3.16.1"]
