# Third-party code

This repository incorporates source code from the following MIT-licensed projects.
The copied files remain under third_party/ and retain their upstream module
layout. Copyright and license notices are preserved in the corresponding
license files.

| Component | Upstream | Revision |
| --- | --- | --- |
| bt | https://github.com/pmorissette/bt | 4c4ad3621ed9d9b78b73610ae69e49746acd4169 |
| ta | https://github.com/bukosabino/ta | a890410710a6e483c9ba08da7f3dd5089e4b9dff |
| quantstats | https://github.com/ranaroussi/quantstats | 9ef4c6d0a4ffe7831f6ebba6a5824fd33a90c05a |

The vendored code is included for reproducible research. New project code in
invest/ provides a narrow, stable integration layer and does not modify the
upstream implementations.

## Runtime reuse: scikit-learn

The workbench study path executes the installed scikit-learn TimeSeriesSplit
implementation. Inspected release 1.8.0 is pinned to commit
`646da0f072a8afef6a980aa427a710311e67eb9d`; actual runtime versions are recorded
in saved study protocols. Its BSD-3-Clause copyright and redistribution notice
is retained unchanged at `third_party/scikit_learn/COPYING`. No scikit-learn
source fork is vendored. See `docs/upstream/sklearn-walkforward-2026-09-30.md`.

## Optional native Qlib data reader

The Invest-authored local data reader executes the official `pyqlib==0.9.7` SDK
(release commit `da920b7f954f48ab1bb64117c976710de198373e`). No Qlib implementation
source is copied or modified. The exact Microsoft MIT license and source/runtime
provenance are retained in `third_party/qlib/`; market-data rights remain separate.

## Durable native research composition

`invest/native_research.py` is Invest-authored persistence and bounded validation
glue for the existing Qlib / DuckDB / Optuna / scikit-learn runtime integrations.
It vendors no new upstream source. Existing exact revisions and license notices
remain unchanged. See `docs/upstream/native-research-record-2026-09-30.md` for the
source/unit contract and synthetic installed-SDK evidence.

## Runtime reuse: search, replay, local archive and charts

These integration modules are Invest-authored adapters that invoke the official
installed SDKs. They do not copy or modify those SDK implementations. Installing
an extra obtains the upstream distribution and its own bundled notices; this
repository additionally retains the reviewed license text and source identity.

| Runtime component | Reviewed upstream source | Retained notice | Actual pilot pin |
| --- | --- | --- | --- |
| Optuna | `optuna/optuna@5c8e50d85b77dd5a1fd7e26e21f63debc81d6016` | `third_party/optuna/LICENSE` (MIT) | 5.0.0 |
| DuckDB | `duckdb/duckdb@7fb68627fd223b7cd06d37b83059e571fa5f994a` | `third_party/duckdb/LICENSE` (MIT) | 1.5.6 |
| MLflow | `mlflow/mlflow@7faf28476bddcebb68ee8b08cdcba1bee7ad6109` | `third_party/mlflow/LICENSE.txt` (Apache-2.0) | 3.16.1 |
| Matplotlib | `matplotlib/matplotlib@1392cbe3c79cdb93f9282747841d648770f60249` | `third_party/matplotlib/LICENSE` (full PSF-based license) | 3.10.8 |

MLflow and Matplotlib source/license hashes are additionally recorded in their
`PROVENANCE.json` files. Optuna and DuckDB package requirements allow a range;
the reproduction commands pin the tested SDKs, and reports record actual runtime
versions. The native chart reuses the same Matplotlib integration and notices.
See [the coherent source handoff](docs/upstream/coherent-source-candidate-2026-10-01.md)
for actual input-to-output paths, constraints and exact acceptance evidence.

## Saved-return statistical diagnostics

`invest/native_diagnostics.py` invokes the official installed `statsmodels==0.15.0`
Ljung-Box, Jarque-Bera and Durbin-Watson APIs. The Invest adapter is original code;
no statsmodels implementation fork is vendored. Exact release source
`278ff9950636cdd4939b4055e339a8e681d79cab`, full BSD-3-Clause license bytes and
license hash are retained in `third_party/statsmodels/`. See
[diagnostic meaning and limits](docs/upstream/statsmodels-native-diagnostics-2026-10-01.md).
