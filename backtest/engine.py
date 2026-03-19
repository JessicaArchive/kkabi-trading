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
        df["sma_200"] = df["close"].rolling(window=200).mean()

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

    def run(self, df: pd.DataFrame, buy_threshold: int = 3, sell_threshold: int = -3,
            trend_filter: bool = False) -> dict:
        """
        Run backtest on OHLCV DataFrame.

        Args:
            trend_filter: If True, suppress signal-based SELL and TP when price > SMA200 (uptrend).
                         SL still active for risk management.

        Returns dict with trades, equity curve, and performance metrics.
        """
        df = df.copy()
        df = self._calc_indicators(df)
        # Drop rows where core indicators are NaN, but keep sma_200 NaN rows
        # (sma_200 needs 200 candles; it's checked for NaN at point of use)
        core_cols = [c for c in df.columns if c != "sma_200" and df[c].dtype != object]
        df = df.dropna(subset=core_cols).reset_index(drop=True)

        if len(df) < 10:
            return {"error": "Not enough data for backtesting"}

        # When trend filter is active, skip warmup bars where SMA200 is still NaN
        # so the filter is never "silently inactive" during simulation
        if trend_filter:
            first_valid = df["sma_200"].first_valid_index()
            if first_valid is None:
                return {"error": "Not enough data for SMA200 warmup (need 200+ candles)"}
            start_bar = max(1, first_valid)
        else:
            start_bar = 1

        capital = self.initial_capital
        position = 0.0  # BTC held
        entry_price = 0.0
        trades = []
        equity_curve = []

        for i in range(start_bar, len(df)):
            row = df.iloc[i]
            price = row["close"]
            exited_this_bar = False

            # Determine if in uptrend (for trend filter)
            in_uptrend = trend_filter and not pd.isna(row.get("sma_200", float("nan"))) and price > row["sma_200"]

            # Check stop loss / take profit if in position
            if position > 0:
                pnl_pct = (price - entry_price) / entry_price
                if pnl_pct <= -self.stop_loss_pct:
                    # Stop loss hit (always active)
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
                    exited_this_bar = True
                elif pnl_pct >= self.take_profit_pct and not in_uptrend:
                    # Take profit hit (suppressed in uptrend to let profits run)
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
                    exited_this_bar = True

            # Score signals
            scores = self._score_at(df, i)
            total = sum(scores.values())

            # Trading logic (skip if we just exited to prevent same-bar re-entry)
            if not exited_this_bar and total >= buy_threshold and position == 0 and capital > 0:
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
                if in_uptrend:
                    pass  # Suppress sell signal in uptrend — hold position
                else:
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
            equity_curve.append({
                "timestamp": df.iloc[-1]["timestamp"],
                "equity": capital,
                "price": final_price,
            })

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

    def run_druckenmiller(self, df: pd.DataFrame, buy_threshold: int = 3,
                          sell_threshold: int = -3, trailing_stop_pct: float = 5.0,
                          initial_stop_pct: float = 2.0, max_pyramids: int = 3) -> dict:
        """
        Druckenmiller-style backtest: conviction-based position sizing + pyramiding.

        Key principles:
        - Position size scales with signal strength (33%/66%/100%)
        - Pyramiding: add to winners when signals stay strong
        - Tight initial stop loss, trailing stop for profits
        - No fixed take profit — let winners run

        Args:
            trailing_stop_pct: Trailing stop from highest price (default 5%)
            initial_stop_pct: Initial stop loss before any profit (default 2%)
            max_pyramids: Maximum number of additional entries (default 3)
        """
        df = df.copy()
        df = self._calc_indicators(df)
        core_cols = [c for c in df.columns if c != "sma_200" and df[c].dtype != object]
        df = df.dropna(subset=core_cols).reset_index(drop=True)

        if len(df) < 10:
            return {"error": "Not enough data for backtesting"}

        capital = self.initial_capital
        position = 0.0  # Total BTC held
        avg_entry = 0.0  # Weighted average entry price
        highest_price = 0.0  # Highest price since entry (for trailing stop)
        pyramid_count = 0  # Number of additional entries
        total_invested = 0.0  # Total USD invested in current position
        trades = []
        equity_curve = []

        trailing_pct = trailing_stop_pct / 100
        init_stop_pct = initial_stop_pct / 100

        def _position_size_pct(score: int) -> float:
            """Determine position size based on signal conviction."""
            abs_score = abs(score)
            if abs_score >= 7:
                return 1.0   # 100% — high conviction
            elif abs_score >= 5:
                return 0.66  # 66% — medium conviction
            elif abs_score >= buy_threshold:
                return 0.33  # 33% — low conviction
            return 0.0

        for i in range(1, len(df)):
            row = df.iloc[i]
            price = row["close"]
            exited_this_bar = False

            # Update trailing stop tracker
            if position > 0 and price > highest_price:
                highest_price = price

            # Check exit conditions if in position
            if position > 0:
                effective_entry = total_invested / position
                pnl_pct = (price * (1 - self.fee_pct) - effective_entry) / effective_entry

                # Initial stop loss (before we have meaningful profit)
                if pnl_pct <= -init_stop_pct:
                    sell_value = position * price * (1 - self.fee_pct)
                    profit = sell_value - total_invested
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
                    avg_entry = 0.0
                    highest_price = 0.0
                    pyramid_count = 0
                    total_invested = 0.0
                    exited_this_bar = True

                # Trailing stop (from highest since entry)
                elif highest_price > 0 and price <= highest_price * (1 - trailing_pct):
                    sell_value = position * price * (1 - self.fee_pct)
                    profit = sell_value - total_invested
                    trades.append({
                        "type": "SELL (TS)",
                        "timestamp": row["timestamp"],
                        "price": price,
                        "amount": position,
                        "profit": profit,
                        "profit_pct": pnl_pct * 100,
                    })
                    capital += sell_value
                    position = 0.0
                    avg_entry = 0.0
                    highest_price = 0.0
                    pyramid_count = 0
                    total_invested = 0.0
                    exited_this_bar = True

            # Score signals
            scores = self._score_at(df, i)
            total = sum(scores.values())

            # Entry / Pyramid logic (skip if we just exited to prevent same-bar re-entry)
            if not exited_this_bar and total >= buy_threshold and capital > 0:
                size_pct = _position_size_pct(total)

                if position == 0:
                    # Initial entry
                    invest_usd = capital * size_pct
                    buy_amount = invest_usd * (1 - self.fee_pct)
                    new_coins = buy_amount / price
                    position = new_coins
                    avg_entry = price
                    highest_price = price
                    total_invested = invest_usd
                    capital -= invest_usd
                    pyramid_count = 0
                    trades.append({
                        "type": f"BUY ({int(size_pct*100)}%)",
                        "timestamp": row["timestamp"],
                        "price": price,
                        "amount": new_coins,
                        "profit": 0,
                        "profit_pct": 0,
                    })

                elif pyramid_count < max_pyramids and price * (1 - self.fee_pct) > total_invested / position:
                    # Pyramid: add to winning position
                    invest_usd = capital * size_pct * 0.5  # Half the normal size for pyramids
                    if invest_usd > 10:  # Minimum $10 to avoid dust
                        buy_amount = invest_usd * (1 - self.fee_pct)
                        new_coins = buy_amount / price
                        # Update weighted average entry
                        avg_entry = (avg_entry * position + price * new_coins) / (position + new_coins)
                        position += new_coins
                        total_invested += invest_usd
                        capital -= invest_usd
                        pyramid_count += 1
                        trades.append({
                            "type": f"PYRAMID #{pyramid_count}",
                            "timestamp": row["timestamp"],
                            "price": price,
                            "amount": new_coins,
                            "profit": 0,
                            "profit_pct": 0,
                        })

            # Signal-based exit
            elif total <= sell_threshold and position > 0:
                sell_value = position * price * (1 - self.fee_pct)
                profit = sell_value - total_invested
                effective_entry = total_invested / position
                pnl_pct = (price * (1 - self.fee_pct) - effective_entry) / effective_entry
                trades.append({
                    "type": "SELL (SIG)",
                    "timestamp": row["timestamp"],
                    "price": price,
                    "amount": position,
                    "profit": profit,
                    "profit_pct": pnl_pct * 100,
                })
                capital += sell_value
                position = 0.0
                avg_entry = 0.0
                highest_price = 0.0
                pyramid_count = 0
                total_invested = 0.0

            # Track equity
            total_equity = capital + (position * price)
            equity_curve.append({
                "timestamp": row["timestamp"],
                "equity": total_equity,
                "price": price,
            })

        # Close any open position at end
        if position > 0:
            final_price = df.iloc[-1]["close"]
            sell_value = position * final_price * (1 - self.fee_pct)
            profit = sell_value - total_invested
            effective_entry = total_invested / position
            pnl_pct = (final_price * (1 - self.fee_pct) - effective_entry) / effective_entry
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
            equity_curve.append({
                "timestamp": df.iloc[-1]["timestamp"],
                "equity": capital,
                "price": final_price,
            })

        metrics = self._calc_metrics(trades, equity_curve)

        # Add Druckenmiller-specific metrics
        pyramid_trades = [t for t in trades if t["type"].startswith("PYRAMID")]
        buy_trades = [t for t in trades if t["type"].startswith("BUY")]
        metrics["pyramid_entries"] = len(pyramid_trades)
        metrics["initial_entries"] = len(buy_trades)
        metrics["avg_pyramids_per_trade"] = (
            round(len(pyramid_trades) / len(buy_trades), 1) if buy_trades else 0
        )

        return {
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": metrics,
        }

    def run_dca(self, df: pd.DataFrame, interval_candles: int = 24,
                mode: str = "regular") -> dict:
        """
        Run DCA backtest.

        Args:
            interval_candles: Buy interval (e.g., 24 = daily on 1h chart)
            mode: "regular" (fixed amount), "sma" (buy more below SMA200),
                  "drawdown" (buy more on drawdown from ATH),
                  "rsi" (buy more when RSI is low)
        """
        df = df.copy()
        df = self._calc_indicators(df)

        # Only drop NaN for indicators the chosen mode actually uses
        if mode == "sma":
            warmup_cols = ["sma_200"]
        elif mode == "rsi":
            warmup_cols = ["rsi"]
        else:
            # "regular" and "drawdown" don't need any indicators
            warmup_cols = []

        if warmup_cols:
            df = df.dropna(subset=warmup_cols).reset_index(drop=True)
        else:
            df = df.dropna(subset=["close"]).reset_index(drop=True)

        if len(df) < 10:
            return {"error": "Not enough data"}

        buy_indices = list(range(0, len(df), interval_candles))
        num_buys = len(buy_indices)

        if mode == "regular":
            amounts = [self.initial_capital / num_buys] * num_buys

        elif mode == "sma":
            weights = []
            for idx in buy_indices:
                price = df.iloc[idx]["close"]
                sma200 = df.iloc[idx].get("sma_200", float("nan"))
                if pd.isna(sma200):
                    sma200 = price
                ratio = sma200 / price
                ratio = max(0.2, min(3.0, ratio))
                weights.append(ratio)
            total_weight = sum(weights)
            amounts = [self.initial_capital * w / total_weight for w in weights]

        elif mode == "drawdown":
            weights = []
            ath = 0
            for idx in buy_indices:
                price = df.iloc[idx]["close"]
                if price > ath:
                    ath = price
                dd = (ath - price) / ath if ath > 0 else 0
                weight = 1.0 + dd * 5  # 0% dd = 1x, 20% dd = 2x, 50% dd = 3.5x
                weights.append(weight)
            total_weight = sum(weights)
            amounts = [self.initial_capital * w / total_weight for w in weights]

        elif mode == "rsi":
            weights = []
            for idx in buy_indices:
                rsi = df.iloc[idx].get("rsi", 50)
                if pd.isna(rsi):
                    rsi = 50
                # RSI 30 = 2.3x, RSI 50 = 1x, RSI 70 = 0.3x
                weight = max(0.1, (100 - rsi) / 30)
                weights.append(weight)
            total_weight = sum(weights)
            amounts = [self.initial_capital * w / total_weight for w in weights]

        else:
            return {"error": f"Unknown DCA mode: {mode}"}

        # Execute DCA
        position = 0.0
        total_invested = 0.0
        remaining_cash = self.initial_capital
        equity_curve = []
        trades = []
        amount_map = dict(zip(buy_indices, amounts))

        for i in range(len(df)):
            price = df.iloc[i]["close"]

            if i in amount_map:
                buy_usd = amount_map[i]
                buy_after_fee = buy_usd * (1 - self.fee_pct)
                coins = buy_after_fee / price
                position += coins
                total_invested += buy_usd
                remaining_cash -= buy_usd
                trades.append({
                    "type": "BUY",
                    "timestamp": df.iloc[i]["timestamp"],
                    "price": price,
                    "amount": coins,
                    "usd_amount": round(buy_usd, 2),
                    "profit": 0,
                    "profit_pct": 0,
                })

            total_equity = position * price + remaining_cash
            equity_curve.append({
                "timestamp": df.iloc[i]["timestamp"],
                "equity": total_equity,
                "price": price,
            })

        final_value = position * df.iloc[-1]["close"] + remaining_cash
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        avg_buy_price = self.initial_capital / position if position > 0 else 0

        # Max drawdown
        equities = [e["equity"] for e in equity_curve]
        peak = equities[0] if equities else 0
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        metrics = {
            "initial_capital": self.initial_capital,
            "final_equity": round(final_value, 2),
            "total_return_pct": round(total_return, 2),
            "total_trades": len(trades),
            "avg_buy_price": round(avg_buy_price, 2),
            "total_invested": round(total_invested, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "position_btc": position,
        }

        return {"trades": trades, "equity_curve": equity_curve, "metrics": metrics}

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

        # Trade-level metrics (from _calc_metrics; absent in DCA results)
        if "winning_trades" in m:
            print(f"  Win / Loss:       {m['winning_trades']} / {m['losing_trades']}")
            print(f"  Win Rate:         {m['win_rate_pct']:.1f}%")
            print(f"  Avg Win:          ${m['avg_win']:,.2f}")
            print(f"  Avg Loss:         ${m['avg_loss']:,.2f}")
            print(f"  Profit Factor:    {m['profit_factor']:.2f}")

        # DCA-specific metrics
        if "avg_buy_price" in m:
            print(f"  Avg Buy Price:    ${m['avg_buy_price']:,.2f}")
            print(f"  Total Invested:   ${m['total_invested']:,.2f}")
            print(f"  Position (BTC):   {m['position_btc']:.6f}")

        print("-" * 60)
        print(f"  Max Drawdown:     {m['max_drawdown_pct']:.2f}%")
        if "sharpe_ratio" in m:
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
