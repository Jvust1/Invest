# Saved native-research PNG reports — 2026-10-01

## Useful path

A saved or explicitly JSON-restored `native_research` record now has a separate
**下载原生研究 PNG** button in the workbench archive's **原生价格探索研究** list.
Install the existing optional `charts` extra (`matplotlib==3.10.8`) to render it:

```sh
python -m pip install -e '.[charts]'
python -m examples.native_research_record restore /path/to/native-research.json \
  --workspace /path/to/recovered-workbench
python -m invest --data-dir /path/to/recovered-workbench --open
```

Recovery itself still requires no optional SDK. The chart is an optional view of
that immutable record. The installed Python API is
`invest.native_charts.render_native_png(record)`, returning PNG bytes. A
source-checkout example renders a bounded existing JSON export directly:

```sh
python -m examples.saved_native_chart tests/fixtures/native_research_v1_synthetic.json \
  /tmp/invest-native-synthetic.png
```

This example uses the explicitly authored historical synthetic fixture, does not
produce new research, and refuses to overwrite an output. For a local client:

`GET /api/workbench/native-chart?id=<saved native record ID>`

This slice adds no research-run, upload or JSON-import HTTP endpoint; the chart
endpoint only validates and renders an existing record. The existing local host,
origin and same-site restrictions apply. Responses use the
server's attachment, `no-store` and security headers. Cash-study chart validators,
routes and behavior are unchanged; native schemas remain invalid there.

## Meaning and identity

The fixed 1200 × 900 PNG contains only the stored later evaluation observations:

- Unit capital compounded from later returns, with the constant initial baseline
  **1**; earlier training observations are never included in the plotted series
- Evaluation drawdown as a **nonpositive fraction**, with the running peak
  initialized at one before the first evaluation observation. A first-observation
  loss is retained. The sign matches the cash chart's nonpositive series, but
  values stay as fractions rather than percentages; this is not the cash engine's
  positive maximum-drawdown summary magnitude
- Equal spacing for actual observed sessions; no missing sessions or artificial
  opening observations are invented
- Visible declared symbol, selected MA fast/slow and native signal fee in bps
- Visible synthetic/user-supplied **declaration** labels, unverified native price
  and volume units, exploratory/non-cash scope, unopened frozen holdout, and
  source/producer/timestamp declarations explicitly distinguished from verification

The PNG `Description` is canonical JSON with chart schema
`invest-native-research-chart-v1`. It binds the content `record_id`, the full
exported envelope `record_sha256` (including the exact `recorded_at` spelling),
`record_schema`, `record_kind`, and `curve_sha256`. It retains the exact original
source snapshot, producer manifest/runtime declarations, optimization and split
claims, conventions and limitations. `renderer` identifies the pinned Matplotlib
version, actual `FigureCanvasAgg` backend, style schema and fixed dimensions;
`render_id` hashes all the other description fields. This renderer/style identity
is not a signature or live-bytecode attestation.

The same record under the same renderer/environment produces byte-identical PNGs,
including after standalone JSON recovery into another workbench. Environment
includes inherited Matplotlib configuration, fonts and rasterizer libraries;
changing these or the OS is not promised to preserve identical pixels. Changing
any declaration changes the corresponding identity even when the visible curve
is unchanged. No original JSON is rewritten or current producer identity stamped
onto the old record.

The source ID and producer declarations are inert metadata, never plotted as
arbitrary text, markup or TeX. They may contain private information supplied by the
caller. **Review both JSON and PNG metadata before sharing**. No paths, credentials,
accounts, holdings or live market calls are collected by this feature.

## Validation, resource bounds and retry behavior

`validate_native_record` fully checks the envelope, embedded original rows,
source hashes, training/evaluation split, all recorded trial arithmetic, selected
maximum, later suffix and summary before optional renderer discovery/import.
This deterministic arithmetic replay is not an optimizer/provider/model/research
rerun; it requires no Qlib, DuckDB, Optuna or MLflow SDK. It does not use the
A-share cash, lot-size or T+1 execution engine.

The inherited Workspace loader materializes SQLite text before its native decode
size check; this slice does not redesign foreign-database loading. The existing
native contract bounds the full record to 8 MiB, source/evaluation
rows to 10,000, recorded trials to 100, folds to 2–5, and JSON shape/text depth.
Chart unit-capital and drawdown magnitudes must additionally be finite with
absolute value at most 1e12. Extreme values are rejected, never clipped. Signed
values accepted by the native validator remain signed in the display; the v1
native arithmetic itself rejects returns below -1. These plot bounds do not
change the saved record or relax the native validator.

