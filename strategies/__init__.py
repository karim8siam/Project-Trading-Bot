"""
Crypto Strategies Package.
"""
from .trend_pullback import evaluate_trend_pullback
from .volatility_breakout import evaluate_volatility_breakout
from .range_mean_reversion import evaluate_range_mean_reversion

__all__ = [
    "evaluate_trend_pullback",
    "evaluate_volatility_breakout",
    "evaluate_range_mean_reversion"
]
