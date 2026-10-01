# Durable native research record — 2026-09-30

## Useful integration boundary

The existing Qlib → exact DuckDB replay → training-prefix Optuna search → later
SMA evaluation can now finish as an immutable `native_research` document in the
existing Workspace `state.sqlite`. The record contains the input rows needed to
replay its arithmetic after the original Qlib files and DuckDB cache are absent.
It uses the existing private backup, archive list and JSON download. No new SDK,
provider, service, execution endpoint or cash-engine format is introduced.

The source-Python entry point is `invest.native_research.run_and_save_native_research`.
It accepts only an explicit cache-only `DuckDBReplayProvider`, reads one exact
native request, captures the producer source/runtime declaration during execution,
runs the existing pipeline and saves immediately. It does not add today's source
identity to an old bundle. A missing/corrupt cache fails without provider fallback.

## Run an actual synthetic SDK pilot

From the source checkout, install the same extras used by the existing integrated
research matrix, then choose a destination directory that does not yet exist:

```sh
python -m pip install '.[qlib,duckdb,optuna]' 'duckdb==1.5.6' 'optuna==5.0.0'
python -m examples.native_research_record synthetic-pilot /tmp/invest-native-demo
python -m examples.native_research_record validate /tmp/invest-native-demo/native-research.json
python -m invest --data-dir /tmp/invest-native-demo --open
```

The pilot writes authored fictional Qlib binary fixtures, reads them using the
actual isolated Qlib SDK, explicitly refreshes a DuckDB snapshot, closes it, then
runs **only cache replay** through seeded Optuna and the durable-record producer.
It saves `state.sqlite` and `native-research.json`, reopens the document and fully
validates it. This output is retained in the chosen directory, unlike the temporary
installed-wheel CI pilot. The workbench archive selector “原生价格探索研究” lists it
and downloads the full verified JSON as the exact HTTP response bytes. JavaScript
does not parse and stringify saved exports: doing so would turn Python
`1.0` into `1` and round large integers, breaking content identity. Export fetches
the persisted record by a captured ID, including for a newly saved study, so
transient tracking fields and later UI selections cannot change the file. Native
records have no cash-chart or MLflow archive button; those endpoints continue accepting only existing cash studies.

For an already populated native cache, use the exact recorded source declaration,
symbol spelling and inclusive YYYYMMDD request dates:

```sh
python -m examples.native_research_record run \
  --workspace /path/to/local-workspace --cache /path/to/native.duckdb \
  --source-id 'declared-source-v1' --symbol 000001.SH \
  --start 20250102 --end 20250618 --input-role user_supplied_unverified --trials 12
```

These local path arguments are not serialized. This command does not refresh the
cache or download input. `input_role` is an explicit caller declaration, not a
finding that data are authentic, licensed or synthetic. The caller's exact
`source_id` is part of the request identity and is preserved, not sanitized.
Exports and private backups **contain the embedded input data and that declaration**;
source declarations can themselves contain private information. Do not put secrets
in them. No arbitrary DataFrame attrs, feature values, study objects, cache paths
or provider paths are automatically collected.

## Saved evidence and validation

Schema `invest-native-research-v1` stores:

- Exact request and snapshot IDs, original columns/order, native Qlib selected-file
  fingerprint, instrument/request-date binding, basis, unverified units and reader
  runtime declarations
- Up to 10,000 original normalized OHLCV rows with exact daily dates; supported
  optional history columns remain in their original order
- Full earlier-training/later-evaluation boundary, fraction and counts
- Selected SMA windows, fee, 2–5 folds, all 1–100 completed trial scores/fold scores,
  training fingerprint, actual owned Optuna version/seed or explicit unknown
  injected-study provenance
- Evaluation-only close, signal, asset return, turnover, strategy return and
  normalized equity; all summary values and explicit metric conventions
- Execution-time source manifest and Python/package runtime declarations, plus
  fixed exploratory/native-unit/no-frozen-holdout limitations

The validator recomputes the embedded source digest against the snapshot. Copied
provenance attrs do not make changed input genuine: a feature transform that alters,
removes or duplicates original source columns is rejected. Derived feature columns
are not archived. The whole pipeline's trading math continues to use original close.

Validation replays the entire source signal, then takes the exact later suffix.
It does not restart the position, invent another entry cost or force liquidation
at the split. Evaluation equity compounds only later returns from **unit capital**;
maximum drawdown is a **nonpositive fraction** against the peak including initial
capital. It is not the cash-study chart's money or drawdown convention. Returns are
annualized over 252 observations; volatility uses sample `ddof=1`; Sharpe is the
arithmetic annualized mean divided by volatility with zero risk-free return.

