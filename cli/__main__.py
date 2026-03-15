"""
Kkabi Trading CLI — Kkabi_c 직원봇에서 subprocess로 호출됨.

Usage:
    python3 -m cli show_config
    python3 -m cli show_price [SYMBOL]
    python3 -m cli analyze [SYMBOL]
    python3 -m cli backtest [SYMBOL]
"""
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


def show_config():
    print(
        f"⚙️ 현재 설정\n\n"
        f"거래소: {Config.EXCHANGE_NAME}\n"
        f"심볼: {Config.SYMBOL}\n"
        f"타임프레임: {Config.TIMEFRAME}\n"
        f"거래 금액: ${Config.TRADE_AMOUNT:,.0f}\n"
        f"손절: {Config.STOP_LOSS_PERCENT}%\n"
        f"익절: {Config.TAKE_PROFIT_PERCENT}%\n"
        f"루프 간격: {Config.LOOP_INTERVAL}s"
    )


def show_price(symbol=None):
    symbol = symbol or Config.SYMBOL
    try:
        from exchange.client import ExchangeClient

        client = ExchangeClient(
            exchange_name=Config.EXCHANGE_NAME,
            api_key=Config.API_KEY,
            api_secret=Config.API_SECRET,
        )
        ticker = client.get_ticker(symbol)
        if not ticker:
            print(f"❌ {symbol} 가격 조회 실패")
            return

        price = ticker["last"]
        change = ticker.get("percentage", 0) or 0
        high = ticker.get("high", 0)
        low = ticker.get("low", 0)
        volume = ticker.get("baseVolume", 0)

        emoji = "🟢" if change >= 0 else "🔴"
        print(
            f"📊 {symbol} 현재 현황\n\n"
            f"💰 가격: ${price:,.2f}\n"
            f"{emoji} 24h 변동: {change:+.2f}%\n"
            f"📈 24h 고가: ${high:,.2f}\n"
            f"📉 24h 저가: ${low:,.2f}\n"
            f"📦 24h 거래량: {volume:,.2f}"
        )
    except Exception as e:
        print(f"❌ 가격 조회 실패: {e}")


def analyze(symbol=None):
    symbol = symbol or Config.SYMBOL
    try:
        from exchange.client import ExchangeClient
        from strategy import create_strategy

        client = ExchangeClient(
            exchange_name=Config.EXCHANGE_NAME,
            api_key=Config.API_KEY,
            api_secret=Config.API_SECRET,
        )
        strategy = create_strategy(Config.STRATEGY, client, symbol)
        result = strategy.analyze(Config.TIMEFRAME)

        signal = result["signal"]
        total = result["total"]
        scores = result["scores"]
        details = result.get("details", {})

        signal_map = {"BUY": "🟢 매수", "SELL": "🔴 매도", "HOLD": "⚪ 관망"}
        signal_text = signal_map.get(signal, signal)

        score_lines = []
        for name, score in scores.items():
            direction = "↑" if score > 0 else "↓" if score < 0 else "→"
            score_lines.append(f"  {name.upper():<10} {score:+d} {direction}")

        detail_labels = {
            "price": ("가격", "${:,.2f}"),
            "sma_7": ("SMA7", "${:,.2f}"),
            "sma_25": ("SMA25", "${:,.2f}"),
            "sma_99": ("SMA99", "${:,.2f}"),
            "rsi": ("RSI", "{:.1f}"),
            "macd": ("MACD", "{:.4f}"),
            "macd_signal": ("MACD시그널", "{:.4f}"),
            "bb_position": ("BB위치", "{:.1%}"),
            "bb_width": ("BB폭", "{:.4f}"),
            "vol_ratio": ("거래량비", "{:.2f}x"),
            "zscore": ("Z-Score", "{:.3f}"),
            "stoch_rsi_k": ("StochRSI K", "{:.3f}"),
            "stoch_rsi_d": ("StochRSI D", "{:.3f}"),
            "atr_pct": ("ATR%", "{:.2f}%"),
            "atr_percentile": ("ATR순위", "{:.1%}"),
            "kc_position": ("KC위치", "{:.1%}"),
            "roc": ("ROC", "{:.2f}%"),
            # Ichimoku
            "tenkan": ("전환선", "${:,.2f}"),
            "kijun": ("기준선", "${:,.2f}"),
            "senkou_a": ("선행A", "${:,.2f}"),
            "senkou_b": ("선행B", "${:,.2f}"),
            "cloud_top": ("구름상단", "${:,.2f}"),
            "cloud_bottom": ("구름하단", "${:,.2f}"),
            "cloud_thickness": ("구름두께", "{:.4f}"),
        }
        detail_lines = []
        for key, val in details.items():
            label, fmt = detail_labels.get(key, (key, "{:.4f}"))
            detail_lines.append(f"  {label}: {fmt.format(val)}")

        print(
            f"📊 {symbol} 전략 분석\n"
            f"타임프레임: {Config.TIMEFRAME}\n\n"
            f"시그널: {signal_text}\n"
            f"총 점수: {total:+d} (매수≥3, 매도≤-3)\n\n"
            f"지표별 점수:\n" + "\n".join(score_lines) + "\n\n"
            f"상세 지표:\n" + "\n".join(detail_lines)
        )
    except Exception as e:
        print(f"❌ 분석 실패: {e}")


