# High-star finance integrations

The current integration batch uses permissive licenses and keeps each upstream
package isolated under third_party. Revisions are pinned in
invest/upstream_registry.json.

Integrated runtime adapters:

- **PyPortfolioOpt** (6,065 stars, MIT): minimum-variance allocation with a
  deterministic inverse-variance fallback when optional cvxpy solvers are absent.
- **Stockstats** (1,523 stars, BSD-3-Clause): RSI, MACD and Bollinger features.
- **Empyrical Reloaded** (124 stars, Apache-2.0): annualized return, volatility,
  drawdown, Sharpe and Sortino metrics.

The batch also vendors **ffn** (2,679 stars, MIT) as a research reference. Its
optional reporting stack requires additional plotting/reporting dependencies and
is not imported by the default pipeline.

Qlib (49,061 stars, MIT), Riskfolio-Lib (4,523 stars, BSD-3-Clause), and
pandas-market-calendars (1,001 stars, MIT) remain registered reference projects
until their heavier dependency and market-calendar contracts are integrated.
Star counts are GitHub snapshot metadata and may change over time.
