from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from strategy.fear_greed import FearGreedStrategy

STRATEGIES = {
    "base": BaseStrategy,
    "fear_greed": FearGreedStrategy,
}

# Optional strategies (may not exist on all branches)
try:
    from strategy.ichimoku import IchimokuStrategy
    STRATEGIES["ichimoku"] = IchimokuStrategy
except ImportError:
    pass

try:
    from strategy.mean_reversion import MeanReversionStrategy
    STRATEGIES["mean_reversion"] = MeanReversionStrategy
except ImportError:
    pass

try:
    from strategy.breakout_hunter import BreakoutHunterStrategy
    STRATEGIES["breakout_hunter"] = BreakoutHunterStrategy
except ImportError:
    pass


def create_strategy(name: str, client: ExchangeClient, symbol: str):
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {list(STRATEGIES.keys())}")
    return cls(client, symbol)
