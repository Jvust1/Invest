# Saved-study PNG charts with Matplotlib

## Useful path

Install `python -m pip install -e '.[charts]'` in a source Python environment.
Run the existing Invest server, load a synthetic demo, and save a hypothesis study.
The results now include a case selector and **下载 PNG 图表**. The archive's
**选择图表** control reopens the same export for previously saved studies.
Failures remain in the JSON archive and cannot be turned into fabricated curves.

The same read-only endpoint is available to local clients:

`GET /api/workbench/study-chart?id=<saved study ID>&case=<zero-based result index>`

It reads the immutable Workspace record, validates its study/protocol/result
identities, and uses the real `FigureCanvasAgg` renderer. It does not retrieve
prices, repeat the backtest, open a frozen holdout or modify a saved document.
The existing host, origin and same-site guards apply. Responses are `image/png`,
downloadable attachments, `no-store`, with the existing security headers.

For a no-provider command-line example:

`python examples/saved_study_chart.py /tmp/invest-demo-study.png`

## Meaning of the image

- Strategy equity, same-period buy-and-hold equity, actual uninvested cash and
  the constant initial-cash baseline are normalized to initial capital = 100
- Strategy and benchmark drawdowns include the original capital before the first
  recorded session, so first-day entry costs are not lost
- Dates are actual observations, plotted at equal session spacing; no missing
  sessions or unobserved opening valuation are invented
- The saved engine's costs, trades and terminal mark remain unchanged. There is
  no assumed final liquidation or new fee calculation
- A visible synthetic-demo or unverified-declared-data label, exploratory scope,
  closed-holdout reminder, and shortened content identifiers travel with the PNG
- Full study, protocol, dataset, code, engine and curve identities, exact case
  descriptors/index and renderer version are stored in the PNG Description JSON
- A chart is a derivative of the JSON evidence, not independent verification of
  market data, data rights, strategy validity or prospective returns

Both `invest-exploratory-study-v1` and the separate sklearn rolling-study
`invest-walk-forward-study-v1` schema are recognized with exact mode pairing.
The result index is local to that protocol, not a globally comparable experiment.

## Bounds and failure behavior

The endpoint accepts only a saved study and one integer case index. It does not
accept a URL, path, dimensions, arbitrary plotting code, HTML, TeX, or styles.
Saved records are bounded to the existing 8 MiB contract; at most 27 cases and
10,000 points in the selected curve; only finite nonnegative monetary values
up to 1e16 and strict chronological ISO dates are accepted. Final return/equity
and drawdown metrics must agree with the saved curve. Unsupported or failed
records return an explicit validation error before importing Matplotlib.

One nonblocking render lock per process bounds concurrent work. A busy request
returns 409 and can be retried; missing/wrong optional SDK returns 503 with an
installation message. All paths preserve the saved study. The exact supported
runtime is Matplotlib 3.10.8; other versions require a reviewed compatibility
change rather than silently changing image semantics.

Rendering is a fixed 1200 × 840 PNG using `Figure` and `FigureCanvasAgg`, not
`pyplot` or a process-wide backend switch. Text is fixed/sanitized, with TeX and
math parsing disabled on every text artist; free-form case descriptors are
inert JSON metadata rather than rendered markup. No provider/network action is
part of chart generation. Font discovery/cache is local SDK behavior; the SDK
may need a writable Matplotlib cache directory. The tests use a temporary cache.
No claim of OS-level sandboxing or frozen Windows executable support is made.

## Upstream selection and license

Official repository: https://github.com/matplotlib/matplotlib

Verified on 2026-09-30 at 20:07 UTC: **23,310 stars**, not archived, last push
2026-09-30 03:22:33 UTC. Stars satisfy the user's threshold; mature CPU rendering,
stable object-oriented APIs and documented headless PNG support are the reasons
for selecting it. Existing catalogue metadata alone did not provide this path.

Release `v3.10.8` resolves through annotated tag
`4c67981258aebe692f58a27e760de9f417db9bae` to commit
`1392cbe3c79cdb93f9282747841d648770f60249`.

Matplotlib uses its own **PSF-based Matplotlib license**, not MIT or a guessed
GitHub SPDX label. Official policy: https://matplotlib.org/3.10.8/project/license.html
The exact release `LICENSE/LICENSE` text is retained in
`third_party/matplotlib/LICENSE` (Git blob
`ec51537db27dd4d9c9ed3cd39fd96485f3cfddea`), including copyright and prior-license
sections. No upstream code or fonts are modified or copied into Invest. The
official installed package retains its separate font/component notices.
Invest's changes are this wrapper, routing, UI, tests and documentation.
`LicenseRef-Matplotlib` documents the manual review; the general registry
safe-license allowlist is deliberately unchanged.

Primary API references:
- https://matplotlib.org/3.10.8/users/explain/figure/backends.html
- https://matplotlib.org/3.10.8/api/backend_agg_api.html
- https://matplotlib.org/3.10.8/gallery/user_interfaces/web_application_server_sgskip.html

## Verification boundaries

Deterministic tests exercise actual Agg PNG bytes/pixels/metadata, repeatability,
initial-capital drawdown, input tampering, unsupported/failed records, bad dates,
invalid money, record/point limits, SDK absence/version mismatch, lock recovery,
host/origin guards and real save → HTTP image → unchanged JSON behavior.
Four Node unit tests exercise the actual UI helper's original case indices,
literal labels, in-flight selection snapshot, failure recovery and all-failed
state. These are not browser-rendering evidence. A genuine PR49 rolling-window
study is also rendered in the combined local worktree, rather than relying only
on the standalone schema fixture.
The produced synthetic PNG is inspected visually as an image. Cloud browser
navigation to the loopback app is blocked in this environment, so this batch
does not claim browser-layout or user Windows desktop acceptance.
