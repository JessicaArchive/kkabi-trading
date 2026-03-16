"""
Fear & Greed Contrarian Strategy — 공포탐욕지수 역발상 전략

Crypto Fear & Greed Index (alternative.me, 0~100)를 활용한 역발상 매매.
"남들이 공포일 때 사라, 남들이 탐욕일 때 팔아라"

점수 체계 (-3 ~ +3):
  Extreme Fear  (0~19)   → +3 (강한 매수)
  Fear          (20~34)  → +1 (약한 매수)
  Neutral       (35~64)  →  0 (관망)
  Greed         (65~79)  → -1 (약한 매도)
  Extreme Greed (80~100) → -3 (강한 매도)

BUY/SELL 기준: 총점 ≥ +3 → BUY, ≤ -3 → SELL
→ 즉 Extreme 구간에서만 단독으로 시그널 발생
"""

import json
import urllib.request
import urllib.error
from typing import Optional
from exchange.client import ExchangeClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

FNG_API_URL = "https://api.alternative.me/fng/?limit=1&format=json"
FNG_API_TIMEOUT = 10


class FearGreedStrategy:
    """Crypto Fear & Greed Index 기반 역발상(Contrarian) 전략."""

    BUY_THRESHOLD = 3
    SELL_THRESHOLD = -3

    def __init__(self, client: ExchangeClient, symbol: str):
        self.client = client
        self.symbol = symbol

    def _fetch_fng(self) -> Optional[dict]:
        """Fear & Greed Index API 호출. 실패 시 None 반환."""
        try:
            req = urllib.request.Request(FNG_API_URL, headers={"User-Agent": "kkabi-trading/1.0"})
            with urllib.request.urlopen(req, timeout=FNG_API_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            entry = data["data"][0]
            return {
                "value": int(entry["value"]),
                "label": entry["value_classification"],
                "timestamp": int(entry["timestamp"]),
            }
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"Fear & Greed API 호출 실패: {e}")
            return None

    def _score_fng(self, fng_value: int) -> dict:
        """F&G 값(0~100)을 역발상 점수로 변환."""
        if fng_value <= 19:
            score = 3   # Extreme Fear → 강한 매수
        elif fng_value <= 34:
            score = 1   # Fear → 약한 매수
        elif fng_value <= 64:
            score = 0   # Neutral → 관망
        elif fng_value <= 79:
            score = -1  # Greed → 약한 매도
        else:
            score = -3  # Extreme Greed → 강한 매도
        return {"fear_greed": score}

    def analyze(self, timeframe: str = "1h") -> dict:
        """
        F&G 역발상 분석. timeframe은 인터페이스 호환용 (F&G는 일 1회 갱신).

        Returns:
            {signal, scores, total, details} — 기존 전략과 동일한 형식
        """
        # F&G 지수 조회
        fng = self._fetch_fng()
        if fng is None:
            return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}

        # 현재 가격 조회 (details용)
        try:
            ticker = self.client.get_ticker(self.symbol)
            price = ticker.get("last", 0)
        except Exception as e:
            logger.error(f"가격 조회 실패: {e}")
            price = 0

        # 점수 산정
        scores = self._score_fng(fng["value"])
        total = sum(scores.values())

        # 시그널 결정
        if total >= self.BUY_THRESHOLD:
            signal = "BUY"
        elif total <= self.SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        details = {
            "price": price,
            "fng_value": fng["value"],
            "fng_label": fng["label"],
        }

        logger.info(f"F&G={fng['value']} ({fng['label']}) | Score: {total:+d} -> {signal}")

        return {
            "signal": signal,
            "scores": scores,
            "total": total,
            "details": details,
        }
