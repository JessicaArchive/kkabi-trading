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
