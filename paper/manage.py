"""
페이퍼 트레이딩 전략 관리 CLI.

기존 strategies/ 폴더의 70개 VIABLE 전략 중 선택해서 페이퍼에 등록한다.

사용법:
    python3 -m paper.manage list                    # 활성 페이퍼 전략 목록
    python3 -m paper.manage available [--category C] # 등록 가능한 전략 목록
    python3 -m paper.manage register <key> [<key>...] # 1개 이상 등록
    python3 -m paper.manage stop <id>               # 전략 중지
"""

from __future__ import annotations

import argparse
from datetime import datetime

from paper.models import PaperStrategy, SessionLocal, init_db


def cmd_list(args):
    """현재 등록된 페이퍼 전략 목록."""
    with SessionLocal() as session:
        strategies = (
            session.query(PaperStrategy).order_by(PaperStrategy.id).all()
        )
        if not strategies:
            print("(등록된 전략 없음)")
            return
        for s in strategies:
            print(
                f"  #{s.id} [{s.status}] {s.name}  "
                f"cash=₩{s.cash_krw:,.0f} btc={s.btc:.8f}  "
                f"source={s.source}  started={s.started_at:%Y-%m-%d}"
            )


def cmd_available(args):
    """strategies/ 레지스트리에서 등록 가능한 전략 목록."""
    from strategies import STRATEGIES

    items = []
    for key, cls in STRATEGIES.items():
        category = getattr(cls, "CATEGORY", "?")
        if args.category and category != args.category:
            continue
        items.append((key, cls.__name__, category))

    items.sort(key=lambda x: (x[2], x[0]))
    cat = None
    for key, name, category in items:
        if category != cat:
            print(f"\n[{category}]")
            cat = category
        print(f"  {key:30s} → {name}")
    print(f"\n총 {len(items)}개")


def cmd_register(args):
    """전략 1개 이상 페이퍼에 등록."""
    from strategies import STRATEGIES

    init_db()
    keys = args.keys

    with SessionLocal() as session:
        registered = []
        for key in keys:
            cls = STRATEGIES.get(key)
            if cls is None:
                print(f"  ❌ 키 없음: {key}")
                continue

            # 이미 같은 source로 active 등록 있는지 체크
            existing = (
                session.query(PaperStrategy)
                .filter(
                    PaperStrategy.source == f"registry:{key}",
                    PaperStrategy.status == "active",
                )
                .first()
            )
            if existing:
                print(f"  ⚠️  이미 등록됨 (#{existing.id}): {key}")
                continue

            name = getattr(cls, "STRATEGY_NAME", cls.__name__)
            strategy = PaperStrategy(
                name=name,
                source=f"registry:{key}",
                started_at=datetime.utcnow(),
                initial_krw=args.capital,
                cash_krw=args.capital,
                btc=0.0,
                avg_entry_price=0.0,
                status="active",
            )
            session.add(strategy)
            registered.append(key)
            print(f"  ✅ 등록: {key} → {name} (자본 ₩{args.capital:,.0f})")

        session.commit()

    if registered:
        print(f"\n총 {len(registered)}개 등록 완료")


def cmd_stop(args):
    """전략 중지 (페이퍼 사이클에서 제외)."""
    with SessionLocal() as session:
        strategy = session.query(PaperStrategy).get(args.id)
        if strategy is None:
            print(f"❌ 전략 없음: #{args.id}")
            return
        strategy.status = "stopped"
        session.commit()
        print(f"✅ 중지: #{args.id} {strategy.name}")


def main():
    parser = argparse.ArgumentParser(description="Paper trading 전략 관리")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="활성 전략 목록")
    p_list.set_defaults(func=cmd_list)

    p_avail = sub.add_parser("available", help="등록 가능한 전략 목록")
    p_avail.add_argument("--category", help="카테고리 필터 (예: momentum)")
    p_avail.set_defaults(func=cmd_available)

    p_reg = sub.add_parser("register", help="전략 등록")
    p_reg.add_argument("keys", nargs="+", help="strategies/ 레지스트리 키들")
    p_reg.add_argument("--capital", type=float, default=100000.0, help="가상 자본 KRW")
    p_reg.set_defaults(func=cmd_register)

    p_stop = sub.add_parser("stop", help="전략 중지")
    p_stop.add_argument("id", type=int)
    p_stop.set_defaults(func=cmd_stop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
