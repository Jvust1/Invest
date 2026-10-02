# Coherent source candidate — 2026-10-01

This main-targeted draft assembles the reviewed research stack into one reviewable source tree. It does not merge, retarget, close or replace any existing PR. Its runtime is byte-for-byte the PR #62 runtime (`invest/` Git tree `7a2562f84abce2da99d008756acf4a8ec1ff0d54`); additions after #62 are acceptance tooling, source delivery, and this handoff. Exact terminal acceptance belongs to the new draft's exact head, not its parents.

## Useful complete paths

1. Explicit local Qlib binary source → real isolated `D.features` → exact-request DuckDB snapshot → close and reopen cache-only → actual seeded Optuna training-prefix search → later evaluation → durable native report with embedded inputs, full trial arithmetic and declared source identities → archive-row exact JSON and native Matplotlib PNG → atomic JSON recovery into an empty workbench → identical chart in the same renderer environment.
2. Explicitly synthetic cash-engine dataset → real scikit-learn rolling time splits → training-only candidate selection → nine later cash/fee scenarios → immutable study → opt-in local MLflow archive/retry → cash/equity/drawdown Matplotlib PNG → private backup → restore → same chart and fresh derivative archive.

The native chart is an evaluation-only unit-capital curve with fractional nonpositive drawdown. It is not a cash account or trade ledger. Qlib-native price and volume units remain unconverted and unverified; those records cannot enter cash-study chart validation. Recovered producer and timestamp values are preserved declarations, not authenticated provenance. All pilots use authored synthetic input. No brokerage, holdings, credentials, paid API, model training or frozen-holdout observation is involved.

## Exactly what is included

- Application/CI prerequisite #48 `1b2d415b2a18bb10f9f817d932bdd7084718af1e`, plus the #51 full-suite discovery correction
- Reviewed sklearn, Optuna, DuckDB, wheel, MLflow, cash-chart and Qlib slices #49–#56, assembled by #57 `cbd6508fc27e6a4da0c9a0a9bd3de901e9fdae43`
- Actual archive timeout phase reporting #58 `b79e8d12a82def150ce7479ce05f351ff0993b5a`
- Durable native record, exact byte downloads and startup diagnostics #59 `5a2ab7de29253af750326bf3d11b20da23001b17`
- Atomic native JSON recovery #61 `a2712ae4d626bb9e56d5db088b0198da4852d7c3`
- Native saved/restored PNG #62 `db94eeae24e647ed1a874b7f1225d93a41c4958e`, full tree `725c6cde8c82c32fb98e031a662b43dad9acebbc`

Diagnostic-only #60 `bd3c1e56ec3a553fc30709e03ec956e917c2a0d0` is excluded. Production SQLite journal policy, official migrations, 45-second archive deadline, tests and privacy protections are retained. No speculative PERSIST/WAL change is present.

Main was rechecked at `8d9e6aaa5ed8e2a71ef22430a45e0a77c4c24f8d`. The draft's first parent is that main commit; the incorporated #62 parent preserves lineage. Review the aggregate diff against main rather than treating all stacked PRs as independent changes to merge again. Existing PR bases and their failure evidence stay intact. This is source delivery only; it is not a new Windows executable release.

## Reproduce the combined installed-wheel pilot

Use Python 3.10–3.12, Node 22, and a fresh output directory containing exactly one Invest wheel:

```sh
python -m pip install '.[qlib,mlflow,charts,duckdb,optuna,test]' 'duckdb==1.5.6' 'optuna==5.0.0'
python -m pip check
python -m pytest tests -q
node --test tests/archive_controls_ui.test.cjs tests/study_charts_ui.test.cjs tests/native_charts_ui.test.cjs tests/record_download_ui.test.cjs
python -m pip wheel --no-deps --wheel-dir dist .
python tools/research_stack_smoke.py dist
python tools/native_restore_smoke.py dist
python tools/native_restore_smoke.py dist --charts
```

The strengthened first pilot uses the actual newly generated native record, not a golden replacement: 120 input rows, 12 Optuna trials, 84 training rows, 36 later rows. It saves and pixel-decodes the original native PNG, downloads exact JSON through the installed package's served JavaScript helper, restores that JSON in a fresh isolated Python process that forbids producer SDK imports, and compares PNG bytes with the original. Cash studies and local archive tests remain separate and unchanged. The historical golden-fixture compatibility gates are still independently run; their default mode forbids Matplotlib too.

Every production import is from a wheel installed into a temporary target under Python `-I`, outside the checkout. Source files are used only to author synthetic Qlib input and load the verification harness. The recovery process audits Python networking and permits only loopback; Node requests are fixed to that loopback base. These are bounded proofs, not an operating-system subprocess sandbox. Temporary outputs are removed after the proof; normal examples and workbench downloads retain their existing output behavior.

Native PNG byte identity is scoped to the same renderer environment, including Matplotlib version, rc settings, fonts and rasterizer. Metadata is content identity, not a cryptographic attestation of renderer bytecode. An independently changed rc setting can change pixels without changing declared renderer identity. The inherited SQLite row read can materialize data before the record-size decoder rejects it; this is not a general hostile-database sandbox.

## Reproducible source-only delivery

