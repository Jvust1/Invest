# Workbench walk-forward studies with scikit-learn

## Upstream and reuse

- Official project: https://github.com/scikit-learn/scikit-learn
- GitHub stars checked 2026-09-30: **67,434**; maintained, not archived
- Inspected release: **1.8.0**, commit `646da0f072a8afef6a980aa427a710311e67eb9d`
- Source: [TimeSeriesSplit](https://github.com/scikit-learn/scikit-learn/blob/646da0f072a8afef6a980aa427a710311e67eb9d/sklearn/model_selection/_split.py)
- License: BSD-3-Clause; unchanged upstream notice in `third_party/scikit_learn/COPYING`
- Integration: the real installed TimeSeriesSplit is called at runtime, not a
  copied replacement or catalogue-only record. The existing scikit-learn>=1.1
  dependency is reused; every saved protocol records the actual runtime version.

## Use

Load a dataset, open **假设实验室**, choose **滚动验证**, set the gap,
acknowledge the illustrative costs, and run. The default remains the existing
three-slice comparison without candidate selection.

The existing `POST /api/workbench/study` accepts this specification, within the
ordinary `dataset_id`/`specification` wrapper and Host/Origin/CSRF protections:

```json
{"symbol":"600000.SH","cost_model_acknowledged":true,"walk_forward":{"n_splits":3,"gap":5}}
```

The Python entry is `invest.experiments.run_study(dataset, specification)`.
Use `invest.data.demo_dataset()` for a complete synthetic offline example.
No provider is called. Workbench HTTP restoration is a dependency on PR #48;
this feature does not duplicate its package/export/route/locking fixes.

## Contract

1. Existing identity, symbol, candidates, cash and cost-acknowledgment gates run
   first. Unknown specification/configuration keys are rejected.
2. The longest declared SMA determines common warmup. TimeSeriesSplit operates
   on ordered sessions after warmup, not equal calendar durations. Each train
   and test window contains at least ten sessions.
3. Per fold/cost, run every declared candidate on the earlier training window.
   Select maximum training excess over the same-window buy-and-hold benchmark;
   exact ties preserve declared candidate order. Only then run the later test.
4. Any failed training candidate blocks selection for that fold/cost. Retain
   every training result and failure; never silently drop failed candidates.
5. Successful training/test runs have independent arithmetic replay. All their
   parameters, curves, failures and metrics persist in the ordinary immutable
   study document and full JSON export.
6. Each fold resets cash. Do not concatenate these independent account curves
   into one continuous investment return. Later folds can train on earlier
   evaluation sessions as normal in rolling historical simulation.
7. Gap sessions are excluded from scoring. Their already-known prices may warm
   up the next signal. This is not purged-label CV or a real holdout gate.
8. Bounded settings: n_splits 2–5, gap 0–60 sessions, optional test_size and
   max_train_size 10–2500; at most 2500 post-warmup sessions, 3 candidates and
   3 cost scenarios (at most 60 engine calls). The existing 8 MiB document
   limit still applies; oversized results are rejected, never truncated.

The protocol is EXPLORATORY_WALK_FORWARD with frozen_holdout_opened=false.
Repeated human inspection can still overfit. These results do not establish
market truth, data licensing, unseen holdout validity, forward-paper evidence,
profitability, or actual trading authority.

## Pilot verification

- 11 new deterministic tests pass on the main-based feature slice
- Combined with PR #48 `1b2d415b2a18bb10f9f817d932bdd7084718af1e`:
  569 unittest cases, 13 optional-dependency skips, no failures/errors
- Real loopback HTTP: study → save → download → idempotent rerun; invalid
  configuration returns an error and releases the lock without a new record
- Causal adversary: changes to all later prices do not change earlier
  training metrics or candidate selection
- Direct parity with upstream TimeSeriesSplit for gaps/rolling windows
- Maximum-budget synthetic probe: 2500 post-warmup sessions, 3 candidates,
  5 folds / 60 engine calls, 15/15 evaluations replayed; 7,048,280-byte report
- Full pytest: 575 passed / 13 skipped / 1 inherited failure, plus 365 passing
  subtests. The failing china_market_data capability-count assertion was also
  reproduced on untouched PR #48 head (1 failed / 6 passed in test_upstreams).
  No assertion is weakened or disabled
- JavaScript syntax check passes
- Visual browser QA is **unverified**: cloud browser denied loopback with
  net::ERR_BLOCKED_BY_CLIENT; CLI browser could not create its socket directory
- Main 8d9e6aa alone retains unrelated defects (533 tests, 2 failures / 8 import
  errors / 13 skips with this slice). PR #48 repairs the prerequisites

Exact published-head CI must be checked separately. A successful temporary
combined checkout does not establish remote CI success or real strategy merit.
