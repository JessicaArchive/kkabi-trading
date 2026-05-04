import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "binance")
    API_KEY = os.getenv("API_KEY", "")
    API_SECRET = os.getenv("API_SECRET", "")

    SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
    TIMEFRAME = os.getenv("TIMEFRAME", "1h")
    TRADE_AMOUNT = float(os.getenv("TRADE_AMOUNT", "100"))

    MAX_LOSS_PERCENT = float(os.getenv("MAX_LOSS_PERCENT", "2.0"))
    STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "1.5"))
    TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "3.0"))

    LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL", "0"))  # 0 = single run, >0 = seconds between runs

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Upbit Auto-Trading
    UPBIT_API_KEY = os.getenv("UPBIT_API_KEY", "")
    UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")
    AUTO_TRADE_SYMBOL = "BTC/KRW"
    AUTO_TRADE_AMOUNT_KRW = float(os.getenv("AUTO_TRADE_AMOUNT_KRW", "100000"))
    AUTO_TRADE_INTERVAL = int(os.getenv("AUTO_TRADE_INTERVAL", "3600"))
    AUTO_TRADE_DRY_RUN = os.getenv("AUTO_TRADE_DRY_RUN", "true").lower() == "true"
