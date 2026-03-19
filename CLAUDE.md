# CLAUDE.md — Kkabi Trading

## 프로젝트 개요
BTC/USDT 암호화폐 시그널 분석 + 백테스트 플랫폼. Binance API 기반.
실매매 기능은 비활성화 상태 (main.py에서 주문 실행 코드 주석 처리됨).

## 기술 스택
- Python 3.9+
- ccxt (거래소 API), pandas/numpy (데이터), plotly (시각화)
- python-telegram-bot (텔레그램 봇), python-dotenv (환경변수)

## 디렉토리 구조
```
├── main.py                 # 라이브 분석 엔트리포인트 (단일실행/루프)
├── cli.py                  # Node.js 연동 CLI 브릿지
├── run_backtest.py         # 백테스트 CLI
├── run_telegram.py         # 텔레그램 봇 실행
├── config.py               # .env 기반 설정 로더
├── Kkabi_Trading.command   # macOS 봇 자동재시작 런처
│
├── strategy/               # 매매 전략
│   ├── __init__.py         # 전략 레지스트리 + 팩토리
│   ├── base.py             # PentaScore v1.0 (SMA/MACD/BB/RSI/Volume)
│   ├── fear_greed.py       # Fear & Greed 역발상 전략
│   ├── ichimoku.py         # 일목균형표 전략
│   ├── mean_reversion.py   # 평균회귀 전략
│   └── breakout_hunter.py  # 변동성 돌파 전략
│
├── backtest/               # 백테스트 엔진
│   ├── engine.py           # 3가지 모드: standard / druckenmiller / dca
│   └── leverage_bnh.py     # 레버리지 B&H 시뮬레이션
│
├── exchange/
│   └── client.py           # CCXT 래퍼 (인증/비인증 모드)
│
├── telegram_bot/
│   └── bot.py              # 텔레그램 명령어 핸들러 + 자동 모니터링
│
├── utils/
│   └── logger.py           # 로깅 설정
│
└── data/                   # 런타임 데이터 (gitignore)
    ├── kkabi.db            # SQLite DB
    └── crons.json          # 크론잡 설정
```

## 전략 시스템

### PentaScore (BaseStrategy) — 핵심 전략
5개 지표 점수 합산: **-9 ~ +9**
| 지표 | 범위 | 설명 |
|------|------|------|
| SMA (7/25/99 EMA) | -2 ~ +2 | 이동평균 배열 |
| MACD (12/26/9) | -2 ~ +2 | 모멘텀 |
| Bollinger (20, 2σ) | -2 ~ +2 | 변동성 |
| RSI (14) | -2 ~ +2 | 과매수/과매도 |
| Volume (20 SMA) | -1 ~ +1 | 거래량 확인 |

시그널: `BUY ≥ +3` / `SELL ≤ -3` / 나머지 `HOLD`

### 기타 전략
- **FearGreed**: F&G 지수 역발상 (극도공포=매수, 극도탐욕=매도)
- **Ichimoku**: 일목균형표 (구름, 전환선/기준선)
- **MeanReversion**: 평균회귀 (BB+RSI+거래량)
- **BreakoutHunter**: 변동성 돌파 (BB 밴드폭+거래량 급증)

팩토리: `create_strategy("base", client, symbol)`

## 백테스트 엔진
3가지 모드:
1. **Standard**: 시그널 기반 매수/매도, SL/TP, 수수료 0.1%
2. **Druckenmiller**: 확신도 비례 포지션 사이징 + 피라미딩 + 트레일링 스탑
3. **DCA**: 정액/SMA/드로다운/RSI 가중 적립식

```bash
python run_backtest.py --days 90 --druckenmiller --trend-filter
```

## 텔레그램 봇 명령어
`/status` `/analyze` `/backtest` `/config` `/monitor`

## 설정
`.env` 파일 사용. `.env.example` 참고.
주요: `EXCHANGE_NAME`, `SYMBOL`, `TIMEFRAME`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## 개발 규칙
- main 직접 커밋 금지 — 항상 feature 브랜치 → PR
- 브랜치명: `feature/<설명>`, `fix/<설명>`, `docs/<설명>`
- 커밋 메시지: 한국어, `feat:` / `fix:` / `docs:` 접두사
- force push, 브랜치 삭제, PR 머지 금지 (사용자가 직접 함)
- API 키나 시크릿 절대 커밋하지 않기

## 자주 쓰는 명령어
```bash
python main.py                    # 라이브 분석
python run_telegram.py            # 텔레그램 봇
python run_backtest.py --days 30  # 30일 백테스트
python3 -m cli analyze            # CLI 분석
python3 -m cli show_price         # 현재가 조회
```

## 주의사항
- `data/` 디렉토리는 gitignore — DB, 로그, 크론 런타임 데이터
- 실매매 코드는 main.py에 주석 처리 상태 — 함부로 활성화하지 않기
- 지표 계산에 최소 99캔들 필요 (SMA99), 트렌드 필터 시 200캔들
- F&G 지수는 하루 1회 갱신 (타임프레임 무관 동일값)
