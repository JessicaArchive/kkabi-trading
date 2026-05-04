"""
RSI 극단값 반전 전략 (RsiExtremeStrategy)
==========================================

개요:
    RSI가 극단적인 과매도(20 이하) 또는 과매수(80 이상) 구간에 진입했을 때,
    가격 다이버전스를 함께 확인하여 반전 신호를 포착하는 평균회귀 전략.

    단순 RSI 과매도/과매수보다 한 단계 더 나아가, 가격과 RSI 지표 간의
    다이버전스(괴리)를 감지해 허위 신호를 걸러낸다.

지표 계산:
    - RSI 14기간 기본 설정
    - 강세 다이버전스: 가격은 저점 갱신, RSI는 저점 미갱신 (매수 신호)
    - 약세 다이버전스: 가격은 고점 갱신, RSI는 고점 미갱신 (매도 신호)

스코어 체계:
    - RSI < 20 + 강세 다이버전스 확인: +3
    - RSI < 30 (다이버전스 없음):      +1
    - RSI > 80 + 약세 다이버전스 확인: -3
    - RSI > 70 (다이버전스 없음):      -1

시그널 임계값:
    - BUY: 합계 >= +3
    - SELL: 합계 <= -3
    - HOLD: 그 외

주의사항:
    - 강한 추세 국면에서는 RSI 극단값이 지속될 수 있음
    - 다이버전스 탐지는 최근 5개 봉 고점/저점 비교로 단순화
    - 단독 사용보다 추세 필터와 병행 사용 권장
"""

