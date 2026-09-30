"""skfolio portfolio optimization adapter with a safe fallback."""
from __future__ import annotations
import pandas as pd

def skfolio_weights(returns, risk_measure: str = "variance") -> dict[str, float]:
    """Fit skfolio's minimum-risk model when installed, else use inverse variance."""
    frame = pd.DataFrame(returns).astype(float).dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("returns must contain at least one non-empty asset")
    try:
        from skfolio import RiskMeasure
        from skfolio.optimization import MeanRisk
        measure = getattr(RiskMeasure, risk_measure.upper())
        model = MeanRisk(risk_measure=measure)
        model.fit(frame)
        portfolio = model.predict(frame)
        weights = portfolio.weights
        return {str(name): float(value) for name, value in zip(frame.columns, weights)}
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError, AttributeError):
        from .portfolio import inverse_variance_weights
        return inverse_variance_weights((1.0 + frame).cumprod())
