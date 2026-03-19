import pandas as pd
import numpy as np
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class IchimokuStrategy:
    """
    Ichimoku Cloud (일목균형표) Strategy v1.0

    5개 선으로 추세, 모멘텀, 지지/저항을 한 눈에 판단:
    - 전환선(Tenkan-sen): 9봉 중간값 — 단기 모멘텀
    - 기준선(Kijun-sen): 26봉 중간값 — 중기 추세/동적 지지저항
    - 선행스팬A(Senkou A): (전환+기준)/2, 26봉 앞 — 구름 상단/하단
    - 선행스팬B(Senkou B): 52봉 중간값, 26봉 앞 — 구름 두께
    - 후행스팬(Chikou): 현재 종가를 26봉 뒤에 표시

    Score range: -8 ~ +8
    """

    BUY_THRESHOLD = 3
    SELL_THRESHOLD = -3

    # Ichimoku periods
    TENKAN_PERIOD = 9
    KIJUN_PERIOD = 26
    SENKOU_B_PERIOD = 52
    DISPLACEMENT = 26

    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def _midpoint(self, series: pd.Series, period: int) -> pd.Series:
        """period 구간의 (최고+최저)/2 — 일목균형표의 기본 계산법."""
        high = series.rolling(window=period).max()
        low = series.rolling(window=period).min()
        return (high + low) / 2

    def _calc_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        # 전환선 (Tenkan-sen) — 9봉 중간값
        df["tenkan"] = self._midpoint(df["close"], self.TENKAN_PERIOD)

        # 기준선 (Kijun-sen) — 26봉 중간값
        df["kijun"] = self._midpoint(df["close"], self.KIJUN_PERIOD)

        # 선행스팬A (Senkou Span A) — (전환+기준)/2, 현재 위치 기준
        df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(self.DISPLACEMENT)

        # 선행스팬B (Senkou Span B) — 52봉 중간값, 현재 위치 기준
        df["senkou_b"] = self._midpoint(df["close"], self.SENKOU_B_PERIOD).shift(self.DISPLACEMENT)

        # 후행스팬 (Chikou Span) — 현재 종가를 26봉 뒤로
        df["chikou"] = df["close"].shift(-self.DISPLACEMENT)

        # 구름 관련 파생값
        df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)
        df["cloud_bottom"] = df[["senkou_a", "senkou_b"]].min(axis=1)
        df["cloud_thickness"] = abs(df["senkou_a"] - df["senkou_b"]) / df["close"]

        return df

    def _score_signals(self, df: pd.DataFrame) -> dict:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        scores = {}

        # 1. 전환선/기준선 교차 (±2)
        tenkan_above = latest["tenkan"] > latest["kijun"]
        prev_tenkan_above = prev["tenkan"] > prev["kijun"]

        if tenkan_above and not prev_tenkan_above:
            scores["tk_cross"] = 2  # 골든크로스 (방금 발생)
        elif tenkan_above:
            scores["tk_cross"] = 1  # 전환선 > 기준선 유지
        elif not tenkan_above and prev_tenkan_above:
            scores["tk_cross"] = -2  # 데드크로스 (방금 발생)
        elif not tenkan_above:
            scores["tk_cross"] = -1  # 전환선 < 기준선 유지
        else:
            scores["tk_cross"] = 0

        # 2. 가격 vs 구름 (±2)
        price = latest["close"]
        cloud_top = latest["cloud_top"]
        cloud_bottom = latest["cloud_bottom"]

        if price > cloud_top:
            scores["price_cloud"] = 2  # 구름 위 = 강한 상승 추세
        elif price > cloud_bottom:
            scores["price_cloud"] = 1  # 구름 안 = 전환 구간 (상단 근접)
        elif price < cloud_bottom:
            scores["price_cloud"] = -2  # 구름 아래 = 강한 하락 추세
        else:
            scores["price_cloud"] = -1  # 구름 안 = 전환 구간 (하단 근접)

        # 3. 미래 구름 색상 — 현재 senkou_a vs senkou_b (shift 전 값으로 미래 구름 추정) (±1)
        current_senkou_a_future = (latest["tenkan"] + latest["kijun"]) / 2
        current_senkou_b_future = self._midpoint_single(df["close"], self.SENKOU_B_PERIOD)

        if current_senkou_a_future > current_senkou_b_future:
            scores["future_cloud"] = 1  # 미래 구름 양운 (상승 전망)
        elif current_senkou_a_future < current_senkou_b_future:
            scores["future_cloud"] = -1  # 미래 구름 음운 (하락 전망)
        else:
            scores["future_cloud"] = 0

        # 4. 후행스팬 vs 26봉 전 가격 (±2)
        # 후행스팬 = 현재 종가, 26봉 전 가격과 비교
        if len(df) > self.DISPLACEMENT:
            price_26_ago = df.iloc[-(self.DISPLACEMENT + 1)]["close"]
            chikou_diff_pct = (price - price_26_ago) / price_26_ago * 100

            if chikou_diff_pct > 5:
                scores["chikou"] = 2  # 현재가가 26봉 전보다 5%+ 위
            elif chikou_diff_pct > 0:
                scores["chikou"] = 1  # 위에 있음
            elif chikou_diff_pct < -5:
                scores["chikou"] = -2  # 5%+ 아래
            elif chikou_diff_pct < 0:
                scores["chikou"] = -1  # 아래에 있음
            else:
                scores["chikou"] = 0
        else:
            scores["chikou"] = 0

        # 5. 구름 두께 — 지지/저항 강도 (±1)
        thickness = latest["cloud_thickness"]
        if thickness > 0.03:  # 두꺼운 구름 = 강한 지지/저항
            if price > cloud_top:
                scores["cloud_strength"] = 1  # 두꺼운 구름이 받쳐줌
            elif price < cloud_bottom:
                scores["cloud_strength"] = -1  # 두꺼운 구름이 눌러줌
            else:
                scores["cloud_strength"] = 0  # 구름 안에 있으면 중립
        else:
            scores["cloud_strength"] = 0  # 얇은 구름 = 돌파 쉬움, 중립

        return scores

    def _midpoint_single(self, series: pd.Series, period: int) -> float:
        """최근 period 구간의 중간값 단일 스칼라 반환."""
        window = series.iloc[-period:]
        return (window.max() + window.min()) / 2

    def analyze(self, timeframe: str = "1h") -> dict:
        # 일목균형표는 52+26=78봉 이상 필요
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=150)
        if not ohlcv:
            return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = self._calc_ichimoku(df)

        # 선행스팬은 shift로 NaN이 생기므로 해당 행만 제거
        analysis_df = df.dropna(subset=["tenkan", "kijun", "senkou_a", "senkou_b"])
        if len(analysis_df) < self.DISPLACEMENT + 2:
            return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        scores = self._score_signals(analysis_df)
        total = sum(scores.values())

        if total >= self.BUY_THRESHOLD:
            signal = "BUY"
        elif total <= self.SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        latest = analysis_df.iloc[-1]
        details = {
            "price": latest["close"],
            "tenkan": round(latest["tenkan"], 2),
            "kijun": round(latest["kijun"], 2),
            "senkou_a": round(latest["senkou_a"], 2),
            "senkou_b": round(latest["senkou_b"], 2),
            "cloud_top": round(latest["cloud_top"], 2),
            "cloud_bottom": round(latest["cloud_bottom"], 2),
            "cloud_thickness": round(latest["cloud_thickness"], 4),
        }

        logger.info(f"Scores: {scores} | Total: {total} -> {signal}")
        logger.info(
            f"Price={details['price']} Tenkan={details['tenkan']} Kijun={details['kijun']} "
            f"Cloud=[{details['cloud_bottom']}-{details['cloud_top']}] "
            f"Thickness={details['cloud_thickness']}"
        )

        return {
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
