# Kkabi Trading

암호화폐 트레이딩 봇 & 분석 도구. 자동 시그널 분석, 백테스트, 텔레그램 알림을 지원한다.

## Features

### Trading Strategies
- **PentaScore v1.0** — 5개 지표(SMA, MACD, BB, RSI, Volume) 종합 스코어링 (-9 ~ +9)
- **Fear & Greed Contrarian v1.0** — Crypto Fear & Greed Index 기반 역발상 전략

### Backtesting
- PentaScore 기반 백테스트 (손절/익절/트렌드 필터)
- 드러켄밀러 스타일 백테스트 (확신도 기반 사이징 + 피라미딩 + 트레일링 스탑)
- 레버리지 Buy & Hold 시뮬레이션
- 성과 지표: 수익률, 승률, Profit Factor, MDD, Sharpe Ratio

### Telegram Bot
- `/status` — 현재 가격 & 24h 변동
- `/analyze` — PentaScore + Fear & Greed 통합 분석
- `/backtest` — 30일 백테스트 실행
- `/config` — 현재 설정 확인
- `/monitor` — 자동 시그널 모니터링 ON/OFF (1H/4H/F&G)

### CLI
```bash
python3 -m cli analyze          # PentaScore + F&G 분석
python3 -m cli show_price       # 현재 가격
python3 -m cli show_config      # 설정 확인
python3 -m cli backtest --days 90  # 90일 백테스트
```

## Tech Stack

- **Language**: Python 3.11+
- **Exchange API**: ccxt (멀티 거래소)
- **Data**: pandas, numpy
- **Visualization**: plotly
- **Bot**: python-telegram-bot

## Getting Started

```bash
# Clone
git clone https://github.com/JessicaArchive/kkabi-trading.git
cd kkabi-trading

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# .env 파일에 API 키 & 텔레그램 토큰 설정

# Run
python main.py              # 시그널 분석 (단일 실행)
python run_telegram.py      # 텔레그램 봇 실행
python run_backtest.py      # 백테스트 실행
```

## Configuration

`.env` 파일에서 설정:

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `EXCHANGE_NAME` | 거래소 | binance |
| `SYMBOL` | 거래 쌍 | BTC/USDT |
| `TIMEFRAME` | 봉 주기 | 1h |
| `TRADE_AMOUNT` | 거래 금액 (USDT) | 100 |
| `STOP_LOSS_PERCENT` | 손절 % | 1.5 |
| `TAKE_PROFIT_PERCENT` | 익절 % | 3.0 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | - |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | - |

## Project Structure

```
kkabi-trading/
├── main.py                 # 엔트리포인트 (시그널 분석 루프)
├── run_backtest.py         # 백테스트 실행기
├── run_telegram.py         # 텔레그램 봇 실행기
├── cli.py                  # CLI 브릿지
├── config.py               # 설정 로더 (.env)
├── exchange/
│   └── client.py           # CCXT 거래소 래퍼
├── strategy/
│   ├── base.py             # PentaScore 전략
│   └── fear_greed.py       # Fear & Greed 역발상 전략
├── backtest/
│   ├── engine.py           # 백테스트 엔진
│   └── leverage_bnh.py     # 레버리지 B&H 시뮬레이션
├── telegram_bot/
│   └── bot.py              # 텔레그램 봇 (명령어 + 모니터링)
├── utils/
│   └── logger.py           # 로깅 설정
├── data/                   # 런타임 데이터 (DB, 로그)
├── requirements.txt
├── .env.example
└── .gitignore
```

## License

MIT
