"""Market-data providers used by Invest."""
from .akshare_eastmoney import fetch_a_share_daily
from .akshare_native import AKShareProvider, normalize_history as normalize_akshare_history, normalize_spot as normalize_akshare_spot
from .ccxt_ohlcv import fetch_ccxt_ohlcv, normalize_ccxt_ohlcv
from .yfinance_ohlcv import fetch_yfinance_ohlcv, normalize_yfinance_ohlcv
from .openbb_provider import OpenBBProvider, normalize_openbb_ohlcv
from .duckdb_cache import (DuckDBMarketCache, DuckDBReplayProvider, DuckDBCacheMiss,
                           DuckDBCacheIntegrityError, DuckDBCacheStaleError)
__all__ = [
    "DuckDBMarketCache",
    "DuckDBReplayProvider",
    "DuckDBCacheMiss",
    "DuckDBCacheIntegrityError",
    "DuckDBCacheStaleError",
    "fetch_a_share_daily",
    "AKShareProvider",
    "normalize_akshare_history",
    "normalize_akshare_spot",
    "fetch_ccxt_ohlcv",
    "fetch_yfinance_ohlcv",
    "normalize_ccxt_ohlcv",
    "normalize_yfinance_ohlcv",
    "OpenBBProvider",
    "normalize_openbb_ohlcv",
]
