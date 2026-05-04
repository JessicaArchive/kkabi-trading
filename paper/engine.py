"""
페이퍼 트레이딩 엔진.

매시간 정각에 모든 활성 전략에 대해:
1. analyze("1h") 호출 → BUY/SELL/HOLD 시그널
2. 시그널에 따라 시뮬레이션 매수/매도 (compound 자본 모델)
3. 결과를 paper_trades / paper_signals에 기록

가격은 ccxt ticker.last 사용 (자동매매와 동일).
수수료: 업비트 KRW 마켓 0.05% × 2회 (매수/매도 각각).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config import Config
from exchange.client import ExchangeClient
from paper.models import (
    PaperSignal,
    PaperStrategy,
    PaperTrade,
    SessionLocal,
    init_db,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)

UPBIT_KRW_FEE_RATE = 0.0005  # 0.05%


class PaperEngine:
    """페이퍼 트레이딩 시뮬레이션 엔진."""

    def __init__(self, symbol: str = "BTC/KRW", timeframe: str = "1h"):
        self.symbol = symbol
        self.timeframe = timeframe
        # 페이퍼 트레이딩은 인증 불필요 — public API만 사용 (ticker, OHLCV)
        self.client = ExchangeClient(exchange_name="upbit")

    # ── 가격 조회 ─────────────────────────────────────

    def get_current_price(self) -> Optional[float]:
        """현재가 조회 (ccxt ticker.last)."""
        ticker = self.client.get_ticker(self.symbol)
        if not ticker:
            return None
        return ticker.get("last")

    # ── 전략 인스턴스화 ────────────────────────────────

    def load_strategy_instance(self, source: str):
        """source 문자열로 전략 클래스를 찾아 인스턴스화.

        source 형식:
        - "registry:<key>"      — 기존 strategies/ 폴더의 STRATEGIES dict 사용
        - "generated:<file>"    — strategies_generated/<file>.py (phase 2)
        """
        if source.startswith("registry:"):
            key = source.split(":", 1)[1]
            from strategies import STRATEGIES

            cls = STRATEGIES.get(key)
            if cls is None:
                raise ValueError(f"전략 키를 찾을 수 없음: {key}")
            return cls(self.client, self.symbol)

        if source.startswith("generated:"):
            # phase 2에서 구현 예정
            raise NotImplementedError("generated 전략 로드는 phase 2")

        raise ValueError(f"지원하지 않는 source 형식: {source}")

    # ── 시뮬레이션: 매수 ──────────────────────────────

    def simulate_buy(
        self,
        session,
        strategy: PaperStrategy,
        price: float,
        score: int,
    ) -> Optional[PaperTrade]:
        """현재 cash 전액으로 시장가 매수 시뮬레이션."""
        if strategy.btc > 0:
            return None  # 이미 보유 중

        # 사용 가능한 KRW 전액으로 매수 (수수료 차감 후)
        cash = strategy.cash_krw
        if cash < 5000:  # 최소 거래 금액 미만
            return None

        # 수수료를 가격에 포함시켜 계산
        # cash = btc * price + fee_paid = btc * price * (1 + fee_rate)
        # → btc = cash / (price * (1 + fee_rate))
        btc_amount = cash / (price * (1 + UPBIT_KRW_FEE_RATE))
        # 사토시 단위 절삭 (실거래와 일관성)
        btc_amount = int(btc_amount * 1e8) / 1e8
        if btc_amount <= 0:
            return None

        gross_krw = btc_amount * price
        fee = gross_krw * UPBIT_KRW_FEE_RATE
        total_paid = gross_krw + fee  # 실제 cash에서 빠지는 금액

        # 포지션 업데이트
        strategy.cash_krw = cash - total_paid
        strategy.btc = btc_amount
        strategy.avg_entry_price = price

        trade = PaperTrade(
            strategy_id=strategy.id,
            side="buy",
            price=price,
            btc=btc_amount,
            krw_gross=gross_krw,
            fee=fee,
            krw_net=total_paid,  # 실제 차감액
            realized_pnl=None,
            score=score,
        )
        session.add(trade)
        logger.info(
            f"[{strategy.name}] 매수 {btc_amount:.8f} BTC @ ₩{price:,.0f} "
            f"(수수료 ₩{fee:,.0f}, 잔액 ₩{strategy.cash_krw:,.0f})"
        )
        return trade

    # ── 시뮬레이션: 매도 ──────────────────────────────

    def simulate_sell(
        self,
        session,
        strategy: PaperStrategy,
        price: float,
        score: int,
    ) -> Optional[PaperTrade]:
        """보유 BTC 전량 시장가 매도 시뮬레이션."""
        if strategy.btc <= 0:
            return None  # 보유 없음

        btc_amount = strategy.btc
        entry_price = strategy.avg_entry_price

        gross_krw = btc_amount * price
        fee = gross_krw * UPBIT_KRW_FEE_RATE
        net_proceeds = gross_krw - fee  # 실제 수령액

        # 실현 PnL (매수 수수료는 이미 cash에서 차감됐으니 entry로 계산)
        # 매수 시 entry로 산 비용 (수수료 포함) = btc * entry * (1 + fee_rate)
        # 매도 시 회수 = btc * price * (1 - fee_rate)
        cost_basis = btc_amount * entry_price * (1 + UPBIT_KRW_FEE_RATE)
        realized_pnl = net_proceeds - cost_basis

        # 포지션 업데이트 (compound: cash에 매도 대금 합산)
        strategy.cash_krw = strategy.cash_krw + net_proceeds
        strategy.btc = 0.0
        strategy.avg_entry_price = 0.0

        trade = PaperTrade(
            strategy_id=strategy.id,
            side="sell",
            price=price,
            btc=btc_amount,
            krw_gross=gross_krw,
            fee=fee,
            krw_net=net_proceeds,
            realized_pnl=realized_pnl,
            score=score,
        )
        session.add(trade)
        pnl_pct = (realized_pnl / cost_basis * 100) if cost_basis else 0
        logger.info(
            f"[{strategy.name}] 매도 {btc_amount:.8f} BTC @ ₩{price:,.0f} "
            f"(PnL ₩{realized_pnl:+,.0f} / {pnl_pct:+.2f}%)"
        )
        return trade

    # ── Mark-to-market 평가손익 ────────────────────────

    @staticmethod
    def mark_to_market(strategy: PaperStrategy, current_price: float) -> dict:
        """현재가 기준 평가손익 계산 (DB 저장 X, 화면 표시용)."""
        unrealized_btc_value = strategy.btc * current_price
        if strategy.btc > 0:
            # 매도 시 받게 될 금액 (수수료 차감)
            potential_proceeds = unrealized_btc_value * (1 - UPBIT_KRW_FEE_RATE)
        else:
            potential_proceeds = 0
        equity = strategy.cash_krw + potential_proceeds
        pnl = equity - strategy.initial_krw
        pnl_pct = (pnl / strategy.initial_krw * 100) if strategy.initial_krw else 0
        return {
            "equity": equity,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "btc_value": unrealized_btc_value,
        }

    # ── 메인 사이클 ────────────────────────────────────

    def tick(self) -> dict:
        """매시간 1회 호출. 모든 활성 전략 평가 + 시뮬레이션."""
        price = self.get_current_price()
        if price is None:
            logger.error("현재가 조회 실패 — 사이클 skip")
            return {"status": "skip", "reason": "no_price"}

        results = {"price": price, "evaluated": 0, "trades": 0, "errors": 0}

        with SessionLocal() as session:
            active = (
                session.query(PaperStrategy)
                .filter(PaperStrategy.status == "active")
                .all()
            )

            for strategy in active:
                try:
                    instance = self.load_strategy_instance(strategy.source)
                    result = instance.analyze(self.timeframe)
                    signal = result.get("signal", "HOLD")
                    score = int(result.get("total", 0))

                    # 시그널 로그 (HOLD 포함)
                    session.add(
                        PaperSignal(
                            strategy_id=strategy.id,
                            signal=signal,
                            score=score,
                            price=price,
                        )
                    )

                    # 시그널에 따라 시뮬레이션
                    if signal == "BUY" and strategy.btc == 0:
                        if self.simulate_buy(session, strategy, price, score):
                            results["trades"] += 1
                    elif signal == "SELL" and strategy.btc > 0:
                        if self.simulate_sell(session, strategy, price, score):
                            results["trades"] += 1
                    # HOLD/NO_DATA: 아무 액션 없음

                    results["evaluated"] += 1

                except Exception as e:
                    logger.exception(f"[{strategy.name}] 분석 오류: {e}")
                    session.add(
                        PaperSignal(
                            strategy_id=strategy.id,
                            signal="ERROR",
                            score=0,
                            price=price,
                        )
                    )
                    results["errors"] += 1

            session.commit()

        logger.info(
            f"tick 완료: 평가 {results['evaluated']}개, "
            f"거래 {results['trades']}건, 오류 {results['errors']}개, "
            f"가격 ₩{price:,.0f}"
        )
        return results


def run_tick():
    """CLI/cron 진입점."""
    init_db()
    engine = PaperEngine()
    return engine.tick()


if __name__ == "__main__":
    run_tick()
