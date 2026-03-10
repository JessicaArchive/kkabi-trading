"""
Kkabi Trading - Telegram Bot Runner

Setup:
    1. Create a bot via @BotFather on Telegram
    2. Get your bot token
    3. Add TELEGRAM_BOT_TOKEN to your .env file
    4. Run: python run_telegram.py

Commands:
    /start    - Welcome message
    /status   - Current price & signal
    /analyze  - Full strategy analysis
    /backtest - 30-day backtest
    /config   - Current settings
"""

import os
from dotenv import load_dotenv
from telegram_bot.bot import KkabiBot
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("\n" + "=" * 50)
        print("  TELEGRAM BOT SETUP")
        print("=" * 50)
        print()
        print("  1. Telegram에서 @BotFather에게 메시지 보내기")
        print("  2. /newbot 명령으로 봇 생성")
        print("  3. 받은 토큰을 .env 파일에 추가:")
        print()
        print('     TELEGRAM_BOT_TOKEN=your_token_here')
        print()
        print("  4. 다시 실행: python run_telegram.py")
        print("=" * 50)
        return

    bot = KkabiBot(token)
    bot.run()


if __name__ == "__main__":
    main()
