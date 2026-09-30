# Optional high-star adapters

Invest exposes optional integrations for quantitative research libraries:

- trading_sessions and exchange_sessions use pandas-market-calendars or exchange-calendars, then fall back to pandas business days.
- riskfolio_weights, skfolio_weights, and optimize_weights provide portfolio optimization engines with inverse-variance fallback.
- to_qlib_frame and load_qlib_features bridge OHLCV data to Qlib.
- to_vnpy_records and to_vnpy_bars bridge OHLCV data to VN.py bar objects.
- to_finrl_frame and finrl_observation bridge OHLCV data to FinRL's date/tic feature schema and observation matrices.

Install only the capability you need with the extras in pyproject.toml. The base package remains usable without FinRL or VN.py.
