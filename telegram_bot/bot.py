"""
Kkabi Trading - Telegram Bot

Commands:
    /start      - Welcome & help
    /status     - Current price & signal analysis
    /analyze    - Run full strategy analysis
    /backtest   - Quick 30-day backtest result
    /config     - Show current config
    /monitor    - Toggle auto signal monitoring
    /help       - Show available commands
"""

import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import Config
from exchange.client import ExchangeClient
from backtest.engine import BacktestEngine
from utils.logger import setup_logger

logger = setup_logger(__name__)


class KkabiBot:
    def __init__(self, token: str):
        self.token = token
        self.client = ExchangeClient(
            exchange_name=Config.EXCHANGE_NAME,
            api_key=Config.API_KEY,
            api_secret=Config.API_SECRET,
        )
        self.app = Application.builder().token(token).build()
        self._last_signal_1h = None
        self._last_signal_4h = None
        self._last_signal_fng = None
        self._monitoring = True
        self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("analyze", self.cmd_analyze))
        self.app.add_handler(CommandHandler("backtest", self.cmd_backtest))
        self.app.add_handler(CommandHandler("config", self.cmd_config))
        self.app.add_handler(CommandHandler("monitor", self.cmd_monitor))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 *Kkabi Trading Bot*\n\n"
            "사용 가능한 명령어:\n"
            "/status - 현재 가격 & 시그널\n"
            "/analyze - 전체 전략 분석\n"
            "/backtest - 30일 백테스트 결과\n"
            "/config - 현재 설정 확인\n"
            "/monitor - 자동 모니터링 ON/OFF\n"
            "/help - 이 메시지\n\n"
            "📡 자동 모니터링이 활성화되어 있습니다.\n"
            "매수/매도 시그널 발생 시 자동으로 알려드립니다!"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⏳ 가격 조회 중...")

        ticker = self.client.get_ticker(Config.SYMBOL)
        if not ticker:
            await update.message.reply_text("❌ 가격 조회 실패")
            return

        price = ticker["last"]
        change = ticker.get("percentage", 0) or 0
        high = ticker.get("high", 0)
        low = ticker.get("low", 0)
        volume = ticker.get("baseVolume", 0)

        emoji = "🟢" if change >= 0 else "🔴"

        msg = (
            f"📊 *{Config.SYMBOL} 현재 현황*\n\n"
            f"💰 가격: `${price:,.2f}`\n"
            f"{emoji} 24h 변동: `{change:+.2f}%`\n"
            f"📈 24h 고가: `${high:,.2f}`\n"
            f"📉 24h 저가: `${low:,.2f}`\n"
            f"📦 24h 거래량: `{volume:,.2f}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 전략 분석 중...")

        from strategy.base import BaseStrategy
        from strategy.fear_greed import FearGreedStrategy

        strategy = BaseStrategy(self.client, Config.SYMBOL)
        result = strategy.analyze(Config.TIMEFRAME)

        signal = result["signal"]
        total = result["total"]
        scores = result["scores"]
        details = result.get("details", {})

        # Signal emoji
        signal_map = {"BUY": "🟢 매수", "SELL": "🔴 매도", "HOLD": "⚪ 관망"}
        signal_text = signal_map.get(signal, signal)

        # Score bars
        score_lines = []
        for name, score in scores.items():
            bar = "🟩" * max(0, score) + "🟥" * abs(min(0, score)) + "⬜" * (2 - abs(score))
            direction = "↑" if score > 0 else "↓" if score < 0 else "→"
            score_lines.append(f"  {name.upper():<10} {bar} {score:+d} {direction}")

        scores_text = "\n".join(score_lines)

        msg = (
            f"📊 *{Config.SYMBOL} PentaScore 분석*\n"
            f"타임프레임: `{Config.TIMEFRAME}`\n\n"
            f"*시그널: {signal_text}*\n"
            f"총 점수: `{total:+d}` (매수≥3, 매도≤-3)\n\n"
            f"*지표별 점수:*\n```\n{scores_text}\n```\n\n"
            f"*상세 지표:*\n"
            f"  가격: `${details.get('price', 0):,.2f}`\n"
            f"  RSI: `{details.get('rsi', 0):.1f}`\n"
            f"  MACD: `{details.get('macd', 0):.4f}`\n"
            f"  BB위치: `{details.get('bb_position', 0):.1%}`\n"
            f"  거래량비: `{details.get('vol_ratio', 0):.2f}x`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

        # Fear & Greed analysis
        fng_strategy = FearGreedStrategy(self.client, Config.SYMBOL)
        fng_result = fng_strategy.analyze()

        if fng_result["signal"] != "NO_DATA":
            fng_signal_text = signal_map.get(fng_result["signal"], fng_result["signal"])
            fng_details = fng_result.get("details", {})
            fng_msg = (
                f"😱 *Fear & Greed 역발상*\n\n"
                f"*시그널: {fng_signal_text}*\n"
                f"F&G Index: `{fng_details.get('fng_value', 0)}` ({fng_details.get('fng_label', 'N/A')})\n"
                f"총점: `{fng_result['total']:+d}` / 3"
            )
            await update.message.reply_text(fng_msg, parse_mode="Markdown")

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📊 30일 백테스트 실행 중... (1~2분 소요)")

        try:
            import pandas as pd
            import time

            # Fetch 30 days of data
            days = 30
            since = int((time.time() - days * 86400) * 1000)
            all_data = []
            while len(all_data) < days * 24:
                batch = self.client.exchange.fetch_ohlcv(
                    Config.SYMBOL, Config.TIMEFRAME, since=since, limit=1000
                )
                if not batch:
                    break
                all_data.extend(batch)
                since = batch[-1][0] + 1
                if len(batch) < 1000:
                    break

            df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])

            engine = BacktestEngine(
                initial_capital=10000.0,
                stop_loss_pct=Config.STOP_LOSS_PERCENT,
                take_profit_pct=Config.TAKE_PROFIT_PERCENT,
            )
            result = engine.run(df)

            if "error" in result:
                await update.message.reply_text(f"❌ {result['error']}")
                return

            m = result["metrics"]
            emoji = "🟢" if m["total_return_pct"] >= 0 else "🔴"

            msg = (
                f"📊 *30일 백테스트 결과*\n"
                f"`{Config.SYMBOL} | {Config.TIMEFRAME}`\n\n"
                f"💰 시작: `$10,000.00`\n"
                f"{emoji} 최종: `${m['final_equity']:,.2f}`\n"
                f"{emoji} 수익률: `{m['total_return_pct']:+.2f}%`\n\n"
                f"📈 거래 횟수: `{m['total_trades']}`\n"
                f"✅ 승률: `{m['win_rate_pct']:.1f}%`\n"
                f"💪 평균 수익: `${m['avg_win']:,.2f}`\n"
                f"💀 평균 손실: `${m['avg_loss']:,.2f}`\n"
                f"📊 Profit Factor: `{m['profit_factor']:.2f}`\n\n"
                f"⚠️ Max Drawdown: `{m['max_drawdown_pct']:.2f}%`\n"
                f"📐 Sharpe Ratio: `{m['sharpe_ratio']:.2f}`"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            await update.message.reply_text(f"❌ 백테스트 실패: {e}")

    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "⚙️ *현재 설정*\n\n"
            f"거래소: `{Config.EXCHANGE_NAME}`\n"
            f"심볼: `{Config.SYMBOL}`\n"
            f"타임프레임: `{Config.TIMEFRAME}`\n"
            f"거래 금액: `${Config.TRADE_AMOUNT:,.0f}`\n"
            f"손절: `{Config.STOP_LOSS_PERCENT}%`\n"
            f"익절: `{Config.TAKE_PROFIT_PERCENT}%`\n"
            f"루프 간격: `{Config.LOOP_INTERVAL}s`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._monitoring = not self._monitoring
        status = "ON ✅" if self._monitoring else "OFF ❌"
        await update.message.reply_text(
            f"📡 자동 모니터링: *{status}*", parse_mode="Markdown"
        )

    async def send_alert(self, chat_id, signal: str, timeframe: str, scores: dict, total: int, details: dict):
        """Send loud trading signal alert."""
        if signal == "BUY":
            header = (
                "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\n"
                "💰💰💰 매수 시그널 발생!!! 💰💰💰\n"
                "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨"
            )
        elif signal == "SELL":
            header = (
                "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n"
                "⚠️⚠️⚠️ 매도 시그널 발생!!! ⚠️⚠️⚠️\n"
                "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            )
        else:
            header = (
                "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪\n"
                "⏸️⏸️⏸️ 관망 시그널 ⏸️⏸️⏸️\n"
                "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"
            )

        score_lines = []
        for name, score in scores.items():
            arrow = "↑" if score > 0 else "↓" if score < 0 else "→"
            score_lines.append(f"  {name.upper():<10} {score:+d} {arrow}")
        scores_text = "\n".join(score_lines)

        msg = (
            f"{header}\n\n"
            f"📊 *{Config.SYMBOL} | {timeframe}*\n"
            f"전략: PentaScore v1.0\n\n"
            f"💰 가격: `${details.get('price', 0):,.2f}`\n"
            f"📈 총점: `{total:+d}` / 9\n\n"
            f"*지표별 점수:*\n```\n{scores_text}\n```\n\n"
            f"*상세:*\n"
            f"  RSI: `{details.get('rsi', 0):.1f}`\n"
            f"  MACD: `{details.get('macd', 0):.4f}`\n"
            f"  BB위치: `{details.get('bb_position', 0):.1%}`\n"
            f"  거래량비: `{details.get('vol_ratio', 0):.2f}x`"
        )
        await self.app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        logger.info(f"Alert sent: {signal} on {timeframe}, score={total}")

    async def _check_signal(self, context: ContextTypes.DEFAULT_TYPE, timeframe: str):
        """Check signal for a timeframe and send alert if BUY/SELL."""
        if not self._monitoring:
            return

        chat_id = Config.TELEGRAM_CHAT_ID
        if not chat_id:
            logger.warning("TELEGRAM_CHAT_ID not set, skipping signal check")
            return

        try:
            from strategy.base import BaseStrategy
            strategy = BaseStrategy(self.client, Config.SYMBOL)
            result = strategy.analyze(timeframe)

            signal = result["signal"]
            last_attr = f"_last_signal_{timeframe.replace('h', 'h')}"

            # Skip if same signal as last check (prevent spam)
            last = getattr(self, last_attr, None)
            if signal == last:
                return

            setattr(self, last_attr, signal)

            await self.send_alert(
                chat_id=int(chat_id),
                signal=signal,
                timeframe=timeframe,
                scores=result["scores"],
                total=result["total"],
                details=result.get("details", {}),
            )
        except Exception as e:
            logger.error(f"Signal check error ({timeframe}): {e}")

    async def send_fng_alert(self, chat_id, signal: str, scores: dict, total: int, details: dict):
        """Send Fear & Greed signal alert."""
        if signal == "BUY":
            header = (
                "🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢\n"
                "😱➡️💰 공포 매수 시그널!!! 😱➡️💰\n"
                "🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢"
            )
        elif signal == "SELL":
            header = (
                "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n"
                "🤑➡️⚠️ 탐욕 매도 시그널!!! 🤑➡️⚠️\n"
                "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            )
        else:
            header = (
                "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪\n"
                "😐 F&G 관망 시그널 😐\n"
                "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"
            )

        fng_value = details.get("fng_value", 0)
        fng_label = details.get("fng_label", "N/A")

        msg = (
            f"{header}\n\n"
            f"📊 *{Config.SYMBOL} | Fear & Greed 역발상*\n"
            f"전략: Contrarian v1.0\n\n"
            f"💰 가격: `${details.get('price', 0):,.2f}`\n"
            f"😱 F&G Index: `{fng_value}` ({fng_label})\n"
            f"📈 총점: `{total:+d}` / 3\n\n"
            f"_\"남들이 공포일 때 사라, 남들이 탐욕일 때 팔아라\"_"
        )
        await self.app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        logger.info(f"F&G Alert sent: {signal}, fng={fng_value} ({fng_label}), score={total}")

    async def _check_fng(self, context: ContextTypes.DEFAULT_TYPE):
        """Check Fear & Greed signal and send alert if BUY/SELL."""
        if not self._monitoring:
            return

        chat_id = Config.TELEGRAM_CHAT_ID
        if not chat_id:
            return

        try:
            from strategy.fear_greed import FearGreedStrategy
            strategy = FearGreedStrategy(self.client, Config.SYMBOL)
            result = strategy.analyze()

            signal = result["signal"]
            if signal == "NO_DATA":
                return

            if signal == self._last_signal_fng:
                return

            self._last_signal_fng = signal

            await self.send_fng_alert(
                chat_id=int(chat_id),
                signal=signal,
                scores=result["scores"],
                total=result["total"],
                details=result.get("details", {}),
            )
        except Exception as e:
            logger.error(f"F&G signal check error: {e}")

    async def _check_1h(self, context: ContextTypes.DEFAULT_TYPE):
        await self._check_signal(context, "1h")

    async def _check_4h(self, context: ContextTypes.DEFAULT_TYPE):
        await self._check_signal(context, "4h")

    def _setup_jobs(self):
        """Schedule automatic signal monitoring."""
        job_queue = self.app.job_queue
        # 1h check: every hour
        job_queue.run_repeating(self._check_1h, interval=3600, first=10)
        # 4h check: every 4 hours
        job_queue.run_repeating(self._check_4h, interval=14400, first=10)
        # F&G check: every 4 hours (daily index, no need for frequent checks)
        job_queue.run_repeating(self._check_fng, interval=14400, first=15)
        logger.info("Signal monitoring jobs scheduled (1h, 4h: PentaScore, 4h: F&G)")

    def run(self):
        """Start the bot with auto monitoring."""
        logger.info("Starting Kkabi Telegram Bot with auto monitoring...")
        self._setup_jobs()
        self.app.run_polling()
