from __future__ import annotations
import ccxt
from utils.logger import setup_logger

logger = setup_logger(__name__)


PLACEHOLDER_KEYS = {"", "your_api_key_here", "your_api_secret_here"}


class ExchangeClient:
    def __init__(self, exchange_name: str, api_key: str = "", api_secret: str = ""):
        exchange_class = getattr(ccxt, exchange_name)
        config = {"enableRateLimit": True}

        self.authenticated = (
            api_key not in PLACEHOLDER_KEYS and api_secret not in PLACEHOLDER_KEYS
        )

        if self.authenticated:
            config["apiKey"] = api_key
            config["secret"] = api_secret

        self.exchange = exchange_class(config)
        mode = "authenticated" if self.authenticated else "public-only"
        logger.info(f"Connected to {exchange_name} ({mode})")

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
        if not self.authenticated:
            logger.warning("API 키가 없어 잔고 조회 불가")
            return None
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return None

    def create_order(self, symbol: str, side: str, amount: float, price: float = None) -> dict | None:
        if not self.authenticated:
            logger.warning("API 키가 없어 주문 불가")
            return None
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
