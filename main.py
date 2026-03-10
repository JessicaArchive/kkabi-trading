import time
from config import Config
from exchange.client import ExchangeClient
from strategy.base import BaseStrategy
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_once(client: ExchangeClient, strategy: BaseStrategy):
    """Run a single analysis cycle."""
    ticker = client.get_ticker(Config.SYMBOL)
    if ticker:
        logger.info(f"Current price: {ticker['last']} USDT")

    result = strategy.analyze(Config.TIMEFRAME)
    signal = result["signal"]
    total = result["total"]
    scores = result["scores"]

    logger.info(f"=== Signal: {signal} (score: {total}) ===")
    for name, score in scores.items():
        indicator = name.upper()
        direction = "BULL" if score > 0 else "BEAR" if score < 0 else "NEUTRAL"
        logger.info(f"  {indicator}: {score:+d} ({direction})")

    if signal == "BUY":
        logger.info(f"BUY signal detected! Amount: {Config.TRADE_AMOUNT} USDT")
        # Uncomment below to enable live trading:
        # price = ticker['last'] if ticker else None
        # amount = Config.TRADE_AMOUNT / price if price else 0
        # client.create_order(Config.SYMBOL, "buy", amount)
    elif signal == "SELL":
        logger.info(f"SELL signal detected!")
        # Uncomment below to enable live trading:
        # balance = client.get_balance()
        # client.create_order(Config.SYMBOL, "sell", amount)

    return result


def main():
    logger.info("=" * 50)
    logger.info("Kkabi Trading Bot v2.0 - Multi-Signal Strategy")
    logger.info("=" * 50)
    logger.info(f"Exchange: {Config.EXCHANGE_NAME} | Symbol: {Config.SYMBOL}")
    logger.info(f"Timeframe: {Config.TIMEFRAME} | Trade Amount: {Config.TRADE_AMOUNT} USDT")
    logger.info(f"Stop Loss: {Config.STOP_LOSS_PERCENT}% | Take Profit: {Config.TAKE_PROFIT_PERCENT}%")
    logger.info(f"Loop Interval: {Config.LOOP_INTERVAL}s")
    logger.info("=" * 50)

    client = ExchangeClient(
        exchange_name=Config.EXCHANGE_NAME,
        api_key=Config.API_KEY,
        api_secret=Config.API_SECRET,
    )

    strategy = BaseStrategy(client, Config.SYMBOL)

    if Config.LOOP_INTERVAL > 0:
        logger.info("Running in loop mode...")
        while True:
            try:
                run_once(client, strategy)
            except Exception as e:
                logger.error(f"Error in loop: {e}")
            time.sleep(Config.LOOP_INTERVAL)
    else:
        run_once(client, strategy)
        logger.info("Single run complete.")


if __name__ == "__main__":
    main()
