from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from strategy.ichimoku import IchimokuStrategy

STRATEGIES = {
    "base": BaseStrategy,
    "ichimoku": IchimokuStrategy,
}


def create_strategy(name: str, client: ExchangeClient, symbol: str):
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {list(STRATEGIES.keys())}")
    return cls(client, symbol)
