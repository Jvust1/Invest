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

## Optional native Qlib data reader

The Invest-authored local data reader executes the official `pyqlib==0.9.7` SDK
(release commit `da920b7f954f48ab1bb64117c976710de198373e`). No Qlib implementation
source is copied or modified. The exact Microsoft MIT license and source/runtime
provenance are retained in `third_party/qlib/`; market-data rights remain separate.
