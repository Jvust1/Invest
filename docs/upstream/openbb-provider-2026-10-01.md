# OpenBB market-data adapter — 2026-10-01

Upstream: `OpenBB-finance/OpenBB`  
Revision inspected: `bbf1ab2020c2ce025333db56ece2036190fcad9c`  
Current repository license: Apache-2.0

The adapter uses the public `obb.equity.price.historical(symbol, ...).to_dataframe()` path and normalizes OHLCV into Invest's provider boundary. OpenBB remains optional. Individual upstream data-provider terms and entitlements remain separate from the OpenBB software license.
