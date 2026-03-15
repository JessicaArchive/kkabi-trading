"""
Signal Daemon — tmux에서 상주하며 주기적으로 시그널 분석 후 텔레그램 알림.

사용법:
    tmux new -s kkabi-signal
    python signal_daemon.py
    # Ctrl+B, D 로 detach
"""

import time
import asyncio
import telegram
from config import Config
from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from strategy.ichimoku import IchimokuStrategy
from utils.logger import setup_logger

logger = setup_logger("signal_daemon")

LOOP_INTERVAL = 3600  # 1시간 (초)
FOURH_EVERY = 4       # 4루프마다 4시간봉 분석


def create_client() -> ExchangeClient:
    return ExchangeClient(
        exchange_name=Config.EXCHANGE_NAME,
        api_key=Config.API_KEY,
        api_secret=Config.API_SECRET,
    )


def format_penta_message(result: dict, timeframe: str) -> str:
    signal = result["signal"]
    total = result["total"]
    scores = result["scores"]
    details = result.get("details", {})
    price = details.get("price", 0)

    emoji = "🚨" if signal == "BUY" else "🔴"
    action = "매수" if signal == "BUY" else "매도"

    score_parts = []
    for name, score in scores.items():
        score_parts.append(f"{name.upper()} {score:+d}")
    scores_text = " | ".join(score_parts)

    return (
        f"{emoji} *PentaScore {action} 시그널!*\n"
        f"BTC/USDT | {timeframe}\n\n"
        f"💰 가격: `${price:,.2f}`\n"
        f"📊 총점: `{total:+d}` (매수≥3, 매도≤-3)\n"
        f"지표: `{scores_text}`"
    )


def format_ichimoku_message(result: dict, timeframe: str) -> str:
    signal = result["signal"]
    total = result["total"]
    scores = result["scores"]
    details = result.get("details", {})
    price = details.get("price", 0)

    emoji = "🚨" if signal == "BUY" else "🔴"
    action = "매수" if signal == "BUY" else "매도"

    score_parts = []
    for name, score in scores.items():
        score_parts.append(f"{name.upper()} {score:+d}")
    scores_text = " | ".join(score_parts)

    cloud_top = details.get("cloud_top", 0)
    cloud_bottom = details.get("cloud_bottom", 0)

    return (
        f"{emoji} *Ichimoku {action} 시그널!*\n"
        f"BTC/USDT | {timeframe}\n\n"
        f"💰 가격: `${price:,.2f}`\n"
        f"☁️ 구름: `${cloud_bottom:,.2f} ~ ${cloud_top:,.2f}`\n"
        f"📊 총점: `{total:+d}` (매수≥3, 매도≤-3)\n"
        f"지표: `{scores_text}`"
    )


async def send_telegram(message: str):
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정 없음 — 콘솔 출력만")
        print(message.replace("*", "").replace("`", ""))
        return

    bot = telegram.Bot(token=Config.TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=Config.TELEGRAM_CHAT_ID,
        text=message,
        parse_mode="Markdown",
    )
    logger.info("텔레그램 전송 완료")


def analyze_and_notify(client: ExchangeClient, timeframe: str, loop_count: int):
    """PentaScore + Ichimoku 분석 후 BUY/SELL이면 알림."""
    symbol = Config.SYMBOL

    # PentaScore
    try:
        penta = BaseStrategy(client, symbol)
        result = penta.analyze(timeframe)
        logger.info(f"[PentaScore {timeframe}] {result['signal']} (총점: {result['total']})")
        if result["signal"] in ("BUY", "SELL"):
            msg = format_penta_message(result, timeframe)
            asyncio.run(send_telegram(msg))
    except Exception as e:
        logger.error(f"[PentaScore {timeframe}] 분석 실패: {e}")

    # Ichimoku
    try:
        ichi = IchimokuStrategy(client, symbol)
        result = ichi.analyze(timeframe)
        logger.info(f"[Ichimoku {timeframe}] {result['signal']} (총점: {result['total']})")
        if result["signal"] in ("BUY", "SELL"):
            msg = format_ichimoku_message(result, timeframe)
            asyncio.run(send_telegram(msg))
    except Exception as e:
        logger.error(f"[Ichimoku {timeframe}] 분석 실패: {e}")


def main():
    logger.info("=== Signal Daemon 시작 ===")
    logger.info(f"심볼: {Config.SYMBOL} | 루프 간격: {LOOP_INTERVAL}s | 4시간봉: 매 {FOURH_EVERY}루프")

    client = create_client()
    loop_count = 0

    while True:
        loop_count += 1
        logger.info(f"--- 루프 #{loop_count} 시작 ---")

        # 1시간봉 분석 (매 루프)
        analyze_and_notify(client, "1h", loop_count)

        # 4시간봉 분석 (매 4루프)
        if loop_count % FOURH_EVERY == 0:
            logger.info("4시간봉 분석 실행")
            analyze_and_notify(client, "4h", loop_count)

        logger.info(f"다음 분석까지 {LOOP_INTERVAL}s 대기")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
