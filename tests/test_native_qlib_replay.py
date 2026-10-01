"""Native basis/source identity survives real DuckDB; all values are synthetic."""
import copy
import importlib.util
import json

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from invest.pipeline import run_a_share_sma_backtest
from invest.providers.duckdb_cache import (DuckDBCacheIntegrityError, DuckDBCacheMiss,
    DuckDBMarketCache, DuckDBReplayProvider, _json, _sha, _MANIFEST, _request, _native_qlib_metadata)
from invest.research_pipeline import run_a_share_research_bundle

REQUEST = {'symbol': '000001.SH', 'start_date': '20250102', 'end_date': '20250618', 'adjust': 'qlib'}
SOURCE = 'synthetic-native-qlib/v1;unconverted-unverified-units'
duckdb = pytest.mark.skipif(importlib.util.find_spec('duckdb') is None, reason='optional actual DuckDB missing')


def native_frame():
    index = pd.bdate_range('2025-01-02', periods=120, name='date')
    close = 1 + np.arange(len(index)) * .002 + np.sin(np.arange(len(index)) / 7) * .03
    frame = pd.DataFrame({'open': close*.998, 'high': close*1.01, 'low': close*.99,
                          'close': close, 'volume': np.arange(len(index))+1000.}, index=index)
    frame.attrs['market_data'] = {
        'provider': 'qlib', 'source_kind': 'local_qlib_dataset_unverified', 'dataset_sha256': 'a'*64,
        'runtime_version': '0.9.7', 'mlflow_runtime_version': '3.16.1', 'frequency': 'day',
        'adjustment': 'qlib', 'price_basis': 'qlib_native_unconverted', 'volume_basis': 'qlib_native_unconverted',
        'price_unit': 'dataset_defined_unverified', 'volume_unit': 'dataset_defined_unverified',
        'tracking': 'disabled', 'network': 'disabled', 'instrument': 'SH000001',
        'start_date': '2025-01-02', 'end_date': '2025-06-18'}
    return frame


class Source:
    def __init__(self, frame=None):
        self.frame = native_frame() if frame is None else frame
        self.calls = []

    def history(self, **request):
        self.calls.append(request)
        return self.frame.copy(deep=True)


def test_native_request_is_exact_and_does_not_broaden_ordinary_adjustments():
    for symbol in ('000001', 'SH000001', '000001.SH', 'SZ000001', '000001.SZ'):
        assert _request(SOURCE, symbol, '20250102', '20250618', 'daily', 'qlib')['symbol'] == symbol
    for symbol in ('garbage', 'SHABCDEF', '000001.SH;DROP', 'sh000001', ' 000001.SH', '０００００１.SH', 1):
        with pytest.raises(ValueError):
            _request(SOURCE, symbol, '20250102', '20250618', 'daily', 'qlib')
    for adjustment in ('', 'qfq', 'hfq'):
        with pytest.raises(ValueError):
            _request(SOURCE, '000001.SH', '20250102', '20250618', 'daily', adjustment)
    with pytest.raises(ValueError):
        _request(SOURCE, '000001.SH', '20250102', '20250618', 'weekly', 'qlib')


@pytest.mark.parametrize('change', [
    {'provider': 'unknown'}, {'instrument': 'SZ000001'}, {'start_date': '2025-01-03'},
    {'end_date': '2025-06-19'}, {'price_basis': 'qfq'}, {'price_unit': 'CNY'},
    {'volume_basis': 'shares'}, {'tracking': 'enabled'}, {'network': 'allowed'},
    {'dataset_sha256': 'not-a-hash'}, {'runtime_version': 'https://bad.invalid'},
    {'api_token': 'must-not-copy-arbitrary-attrs'}, {'runtime_version': '1'*101},
])
def test_invalid_native_metadata_is_rejected(change):
    value = {**native_frame().attrs['market_data'], **change}
    request = _request(SOURCE, **REQUEST, period='daily')
    with pytest.raises(ValueError):
        _native_qlib_metadata(value, request)


