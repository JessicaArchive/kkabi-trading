"""
레버리지 B&H 시뮬레이션
- 대출금으로 BTC 한방 매수
- 매월 BTC 일부 매도하여 이자 충당
- 만기 시 BTC 매도하여 원금 상환
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import ccxt
import pandas as pd


def fetch_daily_data(days: int) -> pd.DataFrame:
    """일봉 데이터 가져오기"""
    exchange = ccxt.binance({"enableRateLimit": True})
    since = int((time.time() - days * 86400) * 1000)

    all_data = []
    while True:
        batch = exchange.fetch_ohlcv("BTC/USDT", "1d", since=since, limit=1000)
        if not batch:
            break
        all_data.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def simulate_leverage_bnh(df: pd.DataFrame, principal: float, annual_rate: float, fee_rate: float = 0.001):
    """레버리지 B&H 시뮬레이션"""
    entry_price = df.iloc[0]['close']
    btc_amount = (principal * (1 - fee_rate)) / entry_price
    initial_btc = btc_amount

    monthly_interest = principal * (annual_rate / 12)
    total_interest_paid = 0
    total_btc_sold = 0
    months = 0
    last_month = df.iloc[0]['timestamp'].month
    margin_call = False

    for _, row in df.iterrows():
        cm = row['timestamp'].month
        if cm != last_month:
            months += 1
            btc_to_sell = monthly_interest / (row['close'] * (1 - fee_rate))
            if btc_to_sell <= btc_amount:
                btc_amount -= btc_to_sell
                total_interest_paid += monthly_interest
                total_btc_sold += btc_to_sell
            else:
                total_interest_paid += btc_amount * row['close'] * (1 - fee_rate)
                btc_amount = 0
                margin_call = True
                break
            last_month = cm

    final_price = df.iloc[-1]['close']
    portfolio = btc_amount * final_price * (1 - fee_rate)  # 매도 수수료 반영
    net_profit = portfolio - principal  # 원금 상환 후

    # 일반 B&H
    bnh_btc = (principal * (1 - fee_rate)) / entry_price
    bnh_final = bnh_btc * final_price * (1 - fee_rate)  # 매도 수수료 반영
    bnh_return = ((bnh_final - principal) / principal) * 100

    # DCA
    total_months = max(months, 1)
    monthly_invest = principal / total_months
    dca_btc = 0
    dca_invested = 0
    lm = df.iloc[0]['timestamp'].month
    dca_btc += (monthly_invest * (1 - fee_rate)) / df.iloc[0]['close']
    dca_invested += monthly_invest
    for _, row in df.iterrows():
        if row['timestamp'].month != lm:
            if dca_invested < principal:
                invest = min(monthly_invest, principal - dca_invested)
                dca_btc += (invest * (1 - fee_rate)) / row['close']
                dca_invested += invest
            lm = row['timestamp'].month
    dca_final = dca_btc * final_price * (1 - fee_rate)  # 매도 수수료 반영
    dca_return = ((dca_final - dca_invested) / dca_invested) * 100

    return {
        'entry_price': entry_price,
        'final_price': final_price,
        'btc_change_pct': ((final_price - entry_price) / entry_price) * 100,
        'annual_rate_pct': annual_rate * 100,
        'months': months,
        'initial_btc': initial_btc,
        'final_btc': btc_amount,
        'btc_sold': total_btc_sold,
        'btc_remaining_pct': (btc_amount / initial_btc) * 100 if initial_btc > 0 else 0,
        'total_interest': total_interest_paid,
        'portfolio': portfolio,
        'net_profit': net_profit,
        'leverage_return_pct': (net_profit / principal) * 100,  # 대출원금 대비 순이익률
        'bnh_return_pct': bnh_return,
        'dca_return_pct': dca_return,
        'margin_call': margin_call,
    }


def main():
    periods = [
        ("1년", 365),
        ("3년", 1095),
        ("8.5년", 3100),
    ]

    rates = [0.04, 0.06, 0.08]
    principal = 10000  # $10,000

    for period_name, days in periods:
        print(f"\n{'='*70}")
        print(f"  {period_name} 시뮬레이션 (대출금 ${principal:,})")
        print(f"{'='*70}")

        df = fetch_daily_data(days)
        print(f"  데이터: {df.iloc[0]['timestamp'].strftime('%Y-%m-%d')} ~ {df.iloc[-1]['timestamp'].strftime('%Y-%m-%d')}")

        for rate in rates:
            r = simulate_leverage_bnh(df, principal, rate)

            mc = " ⚠️ 마진콜!" if r['margin_call'] else ""
            print(f"\n--- 연 {r['annual_rate_pct']:.0f}% ---{mc}")
            print(f"BTC: ${r['entry_price']:,.0f} → ${r['final_price']:,.0f} ({r['btc_change_pct']:+.1f}%)")
            print(f"초기 BTC: {r['initial_btc']:.6f}")
            print(f"이자 납부: ${r['total_interest']:,.0f} ({r['months']}개월, 매월 ${principal * rate / 12:,.0f})")
            print(f"이자용 매도: {r['btc_sold']:.6f} BTC ({100 - r['btc_remaining_pct']:.1f}%)")
            print(f"잔여 BTC: {r['final_btc']:.6f} ({r['btc_remaining_pct']:.1f}%)")
            print(f"")
            print(f"포트폴리오 가치: ${r['portfolio']:,.0f}")
            print(f"원금상환 후 순이익: ${r['net_profit']:,.0f}")
            print(f"")
            print(f"📊 레버리지 B&H: {r['leverage_return_pct']:+.2f}% (대출원금 ${principal:,} 대비 순이익률)")
            print(f"📊 일반 B&H:     {r['bnh_return_pct']:+.2f}% (내돈 ${principal:,})")
            print(f"📊 DCA:          {r['dca_return_pct']:+.2f}% (내돈 ${principal:,})")


if __name__ == "__main__":
    main()
