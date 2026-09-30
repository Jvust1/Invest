# Microsoft Qlib provider integration — 2026-09-30

Upstream: `microsoft/qlib`  
Revision: `be725493eb1a6bbb42bf11b37aa7669f59610ff1`  
License: MIT

The previous Qlib bridge only converted frames or called `D.features` directly. This integration upgrades Qlib into an optional Invest market provider compatible with the existing research pipeline.

`QlibMarketProvider.history()` normalizes A-share symbols, reads `$open/$high/$low/$close/$volume`, and returns Invest's standard OHLCV DataFrame contract. Qlib remains optional and is initialized only by the explicit factory.