def backtest(symbol=None):
    symbol = symbol or Config.SYMBOL
    try:
        import pandas as pd
        import time as _time
        from exchange.client import ExchangeClient
        from backtest.engine import BacktestEngine

        client = ExchangeClient(
            exchange_name=Config.EXCHANGE_NAME,
            api_key=Config.API_KEY,
            api_secret=Config.API_SECRET,
        )

        days = 30
        since = int((_time.time() - days * 86400) * 1000)
        all_data = []
        while len(all_data) < days * 24:
            batch = client.exchange.fetch_ohlcv(
                symbol, Config.TIMEFRAME, since=since, limit=1000
            )
            if not batch:
                break
            all_data.extend(batch)
            since = batch[-1][0] + 1
            if len(batch) < 1000:
                break

        df = pd.DataFrame(
            all_data, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        engine = BacktestEngine(
            initial_capital=10000.0,
            stop_loss_pct=Config.STOP_LOSS_PERCENT,
            take_profit_pct=Config.TAKE_PROFIT_PERCENT,
        )
        result = engine.run(df)

        if "error" in result:
            print(f"❌ {result['error']}")
            return

        m = result["metrics"]
        emoji = "🟢" if m["total_return_pct"] >= 0 else "🔴"
        print(
            f"📊 30일 백테스트 결과\n"
            f"{symbol} | {Config.TIMEFRAME}\n\n"
            f"💰 시작: $10,000.00\n"
            f"{emoji} 최종: ${m['final_equity']:,.2f}\n"
            f"{emoji} 수익률: {m['total_return_pct']:+.2f}%\n\n"
            f"📈 거래 횟수: {m['total_trades']}\n"
            f"✅ 승률: {m['win_rate_pct']:.1f}%\n"
            f"💪 평균 수익: ${m['avg_win']:,.2f}\n"
            f"💀 평균 손실: ${m['avg_loss']:,.2f}\n"
            f"📊 Profit Factor: {m['profit_factor']:.2f}\n\n"
            f"⚠️ Max Drawdown: {m['max_drawdown_pct']:.2f}%\n"
            f"📐 Sharpe Ratio: {m['sharpe_ratio']:.2f}"
        )
    except Exception as e:
        print(f"❌ 백테스트 실패: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m cli <command> [args]")
        print("Commands: show_config, show_price, analyze, backtest")
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "show_config":
        show_config()
    elif cmd == "show_price":
        show_price(args)
    elif cmd == "analyze":
        analyze(args)
    elif cmd == "backtest":
        backtest(args)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
