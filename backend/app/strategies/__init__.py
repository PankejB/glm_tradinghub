"""
app.strategies
--------------
Registry: map strategy_type -> class.
"""
from app.strategies.base import StrategyBase, Signal
from app.strategies.stock_counter_trend import StockCounterTrendStrategy
from app.strategies.mcx_trend_following import McxTrendFollowingStrategy
from app.strategies.index_bar_scoring import IndexBarScoringStrategy

STRATEGY_REGISTRY: dict[str, type[StrategyBase]] = {
    "stock_counter_trend": StockCounterTrendStrategy,
    "mcx_trend_following": McxTrendFollowingStrategy,
    "index_bar_scoring": IndexBarScoringStrategy,
}


def get_strategy_class(strategy_type: str) -> type[StrategyBase]:
    cls = STRATEGY_REGISTRY.get(strategy_type)
    if cls is None:
        raise ValueError(
            f"Unknown strategy_type: {strategy_type!r}. "
            f"Available: {list(STRATEGY_REGISTRY)}"
        )
    return cls


def build_strategy(strategy_type: str, parameters: dict | None = None) -> StrategyBase:
    cls = get_strategy_class(strategy_type)
    return cls(parameters=parameters)


__all__ = [
    "StrategyBase", "Signal",
    "StockCounterTrendStrategy",
    "McxTrendFollowingStrategy",
    "IndexBarScoringStrategy",
    "STRATEGY_REGISTRY",
    "get_strategy_class",
    "build_strategy",
]
