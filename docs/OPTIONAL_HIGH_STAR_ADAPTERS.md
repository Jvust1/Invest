# Optional high-star adapters

Invest exposes optional integrations for quantitative research libraries:

- trading_sessions and exchange_sessions use pandas-market-calendars or exchange-calendars.
- riskfolio_weights, skfolio_weights, and optimize_weights provide portfolio optimization engines.
- Qlib, VN.py, and FinRL bridges connect their data layouts to Invest.
- fetch_ccxt_ohlcv normalizes CCXT exchange candles to Invest's indexed OHLCV schema.

Install only the capability you need with the extras in pyproject.toml. The base package remains usable without these optional dependencies.
