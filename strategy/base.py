import pandas as pd
import numpy as np
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BaseStrategy:
    """
    Multi-signal scoring strategy combining:
    - SMA Crossover (trend detection)
    - MACD (momentum)
    - Bollinger Bands (volatility & mean reversion)
    - RSI (overbought/oversold)
    - Volume Analysis (confirmation)

    Each indicator votes with a score. Final decision based on total score.
    """

    # Score thresholds
    BUY_THRESHOLD = 3
    SELL_THRESHOLD = -3

    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def _calc_sma(self, df: pd.DataFrame) -> pd.DataFrame:
        df["sma_7"] = df["close"].rolling(window=7).mean()
        df["sma_25"] = df["close"].rolling(window=25).mean()
        df["sma_99"] = df["close"].rolling(window=99).mean()
        return df

    def _calc_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        return df

    def _calc_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        return df

    def _calc_bollinger(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
        df["bb_mid"] = df["close"].rolling(window=period).mean()
        bb_std = df["close"].rolling(window=period).std()
        df["bb_upper"] = df["bb_mid"] + (bb_std * std_dev)
        df["bb_lower"] = df["bb_mid"] - (bb_std * std_dev)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        return df

    def _calc_volume(self, df: pd.DataFrame) -> pd.DataFrame:
        df["vol_sma"] = df["volume"].rolling(window=20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_sma"]
        return df

    def _score_signals(self, df: pd.DataFrame) -> dict:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        scores = {}

        # 1. SMA Crossover (+2/-2)
        if latest["sma_7"] > latest["sma_25"] > latest["sma_99"]:
            scores["sma"] = 2  # Strong uptrend
        elif latest["sma_7"] > latest["sma_25"]:
            scores["sma"] = 1  # Mild uptrend
        elif latest["sma_7"] < latest["sma_25"] < latest["sma_99"]:
            scores["sma"] = -2  # Strong downtrend
        elif latest["sma_7"] < latest["sma_25"]:
            scores["sma"] = -1  # Mild downtrend
        else:
            scores["sma"] = 0

        # 2. MACD (+2/-2)
        if latest["macd"] > latest["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
            scores["macd"] = 2  # Bullish crossover (just happened)
        elif latest["macd"] > latest["macd_signal"] and latest["macd_hist"] > prev["macd_hist"]:
            scores["macd"] = 1  # Bullish & strengthening
        elif latest["macd"] < latest["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
            scores["macd"] = -2  # Bearish crossover (just happened)
        elif latest["macd"] < latest["macd_signal"] and latest["macd_hist"] < prev["macd_hist"]:
            scores["macd"] = -1  # Bearish & weakening
        else:
            scores["macd"] = 0

        # 3. Bollinger Bands (+2/-2)
        if latest["bb_position"] < 0.05:
            scores["bollinger"] = 2  # Below lower band = oversold bounce
        elif latest["bb_position"] < 0.2:
            scores["bollinger"] = 1  # Near lower band
        elif latest["bb_position"] > 0.95:
            scores["bollinger"] = -2  # Above upper band = overbought
        elif latest["bb_position"] > 0.8:
            scores["bollinger"] = -1  # Near upper band
        else:
            scores["bollinger"] = 0

        # 4. RSI (+2/-2)
        rsi = latest["rsi"]
        if rsi < 25:
            scores["rsi"] = 2  # Deep oversold
        elif rsi < 35:
            scores["rsi"] = 1  # Oversold
        elif rsi > 75:
            scores["rsi"] = -2  # Deep overbought
        elif rsi > 65:
            scores["rsi"] = -1  # Overbought
        else:
            scores["rsi"] = 0

        # 5. Volume confirmation (+1/-1)
        if latest["vol_ratio"] > 1.5:
            # High volume confirms the trend direction
            price_change = latest["close"] - prev["close"]
            if price_change > 0:
                scores["volume"] = 1  # High vol + price up
            elif price_change < 0:
                scores["volume"] = -1  # High vol + price down
            else:
                scores["volume"] = 0
        else:
            scores["volume"] = 0

        return scores

    def analyze(self, timeframe: str = "1h") -> dict:
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=120)
        if not ohlcv:
            return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Calculate all indicators
        df = self._calc_sma(df)
        df = self._calc_rsi(df)
        df = self._calc_macd(df)
        df = self._calc_bollinger(df)
        df = self._calc_volume(df)

        # Drop NaN rows
        df = df.dropna()
        if len(df) < 2:
            return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        # Score each indicator
        scores = self._score_signals(df)
        total = sum(scores.values())

        # Determine signal
        if total >= self.BUY_THRESHOLD:
            signal = "BUY"
        elif total <= self.SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        latest = df.iloc[-1]
        details = {
            "price": latest["close"],
            "sma_7": round(latest["sma_7"], 2),
            "sma_25": round(latest["sma_25"], 2),
            "sma_99": round(latest["sma_99"], 2),
            "rsi": round(latest["rsi"], 1),
            "macd": round(latest["macd"], 4),
            "macd_signal": round(latest["macd_signal"], 4),
            "bb_position": round(latest["bb_position"], 3),
            "bb_width": round(latest["bb_width"], 4),
            "vol_ratio": round(latest["vol_ratio"], 2),
        }

        logger.info(f"Scores: {scores} | Total: {total} -> {signal}")
        logger.info(
            f"Price={details['price']} SMA7={details['sma_7']} SMA25={details['sma_25']} "
            f"SMA99={details['sma_99']} RSI={details['rsi']} MACD={details['macd']} "
            f"BB%={details['bb_position']} VolRatio={details['vol_ratio']}"
        )

        return {
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
