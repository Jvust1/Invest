# Microsoft Qlib native local-data integration — 2026-09-30

## Concrete path

An explicit existing local Qlib binary directory → actual official `pyqlib==0.9.7` `D.features` → validated `QlibMarketProvider.history` → either existing `run_a_share_sma_backtest` or `run_a_share_research_bundle`.

This repairs the earlier bridge's silent symbol stripping/exchange switching, ignored adjustment, unselected instruments, permissive date conversion and numeric coercion. It is a functional data-reader integration, not a catalogue-only entry. It does not import models, install Torch, download market data, open a holdout, connect a broker, or authenticate dataset rights.

## Explicit price and volume basis

Use `adjust="qlib"`. Qlib's [official data documentation](https://qlib.readthedocs.io/en/latest/component/data.html#qlib-format-dataset) says its distributed prices and volume are adjusted, and prices may be normalized to 1 on the first trading day. Arbitrary locally authored Qlib files can use their own basis. Those values therefore cannot be advertised as raw, qfq, CNY/share or original volume merely because their column names are OHLCV.

This bridge preserves native stored values without adjustment conversion, renaming units, inferring factors or removing missing/suspended rows. `adjust=""`, `qfq`, `hfq` and all other values fail before any SDK request. Only `period="daily"` is supported, including explicit cache-refresh callers; all other periods fail before SDK use. Existing non-Qlib pipeline defaults remain `qfq`.

Output `DataFrame.attrs["market_data"]` retains source kind, file-content fingerprint, actual SDK versions, requested instrument/dates, native price/volume basis and unverified dataset-defined units. Both pipeline backtest frames retain these attributes; the bundle's market frame retains them even when a feature transform discards attributes. The metadata does not prove data rights or correctness. These close-to-close exploratory research paths do not use native normalized prices in the stricter cash/lot/T+1 execution engine. Existing pipeline metric definitions are unchanged in this branch.

## Symbol and data validation

Accepted symbols are exactly six ASCII digits, `SH`/`SZ` plus six digits, or six digits plus `.SH`/`.SZ`; outer whitespace and case are normalized. Bare digits preserve the previous SH-for-5/6/9, otherwise-SZ convention. Use an explicit exchange when ambiguous. Explicit exchange always wins: `000001.SH` stays `SH000001` (a Shanghai index format is not rejected based on its first digit). Syntax is not listing/security-type verification.

The adapter rejects missing/unexpected instruments, absent identity index levels, missing/duplicate columns, empty results, invalid/timezoned/intraday/duplicate/nonchronological/out-of-window dates, nonnumeric values, nonfinite values, nonpositive prices, negative volume, and inconsistent OHLC bounds. Zero volume is allowed. Daily request dates accept only YYYYMMDD or YYYY-MM-DD. It never silently drops a bad row, sorts malformed data, fills prices or substitutes an instrument.

## Local runtime, tracking and resource boundaries

`create_qlib_market_provider(provider_uri=absolute_directory)` requires an existing local directory with `calendars/day.txt`, `instruments/all.txt`, and `features/`. No implicit home dataset, provider URL, UNC share, NFS URI or SDK auto-mount. Required feature paths must stay inside the directory with no symlink traversal. A mounted filesystem's provenance remains the operator's responsibility; this path validator does not certify the operating system's storage backend.

Every request runs in a fresh source-Python child with its own temporary working directory, 45-second timeout, one SDK kernel, no disk/expression/Redis caches, and a maximum 20,000 total calendar-day rows. Up to 16 explicit instruments and five direct OHLCV fields are available to the generic reader, with the same total-row bound. Calendar, manifest and binary-offset/byte-length checks run before SDK initialization. Selected input file hashes are checked before and after the read, and contribute to the result identity. Data is transported as bounded JSON, never pickle.

The child strips inherited `QLIB_*` and `MLFLOW_*` configuration. MLflow telemetry is disabled before any SDK import. A Python audit hook rejects socket/network operations as defense in depth; it is not an OS sandbox. A data-only Qlib experiment-manager hook rejects experiment operations and only permits inert exit cleanup. No MLflow client, run, autologger, model registry or Qlib experiment is created. Parent SDK singleton/configuration and environment state are unchanged, and independent local providers can coexist.

Published Qlib 0.9.7 declares unbounded MLflow, whereas newer Qlib source restricts MLflow for its FILE experiment backend. This integration pins and verifies the actual **pyqlib 0.9.7 + MLflow 3.16.1 data-only** combination without downgrading Invest's separate local MLflow archive. It does **not** claim Qlib FILE experiments are compatible or supported. Changing either tested runtime version requires revalidation. The optional source-Python reader is not embedded in the frozen Windows executable.

## Intentional API migration

```python
from invest.qlib_bridge import create_qlib_market_provider
from invest.pipeline import run_a_share_sma_backtest

provider = create_qlib_market_provider(provider_uri="/absolute/path/to/authorized/local/qlib-data")
result, summary = run_a_share_sma_backtest(
    "000001.SH", start_date="20250102", end_date="20250618",
    adjust="qlib", provider_instance=provider,
)
```