Native validation and rendering share the existing nonblocking renderer lock;
the HTTP path also holds the study/validation lock. All acquired locks are
released before a success, missing-renderer or render-busy response. A busy
request returns 409; absent/wrong/broken Matplotlib returns an explicit 503;
invalid records return validation errors. Saved records remain unchanged, so
retry after installing the exact optional renderer or an interrupted request
uses the same identity. There is no automatic dependency installation.

The browser control captures its record ID and filename when created, rejects
parallel clicks, and re-enables after errors or interruption. A native-specific
response path requires `image/png`, bounds streamed bytes to 8 MiB, and checks
fixed dimensions, PNG structure/chunk CRCs and a complete ending before any
download. This is not a general image decoder or proof of pixel validity. Actual
Agg output is separately decoded and pixel-checked by Python tests. Existing
cash-study and raw JSON download helpers retain their contracts.

Rendering uses real Agg `Figure`/`FigureCanvasAgg`, not pyplot, process-wide
backend changes or caller-selected styles. TeX and math parsing are disabled for
every text artist, and DejaVu Sans is explicit. Local font/cache discovery is SDK
behavior; CI sets a writable `MPLCONFIGDIR`.

## Upstream reuse and evidence boundaries

This slice reuses the already selected and pinned Matplotlib 3.10.8 integration;
no new library or SDK was added. The official repository still had **23,310 stars**
on 2026-10-01 at 01:12 UTC. See the [existing Matplotlib integration record](matplotlib-study-charts-2026-09-30.md)
for the exact upstream release/tag/commit, retained PSF-based Matplotlib license,
notices and primary documentation. GitHub's null license classifier is not used
as a license determination. The safe-license allowlist is unchanged.

Focused tests cover complete-record rejection, foreign/cash schemas, tampered
source/arithmetic, payload and plot-value limits, SDK absence/wrong version,
lock contention/release, no optional research SDKs or provider/search/cash-engine
calls, exact PNG metadata/pixels, repeat bytes and standalone JSON restoration.
Real loopback HTTP and the actual served JavaScript helper exercise the download;
Node tests cover captured identity, double clicks, interrupted/bad responses,
renderer recovery and retry. The chart workflow also builds a wheel and runs
`tools/native_restore_smoke.py dist --charts`; its default mode continues to
forbid every optional SDK. Existing aggregate and core-only recovery gates stay
intact.

This slice does **not** resolve the inherited intermittent Windows actual-MLflow
fresh initialization timeout with last phase `schema_upgrade`. The 45-second
worker and 30-second writer-lock budgets, SQLite behavior, assertions and gates
are unchanged. `study_saved` remains true in those failures. Synthetic journal
comparison results are not a causal storage fix. Passing native chart checks is
not aggregate six-SDK/MLflow acceptance. Browser layout, Windows desktop/frozen
executables, real-market data and strategy validity remain unclaimed.

Local source acceptance on Python 3.12 with actual Matplotlib 3.10.8: **419 tests
passed** across native/cash charts, native validation/budgets/recovery, raw record
HTTP export, growth HTTP and upstream provenance (40.73 seconds). The native
chart file contributes 46 cases. **45 Node helper tests passed**, including 25
native cases and all 20 existing archive/cash/raw-JSON cases unchanged. Script
syntax, Python compilation and workflow YAML parsing also passed. The synthetic
PNG was visually inspected at 1200 × 900; its SHA-256 is
`353d644b622aef5d66192c977c4c59b81a5bf0722d4fd0707c947fe75e4dde8d` in this renderer
environment. These focused local results are not hosted or full aggregate results.


Final local installed-wheel acceptance passed in both modes: default recovery
forbids all relevant optional SDK imports; explicit `--charts` permits only the
pinned Matplotlib renderer. The chart mode decodes real pixels, verifies original
record/curve/declaration metadata, executes the installed served-JavaScript PNG
helper, repeats identical bytes, restores the actual JSON export into a second
empty workspace, and obtains the same PNG. All 62 packaged runtime files matched
the committed production source byte-for-byte. The checks do not claim a general
subprocess network sandbox or cross-environment raster identity.

The corrected base #61 head `a2712ae4d626bb9e56d5db088b0198da4852d7c3` subsequently
finished all 15 exact-head workflows successfully, including the SDK-free and
full six-SDK installed-wheel matrices. That later passing run does not erase the
historical MLflow initialization failures or prove they are fixed. This chart
revision still requires its own exact-head hosted acceptance.
