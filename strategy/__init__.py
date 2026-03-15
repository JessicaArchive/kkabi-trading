from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from strategy.mean_reversion import MeanReversionStrategy
from strategy.breakout_hunter import BreakoutHunterStrategy

STRATEGIES = {
    "base": BaseStrategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout_hunter": BreakoutHunterStrategy,
}


def create_strategy(name: str, client: ExchangeClient, symbol: str):
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {list(STRATEGIES.keys())}")
    return cls(client, symbol)
