"""Optional DuckDB cache for normalized Invest market-data frames.

Upstream: duckdb/duckdb @
7fb68627fd223b7cd06d37b83059e571fa5f994a (MIT).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class DuckDBMarketCache:
    def __init__(self, path: str | Path = ":memory:", *, connection: Any | None = None) -> None:
        if connection is None:
            try:
                import duckdb
            except ImportError as exc:
                raise RuntimeError("DuckDB is optional; install Invest with the 'duckdb' extra") from exc
            connection = duckdb.connect(str(path))
        for name in ("register", "execute"):
            if not callable(getattr(connection, name, None)):
                raise TypeError(f"DuckDB connection must provide {name}()")
        self._connection = connection

    def write_frame(self, table: str, frame: pd.DataFrame) -> None:
        if not table.replace("_", "").isalnum():
            raise ValueError("table name must contain only letters, digits and underscores")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas.DataFrame")
        temp_name = "_invest_frame"
        self._connection.register(temp_name, frame.reset_index())
        self._connection.execute(
            f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM {temp_name}'
        )

    def query(self, sql: str) -> pd.DataFrame:
        statement = str(sql).strip()
        if not statement.casefold().startswith(("select ", "with ")):
            raise ValueError("cache query must be read-only SELECT/WITH")
        result = self._connection.execute(statement)
        fetch_df = getattr(result, "fetchdf", None)
        if not callable(fetch_df):
            raise TypeError("DuckDB result must provide fetchdf()")
        return fetch_df()


def cache_akshare_history(
    cache: DuckDBMarketCache,
    provider: Any,
    symbol: str,
    *,
    table: str = "a_share_history",
    **history_kwargs: Any,
) -> pd.DataFrame:
    frame = provider.history(symbol=symbol, **history_kwargs)
    cache.write_frame(table, frame)
    return frame
