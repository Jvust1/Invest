"""Optional DuckDB storage and exact-request offline market-data replay.

Upstream: duckdb/duckdb @
7fb68627fd223b7cd06d37b83059e571fa5f994a (MIT).
The optional upstream package executes storage, SQL parsing and transactions;
Invest owns the normalized-frame and request-identity contracts.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Any

import numpy as np
import pandas as pd


_PREFIX = "__invest_replay_"
_MANIFEST = f"{_PREFIX}manifest"
_SCHEMA_VERSION = 1
_NUMERIC = {
    "open", "high", "low", "close", "volume", "turnover", "amplitude",
    "change_pct", "change", "turnover_rate",
}
_REQUIRED = {"open", "high", "low", "close", "volume"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DuckDBCacheMiss(LookupError):
    """No snapshot matches the complete declared request."""


class DuckDBCacheIntegrityError(RuntimeError):
    """Stored snapshot or manifest failed validation; no fallback was used."""


class DuckDBCacheStaleError(RuntimeError):
    """The exact snapshot exceeds the caller's explicit maximum age."""


class DuckDBMarketCache:
    """Local DuckDB cache. Owns connections it opens, not injected connections.

    Owned connections disable external file/network access and automatic
    extension loading/installing. Injected connections are trusted dependencies:
    their owner must apply the same settings and must not register unsafe UDFs.
    SQL queries run as one parsed SELECT in a read-only transaction, including
    queries with comments or CTEs. This is not a sandbox for untrusted databases,
    extensions, Python UDFs or other code with access to the connection.
    """

    def __init__(
        self, path: str | Path = ":memory:", *, connection: Any | None = None,
        read_only: bool = False,
    ) -> None:
        self._owns_connection = connection is None
        if connection is None:
            try:
                import duckdb
            except ImportError as exc:
                raise RuntimeError("DuckDB is optional; install Invest with the 'duckdb' extra") from exc
            connection = duckdb.connect(
                str(path), read_only=read_only,
                config={"enable_external_access": False,
                        "autoload_known_extensions": False,
                        "autoinstall_known_extensions": False},
            )
        elif read_only:
            raise ValueError("read_only must be configured by the injected connection's owner")
        for name in ("register", "execute"):
            if not callable(getattr(connection, name, None)):
                raise TypeError(f"DuckDB connection must provide {name}()")
        self._connection = connection
        self._lock = threading.RLock()
        self._closed = False

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError("DuckDB cache is closed")

    @contextmanager
    def _transaction(self, *, read_only: bool = False):
        with self._lock:
            self._check_open()
            self._connection.execute("BEGIN TRANSACTION READ ONLY" if read_only else "BEGIN TRANSACTION")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except BaseException:
                try:
                    self._connection.execute("ROLLBACK")
                except Exception:
                    # Preserve the original failure if the connection was lost
                    # or the database already aborted the transaction.
                    pass
                raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                if self._owns_connection:
                    self._connection.close()
                self._closed = True

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *exc):
        self.close()

    def write_frame(self, table: str, frame: pd.DataFrame) -> None:
        if not isinstance(table, str) or not re.fullmatch(r"[A-Za-z0-9_]+", table):
            raise ValueError("table name must contain only letters, digits and underscores")
        if table.casefold().startswith(_PREFIX):
            raise ValueError("table name is reserved for replay snapshots")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas.DataFrame")
        with self._lock:
            self._check_open()
            temp_name = "_invest_frame"
            self._connection.register(temp_name, frame.reset_index())
            try:
                self._connection.execute(
                    f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM {temp_name}'
                )
            finally:
                unregister = getattr(self._connection, "unregister", None)
                if callable(unregister):
                    unregister(temp_name)

    def query(self, sql: str) -> pd.DataFrame:
        with self._lock:
            self._check_open()
            if not isinstance(sql, str):
                raise TypeError("cache query must be SQL text")
            extract = getattr(self._connection, "extract_statements", None)
            if not callable(extract):
                raise TypeError("DuckDB connection must provide extract_statements() for safe queries")
            try:
                statements = extract(sql)
            except Exception as exc:
                raise ValueError("cache query must be one parsed SELECT statement") from exc
            if len(statements) != 1 or statements[0].type.name != "SELECT":
                raise ValueError("cache query must be one parsed SELECT statement")
            with self._transaction(read_only=True) as connection:
                result = connection.execute(sql)
                fetch_df = getattr(result, "fetchdf", None)
                if not callable(fetch_df):
                    raise TypeError("DuckDB result must provide fetchdf()")
                return fetch_df()


