# Optional high-star adapters

Invest exposes optional integrations for quantitative research libraries:

- trading_sessions and exchange_sessions use pandas-market-calendars or exchange-calendars, then fall back to pandas business days.
- riskfolio_weights and skfolio_weights use minimum-risk portfolio optimizers, then fall back to inverse-variance weights.
- optimize_weights provides one stable dispatcher for skfolio, Riskfolio-Lib, PyPortfolioOpt, or the dependency-free inverse-variance engine.
- to_qlib_frame and load_qlib_features bridge OHLCV data to Microsoft Qlib's (instrument, datetime) layout and feature API.

Install only the capability you need with the extras in pyproject.toml. The base package and tests do not require these optional dependencies.
