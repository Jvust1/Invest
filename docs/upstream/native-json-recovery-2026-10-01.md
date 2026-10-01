# Explicit native JSON recovery — 2026-10-01

## Recover a saved export

From the source checkout, provide both the exported file and destination workbench:

```sh
python -m examples.native_research_record restore /path/to/native-research.json \
  --workspace /path/to/recovered-workbench
python -m invest --data-dir /path/to/recovered-workbench --open
```

Select “原生价格探索研究” in the existing archive list to download the recovered
record. Validate that download independently:

```sh
python -m examples.native_research_record validate /path/to/downloaded-native.json
```

The installed-package Python API is:

```python
from invest.native_research import restore_native_json

# raw_json is bounded UTF-8 JSON text already read by the caller.
record = restore_native_json(raw_json, "/path/to/recovered-workbench/state.sqlite")
```

The API's destination is the explicit SQLite file, while CLI `--workspace` is its
containing directory. Both require the complete `native_research` envelope with
`id`, `kind`, `recorded_at` and `payload`. Cash studies and arbitrary JSON cannot
be restored through this API. There is no HTTP import endpoint, automatic import,
overwrite switch, extra SDK or dependency. The CLI is a source-checkout example;
the production API ships in the wheel.

## Validation and immutable storage

The CLI opens the input in binary mode, reads at most `MAX_BYTES + 1` bytes in one
bounded read, rejects anything larger than 8 MiB, and decodes strict UTF-8. It does
not rely on an earlier file-size check that can race a growing file. The API then
uses the existing strict JSON parser, bounded shape checks and full native-record
arithmetic replay **before opening or creating the destination**. Malformed JSON,
duplicate keys, excessive depth/size, non-finite numbers, unsupported envelopes,
identity mismatches and invalid arithmetic produce no destination writes.

After validation, a single SQLite `BEGIN IMMEDIATE` transaction checks the existing
ID and inserts the record if absent. An identical repeat returns the same record
without adding a row. Comparison uses canonical JSON for the **entire envelope**,
so JSON number types and exact timestamp strings are not conflated by ordinary
Python equality. Whitespace and object key order in the input file are not content
identity; original numeric values/types, ID, payload and declaration strings remain
unchanged. Existing immutable update/delete triggers remain in force.

Before fetching an existing envelope, SQL returns only bounded header facts
(native-kind match, payload/timestamp types and byte lengths). Oversized or
foreign rows are rejected without materializing their payloads in Python. After
an insert, the same bounded lookup verifies the saved envelope before commit;
an unexpected trigger cannot silently ignore, remove or substitute the record
while the API reports success.

The content ID excludes `recorded_at`. A different timestamp for an existing ID,
including another spelling of the same instant, is therefore an explicit conflict;
recovery never silently retains one timestamp while reporting another. Any other
conflicting existing envelope fails too. Concurrent imports serialize their check
and insert. Insert or commit failures roll back the transaction, release its lock
and leave no partially imported record. A validated import whose later storage
operation fails may leave an initialized empty workbench; invalid input never
creates one.

## Declarations, privacy and limits

The exported producer manifest, runtime versions and timestamp are preserved as
**unverified declarations**. Validation proves bounded content identity and the
recorded arithmetic, not who produced it, when it was produced, source-data
authenticity, market-data rights or profitability. Recovery does not inspect the
current source manifest, probe installed SDK versions, invoke providers or rerun
optimization. No original Qlib files, DuckDB cache or optional SDK is needed.

The JSON and restored `state.sqlite` contain the embedded input rows and exact
caller-declared `source_id`, which may themselves be private. Review them before
sharing; do not put credentials or secrets in declarations. Source/destination
paths are not added to the saved envelope. Recovery does not contact a provider,
broker or account and does not execute trades. Native Qlib price units remain
unverified and are not promoted to the A-share cash/lot/T+1 engine.

## Verification scope

`tests/test_native_json_restore.py` uses the existing authored synthetic fixture
and forbids optional SDK imports, provider calls, producer discovery and runtime
version probes during every case. It covers:

- Empty workbench → restore → close/reopen → archive list → raw HTTP download →
  actual served JavaScript Blob export → offline full-record replay, with exact
  HTTP/Blob bytes and canonical numeric identity retained
- Original producer/timestamp retention, identical retries with one row, changed
  timestamp conflicts, and foreign conflicting rows that cannot be overwritten
- Malformed/duplicate/oversized/deep JSON, cash schemas, bad arithmetic/identity,
  invalid UTF-8, and bounded CLI reads without a stat/read race
- Forced insert and commit failures, rollback of an earlier trigger write, retry
  after failure, ignored/substituted/deleted inserts, and deterministic concurrent identical/conflicting imports with
  one transaction held open while the competing connection starts

Run the focused source acceptance and adjacent regressions serially:

```sh
python -m pytest -q tests/test_native_json_restore.py tests/test_native_research.py \
  tests/test_native_research_budget.py tests/test_record_download_http.py \
  tests/test_growth_http.py
node --test tests/record_download_ui.test.cjs
```

This recovery slice is independent of the actual MLflow SDK. At its inherited
PR #59 head `5a2ab7de29253af750326bf3d11b20da23001b17`, the aggregate remains
**16/17 green**: a Windows Python 3.10 fresh MLflow initialization timed out with
last phase `schema_upgrade` before the adversarial case ran. That failed gate is
unresolved. The phase is a diagnostic marker, not a proven migration root cause.
The existing 45-second worker budget, 30-second writer-lock budget, SQLite storage
behavior, aggregate checks and assertions are unchanged. Passing native recovery
checks must not be presented as aggregate six-SDK or MLflow acceptance. Hosted
results apply only to their exact tested candidate head. Browser layout, Windows
desktop/frozen executables and real-market correctness remain unclaimed.

## Installed-package acceptance

`tools/native_restore_smoke.py dist` installs the built wheel into a fresh target
outside the checkout, then starts Python with `-I`. It forbids imports of Qlib,
DuckDB, Optuna, MLflow and Matplotlib before importing the installed package.
Using the historical synthetic JSON fixture, it restores an empty workspace,
checks repeat/conflict behavior, reopens the record, lists it over real loopback
HTTP and uses the installed workbench JavaScript to export the exact served
bytes. The downloaded record is fully revalidated offline. Producer/timestamp
values are preserved as declarations. This is a helper/HTTP proof, not browser
layout or device acceptance.

Python's audit hook rejects external socket operations; the small Node helper
uses its fixed loopback base URL. This is not a general subprocess network
sandbox. The smoke report distinguishes those scopes. The dedicated
`.github/workflows/native-json-recovery.yml` matrix uses core dependencies only,
asserts optional producer SDKs are absent, and runs Ubuntu/Windows with Python
3.10/3.12. Existing aggregate and MLflow gates are unchanged.

Local final source evidence: 322 focused/adjacent Python tests (including 61
recovery cases), 12 JavaScript helper tests, and the guarded installed-wheel
loop passed. All 61 packaged runtime files matched source byte-for-byte. The
local interpreter also had optional SDKs installed, but their imports were
blocked before package import; the hosted matrix additionally checks absence.
Hosted results must be checked on the published exact head.
