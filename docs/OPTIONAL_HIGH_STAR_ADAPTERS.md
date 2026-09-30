# Optional high-star adapters

Invest exposes small integration points for three widely used quantitative projects:

- trading_sessions uses pandas-market-calendars for exchange holidays and falls back to pandas business days.
- riskfolio_weights uses Riskfolio-Lib's historical minimum-risk optimizer and falls back to inverse-variance weights.
- to_qlib_frame and load_qlib_features bridge OHLCV data to Microsoft Qlib's (instrument, datetime) layout and feature API.

Install only the capability you need: pip install -e '.[calendars]', '.[risk]', or '.[qlib]'. The base package and tests do not require these optional dependencies.
