"""
CLI bridge for kkabi-trading.

Node.js (trading.ts) 에서 호출:
  python3 -m cli <action> [args]

Actions:
  show_config          현재 트레이딩 설정 출력
  show_price [SYMBOL]  현재 가격 조회
  analyze [SYMBOL]     5개 전략 멀티 시그널 분석
  backtest [--days N]  백테스트 실행
"""

import sys
import json
from datetime import datetime
from typing import Optional, List

from config import Config
from exchange.client import ExchangeClient
from strategy import create_strategy


def _make_client() -> ExchangeClient:
    return ExchangeClient(Config.EXCHANGE_NAME, Config.API_KEY, Config.API_SECRET)


def _signal_emoji(signal: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪", "NO_DATA": "⚠️"}.get(signal, "❓")


def _score_bar(score: int, max_val: int = 2) -> str:
    if score > 0:
        return "+" * score + "·" * (max_val - score)
    elif score < 0:
        return "-" * abs(score) + "·" * (max_val - abs(score))
    else:
        return "·" * max_val


def show_config():
    lines = [
        "⚙️ Trading Config",
        f"  거래소: {Config.EXCHANGE_NAME}",
        f"  심볼: {Config.SYMBOL}",
        f"  타임프레임: {Config.TIMEFRAME}",
        f"  거래금액: ${Config.TRADE_AMOUNT}",
        f"  손절: {Config.STOP_LOSS_PERCENT}%",
        f"  익절: {Config.TAKE_PROFIT_PERCENT}%",
        f"  최대손실: {Config.MAX_LOSS_PERCENT}%",
        f"  루프: {'OFF (단발)' if Config.LOOP_INTERVAL == 0 else f'{Config.LOOP_INTERVAL}초'}",
    ]
    print("\n".join(lines))


def show_price(symbol: Optional[str] = None):
    symbol = symbol or Config.SYMBOL
    client = _make_client()
    ticker = client.get_ticker(symbol)
    if not ticker:
        print(f"❌ {symbol} 가격 조회 실패")
        return

    price = ticker.get("last", 0)
    bid = ticker.get("bid", 0)
    ask = ticker.get("ask", 0)
    spread = ask - bid if bid and ask else 0

    lines = [
        f"💰 {symbol}",
        f"  현재가: ${price:,.2f}",
        f"  매수호가: ${bid:,.2f}",
        f"  매도호가: ${ask:,.2f}",
        f"  스프레드: ${spread:,.2f}",
    ]
    print("\n".join(lines))


def _run_strategy(name: str, client, symbol: str) -> dict:
    """전략 하나를 실행하고 결과 반환. 실패 시 NO_DATA."""
    try:
        s = create_strategy(name, client, symbol)
        return s.analyze(Config.TIMEFRAME)
    except Exception:
        return {"signal": "NO_DATA", "scores": {}, "total": 0, "details": {}}


# 전략 목록: (key, 표시이름, 최대점수)
STRATEGY_LIST = [
    ("base", "PentaScore", 9),
    ("fear_greed", "FearGreed", 2),
    ("ichimoku", "Ichimoku", 8),
    ("mean_reversion", "MeanRevert", 10),
    ("breakout_hunter", "Breakout", 10),
]


def analyze(symbol: Optional[str] = None):
    symbol = symbol or Config.SYMBOL
    client = _make_client()

    # 전 전략 분석
    results = {}
    for name, _, _ in STRATEGY_LIST:
        results[name] = _run_strategy(name, client, symbol)

    p = results["base"]
    d = p.get("details", {})
    price = d.get("price", 0)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 {symbol} 분석 ({now})",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"  가격: ${price:,.2f}",
        f"",
        f"🎯 전략별 시그널:",
    ]

    # 전략 요약 테이블
    buy_count = 0
    sell_count = 0
    for name, label, max_score in STRATEGY_LIST:
        r = results[name]
        sig = r.get("signal", "NO_DATA")
        total = r.get("total", 0)
        emoji = _signal_emoji(sig)
        lines.append(f"  {emoji} {label:<13} {sig:<5} ({total:+d}/{max_score})")
        if sig == "BUY":
            buy_count += 1
        elif sig == "SELL":
            sell_count += 1

    # 합산 판정
    lines.append(f"")
    lines.append(f"  📢 BUY: {buy_count}개 / SELL: {sell_count}개 / 5개 전략")

    # PentaScore 세부
    scores = p.get("scores", {})
    lines.append(f"")
    lines.append(f"📈 PentaScore 지표별:")

    indicator_names = {
        "sma": ("SMA", "이동평균"),
        "macd": ("MACD", "모멘텀"),
        "bollinger": ("BB", "볼린저"),
        "rsi": ("RSI", "과매수/과매도"),
        "volume": ("VOL", "거래량"),
    }
    for key, (short, desc) in indicator_names.items():
        s = scores.get(key, 0)
        max_v = 1 if key == "volume" else 2
        bar = _score_bar(s, max_v)
        lines.append(f"  {short:>4} [{bar}] {s:+d}  ({desc})")

    # 세부 지표
    if d:
        lines.append("")
        lines.append("📋 세부 지표:")
        if "rsi" in d:
            lines.append(f"  RSI: {d['rsi']}")
        if "sma_7" in d and "sma_25" in d and "sma_99" in d:
            lines.append(f"  SMA: {d['sma_7']:,.0f} / {d['sma_25']:,.0f} / {d['sma_99']:,.0f}")
        if "macd" in d and "macd_signal" in d:
            lines.append(f"  MACD: {d['macd']:.4f} (신호선: {d['macd_signal']:.4f})")
        if "bb_position" in d:
            lines.append(f"  볼린저 위치: {d['bb_position']:.1%}")
        if "vol_ratio" in d:
            lines.append(f"  거래량 비율: {d['vol_ratio']:.2f}x")

    # Fear & Greed 세부
    fg = results["fear_greed"]
    fd = fg.get("details", {})
    if fd.get("fng_value") is not None:
        fng_val = fd["fng_value"]
        fng_label = fd.get("fng_label", "")
        lines.append("")
        lines.append(f"😱 공포탐욕지수: {fng_val}/100 ({fng_label})")

    # Ichimoku 세부
    ichi = results["ichimoku"]
    id_ = ichi.get("details", {})
    if id_.get("tenkan") is not None:
        lines.append("")
        lines.append(f"⛩️ Ichimoku:")
        lines.append(f"  전환선: ${id_['tenkan']:,.2f} / 기준선: ${id_['kijun']:,.2f}")
        lines.append(f"  구름: ${id_['cloud_bottom']:,.2f} ~ ${id_['cloud_top']:,.2f}")

    # MeanRevert 세부
    mr = results["mean_reversion"]
    md = mr.get("details", {})
    if md.get("zscore") is not None:
        lines.append("")
        lines.append(f"📉 MeanRevert:")
        lines.append(f"  Z-Score: {md['zscore']:+.3f} / StochRSI: {md.get('stoch_rsi_k', 0):.3f}")
        lines.append(f"  Keltner위치: {md.get('kc_position', 0):.1%}")

    # Breakout 세부
    bo = results["breakout_hunter"]
    bd = bo.get("details", {})
    if bd.get("adx") is not None:
        lines.append("")
        lines.append(f"💥 Breakout:")
        lines.append(f"  ADX: {bd['adx']:.1f} / Squeeze: {'ON' if bd.get('squeeze_on') else 'OFF'}")
        lines.append(f"  Donchian위치: {bd.get('dc_position', 0):.1%}")

    print("\n".join(lines))


