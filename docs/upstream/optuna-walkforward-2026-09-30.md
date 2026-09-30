# Optuna search fused into the provider research bundle

## Upstream identity

- Official upstream: https://github.com/optuna/optuna
- GitHub stars checked 2026-09-30: **14,865**
- Inspected revision: `5c8e50d85b77dd5a1fd7e26e21f63debc81d6016`
- MIT notice retained byte-for-byte in `third_party/optuna/LICENSE` (Git blob `6bbc1aa30fa6b9da220988c696b0750bd475c5db`)
- Reviewed source: `optuna/study/study.py:create_study` and `optuna/samplers/_tpe/sampler.py:TPESampler`
- Runtime verification: actual Optuna 5.0.0, not an injected fake; the existing optional `.[optuna]` extra is reused

The actual upstream TPESampler and in-memory Study now feed the existing
provider → normalized history → SMA research backtest → summary path. No
upstream fork is copied, no persistent database is selected, and no network
request is added by optimization.

## Complete offline example

```sh
python -m pip install -e '.[optuna]'
python examples/optimized_research_bundle.py
```

The example provider generates deterministic, clearly labeled synthetic data.
The output includes the complete trial list, selected parameters, source-history
fingerprint, actual Optuna version, seed, fold scores, search configuration and
later evaluation boundaries. A zero/negative result is retained as produced.

API:

```python
bundle = run_a_share_research_bundle(
    provider, symbol,
    optimization_trials=12,
    optimization_splits=3,
    training_fraction=0.7,
    optimization_seed=7,
)
```

Omitting optimization_trials preserves the original fixed-parameter bundle.
When enabled, the provider is fetched once. Only the earlier history prefix
enters parameter search; the later suffix is evaluated after parameters are
selected. The returned market frame contains the original full history, while
backtest and summary contain only the later evaluation. The split is based on
observation count, with decimal arithmetic avoiding one-row rounding errors.

## Validation and safeguards

- 1–100 trials, 2–5 chronological inner folds, at most 10,000 search observations
- Chronological, unique index; finite positive close prices; finite fees
- Search space is limited so every validation fold has full SMA warmup
- Default TPE seed is explicit; execution is sequential and in-memory
- An injected study must be fresh and maximize; prior unbound trials are rejected
- An externally injected study is not claimed to use the configured seed or runtime version
- All completed trial scores and parameters are retained, not only the winner
- Later evaluation requires at least 20 observations
- This is exploratory close-to-close signal research, not the A-share cash/lot/T+1 engine in invest.engine
- The signal state continues across the evaluation boundary. No artificial liquidation or new entry fee is invented at the split
- The protocol explicitly records frozen_holdout_opened=false; this is not a certified unseen holdout and repeated human tuning can still overfit

## Metric correction

Previously, Optuna sliced a full backtest but performance_summary read the
slice's final cumulative equity, which still included training returns. A
synthetic increasing-price fixture reported fold totals 9.34%, 15.21%, 21.07%
where evaluation-only compounded returns were 5.67%, 5.37%, 5.09%.

performance_summary now compounds only the supplied strategy_return rows and
includes the initial unit capital in drawdown. Sharpe uses annualized arithmetic
mean divided by annualized sample volatility (zero risk-free rate), instead of
CAGR divided by volatility. Zero volatility keeps the established zero result.
NaN/Infinity or returns below -100% fail closed. Historical outputs are not
rewritten; new OptimizationResult records the score_metric explicitly.

## Verification

- 20 focused tests: actual seeded Optuna determinism across 12 trials (including
  post-startup TPE suggestions), prefix isolation, later-price adversaries,
  manual slice-local return/Sharpe checks, input rejection and split rounding
- Full unittest: 571 cases, 13 optional skips, no failures/errors
- Full pytest: 577 passed, 13 skipped, 375 passing subtests, one inherited
  china_market_data capability-count failure reproduced on unchanged PR #48;
  assertion unchanged
- Example executes end-to-end and emits strict JSON from the real Optuna result
- Dedicated Optuna CI now installs the actual optional package and tests the
  optimizer, research bundle and pipeline across Linux/Windows Python 3.11/3.12
- Exact-head remote CI must be checked after publication

The branch is stacked on PR #48's application restoration. No real provider was
called during verification; no private holdings, paid API, broker connection,
real trade or frozen holdout observation occurred.
