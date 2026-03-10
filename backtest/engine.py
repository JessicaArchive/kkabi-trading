import pandas as pd
import numpy as np
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BacktestEngine:
    """
    Historical backtesting engine for multi-signal scoring strategy.
    Simulates trades on past OHLCV data and calculates performance metrics.
    """

    def __init__(self, initial_capital: float = 10000.0,
                 stop_loss_pct: float = 1.5, take_profit_pct: float = 3.0,
                 fee_pct: float = 0.1):
        self.initial_capital = initial_capital
        self.stop_loss_pct = stop_loss_pct / 100
        self.take_profit_pct = take_profit_pct / 100
        self.fee_pct = fee_pct / 100  # Trading fee (0.1% default)

    def _calc_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators (same as BaseStrategy)."""
        # SMA
        df["sma_7"] = df["close"].rolling(window=7).mean()
        df["sma_25"] = df["close"].rolling(window=25).mean()
        df["sma_99"] = df["close"].rolling(window=99).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands
        df["bb_mid"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + (bb_std * 2)
        df["bb_lower"] = df["bb_mid"] - (bb_std * 2)
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # Volume
        df["vol_sma"] = df["volume"].rolling(window=20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_sma"]

        return df

    def _score_at(self, df: pd.DataFrame, idx: int) -> dict:
        """Score signals at a specific index (same logic as BaseStrategy)."""
        latest = df.iloc[idx]
        prev = df.iloc[idx - 1]
        scores = {}

        # SMA
        if latest["sma_7"] > latest["sma_25"] > latest["sma_99"]:
            scores["sma"] = 2
        elif latest["sma_7"] > latest["sma_25"]:
            scores["sma"] = 1
        elif latest["sma_7"] < latest["sma_25"] < latest["sma_99"]:
            scores["sma"] = -2
        elif latest["sma_7"] < latest["sma_25"]:
            scores["sma"] = -1
        else:
            scores["sma"] = 0

        # MACD
        if latest["macd"] > latest["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
            scores["macd"] = 2
        elif latest["macd"] > latest["macd_signal"] and latest["macd_hist"] > prev["macd_hist"]:
            scores["macd"] = 1
        elif latest["macd"] < latest["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
            scores["macd"] = -2
        elif latest["macd"] < latest["macd_signal"] and latest["macd_hist"] < prev["macd_hist"]:
            scores["macd"] = -1
        else:
            scores["macd"] = 0

        # Bollinger Bands
        if latest["bb_position"] < 0.05:
            scores["bollinger"] = 2
        elif latest["bb_position"] < 0.2:
            scores["bollinger"] = 1
        elif latest["bb_position"] > 0.95:
            scores["bollinger"] = -2
        elif latest["bb_position"] > 0.8:
            scores["bollinger"] = -1
        else:
            scores["bollinger"] = 0

        # RSI
        rsi = latest["rsi"]
        if rsi < 25:
            scores["rsi"] = 2
        elif rsi < 35:
            scores["rsi"] = 1
        elif rsi > 75:
            scores["rsi"] = -2
        elif rsi > 65:
            scores["rsi"] = -1
        else:
            scores["rsi"] = 0

        # Volume
        if latest["vol_ratio"] > 1.5:
            price_change = latest["close"] - prev["close"]
            if price_change > 0:
                scores["volume"] = 1
            elif price_change < 0:
                scores["volume"] = -1
            else:
                scores["volume"] = 0
        else:
            scores["volume"] = 0

        return scores

    def run(self, df: pd.DataFrame, buy_threshold: int = 3, sell_threshold: int = -3) -> dict:
        """
        Run backtest on OHLCV DataFrame.

        Returns dict with trades, equity curve, and performance metrics.
        """
        df = df.copy()
        df = self._calc_indicators(df)
        df = df.dropna().reset_index(drop=True)

        if len(df) < 10:
            return {"error": "Not enough data for backtesting"}

        capital = self.initial_capital
        position = 0.0  # BTC held
        entry_price = 0.0
        trades = []
        equity_curve = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            price = row["close"]

            # Check stop loss / take profit if in position
            if position > 0:
                pnl_pct = (price - entry_price) / entry_price
                if pnl_pct <= -self.stop_loss_pct:
                    # Stop loss hit
                    sell_value = position * price * (1 - self.fee_pct)
                    profit = sell_value - (position * entry_price)
                    trades.append({
                        "type": "SELL (SL)",
                        "timestamp": row["timestamp"],
                        "price": price,
                        "amount": position,
                        "profit": profit,
                        "profit_pct": pnl_pct * 100,
                    })
                    capital += sell_value
                    position = 0.0
                    entry_price = 0.0
                elif pnl_pct >= self.take_profit_pct:
                    # Take profit hit
                    sell_value = position * price * (1 - self.fee_pct)
                    profit = sell_value - (position * entry_price)
                    trades.append({
                        "type": "SELL (TP)",
                        "timestamp": row["timestamp"],
                        "price": price,
                        "amount": position,
                        "profit": profit,
                        "profit_pct": pnl_pct * 100,
                    })
                    capital += sell_value
                    position = 0.0
                    entry_price = 0.0

            # Score signals
            scores = self._score_at(df, i)
            total = sum(scores.values())

            # Trading logic
            if total >= buy_threshold and position == 0 and capital > 0:
                # BUY
                buy_amount = capital * (1 - self.fee_pct)
                position = buy_amount / price
                entry_price = price
                trades.append({
                    "type": "BUY",
                    "timestamp": row["timestamp"],
                    "price": price,
                    "amount": position,
                    "profit": 0,
                    "profit_pct": 0,
                })
                capital = 0.0

            elif total <= sell_threshold and position > 0:
                # SELL signal
                sell_value = position * price * (1 - self.fee_pct)
                profit = sell_value - (position * entry_price)
                pnl_pct = (price - entry_price) / entry_price
                trades.append({
                    "type": "SELL",
                    "timestamp": row["timestamp"],
                    "price": price,
                    "amount": position,
                    "profit": profit,
                    "profit_pct": pnl_pct * 100,
                })
                capital += sell_value
                position = 0.0
                entry_price = 0.0

            # Track equity
            total_equity = capital + (position * price)
            equity_curve.append({
                "timestamp": row["timestamp"],
                "equity": total_equity,
                "price": price,
            })

        # Close any open position at the end
        if position > 0:
            final_price = df.iloc[-1]["close"]
            sell_value = position * final_price * (1 - self.fee_pct)
            profit = sell_value - (position * entry_price)
            pnl_pct = (final_price - entry_price) / entry_price
            trades.append({
                "type": "SELL (END)",
                "timestamp": df.iloc[-1]["timestamp"],
                "price": final_price,
                "amount": position,
                "profit": profit,
                "profit_pct": pnl_pct * 100,
            })
            capital += sell_value
            position = 0.0

        # Calculate metrics
        metrics = self._calc_metrics(trades, equity_curve)

        return {
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": metrics,
        }

    def _calc_metrics(self, trades: list, equity_curve: list) -> dict:
        """Calculate performance metrics."""
        if not equity_curve:
            return {}

        final_equity = equity_curve[-1]["equity"]
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        # Separate buy/sell trades
        sell_trades = [t for t in trades if t["type"].startswith("SELL")]
        winning = [t for t in sell_trades if t["profit"] > 0]
        losing = [t for t in sell_trades if t["profit"] <= 0]

        win_rate = len(winning) / len(sell_trades) * 100 if sell_trades else 0

        # Max drawdown
        equities = [e["equity"] for e in equity_curve]
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Average profit/loss
        avg_win = np.mean([t["profit"] for t in winning]) if winning else 0
        avg_loss = np.mean([t["profit"] for t in losing]) if losing else 0

        # Profit factor
        gross_profit = sum(t["profit"] for t in winning) if winning else 0
        gross_loss = abs(sum(t["profit"] for t in losing)) if losing else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Sharpe ratio (simplified, annualized)
        if len(equities) > 1:
            returns = pd.Series(equities).pct_change().dropna()
            sharpe = (returns.mean() / returns.std()) * np.sqrt(365 * 24) if returns.std() > 0 else 0
        else:
            sharpe = 0

        return {
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return, 2),
            "total_trades": len(sell_trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate_pct": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
        }

    def print_report(self, result: dict):
        """Print a formatted backtest report."""
        if "error" in result:
            logger.error(result["error"])
            return

        m = result["metrics"]
        trades = result["trades"]

        print("\n" + "=" * 60)
        print("  KKABI TRADING - BACKTEST REPORT")
        print("=" * 60)
        print(f"  Initial Capital:  ${m['initial_capital']:,.2f}")
        print(f"  Final Equity:     ${m['final_equity']:,.2f}")
        print(f"  Total Return:     {m['total_return_pct']:+.2f}%")
        print("-" * 60)
        print(f"  Total Trades:     {m['total_trades']}")
        print(f"  Win / Loss:       {m['winning_trades']} / {m['losing_trades']}")
        print(f"  Win Rate:         {m['win_rate_pct']:.1f}%")
        print(f"  Avg Win:          ${m['avg_win']:,.2f}")
        print(f"  Avg Loss:         ${m['avg_loss']:,.2f}")
        print(f"  Profit Factor:    {m['profit_factor']:.2f}")
        print("-" * 60)
        print(f"  Max Drawdown:     {m['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe Ratio:     {m['sharpe_ratio']:.2f}")
        print("=" * 60)

        if trades:
            print("\n  TRADE LOG:")
            print(f"  {'Type':<12} {'Price':>12} {'Profit':>12} {'P&L%':>8}")
            print("  " + "-" * 46)
            for t in trades:
                ts = ""
                if isinstance(t["timestamp"], (int, float)):
                    ts = datetime.fromtimestamp(t["timestamp"] / 1000).strftime("%m/%d %H:%M")
                print(f"  {t['type']:<12} ${t['price']:>10,.2f} ${t['profit']:>10,.2f} {t['profit_pct']:>+7.2f}%")
        print()