The previous `load_qlib_features(..., provider_uri=None)` could borrow or reinitialize global `D`, accept arbitrary expressions, or pick a hidden default dataset. That behavior is deliberately removed. Existing callers must provide an explicit absolute local directory and request direct `$open/$high/$low/$close/$volume` fields for explicit supported instruments. Qlib expressions and market aliases now fail clearly; use a separately managed Qlib process outside this reader for that broader API. The pure `to_qlib_frame` shape converter remains available with its existing behavior. The previously ignored `instrument_prefix` constructor option now raises if non-null rather than implying it works.

An injected `QlibMarketProvider(data_api)` remains available for tests/custom wiring, but its data API is caller-owned and is not covered by the factory's local-only/process-isolation promise. All response and native-basis validation still applies.

The separate DuckDB replay adapter currently does not accept `adjust="qlib"` or explicit-exchange symbols. Do not label Qlib native data qfq to bypass it; that composition needs its own explicit contract extension.

## Reproducible synthetic validation

```sh
python -m pip install -e '.[qlib,mlflow,test]'
python -m pytest tests/test_qlib_provider.py tests/test_qlib_contract.py tests/test_qlib_local.py -q
python -m examples.qlib_local_research
```

The example authors 120 fictional daily rows in the documented layout (calendar text, instrument manifest, little-endian float32 offset followed by feature values). The actual SDK reads those files; both pipelines match. Nothing is downloaded. Tests cover hostile inherited remote settings, no outbound/DNS attempts (including a denied urllib3 local IPv6 capability probe), disabled telemetry/no tracking client, existing parent Qlib configuration isolation, file corruption, changed source fingerprints, adjustment/symbol/date/OHLCV adversaries, and preservation of source metadata. Dedicated hosted CI installs actual SDKs on Ubuntu/Windows × Python 3.11/3.12, checks the no-Torch installation, executes the example, and reruns the existing real MLflow archive tests. Hosted evidence must be checked on the exact published head before claiming cross-platform success.

## Verified local result

- Coinstalled Linux/Python 3.12 full runtime suite before the diagnostic-only base rebase: **786 passed, 13 skipped, 348 passing subtests**, zero failures
- Final diagnostic-only rebase: **133 no-SDK Qlib/provenance/profile checks passed**; production runtime code is unchanged and source compilation/diff checks pass
- Actual packages: pyqlib 0.9.7, MLflow 3.16.1, Matplotlib 3.10.8, pandas 3.0.6, NumPy 2.5.3; `pip check` passes; no Torch installation
- Independent actual-SDK review verifies alternate requested field order, two distinct local dataset identities/values, explicit Shanghai selection, both pipeline metadata paths and qfq rejection
- Exact MIT license blob and runtime-pin regression passes; both Qlib and Matplotlib licenses retain byte-preserving Windows attributes
- A prior combined run exposed the inherited HTTP response-before-lock-release race. The corrected base fixes the response boundary without weakening the immediate-release assertion; the final full rerun passes
- Hosted cross-platform CI remains pending until exact-head verification after publication; local success alone is not a Windows claim

## Stack

The draft is stacked on corrected chart PR #55 (`36f54d76d2289a06c7c726658ddae77881f50598`), which includes PR #54 and its local MLflow archive. This inherits the independently fixed archive lock-wait budget and HTTP response-order correction rather than duplicating those changes. The Qlib slice changes no chart/MLflow implementation. Final combined source tests use pyqlib 0.9.7, MLflow 3.16.1 and Matplotlib 3.10.8 together. Historical Windows archive runs hit the existing 45-second worker deadline and 30-second lock wait. The final base adds synthetic phase diagnostics; its unchanged real SDK gate passes on both platforms. The profiler is not a demonstrated causal fix for the earlier intermittent timeouts. Qlib creates no MLflow tracking client, and its own native data-read timeout is independent. No main merge or deployment.

## Upstream provenance

Official [microsoft/qlib](https://github.com/microsoft/qlib): 49,078 stars checked 2026-09-30 20:22 UTC; MIT; active, last push 2026-09-22T05:57:23Z. Current source inspected at `be725493eb1a6bbb42bf11b37aa7669f59610ff1`; executed release v0.9.7 is `da920b7f954f48ab1bb64117c976710de198373e`. Exact MIT license retained at `third_party/qlib/LICENSE`, Git blob `9e841e7a26e4eb057b24511e7b92d42b257a80e5`.

The binary fixture and bridge are Invest-authored and execute the installed upstream SDK. No implementation source is copied or modified. Official references: [binary/file structure](https://qlib.readthedocs.io/en/latest/component/data.html#data-and-cache-file-structure), [initialization](https://qlib.readthedocs.io/en/latest/start/initialization.html), and [pinned feature storage implementation](https://github.com/microsoft/qlib/blob/da920b7f954f48ab1bb64117c976710de198373e/qlib/data/storage/file_storage.py).
