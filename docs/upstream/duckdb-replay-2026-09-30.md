# DuckDB exact-request offline research replay

## Upstream and scope

- Official upstream: https://github.com/duckdb/duckdb
- 41,832 stars checked on 2026-09-30; permissive MIT license
- Inspected source revision: `7fb68627fd223b7cd06d37b83059e571fa5f994a`
- Exact upstream LICENSE retained at `third_party/duckdb/LICENSE` (Git blob `2719c9a23d2a37c1dfb7402e79f03bd615701e53`)
- Runtime dependency: optional `duckdb>=1.4`, installed with `pip install -e '.[duckdb]'`; actual tested versions are 1.4.0 and 1.5.6. The source revision records provenance, not an assertion that every installed wheel was built from that commit. Each snapshot records the runtime version
- Uses the actual upstream connection, pandas registration, typed DuckDB tables, transactions and SQL parser. No vendored database engine or invented reimplementation
- Feature builds on #51 and its prerequisite #48. It does not include, modify or depend on #49/#50

## Complete runtime path

`normalized provider.history → explicit refresh → validated DuckDB snapshot → close → reopen read-only → cache_only provider.history → existing research bundle / SMA pipeline`

Run a synthetic-only executable slice from the repository root:

```sh
python -m pip install -e '.[duckdb]'
python -m examples.duckdb_offline_replay
```

The example records 120 fictional rows, closes the database, reopens it read-only without any upstream attached, executes both existing research pipelines, and asserts that frames, backtests, summaries and snapshot IDs match. Exactly one synthetic provider call occurs. The temporary file is cleaned up after the example; use an explicit persistent path in application wiring.

## Provider contract

```python
from invest.providers import DuckDBMarketCache, DuckDBReplayProvider

request = dict(symbol="000001", start_date="20240101", end_date="20240430", adjust="qfq")
source = "my-authorized-provider/product/normalizer-v1;volume=declared-units"

# Call upstream only when deliberately refreshing an authorized data source.
with DuckDBMarketCache("history.duckdb") as cache:
    refresh = DuckDBReplayProvider(cache, source_id=source, upstream=provider, mode="refresh")
    frame = refresh.history(**request)

# No provider object is required for offline replay.
with DuckDBMarketCache("history.duckdb", read_only=True) as cache:
    replay = DuckDBReplayProvider(cache, source_id=source)
    bundle = run_a_share_research_bundle(replay, **request)
    provenance = replay.last_snapshot
```

The source example is a placeholder, not a claim of data authorization. Import `run_a_share_research_bundle` from `invest.research_pipeline` and supply an authorized normalized provider before using the first block with real data.

- `cache_only` is the default. It never calls upstream, even when an upstream was supplied, a key is absent, integrity validation fails or a freshness limit is exceeded
- `refresh` always calls the explicitly injected upstream once. It never quietly accepts an older hit. Invalid data and upstream/storage errors are raised; no fallback result is returned. Table and manifest replacement are transactional
- The exact key binds schema version, declared source/product/normalizer/units identity, six-digit symbol string, both inclusive date bounds, period (`daily`, `weekly`, `monthly`) and adjustment (`""`, `qfq`, `hfq`)
- No substring matching, range slicing, automatic aggregation, interpolation, previous-source fallback or adjustment conversion occurs. Changed bounds/source/adjustment/period require their own refresh
- Required normalized columns: open/high/low/close/volume. Optional: symbol, turnover, amplitude, change_pct, change and turnover_rate. Numeric columns become float64; optional symbol must already be an exact matching string, preserving leading zeros. Unsupported columns are rejected rather than silently dropped
- Dates must be unique, increasing, timezone-naive midnight values, inside the requested bounds and representable by nanosecond timestamps. The index is named `date`. Invalid order and duplicates are rejected, never repaired
- Every numeric value must be finite; OHLC must be positive and consistent; volume must be nonnegative. Missing trading sessions, corporate actions, currency/volume units, source truth and data licensing are not inferred or certified
- `source_id` is a caller declaration. Include the product and normalization/unit revision; update it when their semantics change. Never put credentials in it
- Snapshot provenance is attached to `frame.attrs["duckdb_replay"]`: request, request ID, column schema, row count, acquisition time in UTC, actual DuckDB version, data digest, snapshot ID and explicit cache mode. `replay.last_snapshot` returns a defensive copy and clears before failed calls
- The bundle preserves provenance on `bundle.market`. The existing SMA tuple is unchanged; use `replay.last_snapshot` alongside its result. Do not claim the SMA result alone contains provenance
- The data digest covers column order, every date and normalized value. Float hex serialization retains exact normalized floating-point identity. Snapshot ID also binds manifest/acquisition metadata. Verification on every read catches accidental corruption or edits, not a malicious actor able to replace both data and hashes
- Cache-only replay makes no freshness claim. Acquisition time is always explicit. Set `max_age_seconds` to reject snapshots older than a chosen limit, with no automatic refresh. Refresh intentionally replaces the latest snapshot for that exact request; this is not a version-history archive
- One typed table per exact request plus a shared manifest is intentionally simple. This is a local research cache, not a multi-user store or scalable market-data warehouse

