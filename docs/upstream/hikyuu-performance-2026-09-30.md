# Hikyuu performance adapter — 2026-09-30

Upstream: `fasiondog/hikyuu`  
Revision inspected: `daeb2c792a2095178fd5af051eda76d1b23e96c6`  
License: Apache-2.0

Invest now consumes Hikyuu only through a read-only performance boundary:
`TradeManager.get_performance() -> Performance.to_dict() -> HikyuuPerformanceSnapshot`.

The adapter does **not** construct brokers, orders or execution paths. It is intended for independent research/backtest cross-checks against Invest's existing metrics stack.
