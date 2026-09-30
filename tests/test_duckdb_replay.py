"""Actual DuckDB contracts. All price data and providers are synthetic/offline."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from invest.pipeline import run_a_share_sma_backtest
from invest.providers.duckdb_cache import (
    DuckDBCacheIntegrityError, DuckDBCacheMiss, DuckDBCacheStaleError,
    DuckDBMarketCache, DuckDBReplayProvider,
)
from invest.research_pipeline import run_a_share_research_bundle


REQUEST = {"symbol": "000001", "start_date": "20240101", "end_date": "20240229",
           "period": "daily", "adjust": "qfq"}
SOURCE = "synthetic-fixture/v1;volume=declared-units"


def synthetic_frame():
    close = np.array([10., 11., 10.5, 12., 11.5, 12.5, 13., 12., 11., 13., 14., 12.])
    return pd.DataFrame({"symbol": ["000001"] * len(close), "open": close - .25,
                         "high": close + .5, "low": close - .5, "close": close,
                         "volume": np.arange(len(close)) * 100.,
                         "change_pct": np.linspace(-3., 4., len(close))},
                        index=pd.date_range("2024-01-02", periods=len(close), name="date"))


class SyntheticProvider:
    def __init__(self, frame=None):
        self.frame = synthetic_frame() if frame is None else frame
        self.calls = []

    def history(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame.copy()


class NeverCallProvider:
    def history(self, **kwargs):
        raise AssertionError("cache-only must never invoke an upstream")


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "optional DuckDB is not installed")
class DuckDBReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.duckdb"
        self.cache = DuckDBMarketCache(self.path)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cache.close)

    def refresh(self, upstream=None, **kwargs):
        provider = DuckDBReplayProvider(self.cache, source_id=SOURCE, mode="refresh",
                                        upstream=upstream or SyntheticProvider())
        frame = provider.history(**{**REQUEST, **kwargs})
        return provider, frame

    def replay(self, **kwargs):
        return DuckDBReplayProvider(self.cache, source_id=SOURCE, **kwargs)

    def test_durable_reopen_preserves_exact_data_symbols_and_provenance(self):
        upstream = SyntheticProvider()
        _, first = self.refresh(upstream)
        self.assertEqual(upstream.calls, [REQUEST])
        self.cache.close()
        with DuckDBMarketCache(self.path, read_only=True) as reopened:
            provider = DuckDBReplayProvider(reopened, source_id=SOURCE, upstream=NeverCallProvider())
            offline = provider.history(**REQUEST)
            assert_frame_equal(first, offline, check_flags=False)
            self.assertEqual(offline.attrs["duckdb_replay"]["cache_status"], "cache_only")
            self.assertEqual(offline.attrs["duckdb_replay"]["request"],
                             {**REQUEST, "source_id": SOURCE, "schema_version": 1})
            self.assertEqual(first.attrs["duckdb_replay"]["snapshot_id"],
                             offline.attrs["duckdb_replay"]["snapshot_id"])
            self.assertEqual(offline.symbol.tolist(), ["000001"] * len(first))
            self.assertEqual(provider.last_snapshot, offline.attrs["duckdb_replay"])

    def test_existing_bundle_and_sma_pipeline_run_without_network(self):
        _, frame = self.refresh()
        provider = self.replay(upstream=NeverCallProvider())
        kwargs = {k: v for k, v in REQUEST.items() if k != "period"}
        with patch("requests.sessions.Session.request", side_effect=AssertionError("network disabled")):
            bundle = run_a_share_research_bundle(provider, **kwargs, fast=2, slow=4)
            result, summary = run_a_share_sma_backtest(**kwargs, provider_instance=provider, fast=2, slow=4)
        assert_frame_equal(bundle.backtest, result)
        self.assertEqual(bundle.summary, summary)
        self.assertEqual(bundle.market.attrs["duckdb_replay"]["snapshot_id"],
                         frame.attrs["duckdb_replay"]["snapshot_id"])

    def test_empty_cache_miss_does_not_fetch_or_create_manifest(self):
        with self.assertRaises(DuckDBCacheMiss):
            self.replay(upstream=NeverCallProvider()).history(**REQUEST)
        self.assertTrue(self.cache.query("SHOW TABLES").empty)

    def test_each_identity_dimension_is_bound_and_not_silently_sliced(self):
        self.refresh()
        for change in ({"symbol": "600000"}, {"start_date": "20240102"},
                       {"end_date": "20240301"}, {"adjust": "hfq"},
                       {"adjust": ""}, {"period": "weekly"}):
            with self.subTest(change=change), self.assertRaises(DuckDBCacheMiss):
                self.replay(upstream=NeverCallProvider()).history(**{**REQUEST, **change})
        with self.assertRaises(DuckDBCacheMiss):
            DuckDBReplayProvider(self.cache, source_id="different-source", upstream=NeverCallProvider()).history(**REQUEST)

    def test_refresh_always_fetches_and_explicitly_replaces_only_exact_request(self):
        upstream = SyntheticProvider()
        provider, before = self.refresh(upstream)
        self.refresh(adjust="")
        upstream.frame.loc[:, "volume"] += 1
        after = provider.history(**REQUEST)
        self.assertEqual(len(upstream.calls), 2)
        self.assertNotEqual(before.attrs["duckdb_replay"]["snapshot_id"], after.attrs["duckdb_replay"]["snapshot_id"])
        offline = self.replay().history(**REQUEST)
        assert_frame_equal(after, offline)
        raw = self.replay().history(**{**REQUEST, "adjust": ""})
        self.assertEqual(raw.volume.iloc[0], 0.)
        self.assertEqual(offline.volume.iloc[0], 1.)

    def test_upstream_failure_raises_and_retains_old_snapshot_without_fallback(self):
        provider, before = self.refresh()
        with patch.object(provider._upstream, "history", side_effect=RuntimeError("synthetic source failed")):
            with self.assertRaisesRegex(RuntimeError, "synthetic source failed"):
                provider.history(**REQUEST)
        self.assertIsNone(provider.last_snapshot)
        assert_frame_equal(before, self.replay().history(**REQUEST))

    def test_invalid_refresh_is_not_stored_and_retains_prior_snapshot(self):
        provider, before = self.refresh()
        provider._upstream.frame.loc[:, "close"] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            provider.history(**REQUEST)
        self.assertIsNone(provider.last_snapshot)
        assert_frame_equal(before, self.replay().history(**REQUEST))

    def test_transaction_failure_rolls_back_table_and_manifest_together(self):
        _, before = self.refresh()
        real = self.cache._connection

        class FailOnManifestInsert:
            def __getattr__(self, name):
                return getattr(real, name)

            def execute(self, sql, *args):
                if sql.startswith('INSERT INTO "__invest_replay_manifest"'):
                    raise RuntimeError("simulated disk write failure")
                return real.execute(sql, *args)

        self.cache._connection = FailOnManifestInsert()
        upstream = SyntheticProvider()
        upstream.frame.loc[:, "volume"] += 10
        with self.assertRaisesRegex(RuntimeError, "disk write failure"):
            self.refresh(upstream)
        self.cache._connection = real
        after = self.replay().history(**REQUEST)
        assert_frame_equal(before, after)
        self.assertEqual(before.attrs["duckdb_replay"]["snapshot_id"], after.attrs["duckdb_replay"]["snapshot_id"])

    def test_commit_failure_rolls_back_and_cache_remains_usable(self):
        _, before = self.refresh()
        real = self.cache._connection

        class FailBeforeCommit:
            def __getattr__(self, name):
                return getattr(real, name)

            def execute(self, sql, *args):
                if sql == "COMMIT":
                    raise RuntimeError("simulated commit failure")
                return real.execute(sql, *args)

        self.cache._connection = FailBeforeCommit()
        upstream = SyntheticProvider()
        upstream.frame.loc[:, "volume"] += 10
        with self.assertRaisesRegex(RuntimeError, "commit failure"):
            self.refresh(upstream)
        self.cache._connection = real
        assert_frame_equal(before, self.replay().history(**REQUEST))
        self.assertEqual(self.cache.query("SELECT 1 AS n").n.iloc[0], 1)

    def test_non_nanosecond_index_cannot_silently_wrap_dates(self):
        frame = synthetic_frame().iloc[:1].copy()
        try:
            frame.index = pd.DatetimeIndex(np.array(["2500-01-01"], dtype="datetime64[s]"))
        except pd.errors.OutOfBoundsDatetime:
            self.skipTest("this pandas version already rejects out-of-ns-range dates")
        with self.assertRaisesRegex(ValueError, "nanosecond timestamp range"):
            self.refresh(SyntheticProvider(frame), start_date="25000101", end_date="25000102")
        with self.assertRaises(DuckDBCacheMiss):
            self.replay().history(**{**REQUEST, "start_date": "25000101", "end_date": "25000102"})

    def test_manifest_and_content_tampering_fail_closed(self):
        for tamper in ("price", "duplicate_date", "missing_row", "schema", "metadata", "digest", "missing_table"):
            with self.subTest(tamper=tamper):
                _, frame = self.refresh()
                metadata = frame.attrs["duckdb_replay"]
                key = metadata["request_id"]
                table = f'"__invest_replay_{key}"'
                connection = self.cache._connection
                if tamper == "price":
                    connection.execute(f"UPDATE {table} SET close = close + 0.125")
                elif tamper == "duplicate_date":
                    connection.execute(f"UPDATE {table} SET date = '2024-01-02'")
                elif tamper == "missing_row":
                    connection.execute(f"DELETE FROM {table} WHERE date = '2024-01-02'")
                elif tamper == "schema":
                    connection.execute(f"ALTER TABLE {table} ADD extra DOUBLE")
                elif tamper == "metadata":
                    connection.execute("UPDATE __invest_replay_manifest SET metadata_json = '{}' WHERE request_id = ?", [key])
                elif tamper == "digest":
                    connection.execute("UPDATE __invest_replay_manifest SET snapshot_id = 'wrong' WHERE request_id = ?", [key])
                else:
                    connection.execute(f"DROP TABLE {table}")
                with self.assertRaises(DuckDBCacheIntegrityError):
                    self.replay(upstream=NeverCallProvider()).history(**REQUEST)

    def test_bad_normalized_frames_are_rejected_before_any_storage(self):
        bad = []
        frame = synthetic_frame()
        bad.extend([frame.iloc[0:0], frame.iloc[::-1], pd.concat([frame, frame.iloc[-1:]]),
                    frame.reset_index(drop=True), frame.drop(columns="volume"),
                    frame.assign(extra=1), frame.assign(symbol="600000"),
                    frame.assign(symbol=1), frame.assign(close=np.inf),
                    frame.assign(volume=-1), frame.assign(low=100),
                    frame.assign(close=0), frame.assign(close="10.0"),
                    frame.assign(close=True), frame.assign(close=1 + 2j)])
        for index in [frame.index.tz_localize("UTC"), frame.index + pd.Timedelta(hours=1),
                      pd.DatetimeIndex([pd.NaT, *frame.index[1:]]),
                      frame.index + pd.Timedelta(days=100)]:
            value = frame.copy()
            value.index = index
            bad.append(value)
        value = frame.copy()
        value.columns = ["close", *value.columns[1:]]
        bad.append(value)
        for i, invalid in enumerate(bad):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.refresh(SyntheticProvider(invalid))
        with self.assertRaises(DuckDBCacheMiss):
            self.replay().history(**REQUEST)

    def test_invalid_request_never_calls_provider(self):
        provider = DuckDBReplayProvider(self.cache, source_id=SOURCE, upstream=NeverCallProvider(), mode="refresh")
        for change in ({"symbol": 1}, {"symbol": "1"}, {"start_date": "2024-01-01"},
                       {"start_date": "20240230"}, {"start_date": "20240301"},
                       {"period": "minute"}, {"adjust": "something"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                provider.history(**{**REQUEST, **change})

    def test_weekly_and_monthly_are_preserved_without_aggregation(self):
        for period in ("weekly", "monthly"):
            _, first = self.refresh(period=period)
            replay = self.replay().history(**{**REQUEST, "period": period})
            assert_frame_equal(first, replay)
            self.assertEqual(replay.attrs["duckdb_replay"]["request"]["period"], period)

    def test_explicit_maximum_age_fails_without_refresh_and_clears_provenance(self):
        self.refresh()
        with self.assertRaises(DuckDBCacheStaleError):
            self.replay(upstream=NeverCallProvider(), max_age_seconds=0).history(**REQUEST)
        self.replay(max_age_seconds=60).history(**REQUEST)
        for invalid in (-1, np.inf, np.nan, True, "10"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.replay(max_age_seconds=invalid)

    def test_returned_data_and_metadata_do_not_mutate_stored_snapshot(self):
        _, first = self.refresh()
        provider = self.replay()
        result = provider.history(**REQUEST)
        result.loc[:, "volume"] = 999
        result.attrs["duckdb_replay"]["request"]["adjust"] = "wrong"
        exposed = provider.last_snapshot
        exposed["request"]["source_id"] = "wrong"
        self.assertEqual(provider.last_snapshot["request"]["source_id"], SOURCE)
        assert_frame_equal(first, provider.history(**REQUEST))
        with self.assertRaises(DuckDBCacheMiss):
            provider.history(**{**REQUEST, "symbol": "600000"})
        self.assertIsNone(provider.last_snapshot)

    def test_provider_constructor_fails_closed(self):
        for source in ("", " ", "bad\nsource", "a" * 501, None):
            with self.subTest(source=source), self.assertRaises(ValueError):
                DuckDBReplayProvider(self.cache, source_id=source)
        with self.assertRaises(ValueError):
            self.replay(mode="fallback")
        with self.assertRaises(TypeError):
            self.replay(mode="refresh")
        with self.assertRaises(TypeError):
            DuckDBReplayProvider(object(), source_id=SOURCE)

    def test_generic_cache_preserves_pandas_string_columns_index_and_nulls(self):
        frame = pd.DataFrame({"symbol": pd.Series(["000001", None], dtype="string")})
        frame.index = pd.Index(["first", "second"], dtype="string", name="label")
        original = frame.copy()
        self.cache.write_frame("nullable_symbols", frame)
        stored = self.cache.query("SELECT * FROM nullable_symbols ORDER BY label")
        self.assertEqual(stored.label.tolist(), ["first", "second"])
        self.assertEqual(stored.symbol.iloc[0], "000001")
        self.assertTrue(pd.isna(stored.symbol.iloc[1]))
        assert_frame_equal(frame, original)

    def test_generic_cache_and_context_lifecycle_remain_compatible(self):
        self.cache.write_frame("prices", synthetic_frame())
        result = self.cache.query('SELECT count(*) AS n FROM prices')
        self.assertEqual(result.n.iloc[0], len(synthetic_frame()))
        self.cache.close()
        self.cache.close()
        for action in (lambda: self.cache.query("SELECT 1"),
                       lambda: self.cache.write_frame("prices", synthetic_frame()),
                       lambda: self.replay().history(**REQUEST)):
            with self.assertRaisesRegex(RuntimeError, "closed"):
                action()

    def test_injected_connection_is_not_closed_by_cache(self):
        import duckdb
        connection = duckdb.connect()
        with DuckDBMarketCache(connection=connection) as cache:
            self.assertEqual(cache.query("SELECT 1 AS x").x.iloc[0], 1)
        self.assertEqual(connection.execute("SELECT 2").fetchone()[0], 2)
        connection.close()

    def test_query_accepts_cte_comments_and_semicolon_inside_literal(self):
        self.cache.write_frame("prices", synthetic_frame())
        sql = "-- safe leading comment\nWITH x AS (SELECT ';DELETE' AS s) SELECT s FROM x;"
        self.assertEqual(self.cache.query(sql).s.iloc[0], ";DELETE")

    def test_query_rejects_stacked_and_disguised_mutations_without_side_effects(self):
        self.cache.write_frame("prices", synthetic_frame())
        for sql in ("SELECT 1; DROP TABLE prices", "WITH x AS (SELECT 1) DELETE FROM prices",
                    "SELECT 1; SELECT 2", "COPY prices TO '/tmp/should-not-exist.csv'",
                    "PRAGMA enable_external_access=true", "CREATE TABLE bad AS SELECT 1",
                    "DELETE FROM prices", "", "/* no query */", "SELECT from broken("):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                self.cache.query(sql)
        self.assertEqual(self.cache.query("SELECT count(*) AS n FROM prices").n.iloc[0], len(synthetic_frame()))

    def test_read_only_transaction_blocks_select_side_effects_and_recovers(self):
        import duckdb
        self.cache._connection.execute("CREATE SEQUENCE probe_sequence")
        with self.assertRaises(duckdb.TransactionException):
            self.cache.query("SELECT nextval('probe_sequence')")
        self.assertEqual(self.cache.query("SELECT 42 AS n").n.iloc[0], 42)
        self.assertEqual(self.cache._connection.execute("SELECT nextval('probe_sequence')").fetchone()[0], 1)

    def test_owned_connection_disables_external_reads_and_extension_autoload(self):
        import duckdb
        path = Path(self.tmp.name) / "must-not-read.csv"
        path.write_text("x\n123\n", encoding="utf-8")
        for setting in ("enable_external_access", "autoload_known_extensions", "autoinstall_known_extensions"):
            value = self.cache.query(f"SELECT current_setting('{setting}') AS value").value.iloc[0]
            self.assertFalse(value)
        with self.assertRaises(duckdb.PermissionException):
            self.cache.query(f"SELECT * FROM read_csv('{path.as_posix()}')")
        self.assertEqual(self.cache.query("SELECT 1 AS n").n.iloc[0], 1)

    def test_generic_writes_cannot_clobber_reserved_snapshot_tables(self):
        for name in ("__invest_replay_manifest", "__INVEST_REPLAY_INPUT"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "reserved"):
                self.cache.write_frame(name, synthetic_frame())


if __name__ == "__main__":
    unittest.main()