def backtest(args: List[str]):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--capital", type=float, default=10000.0)
    parsed = parser.parse_args(args)

    client = _make_client()
    strategy = create_strategy("base", client, Config.SYMBOL)

    # OHLCV 데이터 가져오기
    limit = parsed.days * 24  # 1h 캔들 기준
    ohlcv = client.get_ohlcv(Config.SYMBOL, Config.TIMEFRAME, limit=limit)
    if not ohlcv:
        print(f"❌ {Config.SYMBOL} OHLCV 데이터 조회 실패")
        return

    import pandas as pd
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

    from backtest.engine import BacktestEngine
    engine = BacktestEngine(
        initial_capital=parsed.capital,
        stop_loss_pct=Config.STOP_LOSS_PERCENT,
        take_profit_pct=Config.TAKE_PROFIT_PERCENT,
    )
    result = engine.run(df)
    m = result.get("metrics", {})

    lines = [
        f"📉 백테스트 결과 ({Config.SYMBOL}, {parsed.days}일)",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"  초기자본: ${m.get('initial_capital', parsed.capital):,.0f}",
        f"  최종자산: ${m.get('final_equity', 0):,.0f}",
        f"  수익률: {m.get('total_return_pct', 0):+.1f}%",
        f"",
        f"  총 거래: {m.get('total_trades', 0)}회",
        f"  승률: {m.get('win_rate_pct', 0):.1f}%",
        f"  승: {m.get('winning_trades', 0)} / 패: {m.get('losing_trades', 0)}",
        f"  평균 수익: ${m.get('avg_win', 0):,.0f} / 평균 손실: ${m.get('avg_loss', 0):,.0f}",
        f"",
        f"  Profit Factor: {m.get('profit_factor', 0):.2f}",
        f"  최대 낙폭: {m.get('max_drawdown_pct', 0):.1f}%",
        f"  샤프 비율: {m.get('sharpe_ratio', 0):.2f}",
    ]
    print("\n".join(lines))


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m cli <action> [args]")
        print("Actions: show_config, show_price, analyze, backtest")
        sys.exit(1)

    action = sys.argv[1]
    rest = sys.argv[2:]

    try:
        if action == "show_config":
            show_config()
        elif action == "show_price":
            show_price(rest[0] if rest else None)
        elif action == "analyze":
            analyze(rest[0] if rest else None)
        elif action == "backtest":
            backtest(rest)
        else:
            print(f"❌ 알 수 없는 액션: {action}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