import pandas as pd
import numpy as np
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RsiExtremeStrategy:
    """
    RSI 극단값 + 가격 다이버전스 기반 평균회귀 전략.

    RSI 14기간을 계산하고, 극단 구간(20 이하 / 80 이상)에서
    가격과 RSI 간 다이버전스를 감지하여 반전 매매 시그널을 생성한다.
    """

    STRATEGY_NAME = "RsiExtreme"
    STRATEGY_VERSION = "1.0"
    VIABLE = True
    TIER = 1
    CATEGORY = "mean_reversion"
    TAGS = ["rsi", "divergence", "oversold"]
    # 단일 지표 전략 — 다이버전스+극단 동시 충족이 너무 빡빡해 임계값 ±2로 완화
    # (RSI < 20 단독으로도 매수 가능하게)
    BUY_THRESHOLD = 2
    SELL_THRESHOLD = -2

    # RSI 설정
    RSI_PERIOD = 14
    # 다이버전스 탐지 비교 구간 (최근 N봉 내 이전 극단값 탐색)
    DIVERGENCE_LOOKBACK = 10

    def __init__(self, client, symbol: str):
        """
        전략 초기화.

        Args:
            client: CCXT 래퍼 클라이언트 (get_ohlcv, get_ticker 지원)
            symbol: 거래 심볼 (예: "BTC/USDT")
        """
        self.client = client
        self.symbol = symbol

    def _calc_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """RSI 14기간 계산."""
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.RSI_PERIOD).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        return df

    def _detect_bullish_divergence(self, df: pd.DataFrame) -> bool:
        """
        강세 다이버전스 감지.

        가격은 최근 저점보다 낮은데, RSI는 최근 저점보다 높은 경우.
        이는 매도 압력이 약해지고 있음을 의미하며 반등 신호로 해석.

        Returns:
            bool: 강세 다이버전스가 탐지되면 True
        """
        if len(df) < self.DIVERGENCE_LOOKBACK + 2:
            return False

        recent = df.iloc[-1]
        lookback = df.iloc[-(self.DIVERGENCE_LOOKBACK + 1):-1]

        # 이전 구간에서 RSI 최저점 찾기
        prev_rsi_low_idx = lookback["rsi"].idxmin()
        prev_rsi_low = lookback.loc[prev_rsi_low_idx, "rsi"]
        prev_price_low = lookback.loc[prev_rsi_low_idx, "close"]

        # 현재 가격이 이전 저점보다 낮지만, RSI는 이전 RSI 저점보다 높은 경우
        price_lower = recent["close"] < prev_price_low
        rsi_higher = recent["rsi"] > prev_rsi_low

        return price_lower and rsi_higher

    def _detect_bearish_divergence(self, df: pd.DataFrame) -> bool:
        """
        약세 다이버전스 감지.

        가격은 최근 고점보다 높은데, RSI는 최근 고점보다 낮은 경우.
        이는 매수 압력이 약해지고 있음을 의미하며 하락 신호로 해석.

        Returns:
            bool: 약세 다이버전스가 탐지되면 True
        """
        if len(df) < self.DIVERGENCE_LOOKBACK + 2:
            return False

        recent = df.iloc[-1]
        lookback = df.iloc[-(self.DIVERGENCE_LOOKBACK + 1):-1]

        # 이전 구간에서 RSI 최고점 찾기
        prev_rsi_high_idx = lookback["rsi"].idxmax()
        prev_rsi_high = lookback.loc[prev_rsi_high_idx, "rsi"]
        prev_price_high = lookback.loc[prev_rsi_high_idx, "close"]

        # 현재 가격이 이전 고점보다 높지만, RSI는 이전 RSI 고점보다 낮은 경우
        price_higher = recent["close"] > prev_price_high
        rsi_lower = recent["rsi"] < prev_rsi_high

        return price_higher and rsi_lower

    def analyze(self, timeframe: str = "1h") -> dict:
        """
        RSI 극단값 + 다이버전스 분석 실행.

        Args:
            timeframe: 캔들 타임프레임 (기본 "1h")

        Returns:
            dict: strategy, signal, scores, total, details
        """
        strategy_label = f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}"

        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=100)
        if not ohlcv:
            return {
                "strategy": strategy_label,
                "signal": "NO_DATA",
                "scores": {},
                "total": 0,
                "details": {},
            }

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = self._calc_rsi(df)
        df = df.dropna(subset=["rsi"])

        if len(df) < self.DIVERGENCE_LOOKBACK + 2:
            return {
                "strategy": strategy_label,
                "signal": "NO_DATA",
                "scores": {},
                "total": 0,
                "details": {},
            }

        latest = df.iloc[-1]
        rsi = latest["rsi"]

        # 다이버전스 탐지
        bullish_div = self._detect_bullish_divergence(df)
        bearish_div = self._detect_bearish_divergence(df)

        # 스코어 계산
        rsi_score = 0
        if rsi < 20 and bullish_div:
            rsi_score = 3  # RSI 극단 과매도 + 강세 다이버전스
        elif rsi < 20:
            rsi_score = 2  # RSI 극단 과매도
        elif rsi < 30:
            rsi_score = 1  # RSI 과매도
        elif rsi > 80 and bearish_div:
            rsi_score = -3  # RSI 극단 과매수 + 약세 다이버전스
        elif rsi > 80:
            rsi_score = -2  # RSI 극단 과매수
        elif rsi > 70:
            rsi_score = -1  # RSI 과매수

        scores = {"rsi_extreme": rsi_score}
        total = sum(scores.values())

        if total >= self.BUY_THRESHOLD:
            signal = "BUY"
        elif total <= self.SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        details = {
            "price": latest["close"],
            "rsi": round(rsi, 2),
            "bullish_divergence": bullish_div,
            "bearish_divergence": bearish_div,
            "rsi_zone": (
                "extreme_oversold" if rsi < 20
                else "oversold" if rsi < 30
                else "extreme_overbought" if rsi > 80
                else "overbought" if rsi > 70
                else "neutral"
            ),
        }

        logger.info(
            f"[{self.STRATEGY_NAME}] RSI={rsi:.1f} | "
            f"강세다이버전스={bullish_div} | 약세다이버전스={bearish_div} | "
            f"스코어={scores} | 합계={total} -> {signal}"
        )

        return {
            "strategy": strategy_label,
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
