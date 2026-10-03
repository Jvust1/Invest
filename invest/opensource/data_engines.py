"""Optional native, in-memory descriptions of a caller-supplied numeric series.

No adapter accepts a path, SQL fragment, URL, extension, or executable callback.
These are descriptive statistics, not a forecast, market-data source, or trade.

API references checked for this implementation:
https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.Expr.std.html
https://duckdb.org/docs/current/clients/python/dbapi
https://duckdb.org/docs/current/configuration/overview
https://duckdb.org/docs/current/sql/functions/aggregates
https://arrow.apache.org/docs/python/compute.html
https://arrow.apache.org/docs/python/generated/pyarrow.compute.stddev.html
"""

from __future__ import annotations

from contextlib import closing
import math
import sys
from typing import Any

from invest.opensource.common import load_dependency, validated_series


_NAMES = ("polars", "duckdb", "pyarrow")
_COLUMNS = ("count", "mean", "min", "max", "std_population")
# Float64 variance below the normal range can silently underflow or lose large
# relative precision in all three engines at once; agreement is not proof here.
_MIN_RELIABLE_STD = math.sqrt(sys.float_info.min)
_DUCKDB_QUERY = """
SELECT count(value), avg(value), min(value), max(value), stddev_pop(value)
FROM UNNEST(?::DOUBLE[]) AS observations(value)
"""
_DUCKDB_CONFIG = {
    "enable_external_access": "false",
    "autoinstall_known_extensions": "false",
    "autoload_known_extensions": "false",
    "allow_unsigned_extensions": "false",
    "threads": "1",
    "memory_limit": "64MB",
    # An empty temporary directory disables disk spilling for an in-memory DB.
    "temp_directory": "",
}


def _polars(values: list[float]) -> dict[str, Any]:
    """Use Polars expressions; explicitly override its sample-std default."""
    pl = load_dependency("polars", "polars")
    frame = pl.DataFrame({"value": values}, schema={"value": pl.Float64})
    column = pl.col("value")
    return frame.select(
        column.count().alias("count"),
        column.mean().alias("mean"),
        column.min().alias("min"),
        column.max().alias("max"),
        column.std(ddof=0).alias("std_population"),
    ).row(0, named=True)


def _duckdb(values: list[float]) -> dict[str, Any]:
    """Create and close an isolated DB; all data use one bound list parameter."""
    duckdb = load_dependency("duckdb", "duckdb")
    with closing(duckdb.connect(database=":memory:", config=dict(_DUCKDB_CONFIG))) as db:
        row = db.execute(_DUCKDB_QUERY, [values]).fetchone()
    if row is None or len(row) != len(_COLUMNS):
        raise ValueError("duckdb returned an invalid descriptive statistics row")
    return dict(zip(_COLUMNS, row))


def _pyarrow(values: list[float]) -> dict[str, Any]:
    """Use an Arrow Table and Arrow C++ compute kernels, without file I/O."""
    pa = load_dependency("pyarrow", "pyarrow")
    pc = load_dependency("pyarrow.compute", "pyarrow")
    table = pa.table({"value": pa.array(values, type=pa.float64())})
    column = table.column("value")
    return {
        "count": pc.count(column).as_py(),
        "mean": pc.mean(column).as_py(),
        "min": pc.min(column).as_py(),
        "max": pc.max(column).as_py(),
        "std_population": pc.stddev(column, ddof=0).as_py(),
    }


def run(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Compute the same bounded population statistics with a named engine.

    Args:
        name: Exactly ``polars``, ``duckdb``, or ``pyarrow``.
        payload: Only ``values``: 8..5000 finite JSON numbers, absolute value
            at most 1,000,000. Negative and constant series are valid.

    Returns:
        Native-engine count, mean, min, max, population standard deviation;
        ``ddof=0`` makes the convention explicit. Input is not modified.

    Raises:
        ValueError: Invalid input, missing optional engine, nonfinite output, or
            nonconstant variation below the reliable float64 variance range.
    """
    if type(name) is not str or name not in _NAMES:
        raise ValueError("data engine must be polars, duckdb, or pyarrow")
    values = validated_series(payload)
    adapters = {"polars": _polars, "duckdb": _duckdb, "pyarrow": _pyarrow}
    result = adapters[name](values)
    if result.get("count") != len(values):
        raise ValueError(f"{name} returned an inconsistent observation count")
    for key in _COLUMNS[1:]:
        value = result.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} returned a nonfinite {key}")
        result[key] = float(value)
    if result["std_population"] < 0:
        raise ValueError(f"{name} returned a negative population standard deviation")
    if result["std_population"] < _MIN_RELIABLE_STD and any(
        value != values[0] for value in values[1:]
    ):
        raise ValueError(
            "NUMERIC_RANGE_EXCEEDED: nonconstant series variance is below "
            "the reliable float64 range; a zero or subnormal-variance estimate "
            "would be misleading"
        )
    result["count"] = int(result["count"])
    return {"engine": name, "operation": "describe", "ddof": 0, **result}
