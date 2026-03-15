# Kkabi Trading

BTC/USDT 자동 시그널 분석 및 알림 시스템. 다중 전략 기반 매수/매도 시그널을 생성하고 텔레그램으로 알림을 보낸다.

## Features

- **4가지 독립 전략**: PentaScore, Ichimoku, MeanReversion, BreakoutHunter
- **자동 시그널 데몬**: tmux 상주, 1h/4h 캔들 마감마다 분석
- **텔레그램 봇**: 실시간 가격 조회, 분석, 백테스트 실행
- **백테스팅**: 과거 데이터 기반 전략 성능 검증
- **멀티 타임프레임**: 1시간봉 + 4시간봉 동시 분석

## Tech Stack

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| 거래소 API | ccxt (Binance 기본, 100+ 거래소 지원) |
| 데이터 | pandas, numpy |
| 시각화 | plotly |
| 봇 | python-telegram-bot ≥21.0 |
| 실행 환경 | tmux |

## Quick Start

```bash
# 설치
git clone https://github.com/JessicaArchive/kkabi-trading.git
cd kkabi-trading
pip install -r requirements.txt

# 설정
cp .env.example .env
# .env 파일에 API 키, 텔레그램 토큰 입력

# 시그널 데몬 실행 (메인 운영 모드)
tmux new -s kkabi-signal
python signal_daemon.py
# Ctrl+B, D 로 detach

# 텔레그램 봇 실행
python run_telegram.py

# 백테스트
python run_backtest.py --symbol BTC/USDT --timeframe 1h --days 30
```

## Project Structure

```
kkabi-trading/
├── signal_daemon.py        # 시그널 데몬 (1h/4h 자동 분석 + 텔레그램 알림)
├── main.py                 # 메인 트레이딩 루프
├── run_backtest.py         # 백테스트 CLI
├── run_telegram.py         # 텔레그램 봇 런처
├── config.py               # 환경변수 설정 로더
│
├── exchange/
│   └── client.py           # CCXT 거래소 클라이언트
│
├── strategy/
│   ├── __init__.py         # 전략 팩토리
│   ├── base.py             # PentaScore (5지표 투표)
│   ├── ichimoku.py         # 일목균형표
│   ├── mean_reversion.py   # 평균회귀
│   └── breakout_hunter.py  # 변동성 브레이크아웃
│
├── backtest/
│   └── engine.py           # 백테스트 엔진
│
├── telegram_bot/
│   └── bot.py              # 텔레그램 봇 핸들러
│
└── utils/
    └── logger.py           # 로깅
```

## Strategies

모든 전략은 동일한 판단 기준: **총점 ≥ +3 → BUY**, **≤ -3 → SELL**, 사이 → HOLD

| 전략 | 지표 | 성격 |
|------|------|------|
| **PentaScore** | SMA, MACD, 볼린저밴드, RSI, 거래량 | 추세추종 |
| **Ichimoku** | 전환/기준선, 구름, 미래구름, 후행스팬, 구름두께 | 균형분석 |
| **MeanReversion** | Z-Score, StochRSI, ATR, Keltner, ROC | 역추세 |
| **BreakoutHunter** | Donchian, ADX, Squeeze, OBV, Range | 돌파매매 |

## Signal Daemon

시그널 데몬은 tmux에서 상주하며 캔들 마감마다 자동 분석한다.

```
매시 정각 + 15초
├── PentaScore 1h 분석 → BUY/SELL이면 텔레그램 전송
├── Ichimoku 1h 분석 → BUY/SELL이면 텔레그램 전송
│
└── 4시간 경계 (0,4,8,12,16,20 UTC)
    ├── PentaScore 4h 분석
    └── Ichimoku 4h 분석
```

HOLD일 때는 알림 없음.

## Telegram Bot Commands

| 커맨드 | 기능 |
|--------|------|
| `/status` | 현재 가격, 24h 변동, 거래량 |
| `/analyze` | 전체 전략 분석 + 지표별 점수 |
| `/backtest` | 30일 백테스트 실행 |
| `/config` | 현재 설정 표시 |

## Configuration (.env)

```env
EXCHANGE_NAME=binance
API_KEY=your_api_key
API_SECRET=your_api_secret
SYMBOL=BTC/USDT
TIMEFRAME=1h
TRADE_AMOUNT=100
STOP_LOSS_PERCENT=1.5
TAKE_PROFIT_PERCENT=3.0
STRATEGY=base
LOOP_INTERVAL=0
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## License

MIT