Each recorded candidate is rescored on the earlier prefix using the existing
`_walkforward_score` / scikit-learn TimeSeriesSplit implementation. Selection must
match an evaluated maximum. This proves recorded candidate arithmetic, not that
an external sampler generated the declared sequence, that every possible candidate
was tested, or that a strategy is optimal/profitable. Injected studies retain null
optimizer version and seed rather than being relabeled Optuna. Timestamp resolution
is normalized to nanoseconds before training hashing so pandas defaults do not
change source identity across supported Python environments. Numeric replay uses
relative `1e-10`, absolute `1e-12` tolerances for runtime floating-point differences.

All schemas have exact keys; values must be finite plain JSON. Shape/depth/node
limits run before reconstruction. An incremental exact canonical UTF-8 byte budget
counts JSON escaping and punctuation without first serializing an oversized object,
in addition to 8 MiB, row, trial and fold limits. Restored raw JSON is size-checked
before parsing and rejects duplicate keys, excessive nesting and unbounded numbers.
`Workspace.put('native_research', ...)` validates before writing. Explicit JSON
validation and HTTP document download replay all arithmetic without importing
Qlib, DuckDB or Optuna or reading original files. Archive listing verifies only
content-addressed identity, labels that limited check, and retains one payload at
a time; it does not run 100 full trial suites. Native downloads share the bounded
research-operation lock and return a retryable busy response if occupied.

Private backup includes the immutable record in `state.sqlite`, including embedded
rows. It does not include `native.duckdb`, original Qlib files or the derivative
MLflow database. Restored source identity is a historical declaration: validation
checks that it is internally consistent, never replaces it with the current code
or installed SDK versions. SHA-256/build declarations are not signatures, live
bytecode attestations, data-rights evidence or authenticity proofs. Qlib's disabled
network/tracking metadata describe its source reader, not every computation.

## Reproduction and evidence

```sh
python -m pytest -q tests/test_native_research.py tests/test_optuna_walkforward.py tests/test_research_pipeline.py
python -m pip wheel --no-deps --wheel-dir dist .
python tools/research_stack_smoke.py dist
```

The installed-wheel proof also requires Node 22 or later for the actual JavaScript byte
export test (the hosted matrix pins Node 22); the application itself still uses the browser and Python server.

The installed-wheel pilot now validates/save/deduplicates the actual native record,
serves its JSON/list, passes its exact HTTP bytes through the installed JavaScript
Blob helper and back into Python identity validation, restores its private backup and revalidates embedded input and
trial arithmetic without provider or optimizer calls, alongside the unchanged cash
study, MLflow and Matplotlib paths. The existing Ubuntu/Windows × Python 3.10/3.12
matrix also revalidates the same authored synthetic golden report in
`tests/fixtures/native_research_v1_synthetic.json`; its producer manifest is the
historical version captured when it was generated, not the current checkout.

Independent prewarmed-memory check: listing 2 versus 20 approximately 3 MiB
identity-only foreign records peaked at 12,863,045 and 12,884,430 traced bytes,
respectively, with each returned summary below 1 KiB. Full-payload retention no
longer scales with the list count; this is a targeted local probe, not a universal
latency or process-memory guarantee.

Final local candidate on the green timeout-phase base: **1,138 passed, 13 explicit
optional skips, 454 subtests passed**, plus **20 JavaScript helper tests**, the
actual HTTP → served JavaScript Blob → Python identity regression, dependency
consistency and rebuilt six-SDK installed-wheel proof. The 61 packaged runtime
files were compared byte-for-byte with the final worktree. One preceding aggregate
attempt ended with SIGKILL/exit 137 around 88%, without an assertion failure shown;
its cause is unverified and that attempt is not counted as a pass. The existing
retry then completed successfully. Exact local evidence and limits are retained in
[the verification record](validation/20260930_native_research_record.json).
Hosted CI still must be checked for the exact published candidate head.

Initial actual local pilot: Qlib 0.9.7, DuckDB 1.5.6, Optuna 5.0.0, 120 rows,
12 trials, 84 training / 36 evaluation rows, durable save/reopen and independent
full-record validation passed. Further focused/full-suite/hosted results are
recorded on the candidate's exact reviewed head; this document does not assume
that unpublished edits or pending CI have passed. Only synthetic data are used.
Browser layout, Windows desktop/frozen-executable behavior, real-market correctness,
data rights, future performance and frozen-holdout acceptance remain unclaimed.

## Upstream provenance

This is Invest-authored persistence/validation glue around already integrated
mature SDKs. It copies no additional upstream implementation. The exact upstream
source revisions and unchanged licenses remain under `third_party/` and in the
[integrated research provenance](research-stack-2026-09-30.md). Qlib performs local
feature reads, DuckDB snapshot SQL/storage, Optuna owned TPE search, and scikit-learn
chronological fold splitting. The durable document now makes their combined
research output reusable through the existing application and backup contract.