[Source-delivery instructions](../SOURCE_DELIVERY.md) describe the separate stdlib builder, trusted-Git verifier and exact-head hosted artifacts. The archive contains only admitted committed source/text, tests, synthetic fixtures, documentation and licenses/provenance; legacy roots containing compiled chunks, runtime databases, private/generated paths and untracked files are excluded. No executable is built or bundled.

The builder checks full immutable local Git commit/tree/blob identities, rejects links, unsafe/case-colliding paths and resource excess, and uses fixed metadata with uncompressed sorted ZIP members. Verification regenerates expected bytes from the independently chosen trusted commit; an archive's own manifest cannot authenticate itself. Existing destinations are never overwritten and failed extraction removes its newly created destination. This is not a secret scanner or a hostile concurrent-filesystem sandbox.

A dedicated Linux/Windows workflow checks out the actual PR head, builds twice, compares bytes, verifies/extracts, builds a wheel from the extracted tree, and proves core-only native JSON recovery outside both source trees before uploading the source ZIP and compact manifest/report. Dependency wheels are installed separately for verification and are not copied into the source archive. A source package does not establish Windows EXE or user-device acceptance. The final 63 focused boundary tests pass locally; independent review cleared the Windows-path, explicit Git-transport and write/close-failure cleanup fixes. A local aggregate extraction retained all 17 license/provenance files byte-exact and built a wheel with all 62 runtime files byte-equal; its isolated core recovery passed. Windows and final artifact identity remain exact-head hosted gates.

## Current upstream evidence

Official repository counts were read again on 2026-10-01 at 01:54:55 UTC. Stars satisfy the requested threshold, but the selection also considered actual API fit, licensing, offline boundaries and representative full-loop tests.

| Official upstream | Stars | Runtime/source identity | Retained license |
| --- | ---: | --- | --- |
| scikit-learn/scikit-learn | 67,435 | public TimeSeriesSplit; source `646da0f072a8afef6a980aa427a710311e67eb9d`; actual pilot 1.9.1 | BSD-3-Clause |
| optuna/optuna | 14,865 | 5.0.0; `5c8e50d85b77dd5a1fd7e26e21f63debc81d6016` | MIT |
| duckdb/duckdb | 41,837 | 1.5.6; `7fb68627fd223b7cd06d37b83059e571fa5f994a` | MIT |
| mlflow/mlflow | 28,205 | 3.16.1; `7faf28476bddcebb68ee8b08cdcba1bee7ad6109` | Apache-2.0 |
| matplotlib/matplotlib | 23,310 | 3.10.8; `1392cbe3c79cdb93f9282747841d648770f60249` | Full PSF-based Matplotlib license |
| microsoft/qlib | 49,081 | pyqlib 0.9.7; `da920b7f954f48ab1bb64117c976710de198373e` | MIT |

See `THIRD_PARTY.md`, `third_party/`, and the per-integration documents for exact notices, source links, license bytes and changes. GitHub's Matplotlib license classifier was null; the already retained full upstream license, not that classifier, is the evidence. The package supports a scikit-learn range and records the actual installed version; compatible wheels differ by Python version. No new framework is introduced by this handoff.

## Evidence and remaining limits

The enhanced combined pilot passed locally on Linux/Python 3.12 with all six actual SDKs, including current-record JSON restoration and PNG equality. Its bounded 44-line smoke-test diff received independent read-only review; no blocking findings, all previous assertions preserved. The production runtime is unchanged from #62. At #62 exact head `db94eeae24e647ed1a874b7f1225d93a41c4958e`, all 17 workflows passed: four full six-SDK jobs each passed 1,255 tests / 13 skips / 454 subtests plus installed wheels; six chart jobs and four SDK-free recovery jobs passed. See [full stack](https://github.com/Jvust1/Invest/actions/runs/36801988580), [charts](https://github.com/Jvust1/Invest/actions/runs/36801988498), and [SDK-free recovery](https://github.com/Jvust1/Invest/actions/runs/36801988541). Source packaging and final exact-head CI have their own acceptance and must not be inferred from parent runs.

Historical archive initialization failures remain unresolved: original #59 standalone Windows Python 3.11 timed out at `client_initialization` in run `36789951703`; #59 current-head six-SDK Windows Python 3.10 timed out at `schema_upgrade` in run `36794299116`. Those stages narrow the location, not the cause. Later #61 passed all 15 workflows, including four full-SDK jobs with 1,209 passed / 13 skipped / 454 subtests and four SDK-free recovery jobs. A later green run does not cure an intermittent limit. Failed optional archive responses truthfully retain the already saved study and permit retry.

The #60 diagnostic experiment did not reproduce a timeout. Both DELETE/FULL and PERSIST/FULL succeeded in 16 synthetic hosted cases, but one PERSIST run was slower than every corresponding DELETE sample. This does not establish causation, reliability or power-loss behavior, and no production storage change was adopted.

An earlier local full-suite process ended with exit 137; cause was not established. Its subsequent serial retry passed and both outcomes remain recorded in #59. Browser navigation was blocked in this environment: HTTP flows, served-JavaScript helper execution, SDK tests and PNG inspection do not establish full browser layout, Windows desktop/frozen-executable acceptance, physical filesystem locality, licensed real-market correctness, profitability or investment suitability.
