# Integrated research candidate — 2026-09-30

## What now works together

This is a coherent candidate combining the independently reviewable PR #48 repair and PRs #49–#55 with the local Qlib contract. It is not a statement that those PRs are merged into main. The candidate PR records each exact remote source head and its base. No broker, account, credential, paid provider, order or real holdings are involved.

Two end-to-end paths deliberately use different data contracts:

1. **Native-price research:** explicit authorized local Qlib files → real isolated `D.features` → exact-request DuckDB snapshot → reopen with no upstream → real seeded Optuna TPE using only the training prefix → evaluate later observations → summary with both source and replay identities.
2. **Saved cash-engine research:** existing explicitly synthetic workbench dataset → real scikit-learn rolling split with gap → training-only candidate selection and later cost scenarios → immutable Workspace JSON → opt-in local MLflow archive/retry → Matplotlib PNG with identity metadata → private backup/restore.

Native Qlib prices and volume remain unconverted and their dataset-defined units remain unverified. They do not enter the stricter cash/lot/T+1 engine. No frozen holdout is opened. A successful synthetic pilot establishes software behavior, not market profitability or data rights.

## New composition contracts

`DuckDBReplayProvider` now accepts `adjust="qlib"` for daily requests with exact six-digit, `SH`/`SZ` prefix or `.SH`/`.SZ` suffix symbols. The cache key keeps the exact accepted request: aliases intentionally do not match each other. Refresh is explicit; cache-only misses never fetch.

Native snapshots require the Qlib source contract: content hash, instrument, date range, actual runtime versions, native price/volume basis, unverified units and disabled network/tracking. This narrow metadata schema rejects extra keys, wrong exchange/date binding or mislabelled raw/qfq/hfq data. The metadata is part of the hashed snapshot and is validated after close/reopen. Existing ordinary v1 snapshots remain readable; native adjustment is a disjoint new request domain. Both existing pipelines preserve defensive copies of `market_data` and `duckdb_replay`, including after feature transforms and the Optuna evaluation slice.

The workbench exposes the existing local archive endpoint beside chart export for newly saved and restored studies. Status is scoped to that record; retry is disabled while pending, validates response identity and cannot enable tracking. An archive failure or interrupted response leaves the saved research available. Unknown archive reasons do not become raw SDK details. MLflow remains default-off, local-only and derivative; backups retain authoritative Workspace records, not the rebuildable MLflow archive.

Python 3.10 lacks SQLite's newer exception-code attributes. Busy classification now supports its exact legacy lock messages (including qualified locked-table messages), while newer structured codes are masked to SQLite primary BUSY/LOCKED values. The worker's 45-second deadline and success assertions are unchanged.

## Reproduce the installed distribution proof

```sh
python -m pip install '.[qlib,mlflow,charts,duckdb,optuna,test]' 'duckdb==1.5.6' 'optuna==5.0.0'
python -m pip check
python -m pytest tests -q
node --test tests/archive_controls_ui.test.cjs tests/study_charts_ui.test.cjs
python -m pip wheel --no-deps --wheel-dir dist .
python tools/research_stack_smoke.py dist
```

Use a fresh wheel directory with one Invest wheel. The pilot creates only synthetic inputs in a temporary directory, installs the wheel into another directory without network/dependency resolution, and starts Python `-I` outside the checkout. It asserts every Invest import is from the installed wheel. Actual Qlib and MLflow workers resolve that installed package too.

The JSON report verifies 120 native rows, 12 actual Optuna trials, an 84/36 training/evaluation split, independently matched later-period metrics, preserved source/snapshot identities, an exact-request alias cache miss, nine rolling cash-engine cases, a reused single MLflow run, PNG identity, private-backup restore, byte-identical chart regeneration and a rebuilt local archive from the unchanged restored record. Temporary input/output files are removed after verification; no user data is read. The existing source APIs and workbench retain their normal output behavior.

The dedicated hosted matrix runs the full source suite plus this isolated wheel pilot with all optional SDKs coinstalled on Ubuntu/Windows and Python 3.10/3.12, including the declared minimum Python version. The existing narrower matrices remain unchanged. Check terminal results for the candidate's exact head before claiming cross-platform acceptance.

## Upstream identity and attribution

All counts below were read from official GitHub repositories on 2026-09-30, not inferred from popularity. Stars were a user threshold, not the only selection criterion: stable APIs, compatible terms, bounded runtime behavior and deterministic integration evidence were also required.

| Upstream | Verified stars | Runtime/source pin | License |
| --- | ---: | --- | --- |
| scikit-learn/scikit-learn | 67,434 | TimeSeriesSplit public API; source `646da0f072a8afef6a980aa427a710311e67eb9d` | BSD-3-Clause |
| optuna/optuna | 14,865 | actual pilot 5.0.0; source `5c8e50d85b77dd5a1fd7e26e21f63debc81d6016` | MIT |
| duckdb/duckdb | 41,832 | actual pilot 1.5.6; source `7fb68627fd223b7cd06d37b83059e571fa5f994a` | MIT |
| mlflow/mlflow | 28,199 | 3.16.1; `7faf28476bddcebb68ee8b08cdcba1bee7ad6109` | Apache-2.0 |
| matplotlib/matplotlib | 23,310 | 3.10.8; `1392cbe3c79cdb93f9282747841d648770f60249` | PSF-based Matplotlib license |
| microsoft/qlib | 49,078 | pyqlib 0.9.7; `da920b7f954f48ab1bb64117c976710de198373e` | MIT |

Exact upstream license bytes, copyright, source links and change summaries remain in `third_party/`, `THIRD_PARTY.md` and the individual documents below. No new unreviewed upstream implementation is copied by this composition. Qlib's data-only experiment hook supports the stated MLflow combination; Qlib FILE experiments and model training are not claimed compatible. The pilot reports the actual installed scikit-learn version because the core package supports a range and available wheels differ by Python version.

- [Rolling study](sklearn-walkforward-2026-09-30.md)
- [Native Qlib reader](qlib-provider-2026-09-30.md)
- [Saved-study charts](matplotlib-study-charts-2026-09-30.md)
- Individual Optuna, DuckDB, MLflow and wheel PR descriptions contain exact test/run evidence

## Evidence and remaining limits

The final local Linux/Python 3.12 source suite passed **863 tests, 13 explicit optional skips and 454 subtests**, with zero failures; all eight UI state tests and `pip check` passed. The rebuilt installed-wheel pilot passed all six SDKs and both complete flows, including restore → byte-identical PNG → fresh local archive reconstruction. Independent review accepted the native replay metadata bridge, source identities, installed-wheel isolation, archive UI state behavior and Python 3.10 compatibility fallback; it found no remaining blocker after the qualified SQLite lock-message regression was added. Final full-suite and hosted results are recorded on the exact candidate PR, not presumed here.

Earlier chart-stack Windows CI observed intermittent local archive contention/deadline failures. A later exact head passed all SDK tests; the added phase profiler is diagnostic, not a proven causal reliability fix. A local archive timeout remains an explicit retryable failure after saving the study. Neither a profiler's zero exit nor a single green matrix is a guarantee under every resource condition.

Browser navigation is blocked in this execution environment. HTTP, actual SDKs, UI state tests and PNG pixel inspection do not establish browser-layout, Windows desktop/frozen-executable, physical filesystem locality, real-market correctness or profitability acceptance.
