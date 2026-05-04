"""
페이퍼 트레이딩 웹앱 (Flask).

단일 페이지: 활성 전략 목록 + 평가손익 + 최근 거래.
모바일 first, 다크 테마, Tailwind CDN, PWA manifest.

실행:
    python3 -m webapp.app                 # 0.0.0.0:5000 (Tailscale 포함)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory
from sqlalchemy import desc

from exchange.client import ExchangeClient
from paper.engine import PaperEngine
from paper.models import PaperStrategy, PaperTrade, SessionLocal, init_db

BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

# 페이퍼 엔진은 가격 조회용으로만 (시뮬레이션 X)
_client = ExchangeClient(exchange_name="upbit")


def _get_current_price() -> float | None:
    ticker = _client.get_ticker("BTC/KRW")
    return ticker.get("last") if ticker else None


def _strategy_summary(strategy: PaperStrategy, current_price: float | None) -> dict:
    """전략 1개 요약 dict."""
    if current_price:
        mtm = PaperEngine.mark_to_market(strategy, current_price)
        equity = mtm["equity"]
        pnl = mtm["pnl"]
        pnl_pct = mtm["pnl_pct"]
    else:
        equity = strategy.cash_krw
        pnl = equity - strategy.initial_krw
        pnl_pct = (pnl / strategy.initial_krw * 100) if strategy.initial_krw else 0

    return {
        "id": strategy.id,
        "name": strategy.name,
        "status": strategy.status,
        "started_at": strategy.started_at,
        "initial_krw": strategy.initial_krw,
        "cash_krw": strategy.cash_krw,
        "btc": strategy.btc,
        "avg_entry_price": strategy.avg_entry_price,
        "equity": equity,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "holding": strategy.btc > 0,
    }


@app.route("/")
def index():
    """전략 목록 메인 화면."""
    current_price = _get_current_price()

    with SessionLocal() as session:
        strategies = (
            session.query(PaperStrategy)
            .filter(PaperStrategy.status == "active")
            .order_by(PaperStrategy.id)
            .all()
        )
        summaries = [_strategy_summary(s, current_price) for s in strategies]

        # 최근 거래 5건 (전체)
        recent_trades_q = (
            session.query(PaperTrade, PaperStrategy)
            .join(PaperStrategy, PaperTrade.strategy_id == PaperStrategy.id)
            .order_by(desc(PaperTrade.time))
            .limit(5)
            .all()
        )
        recent_trades = [
            {
                "time": t.time,
                "strategy": s.name,
                "side": t.side,
                "price": t.price,
                "btc": t.btc,
                "realized_pnl": t.realized_pnl,
            }
            for t, s in recent_trades_q
        ]

        # 합산 — 가상 자산 총액 + 총 PnL
        total_initial = sum(s["initial_krw"] for s in summaries) or 1
        total_equity = sum(s["equity"] for s in summaries)
        total_pnl = total_equity - total_initial
        total_pnl_pct = total_pnl / total_initial * 100

    summaries.sort(key=lambda x: x["pnl_pct"], reverse=True)

    return render_template(
        "index.html",
        strategies=summaries,
        recent_trades=recent_trades,
        current_price=current_price,
        total_equity=total_equity,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        active_count=len(summaries),
        now=datetime.now(),
    )


@app.route("/api/health")
def health():
    return "ok", 200


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json", mimetype="application/manifest+json")


@app.route("/api/pnl")
def api_pnl():
    """JSON 응답 — 향후 폴링용 (phase 2)."""
    current_price = _get_current_price()
    with SessionLocal() as session:
        strategies = (
            session.query(PaperStrategy)
            .filter(PaperStrategy.status == "active")
            .all()
        )
        return jsonify(
            {
                "price": current_price,
                "strategies": [_strategy_summary(s, current_price) for s in strategies],
            }
        )


def main():
    import os
    init_db()
    # macOS 5000 = AirPlay Receiver 충돌, 8080 default. PORT 환경변수로 override 가능.
    port = int(os.getenv("PAPER_WEBAPP_PORT", "8080"))
    # 0.0.0.0 바인딩으로 Tailscale 100.85.76.9에서도 접근 가능
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
