import pandas as pd
import numpy as np
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BreakoutHunterStrategy:
    """
    BreakoutHunter Strategy v1.0

    Volatility breakout strategy that detects consolidation phases
    and catches the explosive move when price breaks out.

    Opposite philosophy to both PentaScore (trend-following) and
    MeanRevert (reversal). This strategy asks: "Is a big move coming?"

    Indicators:
    - Donchian Channel Breakout (price at N-period extremes)
    - ADX (trend strength, not direction)
    - Squeeze Detection (BB inside KC = compressed volatility)
    - OBV Slope (smart money flow via On-Balance Volume)
    - Range Contraction (ATR compression = breakout imminent)

    Each indicator votes with a score (-2 to +2).
    Final signal determined by total score vs thresholds.
    Score range: -10 to +10
    """

    STRATEGY_NAME = "BreakoutHunter"
    STRATEGY_VERSION = "1.0"

    BUY_THRESHOLD = 3
    SELL_THRESHOLD = -3

    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def _calc_donchian(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        df["dc_upper"] = df["high"].rolling(window=period).max()
        df["dc_lower"] = df["low"].rolling(window=period).min()
        df["dc_mid"] = (df["dc_upper"] + df["dc_lower"]) / 2
        dc_range = df["dc_upper"] - df["dc_lower"]
        df["dc_position"] = np.where(dc_range == 0, 0.5, (df["close"] - df["dc_lower"]) / dc_range)
        return df

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = true_range.ewm(span=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

        di_sum = plus_di + minus_di
        dx = np.where(di_sum == 0, 0, 100 * (plus_di - minus_di).abs() / di_sum)
        df["adx"] = pd.Series(dx, index=df.index).ewm(span=period, adjust=False).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di
        return df

    def _calc_squeeze(self, df: pd.DataFrame, bb_period: int = 20, bb_mult: float = 2.0,
                      kc_period: int = 20, kc_mult: float = 1.5) -> pd.DataFrame:
        # Bollinger Bands
        bb_mid = df["close"].rolling(window=bb_period).mean()
        bb_std = df["close"].rolling(window=bb_period).std()
        bb_upper = bb_mid + (bb_std * bb_mult)
        bb_lower = bb_mid - (bb_std * bb_mult)

        # Keltner Channel
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=kc_period).mean()
        kc_mid = df["close"].ewm(span=kc_period, adjust=False).mean()
        kc_upper = kc_mid + (atr * kc_mult)
        kc_lower = kc_mid - (atr * kc_mult)

        # Squeeze: BB inside KC
        df["squeeze_on"] = (bb_lower > kc_lower) & (bb_upper < kc_upper)

        # Squeeze momentum (Linear regression of close - KC midline)
        delta = df["close"] - kc_mid
        df["squeeze_momentum"] = delta
        df["squeeze_momentum_prev"] = delta.shift(1)

        # Count consecutive squeeze bars
        squeeze_count = []
        count = 0
        for sq in df["squeeze_on"]:
            if sq:
                count += 1
            else:
                count = 0
            squeeze_count.append(count)
        df["squeeze_count"] = squeeze_count

        return df

    def _calc_obv(self, df: pd.DataFrame, slope_period: int = 10) -> pd.DataFrame:
        obv = [0]
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                obv.append(obv[-1] + df["volume"].iloc[i])
            elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                obv.append(obv[-1] - df["volume"].iloc[i])
            else:
                obv.append(obv[-1])
        df["obv"] = obv
        df["obv_sma"] = df["obv"].rolling(window=slope_period).mean()
        # Normalize OBV slope as percentage change of SMA
        df["obv_slope"] = df["obv_sma"].pct_change(periods=slope_period) * 100
        return df

    def _calc_range_contraction(self, df: pd.DataFrame, short: int = 5, long: int = 50) -> pd.DataFrame:
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr_short = true_range.rolling(window=short).mean()
        atr_long = true_range.rolling(window=long).mean()

        # Ratio < 1 means current volatility is below average = contraction
        df["range_ratio"] = np.where(atr_long == 0, 1.0, atr_short / atr_long)
        return df

    def _score_signals(self, df: pd.DataFrame) -> dict:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        scores = {}

        # 1. Donchian Channel Breakout (+2/-2)
        dc_pos = latest["dc_position"]
        if dc_pos >= 1.0:
            scores["donchian"] = 2   # Breaking above channel high
        elif dc_pos > 0.9:
            scores["donchian"] = 1   # Near channel high
        elif dc_pos <= 0.0:
            scores["donchian"] = -2  # Breaking below channel low
        elif dc_pos < 0.1:
            scores["donchian"] = -1  # Near channel low
        else:
            scores["donchian"] = 0

        # 2. ADX: trend strength (+2/-2, direction from DI)
        adx = latest["adx"]
        direction = 1 if latest["plus_di"] > latest["minus_di"] else -1
        if adx > 30:
            scores["adx"] = 2 * direction   # Strong trend forming
        elif adx > 20 and adx > prev["adx"]:
            scores["adx"] = 1 * direction   # Trend strengthening
        else:
            scores["adx"] = 0  # No trend or weakening

        # 3. Squeeze Detection (+2/-2)
        squeeze_just_fired = prev["squeeze_on"] and not latest["squeeze_on"]
        if squeeze_just_fired:
            # Squeeze released! Direction from momentum
            if latest["squeeze_momentum"] > 0:
                scores["squeeze"] = 2   # Bullish breakout from squeeze
            else:
                scores["squeeze"] = -2  # Bearish breakout from squeeze
        elif latest["squeeze_on"] and latest["squeeze_count"] > 6:
            # Long squeeze building pressure — no direction yet
            scores["squeeze"] = 0
        else:
            scores["squeeze"] = 0

        # 4. OBV Slope: smart money flow (+2/-2)
        obv_slope = latest["obv_slope"]
        if not np.isfinite(obv_slope):
            scores["obv"] = 0
        elif obv_slope > 5:
            scores["obv"] = 2    # Strong buying pressure
        elif obv_slope > 2:
            scores["obv"] = 1    # Mild buying pressure
        elif obv_slope < -5:
            scores["obv"] = -2   # Strong selling pressure
        elif obv_slope < -2:
            scores["obv"] = -1   # Mild selling pressure
        else:
            scores["obv"] = 0

        # 5. Range Contraction → Expansion (+2/-2)
        range_ratio = latest["range_ratio"]
        prev_ratio = prev["range_ratio"]
        if range_ratio > 1.3 and prev_ratio < 0.8:
            # Volatility just expanded from compression — breakout!
            price_dir = 1 if latest["close"] > latest["dc_mid"] else -1
            scores["range"] = 2 * price_dir
        elif range_ratio < 0.5:
            # Extreme contraction — breakout incoming but no direction yet
            scores["range"] = 0
        elif range_ratio > 1.5:
            # Already expanded — momentum confirmation
            price_dir = 1 if latest["close"] > prev["close"] else -1
            scores["range"] = 1 * price_dir
        else:
            scores["range"] = 0

        return scores

    def analyze(self, timeframe: str = "1h") -> dict:
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=200)
        if not ohlcv:
            return {"strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}", "signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Calculate all indicators
        df = self._calc_donchian(df)
        df = self._calc_adx(df)
        df = self._calc_squeeze(df)
        df = self._calc_obv(df)
        df = self._calc_range_contraction(df)

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
            "dc_position": round(latest["dc_position"], 3),
            "dc_upper": round(latest["dc_upper"], 2),
            "dc_lower": round(latest["dc_lower"], 2),
            "adx": round(latest["adx"], 1),
            "plus_di": round(latest["plus_di"], 1),
            "minus_di": round(latest["minus_di"], 1),
            "squeeze_on": bool(latest["squeeze_on"]),
            "squeeze_count": int(latest["squeeze_count"]),
            "squeeze_momentum": round(latest["squeeze_momentum"], 2),
            "obv_slope": round(latest["obv_slope"], 2) if np.isfinite(latest["obv_slope"]) else 0,
            "range_ratio": round(latest["range_ratio"], 3),
        }

        logger.info(f"Scores: {scores} | Total: {total} -> {signal}")
        logger.info(
            f"Price={details['price']} DC%={details['dc_position']} "
            f"ADX={details['adx']} +DI={details['plus_di']} -DI={details['minus_di']} "
            f"Squeeze={'ON' if details['squeeze_on'] else 'OFF'}({details['squeeze_count']}) "
            f"OBV_Slope={details['obv_slope']} RangeRatio={details['range_ratio']}"
        )

        return {
            "strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}",
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
