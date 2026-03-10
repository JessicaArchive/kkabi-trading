import pandas as pd
import numpy as np
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BaseStrategy:
    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def analyze(self, timeframe: str = "1h") -> str:
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=50)
        if not ohlcv:
            return "NO_DATA"

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Simple Moving Average crossover
        df["sma_short"] = df["close"].rolling(window=7).mean()
        df["sma_long"] = df["close"].rolling(window=25).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]

        if latest["sma_short"] > latest["sma_long"] and latest["rsi"] < 70:
            signal = "BUY"
        elif latest["sma_short"] < latest["sma_long"] and latest["rsi"] > 30:
            signal = "SELL"
        else:
            signal = "HOLD"

        logger.info(
            f"SMA7={latest['sma_short']:.2f} SMA25={latest['sma_long']:.2f} "
            f"RSI={latest['rsi']:.1f} -> {signal}"
        )
        return signal
