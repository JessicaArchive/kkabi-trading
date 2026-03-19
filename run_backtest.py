"""
Kkabi Trading - Backtest Runner

Usage:
    python run_backtest.py                    # Default: BTC/USDT, 1h, 30 days
    python run_backtest.py --days 90          # Last 90 days
    python run_backtest.py --symbol ETH/USDT  # Different pair
    python run_backtest.py --timeframe 4h     # Different timeframe
    python run_backtest.py --capital 50000    # Different starting capital
"""

import argparse
import pandas as pd
from config import Config
from exchange.client import ExchangeClient
from backtest.engine import BacktestEngine
from utils.logger import setup_logger

logger = setup_logger(__name__)


def fetch_historical_data(client: ExchangeClient, symbol: str,
                          timeframe: str, days: float) -> pd.DataFrame:
    """Fetch historical OHLCV data from exchange."""
    # Calculate how many candles we need
    tf_hours = {"1m": 1/60, "5m": 5/60, "15m": 0.25, "30m": 0.5,
                "1h": 1, "4h": 4, "1d": 24}
    hours_per_candle = tf_hours.get(timeframe, 1)
    total_candles = int(days * 24 / hours_per_candle)

    logger.info(f"Fetching {total_candles} candles ({days} days) of {symbol} @ {timeframe}...")

    # CCXT limits per request, so we fetch in batches
    all_data = []
    limit_per_request = 1000
    since = None

    # Calculate starting timestamp
    import time
    since = int((time.time() - days * 86400) * 1000)

    while len(all_data) < total_candles:
        batch = client.exchange.fetch_ohlcv(
            symbol, timeframe, since=since,
            limit=min(limit_per_request, total_candles - len(all_data))
        )
        if not batch:
            break
        all_data.extend(batch)
        since = batch[-1][0] + 1  # Next timestamp after last candle

        if len(batch) < limit_per_request:
            break

    logger.info(f"Fetched {len(all_data)} candles")

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df


def main():
    parser = argparse.ArgumentParser(description="Kkabi Trading Backtester")
    parser.add_argument("--symbol", default=Config.SYMBOL, help="Trading pair (default: BTC/USDT)")
    parser.add_argument("--timeframe", default=Config.TIMEFRAME, help="Timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=30, help="Days of history (default: 30)")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital in USDT")
    parser.add_argument("--stop-loss", type=float, default=Config.STOP_LOSS_PERCENT, help="Stop loss %%")
    parser.add_argument("--take-profit", type=float, default=Config.TAKE_PROFIT_PERCENT, help="Take profit %%")
    parser.add_argument("--buy-threshold", type=int, default=3, help="Buy score threshold")
    parser.add_argument("--sell-threshold", type=int, default=-3, help="Sell score threshold")
    parser.add_argument("--trend-filter", action="store_true", help="Enable trend filter (suppress SELL/TP in uptrend, SMA200)")
    parser.add_argument("--druckenmiller", action="store_true", help="Run Druckenmiller-style strategy")
    parser.add_argument("--trailing-stop", type=float, default=5.0, help="Trailing stop %% (Druckenmiller, default: 5)")
    parser.add_argument("--initial-stop", type=float, default=2.0, help="Initial stop loss %% (Druckenmiller, default: 2)")
    parser.add_argument("--max-pyramids", type=int, default=3, help="Max pyramid entries (Druckenmiller, default: 3)")
    args = parser.parse_args()

    # Auto-extend history when --trend-filter needs SMA200 warmup
    fetch_days = args.days
    if args.trend_filter and args.druckenmiller:
        logger.warning("--trend-filter is not supported with --druckenmiller (uses trailing stops instead). Ignoring --trend-filter.")
        args.trend_filter = False
    if args.trend_filter:
        tf_hours = {"1m": 1/60, "5m": 5/60, "15m": 0.25, "30m": 0.5,
                    "1h": 1, "4h": 4, "1d": 24}
        hpc = tf_hours.get(args.timeframe, 1)
        warmup_days = 200 * hpc / 24  # exact fractional days for 200 candles
        fetch_days = args.days + warmup_days
        logger.info(
            f"--trend-filter: fetching {fetch_days:.1f} days ({args.days} requested + {warmup_days:.1f}d SMA200 warmup)"
        )

    # Connect to exchange (public API, no keys needed for OHLCV)
    client = ExchangeClient(
        exchange_name=Config.EXCHANGE_NAME,
        api_key=Config.API_KEY,
        api_secret=Config.API_SECRET,
    )

    # Fetch data (fetch_days includes warmup when --trend-filter is active)
    df = fetch_historical_data(client, args.symbol, args.timeframe, fetch_days)

    if df.empty:
        logger.error("No data fetched. Check your connection and symbol.")
        return

    # Run backtest
    engine = BacktestEngine(
        initial_capital=args.capital,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )

    if args.druckenmiller:
        logger.info(f"Running Druckenmiller backtest: {args.symbol} | {args.timeframe} | {args.days} days | ${args.capital:,.0f}")
        result = engine.run_druckenmiller(
            df, buy_threshold=args.buy_threshold, sell_threshold=args.sell_threshold,
            trailing_stop_pct=args.trailing_stop, initial_stop_pct=args.initial_stop,
            max_pyramids=args.max_pyramids,
        )
    else:
        logger.info(f"Running backtest: {args.symbol} | {args.timeframe} | {args.days} days | ${args.capital:,.0f}")
        result = engine.run(df, buy_threshold=args.buy_threshold, sell_threshold=args.sell_threshold,
                            trend_filter=args.trend_filter)

    # Print report
    engine.print_report(result)


if __name__ == "__main__":
    main()
