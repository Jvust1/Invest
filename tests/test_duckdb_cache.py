import unittest
import pandas as pd

from invest.providers.duckdb_cache import DuckDBMarketCache, cache_akshare_history


class FakeResult:
    def fetchdf(self):
        return pd.DataFrame([{"x": 1}])


class FakeConnection:
    def __init__(self):
        self.registered = []
        self.sql = []

    def register(self, name, frame):
        self.registered.append((name, frame.copy()))

    def execute(self, sql):
        self.sql.append(sql)
        return FakeResult()


class FakeProvider:
    def history(self, symbol, **kwargs):
        assert symbol == "600000"
        return pd.DataFrame({"close": [10.0, 10.5]})


class DuckDBCacheTests(unittest.TestCase):
    def test_cache_writes_normalized_frame_and_allows_read_only_query(self):
        conn = FakeConnection()
        cache = DuckDBMarketCache(connection=conn)
        frame = cache_akshare_history(cache, FakeProvider(), "600000")
        self.assertEqual(len(frame), 2)
        self.assertTrue(conn.registered)
        self.assertIn("CREATE OR REPLACE TABLE", conn.sql[0])
        result = cache.query("SELECT 1 AS x")
        self.assertEqual(int(result.iloc[0]["x"]), 1)

    def test_cache_rejects_mutating_query(self):
        cache = DuckDBMarketCache(connection=FakeConnection())
        with self.assertRaises(ValueError):
            cache.query("DELETE FROM prices")


if __name__ == "__main__":
    unittest.main()
