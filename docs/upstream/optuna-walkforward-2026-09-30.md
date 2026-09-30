# Optuna walk-forward optimization — 2026-09-30

Upstream: `optuna/optuna`  
Revision inspected: `5c8e50d85b77dd5a1fd7e26e21f63debc81d6016`  
License: MIT

Invest uses Optuna only through a time-series split objective. SMA parameters are evaluated on multiple forward validation folds with transaction costs; the adapter does not optimize against one full in-sample backtest.
