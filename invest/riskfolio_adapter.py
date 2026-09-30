"""Riskfolio-Lib adapter with a deterministic inverse-variance fallback."""
from __future__ import annotations
import pandas as pd

def riskfolio_weights(returns, model: str = "Classic", risk_measure: str = "MV") -> dict[str, float]:
    """Optimize asset weights with Riskfolio-Lib when available."""
    frame = pd.DataFrame(returns).astype(float).dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("returns must contain at least one non-empty asset")
    try:
        import riskfolio as rp
        port = rp.Portfolio(returns=frame)
        port.assets_stats(method_mu="hist", method_cov="hist")
        weights = port.optimization(model=model, rm=risk_measure, obj="MinRisk", rf=0, l=0, hist=True)
        return {str(name): float(weights.iloc[i, 0]) for i, name in enumerate(weights.index)}
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError):
        from .portfolio import inverse_variance_weights
        return inverse_variance_weights((1.0 + frame).cumprod())