@duckdb
def test_real_native_refresh_close_reopen_both_pipelines_and_defensive_metadata(tmp_path, monkeypatch):
    path = tmp_path/'native.duckdb'
    source = Source()
    with DuckDBMarketCache(path) as cache:
        first = DuckDBReplayProvider(cache, source_id=SOURCE, upstream=source, mode='refresh').history(**REQUEST)
        snapshot_id = first.attrs['duckdb_replay']['snapshot_id']
    assert source.calls == [{**REQUEST, 'period': 'daily'}]
    with DuckDBMarketCache(path, read_only=True) as cache:
        replay = DuckDBReplayProvider(cache, source_id=SOURCE)
        monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('cache replay must not spawn Qlib'))
        monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('network forbidden'))
        bundle = run_a_share_research_bundle(replay, **REQUEST, fast=5, slow=20)
        result, summary = run_a_share_sma_backtest(**REQUEST, fast=5, slow=20, provider_instance=replay)
        assert_frame_equal(bundle.backtest, result)
        assert summary == bundle.summary
        for frame in (bundle.market, bundle.backtest, result):
            assert frame.attrs['market_data'] == native_frame().attrs['market_data']
            assert frame.attrs['duckdb_replay']['snapshot_id'] == snapshot_id
        bundle.backtest.attrs['market_data']['instrument'] = 'changed-by-caller'
        assert bundle.market.attrs['market_data']['instrument'] == 'SH000001'
        assert replay.last_snapshot['market_data']['instrument'] == 'SH000001'
        assert replay.history(**REQUEST).attrs['market_data']['instrument'] == 'SH000001'
        # Same-asset aliases are still different exact request identities.
        with pytest.raises(DuckDBCacheMiss):
            replay.history(**{**REQUEST, 'symbol': 'SH000001'})


@duckdb
def test_invalid_native_refresh_retains_old_snapshot_and_never_relabels_prices(tmp_path):
    with DuckDBMarketCache(tmp_path/'native.duckdb') as cache:
        source = Source()
        provider = DuckDBReplayProvider(cache, source_id=SOURCE, upstream=source, mode='refresh')
        first = provider.history(**REQUEST)
        source.frame.attrs['market_data']['price_unit'] = 'CNY'
        with pytest.raises(ValueError):
            provider.history(**REQUEST)
        assert provider.last_snapshot is None
        replay = DuckDBReplayProvider(cache, source_id=SOURCE)
        assert replay.history(**REQUEST).attrs['duckdb_replay']['snapshot_id'] == first.attrs['duckdb_replay']['snapshot_id']
        for adjustment in ('', 'qfq', 'hfq'):
            with pytest.raises(ValueError, match='cannot be cached'):
                provider.history(**{**REQUEST, 'symbol': '000001', 'adjust': adjustment})
            with pytest.raises(DuckDBCacheMiss):
                replay.history(**{**REQUEST, 'symbol': '000001', 'adjust': adjustment})


@duckdb
def test_missing_native_metadata_never_creates_snapshot(tmp_path):
    frame = native_frame(); frame.attrs = {}
    with DuckDBMarketCache(tmp_path/'native.duckdb') as cache:
        provider = DuckDBReplayProvider(cache, source_id=SOURCE, upstream=Source(frame), mode='refresh')
        with pytest.raises(ValueError, match='metadata'):
            provider.history(**REQUEST)
        with pytest.raises(DuckDBCacheMiss):
            DuckDBReplayProvider(cache, source_id=SOURCE).history(**REQUEST)


@duckdb
def test_resealed_metadata_for_different_exchange_is_rejected(tmp_path):
    with DuckDBMarketCache(tmp_path/'native.duckdb') as cache:
        frame = DuckDBReplayProvider(cache, source_id=SOURCE, upstream=Source(), mode='refresh').history(**REQUEST)
        metadata = copy.deepcopy(frame.attrs['duckdb_replay'])
        metadata.pop('snapshot_id'); metadata.pop('cache_status')
        metadata['market_data']['instrument'] = 'SZ000001'
        # Simulate a corrupt manifest with a recomputed digest: semantic linkage
        # still cannot cross from the explicit Shanghai request to Shenzhen.
        cache._connection.execute(f'UPDATE "{_MANIFEST}" SET metadata_json=?, snapshot_id=?',
                                  [_json(metadata), _sha(_json(metadata))])
        with pytest.raises(DuckDBCacheIntegrityError):
            DuckDBReplayProvider(cache, source_id=SOURCE).history(**REQUEST)


@duckdb
def test_generic_legacy_snapshot_still_works_without_native_metadata(tmp_path):
    frame = native_frame(); frame.attrs = {}
    ordinary = {**REQUEST, 'symbol': '000001', 'adjust': 'qfq'}
    with DuckDBMarketCache(tmp_path/'ordinary.duckdb') as cache:
        first = DuckDBReplayProvider(cache, source_id=SOURCE, upstream=Source(frame), mode='refresh').history(**ordinary)
        assert 'market_data' not in first.attrs
        later = DuckDBReplayProvider(cache, source_id=SOURCE).history(**ordinary)
        assert 'market_data' not in later.attrs
        assert later.attrs['duckdb_replay']['request']['schema_version'] == 1
        assert first.attrs['duckdb_replay']['snapshot_id'] == later.attrs['duckdb_replay']['snapshot_id']
