"""
ChandeMomentumStrategy — Chande Momentum Oscillator (CMO) 전략

## 개요
CMO(Chande Momentum Oscillator)는 Tushar Chande가 개발한 정규화 모멘텀 지표다.
RSI와 달리 상승 합계와 하락 합계를 직접 비교하여 -100 ~ +100 범위로 정규화한다.

RSI가 상승 이동평균만 분모에 넣는 반면, CMO는 전체 이동합(상승+하락)을 분모로 써서
시장의 전반적 활동성 대비 방향성을 측정한다. 이 덕분에 RSI보다 민감하고 극단적 값에
더 빠르게 도달한다.

## 계산 공식
Su = 상승 마감한 봉의 변화량 합 (N기간)
Sd = 하락 마감한 봉의 |변화량| 합 (N기간)

CMO = ((Su - Sd) / (Su + Sd)) × 100

기본 파라미터: 기간 N=14

## 해석
- CMO > +50: 강한 상승 모멘텀 (과매수 주의)
- CMO > +25: 온건한 상승 모멘텀
- -25 < CMO < +25: 중립 (횡보 구간)
- CMO < -25: 온건한 하락 모멘텀
- CMO < -50: 강한 하락 모멘텀 (과매도 — 반등 주의)

## 스코어링 로직
| 조건 | 점수 |
|------|------|
| CMO > +50 | +2 |
| CMO > +25 (이하 조건 불충족) | +1 |
| CMO < -50 | -2 |
| CMO < -25 (이하 조건 불충족) | -1 |
| -25 ≤ CMO ≤ +25 | 0 |

총 스코어 범위: -2 ~ +2
"""

import pandas as pd
import numpy as np
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ChandeMomentumStrategy:
    """
    Chande Momentum Oscillator (CMO, 14기간) 전략.

    -100 ~ +100 정규화 범위에서 모멘텀의 방향성과 강도를 동시에 측정한다.
    """

    STRATEGY_NAME = "ChandeMomentum"
    STRATEGY_VERSION = "1.0"
    VIABLE = True
    TIER = 2
    CATEGORY = "momentum"
    TAGS = ["cmo", "chande", "normalized"]

    # 단일 지표 전략 — 점수 범위 ±2에 맞춰 임계값 조정 (원본 ±3은 시그널 발생 불가능)
    BUY_THRESHOLD = 2
    SELL_THRESHOLD = -2

    # CMO 파라미터
    CMO_PERIOD = 14

    # 스코어 임계값
    STRONG_THRESHOLD = 50
    MILD_THRESHOLD = 25

    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol

    def _calc_cmo(self, df: pd.DataFrame) -> pd.DataFrame:
        """CMO 계산."""
        diff = df["close"].diff()

        # 상승분 / 하락분 분리
        up = diff.where(diff > 0, 0.0)
        down = (-diff).where(diff < 0, 0.0)

        su = up.rolling(window=self.CMO_PERIOD).sum()
        sd = down.rolling(window=self.CMO_PERIOD).sum()

        total = su + sd
        # 분모가 0인 경우(변동 없음) 처리
        df["cmo"] = np.where(total != 0, (su - sd) / total * 100, 0.0)

        return df

    def _score_signals(self, df: pd.DataFrame) -> dict:
        """CMO 값 기준 스코어 산출."""
        latest = df.iloc[-1]
        scores = {}

        cmo = latest["cmo"]

        if cmo > self.STRONG_THRESHOLD:
            scores["cmo"] = 2
        elif cmo > self.MILD_THRESHOLD:
            scores["cmo"] = 1
        elif cmo < -self.STRONG_THRESHOLD:
            scores["cmo"] = -2
        elif cmo < -self.MILD_THRESHOLD:
            scores["cmo"] = -1
        else:
            scores["cmo"] = 0

        return scores

    def analyze(self, timeframe: str = "1h") -> dict:
        """
        CMO 분석 실행.

        Args:
            timeframe: 캔들 타임프레임 (기본값 "1h")

        Returns:
            dict: strategy, signal, scores, total, details
        """
        ohlcv = self.client.get_ohlcv(self.symbol, timeframe, limit=50)
        if not ohlcv:
            return {
                "strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}",
                "signal": "NO_DATA",
                "scores": {},
                "total": 0,
                "details": {},
            }

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = self._calc_cmo(df)
        df = df.dropna()

        if len(df) < 1:
            return {
                "strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}",
                "signal": "NO_DATA",
                "scores": {},
                "total": 0,
                "details": {},
            }

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
            "cmo": round(latest["cmo"], 2),
            "interpretation": (
                "강한 상승 모멘텀" if latest["cmo"] > self.STRONG_THRESHOLD else
                "온건한 상승 모멘텀" if latest["cmo"] > self.MILD_THRESHOLD else
                "강한 하락 모멘텀" if latest["cmo"] < -self.STRONG_THRESHOLD else
                "온건한 하락 모멘텀" if latest["cmo"] < -self.MILD_THRESHOLD else
                "중립 횡보"
            ),
        }

        logger.info(
            f"[{self.STRATEGY_NAME}] Scores: {scores} | Total: {total} -> {signal} | "
            f"CMO={details['cmo']} ({details['interpretation']})"
        )

        return {
            "strategy": f"{self.STRATEGY_NAME} v{self.STRATEGY_VERSION}",
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
