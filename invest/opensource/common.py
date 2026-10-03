"""Bounded, offline inputs shared by the optional open-source research adapters."""
from __future__ import annotations

import importlib
import math


def validated_series(payload: dict) -> list[float]:
    """Accept only 8..5000 finite JSON numbers; never paths, code, URLs or SQL."""
    if not isinstance(payload, dict) or set(payload) != {'values'}:
        raise ValueError('payload must contain only values')
    values = payload['values']
    if not isinstance(values, list) or not 8 <= len(values) <= 5000:
        raise ValueError('values must contain 8-5000 observations')
    result = []
    for value in values:
        if type(value) not in (int, float) or abs(value) > 1e6 or not math.isfinite(value):
            raise ValueError('values must be finite JSON numbers with abs(value) <= 1000000')
        result.append(float(value))
    return result


def load_dependency(module: str, distribution: str):
    """Import only a hard-coded adapter dependency, with no silent substitute."""
    try:
        return importlib.import_module(module)
    except ImportError:
        raise ValueError(f'Optional backend {distribution} is unavailable; install Invest research extras in the server environment') from None


def positive_prices(values: list[float], *, minimum_count: int = 8):
    if len(values) < minimum_count or any(v < 1e-6 for v in values):
        raise ValueError(f'price backend requires at least {minimum_count} positive prices >= 0.000001')