def _request(source_id: str, symbol: str, start_date: str, end_date: str,
             period: str, adjust: str) -> dict[str, Any]:
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("symbol must be an exact six-digit string, preserving leading zeros")
    for value in (start_date, end_date):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
            raise ValueError("request dates must use YYYYMMDD")
        datetime.strptime(value, "%Y%m%d")
    if start_date > end_date:
        raise ValueError("start_date must not follow end_date")
    if period not in ("daily", "weekly", "monthly"):
        raise ValueError("period must be daily, weekly or monthly")
    if adjust not in ("", "qfq", "hfq"):
        raise ValueError("adjust must be '', 'qfq' or 'hfq'")
    return {"schema_version": _SCHEMA_VERSION, "source_id": source_id,
            "symbol": symbol, "start_date": start_date, "end_date": end_date,
            "period": period, "adjust": adjust}


def _normalize(frame: pd.DataFrame, request: dict[str, Any]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("replay requires a nonempty normalized OHLCV DataFrame")
    columns = frame.columns.tolist()
    if not frame.columns.is_unique or not all(isinstance(c, str) for c in columns):
        raise ValueError("normalized columns must be unique strings")
    if not _REQUIRED.issubset(columns) or set(columns) - (_NUMERIC | {"symbol"}):
        raise ValueError("replay requires OHLCV and only supported normalized history columns")
    index = frame.index
    if (not isinstance(index, pd.DatetimeIndex) or index.tz is not None or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing
            or not index.equals(index.normalize())):
        raise ValueError("history index must contain unique increasing timezone-naive dates")
    if index[0] < pd.Timestamp(request["start_date"]) or index[-1] > pd.Timestamp(request["end_date"]):
        raise ValueError("history dates fall outside the exact request bounds")
    if index[0] < pd.Timestamp.min or index[-1] > pd.Timestamp.max:
        raise ValueError("history dates must fit the stored nanosecond timestamp range")
    result = frame.copy()
    result.index = pd.DatetimeIndex(index.to_numpy(dtype="datetime64[ns]"), name="date")
    result.attrs = {}
    for column in columns:
        if column == "symbol":
            if not all(isinstance(value, str) and value == request["symbol"] for value in result[column]):
                raise ValueError("history symbols must exactly match the requested symbol string")
            result[column] = result[column].astype(object)
        else:
            if not pd.api.types.is_numeric_dtype(result[column]) or pd.api.types.is_bool_dtype(result[column]):
                raise ValueError(f"normalized {column} must be numeric")
            if pd.api.types.is_complex_dtype(result[column]):
                raise ValueError(f"normalized {column} must be real-valued")
            result[column] = result[column].astype("float64")
            if not np.isfinite(result[column]).all():
                raise ValueError(f"normalized {column} must be finite")
    prices = result[["open", "high", "low", "close"]]
    if (prices <= 0).any().any() or (result["volume"] < 0).any():
        raise ValueError("OHLC must be positive and volume must be nonnegative")
    if ((result["high"] < prices.max(axis=1)).any()
            or (result["low"] > prices.min(axis=1)).any()):
        raise ValueError("inconsistent OHLC bounds")
    return result


def _frame_digest(frame: pd.DataFrame) -> str:
    # float.hex preserves every normalized float bit across DuckDB round trips.
    payload = {"columns": frame.columns.tolist(),
               "dates": frame.index.strftime("%Y-%m-%d").tolist(),
               "rows": [[v if isinstance(v, str) else float(v).hex() for v in row]
                        for row in frame.itertuples(index=False, name=None)]}
    return _sha(_json(payload))


class DuckDBReplayProvider:
    """Exact-request provider for the existing research bundle/SMA pipelines.

    cache_only (default) never calls upstream, even on a miss or corruption.
    refresh always calls the explicitly injected upstream and atomically replaces
    only that exact request after validation. Failures leave its old snapshot
    untouched but are raised, never hidden by returning the old snapshot.

    source_id is the caller's declared provider/product/normalizer/units identity,
    not an authenticity or data-license verification. Change it when those
    semantics change. Stored data is never silently sliced, combined or filled.
    The cache does not own the provider, and closing it is the caller's job.
    """

    name = "duckdb_replay"

    def __init__(self, cache: DuckDBMarketCache, *, source_id: str,
                 upstream: Any | None = None, mode: str = "cache_only",
                 max_age_seconds: float | None = None) -> None:
        if not isinstance(cache, DuckDBMarketCache):
            raise TypeError("cache must be a DuckDBMarketCache")
        if (not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 500
                or any(ord(char) < 32 or ord(char) == 127 for char in source_id)):
            raise ValueError("source_id must be nonempty text without control characters (max 500)")
        if mode not in ("cache_only", "refresh"):
            raise ValueError("mode must be cache_only or refresh")
        if mode == "refresh" and not callable(getattr(upstream, "history", None)):
            raise TypeError("refresh requires an explicit upstream with history()")
        if max_age_seconds is not None:
            if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
                    or not math.isfinite(max_age_seconds) or max_age_seconds < 0):
                raise ValueError("max_age_seconds must be finite and nonnegative")
        self._cache, self._source_id = cache, source_id
        self._upstream, self._mode = upstream, mode
        self._max_age_seconds = max_age_seconds
        self._last_snapshot: dict[str, Any] | None = None

    @property
    def last_snapshot(self) -> dict[str, Any] | None:
        """Copy of the last successful call's provenance; cleared before each call."""
        return json.loads(_json(self._last_snapshot))

    def history(self, symbol: str, *, start_date: str = "19700101",
                end_date: str = "20500101", period: str = "daily",
                adjust: str = "") -> pd.DataFrame:
        self._last_snapshot = None
        self._cache._check_open()
        request = _request(self._source_id, symbol, start_date, end_date, period, adjust)
        request_json = _json(request)
        key = _sha(request_json)
        if self._mode == "refresh":
            frame = _normalize(self._upstream.history(
                symbol=symbol, start_date=start_date, end_date=end_date,
                period=period, adjust=adjust,
            ), request)
            metadata = self._store(key, request, frame)
        else:
            frame, metadata = self._load(key, request)
        provenance = {**metadata, "snapshot_id": _sha(_json(metadata)),
                      "cache_status": self._mode}
        frame.attrs["duckdb_replay"] = provenance
        self._last_snapshot = json.loads(_json(provenance))
        return frame

    def _store(self, key: str, request: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
        table, staging = _PREFIX + key, _PREFIX + "input"
        with self._cache._transaction() as connection:
            metadata = {"request": request, "request_id": key,
                        "columns": frame.columns.tolist(), "row_count": len(frame),
                        "data_sha256": _frame_digest(frame),
                        "acquired_at": datetime.now(timezone.utc).isoformat(),
                        "duckdb_version": connection.execute("SELECT version()").fetchone()[0]}
            connection.execute(f'CREATE TABLE IF NOT EXISTS "{_MANIFEST}" '
                               '(request_id VARCHAR PRIMARY KEY, metadata_json VARCHAR NOT NULL, '
                               'snapshot_id VARCHAR NOT NULL)')
            connection.register(staging, frame.reset_index())
            try:
                connection.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM "{staging}"')
                connection.execute(f'DELETE FROM "{_MANIFEST}" WHERE request_id = ?', [key])
                connection.execute(f'INSERT INTO "{_MANIFEST}" VALUES (?, ?, ?)',
                                   [key, _json(metadata), _sha(_json(metadata))])
            finally:
                connection.unregister(staging)
        return metadata

    def _load(self, key: str, request: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
        try:
            with self._cache._transaction(read_only=True) as connection:
                exists = connection.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_name = ?",
                    [_MANIFEST],
                ).fetchone()[0]
                if not exists:
                    raise DuckDBCacheMiss(f"no cached snapshot for exact request {key}")
                row = connection.execute(f'SELECT metadata_json, snapshot_id FROM "{_MANIFEST}" '
                                         'WHERE request_id = ?', [key]).fetchone()
                if row is None:
                    raise DuckDBCacheMiss(f"no cached snapshot for exact request {key}")
                raw_metadata, snapshot_id = row
                metadata = json.loads(raw_metadata)
                if (_sha(_json(metadata)) != snapshot_id or metadata["request"] != request
                        or metadata["request_id"] != key):
                    raise ValueError("manifest identity mismatch")
                acquired_at = datetime.fromisoformat(metadata["acquired_at"])
                if acquired_at.tzinfo != timezone.utc:
                    raise ValueError("snapshot acquisition time must be UTC")
                stored = connection.execute(f'SELECT * FROM "{_PREFIX + key}" ORDER BY date').fetchdf()
                if stored.columns.tolist() != ["date", *metadata["columns"]]:
                    raise ValueError("stored schema differs from manifest")
                frame = _normalize(stored.set_index("date"), request)
                if len(frame) != metadata["row_count"] or _frame_digest(frame) != metadata["data_sha256"]:
                    raise ValueError("snapshot content differs from manifest")
        except DuckDBCacheMiss:
            raise
        except Exception as exc:
            raise DuckDBCacheIntegrityError(f"cached snapshot failed integrity validation for request {key}") from exc
        if (self._max_age_seconds is not None
                and (datetime.now(timezone.utc) - acquired_at).total_seconds() > self._max_age_seconds):
            raise DuckDBCacheStaleError(f"cached snapshot exceeds max_age_seconds for request {key}")
        return frame, metadata


def cache_akshare_history(
    cache: DuckDBMarketCache, provider: Any, symbol: str, *,
    table: str = "a_share_history", **history_kwargs: Any,
) -> pd.DataFrame:
    """Legacy generic one-table helper; use DuckDBReplayProvider for provenance."""
    frame = provider.history(symbol=symbol, **history_kwargs)
    cache.write_frame(table, frame)
    return frame
