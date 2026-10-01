# Saved evaluation diagnostics with statsmodels

The archive row for a saved native research report now offers `下载收益统计诊断`.
The existing full-record validator checks its identity and all recorded input,
trial and evaluation arithmetic; the diagnostic statistics then consume only
`strategy_return` from the saved later-evaluation curve. No provider, optimizer,
model fit, new authoritative study, MLflow archive or financial transaction runs.

This activates a previously catalog-only upstream, rather than counting another
catalog entry as integration. Official statsmodels had **11,666 stars** when
checked on 2026-10-01 at 03:20 UTC. The runtime is pinned to **0.15.0**, official
release source `278ff9950636cdd4939b4055e339a8e681d79cab`. Its complete BSD-3-Clause
license and provenance are retained in `third_party/statsmodels/`; no upstream
implementation fork is copied. Python 3.10+ is supported by that release.

## Actual behavior

- The optional SDK executes `acorr_ljungbox`, `jarque_bera`, and `durbin_watson`
- One predetermined Ljung-Box lag is `min(10, n // 5)`, with `model_df=0`, no
  automatic lag search, period setting, fitting or user-supplied execution code
- All three receive mean-centered returns, scaled by their maximum absolute
  centered magnitude for numerical stability; this does not change their scale-
  invariant statistics. Durbin-Watson is explicitly labeled as centered
- Values must be finite, non-Boolean numbers, at most 10,000 observations and
  magnitude 1,000,000. Invalid data is rejected, never clipped or dropped
- Fewer than 30 observations produces `insufficient_observations`; an exact
  constant series produces `constant_series`. Both have `results: null`, never
  invented p-values. The 30-observation floor is a conservative reporting policy,
  not a statistical-validity guarantee
- Missing/wrong-version statsmodels returns a clear 503 with `record_saved: true`
  after a saved record has been located/validated. The rest of the app remains
  usable, and the dependency is imported only on a diagnostic request
- Nonblocking work/diagnostic locks bound concurrency and release before HTTP
  responses; failures leave the saved record unchanged

The JSON derivative binds original record ID, full-envelope hash (including
exact timestamp spelling), curve and return-series hashes, evaluation dates,
actual SDK version, source pin, fixed protocol and a digest of the whole output.
Original source/producer/timestamp values remain declarations. It does not claim
that content hashes authenticate the source or attest live process bytecode.
The archive button captures the original ID/filename, suppresses double clicks,
retains exact bounded response bytes and recovers after errors.

These are exploratory descriptive statistics. P-values are asymptotic and
unadjusted across diagnostics; small/dependent samples, strategy selection,
multiple research attempts and market/data biases are not calibrated away.
A large p-value does not establish normality, independence or profitable
performance. There is no alpha threshold, pass/fail strategy decision, candidate
ranking or holdout reopening. Native units stay unverified and separate from
cash/lot/T+1 execution.

## Reproduce

Install the optional dependency into the chosen test environment:

```sh
python -m pip install '.[diagnostics,test]'
python -m examples.saved_native_diagnostics tests/fixtures/native_research_v1_synthetic.json diagnostic-proof.json
python -m pytest tests/test_native_diagnostics.py -q
node --test tests/native_diagnostics_ui.test.cjs
python -m pip wheel --no-deps --wheel-dir dist .
python tools/native_restore_smoke.py dist --diagnostics
python tools/native_restore_smoke.py dist
```

Use Node 22 and a wheel directory containing exactly one Invest wheel. The CLI
uses the existing bounded native JSON reader and exclusive output creation.
The installed-wheel proof runs from a fresh target under Python `-I`, blocks all
other optional SDK imports and external Python networking, exercises the actual
served JavaScript download, and restores the raw JSON into a second empty
workbench to obtain identical diagnostic bytes. Node fetches are fixed to the
loopback server; this is not a general operating-system subprocess sandbox.
The default core-only proof now also forbids statsmodels import.

The dedicated Windows/Linux × Python 3.10/3.12 workflow runs actual SDK tests,
unchanged native-record/recovery regressions, CLI, current and older download
helpers, built-wheel diagnostics and core-only recovery. All earlier workflows
and assertions remain; two existing UI assertions now explicitly require the
new native diagnostic button while retaining JSON/PNG and excluding cash
controls. Exact-head CI is required before cross-platform acceptance.

## Evidence and remaining limits

Local focused diagnostic tests passed 37 cases (including exact license bytes) with the real SDK, including a
valid 21-observation record and constant record; all 50 old/new Node tests
passed. Independent runtime review reran the 36 Python and five new Node cases.
A broader combined native/recovery/chart run ended with exit 137 after partial
progress; its cause was not established and it is not a pass. No full-suite
local retry was used; hosted gates retain broad acceptance.

The parent #63 candidate has three retained MLflow fresh-initialization timeout
failures. This feature neither uses nor repairs that optional archive; budget,
storage and old assertions remain unchanged. The broad discovery inventory is
[separate evidence](discovery-invest-2026-10-01.json): 20 unique repositories
screened, 13 meet the star threshold, seven do not. Screening is not adoption;
only statsmodels is activated in this slice. No live financial dataset, paid
API, account, holding, broker or trading action was used.
