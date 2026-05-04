"""
페이퍼 트레이딩 SQLAlchemy 모델.

기존 kkabi.db에 paper_* prefix 테이블로 추가. 자동매매 시스템과 격리.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "kkabi.db"
ENGINE = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False, future=True)
Base = declarative_base()


class PaperCandidate(Base):
    """AI가 생성한 전략 후보 (phase 2). 지금은 빈 테이블만 준비."""

    __tablename__ = "paper_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    name = Column(String, nullable=False)
    description_ko = Column(String, nullable=False, default="")
    code = Column(String, nullable=False, default="")
    hypothesis_ko = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="pending")  # pending|selected|rejected
    selected_at = Column(DateTime)
    rejection_reason = Column(String)


class PaperStrategy(Base):
    """페이퍼 트레이딩 활성 전략."""

    __tablename__ = "paper_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("paper_candidates.id"), nullable=True)
    name = Column(String, nullable=False)              # 전략 이름 (사람이 보는)
    source = Column(String, nullable=False)            # "registry:<key>" or "generated:<file>"
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    initial_krw = Column(Float, nullable=False, default=100000.0)
    cash_krw = Column(Float, nullable=False, default=100000.0)
    btc = Column(Float, nullable=False, default=0.0)
    avg_entry_price = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="active")  # active|paused|stopped
    note = Column(String)                              # 사람이 본인 메모 (선택)

    trades = relationship("PaperTrade", back_populates="strategy", cascade="all, delete-orphan")
    signals = relationship("PaperSignal", back_populates="strategy", cascade="all, delete-orphan")


class PaperTrade(Base):
    """체결 거래 (BUY/SELL)."""

    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("paper_strategies.id"), nullable=False)
    time = Column(DateTime, default=datetime.utcnow, nullable=False)
    side = Column(String, nullable=False)              # buy|sell
    price = Column(Float, nullable=False)              # 체결가
    btc = Column(Float, nullable=False)                # 거래 BTC 수량
    krw_gross = Column(Float, nullable=False)          # price * btc (수수료 전)
    fee = Column(Float, nullable=False)                # 수수료 KRW
    krw_net = Column(Float, nullable=False)            # buy: gross+fee 차감 / sell: gross-fee 입금
    realized_pnl = Column(Float)                       # 매도 시만 (매수는 NULL)
    score = Column(Integer, nullable=False, default=0)
    note = Column(String)

    strategy = relationship("PaperStrategy", back_populates="trades")


class PaperSignal(Base):
    """매시간 시그널 로그 (HOLD 포함, 디버그/회고용)."""

    __tablename__ = "paper_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("paper_strategies.id"), nullable=False)
    time = Column(DateTime, default=datetime.utcnow, nullable=False)
    signal = Column(String, nullable=False)            # BUY|SELL|HOLD|NO_DATA|ERROR
    score = Column(Integer)
    price = Column(Float)

    strategy = relationship("PaperStrategy", back_populates="signals")


Index("idx_trades_strategy_time", PaperTrade.strategy_id, PaperTrade.time)
Index("idx_signals_strategy_time", PaperSignal.strategy_id, PaperSignal.time)


def init_db():
    """테이블 생성 (이미 있으면 skip)."""
    Base.metadata.create_all(ENGINE)


if __name__ == "__main__":
    init_db()
    print(f"OK: paper_* tables ready in {DB_PATH}")
