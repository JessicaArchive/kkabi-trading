from config import Config
from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from utils.logger import setup_logger

logger = setup_logger(__name__)


def main():
    logger.info("Kkabi Trading Bot starting...")
    logger.info(f"Exchange: {Config.EXCHANGE_NAME} | Symbol: {Config.SYMBOL}")

    client = ExchangeClient(
        exchange_name=Config.EXCHANGE_NAME,
        api_key=Config.API_KEY,
        api_secret=Config.API_SECRET,
    )

    ticker = client.get_ticker(Config.SYMBOL)
    if ticker:
        logger.info(f"Current price: {ticker['last']} USDT")

    strategy = BaseStrategy(client, Config.SYMBOL)
    signal = strategy.analyze(Config.TIMEFRAME)
    logger.info(f"Signal: {signal}")

    logger.info("Kkabi Trading Bot ready.")


if __name__ == "__main__":
    main()
