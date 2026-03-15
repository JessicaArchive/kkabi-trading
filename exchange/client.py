from __future__ import annotations

import ccxt
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ExchangeClient:
    def __init__(self, exchange_name: str, api_key: str, api_secret: str):
        exchange_class = getattr(ccxt, exchange_name)
        self.exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        logger.info(f"Connected to {exchange_name}")

    def get_ticker(self, symbol: str) -> dict | None:
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch ticker: {e}")
            return None

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list:
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV: {e}")
            return []

    def get_balance(self) -> dict | None:
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return None

    def create_order(self, symbol: str, side: str, amount: float, price: float = None) -> dict | None:
        try:
            if price:
                order = self.exchange.create_limit_order(symbol, side, amount, price)
            else:
                order = self.exchange.create_market_order(symbol, side, amount)
            logger.info(f"Order created: {side} {amount} {symbol} @ {price or 'market'}")
            return order
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            return None