## Query safety and ownership

The older generic `write_frame` and `cache_akshare_history` APIs remain available. Generic registration losslessly converts pandas StringDtype columns (including index columns) to object-backed strings on a copy, so DuckDB 1.4 also handles pandas 3 default string dtype while preserving leading zeros and nulls. They do not provide exact-request provenance; use the replay provider for that. Generic writes cannot overwrite reserved replay table names.

`query()` uses DuckDB `extract_statements` and requires exactly one SELECT-class statement. Comments and SELECT CTEs work; stacked statements and mutating CTE statements fail before execution. A read-only transaction additionally blocks side-effecting SQL such as `SELECT nextval(...)`. Failed queries roll back and the cache remains usable.

Cache-owned connections disable `enable_external_access`, `autoload_known_extensions` and `autoinstall_known_extensions`. Explicit registration of the supplied DataFrame still works; implicit filesystem/network SQL reads do not. Injected connections remain caller-owned, must provide the upstream parser for `query()`, and must be configured safely by that caller. Closing the cache does not close an injected connection. This is not a sandbox for an untrusted database, extension or Python UDF, and does not prevent code that already possesses the underlying connection from changing data.

References:
- [DuckDB Python API and extract_statements](https://duckdb.org/docs/current/clients/python/reference/)
- [DuckDB security overview](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)
- [DuckDB configuration](https://duckdb.org/docs/current/configuration/overview)

## Validation and boundaries

Focused tests use actual DuckDB plus synthetic providers and cover close/reopen, both existing pipelines, every key dimension, numeric/index/schema rejection, corruption, failed refresh, transaction/commit rollback, caller mutation, explicit freshness, parsed read-only queries and blocked external file reads. `.github/workflows/duckdb-replay.yml` installs the actual optional dependency and runs the contracts and executable example on Ubuntu/Windows with Python 3.11/3.12 and DuckDB 1.4.0/1.5.6.

Local verification after rebasing onto #51: `python -m pytest tests -q` reports **590 passed, 13 optional-dependency skips, 410 passing subtests** with DuckDB 1.5.6. Both DuckDB 1.4.0 and 1.5.6 pass all **31 focused tests / 62 adversarial subtests** and the executable 120-row example. Compatibility was also verified with pandas 3.0.6, including the DuckDB 1.4 + pandas 3 string-registration failure first exposed by remote CI. The same complete suite passes on pandas 3.0.6 / DuckDB 1.4.0. Source compilation and diff whitespace checks pass. Independent review found and verified fixes for timestamp overflow and transaction commit recovery; no remaining actionable findings. Remote exact-head CI is reported on the Draft PR after publication. Running bare pytest outside the declared `tests` target also collects the pre-existing `legacy_research` duplicate test names and fails import-file matching; this feature does not change legacy collection.

No real data provider, paid service, credentials, private holdings, broker, live order or frozen evaluation holdout was used. The consuming pipelines are exploratory close-to-close signal research, not the stricter A-share execution/ledger engine. Software/cache test success is not evidence of strategy returns or data authenticity. The existing pipeline metrics are unchanged here; #50 independently improves those metrics.
