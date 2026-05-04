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

    def fetch_order(self, order_id: str, symbol: str) -> dict | None:
        if not self.authenticated:
            return None
        try:
            return self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return None

    def create_order(
        self,
        symbol: str,
        side: str,
        amount: float = None,
        price: float = None,
        cost: float = None,
        test: bool = False,
    ) -> dict | None:
        """주문 생성. 업비트 KRW 마켓 시장가 매수는 cost(KRW 총액) 기반.

        - 시장가 매수 (KRW 마켓): cost 인자로 KRW 총액 전달
        - 시장가 매도: amount 인자로 BTC 수량 전달
        - 지정가: amount + price
        - test=True 면 업비트 testOrders 엔드포인트로 검증만 (실주문 없음)
        """
        if not self.authenticated:
            logger.warning("API 키가 없어 주문 불가")
            return None
        params = {}
        if test:
            params["test"] = True
        try:
            if cost is not None and side == "buy":
                params["cost"] = cost
                order = self.exchange.create_order(symbol, "market", "buy", None, None, params)
                logger.info(f"Order created: buy {symbol} cost=₩{cost:,.0f} test={test}")
            elif price:
                order = self.exchange.create_order(symbol, "limit", side, amount, price, params)
                logger.info(f"Order created: {side} {amount} {symbol} @ {price} test={test}")
            else:
                order = self.exchange.create_order(symbol, "market", side, amount, None, params)
                logger.info(f"Order created: {side} {amount} {symbol} @ market test={test}")
            return order
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            return None
