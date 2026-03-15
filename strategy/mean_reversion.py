import pandas as pd
import numpy as np
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MeanReversionStrategy:
    """
    MeanRevert Strategy v1.0

    Mean-reversion strategy that bets on price returning to fair value.
    Opposite philosophy to PentaScore (trend-following).

    Indicators:
    - Z-Score (statistical deviation from rolling mean)
    - Stochastic RSI (momentum exhaustion, more sensitive than RSI)
    - ATR Percentile (volatility regime detection)
    - Keltner Channel Position (ATR-based envelope)
    - ROC Divergence (price vs momentum divergence)

    Each indicator votes with a score (-2 to +2).
    Final signal determined by total score vs thresholds.
    Score range: -10 to +10
    """

    STRATEGY_NAME = "MeanRevert"
    STRATEGY_VERSION = "1.0"

    BUY_THRESHOLD = 3
    SELL_THRESHOLD = -3

    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def _calc_zscore(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        rolling_mean = df["close"].rolling(window=period).mean()
        rolling_std = df["close"].rolling(window=period).std()
        df["zscore"] = (df["close"] - rolling_mean) / rolling_std
        return df

    def _calc_stoch_rsi(self, df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        rsi_min = rsi.rolling(window=stoch_period).min()
        rsi_max = rsi.rolling(window=stoch_period).max()
        df["stoch_rsi"] = (rsi - rsi_min) / (rsi_max - rsi_min)
        df["stoch_rsi_k"] = df["stoch_rsi"].rolling(window=3).mean()
        df["stoch_rsi_d"] = df["stoch_rsi_k"].rolling(window=3).mean()
        return df

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=period).mean()
        df["atr_pct"] = df["atr"] / df["close"] * 100
        # ATR percentile over longer window
        df["atr_percentile"] = df["atr_pct"].rolling(window=100).rank(pct=True)
        return df

    def _calc_keltner(self, df: pd.DataFrame, ema_period: int = 20, atr_mult: float = 2.0) -> pd.DataFrame:
        df["kc_mid"] = df["close"].ewm(span=ema_period, adjust=False).mean()
        df["kc_upper"] = df["kc_mid"] + (df["atr"] * atr_mult)
        df["kc_lower"] = df["kc_mid"] - (df["atr"] * atr_mult)
        kc_range = df["kc_upper"] - df["kc_lower"]
        df["kc_position"] = (df["close"] - df["kc_lower"]) / kc_range
        return df

    def _calc_roc(self, df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
        df["roc"] = (df["close"] - df["close"].shift(period)) / df["close"].shift(period) * 100
        df["roc_sma"] = df["roc"].rolling(window=6).mean()
        return df

    def _score_signals(self, df: pd.DataFrame) -> dict:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        scores = {}

        # 1. Z-Score: extreme deviation = reversion signal (+2/-2)
        z = latest["zscore"]
        if z < -2.0:
            scores["zscore"] = 2   # Extremely below mean -> buy
        elif z < -1.0:
            scores["zscore"] = 1   # Below mean -> mild buy
        elif z > 2.0:
            scores["zscore"] = -2  # Extremely above mean -> sell
        elif z > 1.0:
            scores["zscore"] = -1  # Above mean -> mild sell
        else:
            scores["zscore"] = 0

        # 2. Stochastic RSI: exhaustion signal (+2/-2)
        stoch_k = latest["stoch_rsi_k"]
        stoch_d = latest["stoch_rsi_d"]
        if stoch_k < 0.1 and stoch_k > stoch_d:
            scores["stoch_rsi"] = 2   # Deep oversold + turning up
        elif stoch_k < 0.2:
            scores["stoch_rsi"] = 1   # Oversold
        elif stoch_k > 0.9 and stoch_k < stoch_d:
            scores["stoch_rsi"] = -2  # Deep overbought + turning down
        elif stoch_k > 0.8:
            scores["stoch_rsi"] = -1  # Overbought
        else:
            scores["stoch_rsi"] = 0

        # 3. ATR Percentile: high volatility = more likely to revert (+2/-2)
        atr_pctl = latest["atr_percentile"]
        trend_dir = 1 if latest["close"] > latest["kc_mid"] else -1
        if atr_pctl > 0.9:
            scores["atr"] = -2 * trend_dir  # Extreme vol, bet against current direction
        elif atr_pctl > 0.7:
            scores["atr"] = -1 * trend_dir  # High vol, mild counter-trend
        else:
            scores["atr"] = 0  # Normal vol, no signal

        # 4. Keltner Channel Position (+2/-2)
        kc_pos = latest["kc_position"]
        if kc_pos < 0.0:
            scores["keltner"] = 2   # Below lower band
        elif kc_pos < 0.15:
            scores["keltner"] = 1   # Near lower band
        elif kc_pos > 1.0:
            scores["keltner"] = -2  # Above upper band
        elif kc_pos > 0.85:
            scores["keltner"] = -1  # Near upper band
        else:
            scores["keltner"] = 0

        # 5. ROC Divergence: momentum fading while price extends (+2/-2)
        roc = latest["roc"]
        roc_prev = prev["roc"]
        price_up = latest["close"] > prev["close"]
        if price_up and roc < roc_prev and roc < latest["roc_sma"]:
            scores["roc_div"] = -1  # Price up but momentum fading -> bearish divergence
        elif not price_up and roc > roc_prev and roc > latest["roc_sma"]:
            scores["roc_div"] = 1   # Price down but momentum improving -> bullish divergence
        else:
            scores["roc_div"] = 0

        return scores

    def analyze(self, timeframe: str = "1h") -> dict:
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=150)
        if not ohlcv:
            return {"strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}", "signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Calculate all indicators
        df = self._calc_zscore(df)
        df = self._calc_stoch_rsi(df)
        df = self._calc_atr(df)
        df = self._calc_keltner(df)
        df = self._calc_roc(df)

        df = df.dropna()
        if len(df) < 2:
            return {"strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}", "signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        scores = self._score_signals(df)
        total = sum(scores.values())

        if total >= self.BUY_THRESHOLD:
            signal = "BUY"
        elif total <= self.SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        latest = df.iloc[-1]
        details = {
            "price": latest["close"],
            "zscore": round(latest["zscore"], 3),
            "stoch_rsi_k": round(latest["stoch_rsi_k"], 3),
            "stoch_rsi_d": round(latest["stoch_rsi_d"], 3),
            "atr_pct": round(latest["atr_pct"], 3),
            "atr_percentile": round(latest["atr_percentile"], 3),
            "kc_position": round(latest["kc_position"], 3),
            "roc": round(latest["roc"], 3),
        }

        logger.info(f"Scores: {scores} | Total: {total} -> {signal}")
        logger.info(
            f"Price={details['price']} Z={details['zscore']} StochRSI_K={details['stoch_rsi_k']} "
            f"ATR%={details['atr_pct']} ATR_Pctl={details['atr_percentile']} "
            f"KC%={details['kc_position']} ROC={details['roc']}"
        )

        return {
            "strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}",
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
