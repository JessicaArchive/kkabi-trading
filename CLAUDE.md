# CLAUDE.md — Kkabi Trading

## 1. 프로젝트 설명

**Kkabi Trading**은 암호화폐 자동매매 분석 플랫폼이다.
다중 전략(Multi-Strategy) 시그널 생성, 백테스팅, 텔레그램 알림을 통합한 Python 기반 트레이딩 시스템.

- **핵심 기능**: 기술적 지표 기반 매수/매도 시그널 생성
- **운영 방식**: tmux 상주 데몬이 1h/4h 캔들 마감마다 분석 실행
- **알림**: BUY/SELL 시그널 발생 시 텔레그램 자동 전송, HOLD는 무시
- **백테스팅**: 과거 데이터로 전략 성능 검증 가능
- **대상 페어**: BTC/USDT (설정으로 변경 가능)

## 2. 기술 스택

| 분류 | 기술 | 용도 |
|------|------|------|
| 언어 | Python 3.11+ | 메인 런타임 |
| 거래소 API | ccxt ≥4.0 | 100+ 거래소 통합 추상화 |
| 데이터 처리 | pandas, numpy | OHLCV 데이터 분석, 지표 계산 |
| 시각화 | plotly | 차트 렌더링 |
| 봇 프레임워크 | python-telegram-bot ≥21.0 | 텔레그램 커맨드 핸들링 |
| 환경 설정 | python-dotenv | .env 기반 설정 로드 |
| 실행 환경 | tmux | 시그널 데몬 백그라운드 상주 |

## 3. 아키텍처

### 디렉토리 구조

```
kkabi-trading/
├── main.py                 # 메인 트레이딩 루프 (단일 실행 / 반복)
├── signal_daemon.py        # tmux 상주 시그널 데몬 (1h/4h 자동 분석)
├── run_backtest.py         # 백테스트 CLI 러너
├── run_telegram.py         # 텔레그램 봇 런처
├── config.py               # 환경변수 기반 설정 로더
│
├── exchange/
│   └── client.py           # CCXT 래퍼 (Facade 패턴)
│
├── strategy/               # 전략 모듈 (Strategy 패턴)
│   ├── __init__.py         # 전략 팩토리 (create_strategy)
│   ├── base.py             # PentaScore — 5지표 투표 전략
│   ├── ichimoku.py         # 일목균형표 — 구름 기반 전략
│   ├── mean_reversion.py   # 평균회귀 — 통계적 극단값 전략
│   └── breakout_hunter.py  # 브레이크아웃 — 변동성 확장 전략
│
├── backtest/
│   └── engine.py           # 바-바이-바 백테스트 엔진
│
├── telegram_bot/
│   └── bot.py              # KkabiBot 텔레그램 핸들러
│
├── utils/
│   └── logger.py           # 로깅 설정
│
└── data/                   # 히스토리컬 데이터 캐시 (gitignore)
```

### 모듈 의존성

```
config.py ◄──────────────────── 모든 모듈이 참조
    │
    ▼
exchange/client.py ◄──────────── CCXT 래핑
    │
    ├──► strategy/*.py           각 전략이 client를 통해 OHLCV 조회
    │       │
    │       ▼
    │   analyze() → {signal, scores, total, details}
    │
    ├──► backtest/engine.py      히스토리컬 OHLCV → 시뮬레이션
    │
    ├──► signal_daemon.py        전략 결과 → 텔레그램 전송
    │
    └──► telegram_bot/bot.py     /analyze 등 커맨드 → 전략 호출
```

## 4. 디자인 패턴

### Factory Pattern — 전략 생성
`strategy/__init__.py`의 `create_strategy(name, client, symbol)` 함수가 문자열 이름으로 전략 인스턴스를 생성한다.

```python
STRATEGIES = {
    "base": BaseStrategy,
    "ichimoku": IchimokuStrategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout_hunter": BreakoutHunterStrategy,
}
```

### Strategy Pattern — 전략 인터페이스
모든 전략은 동일한 인터페이스를 구현한다:

```python
def analyze(timeframe: str) -> dict:
    return {
        "signal": "BUY" | "SELL" | "HOLD",
        "scores": {지표명: 점수},
        "total": int,
        "details": {지표 상세값}
    }
```

### Facade Pattern — 거래소 클라이언트
`exchange/client.py`가 CCXT 라이브러리의 복잡성을 숨기고, `get_ticker()`, `get_ohlcv()`, `create_order()` 등 단순화된 인터페이스를 제공한다.

### Command Pattern — 텔레그램 봇
각 슬래시 커맨드(`/status`, `/analyze`, `/backtest`)가 독립적인 핸들러 함수에 매핑된다.

### Observer Pattern (Polling) — 시그널 데몬
`signal_daemon.py`가 캔들 마감 시점을 폴링으로 감시하고, 조건 충족 시 텔레그램 알림을 트리거한다.

## 5. 흐름

### 5.1 시그널 데몬 흐름 (signal_daemon.py) — 메인 운영 모드

```
시작
 ├─► 현재 시각 확인
 │    ├─ 정시 마감 5분 이내 → 즉시 분석
 │    └─ 아니면 → 다음 정시까지 대기
 │
 ▼
[매시 정각 + 15초] ─────────────────────────────────
 │
 ├─► BaseStrategy.analyze("1h")
 │    └─ BUY/SELL → 텔레그램 전송
 │    └─ HOLD → 패스
 │
 ├─► IchimokuStrategy.analyze("1h")
 │    └─ BUY/SELL → 텔레그램 전송
 │    └─ HOLD → 패스
 │
 ├─► UTC 시각이 0,4,8,12,16,20시? ──── Yes ──►
 │    │                                        │
 │    │   ├─► BaseStrategy.analyze("4h")       │
 │    │   │    └─ BUY/SELL → 텔레그램          │
 │    │   └─► IchimokuStrategy.analyze("4h")   │
 │    │        └─ BUY/SELL → 텔레그램          │
 │    │                                        │
 │    └─────────────── No ─── 1h만 분석 ◄──────┘
 │
 └─► 다음 정시까지 sleep → 반복
```

### 5.2 텔레그램 봇 흐름 (run_telegram.py)

```
/status  → get_ticker() → 가격/변동률/거래량 표시
/analyze → strategy.analyze() → 각 지표별 점수 + 시그널 표시
/backtest → fetch_historical → BacktestEngine.run() → 성과 리포트
/config  → Config 값 표시
```

### 5.3 백테스트 흐름 (run_backtest.py)

```
CLI 인자 파싱 (--symbol, --timeframe, --days, --capital)
 → CCXT로 히스토리컬 OHLCV 조회
 → BacktestEngine.run(df)
   → 봉마다 지표 계산 → 점수 산정
   → BUY/SELL/SL/TP 체크 → 포지션 관리
   → 수익률, 승률, 샤프비율, MDD 계산
 → 리포트 출력
```

### 5.4 매수/매도 판단 기준

**공통**: 총점 ≥ +3 → BUY, ≤ -3 → SELL, 그 사이 → HOLD

| 전략 | 점수 범위 | 지표 수 | 성격 |
|------|-----------|---------|------|
| PentaScore | -10 ~ +10 | 5개 (SMA, MACD, 볼린저, RSI, 거래량) | 추세추종 |
| Ichimoku | -8 ~ +8 | 5개 (전환/기준, 구름, 미래구름, 후행, 두께) | 균형분석 |
| MeanReversion | -10 ~ +10 | 5개 (Z-Score, StochRSI, ATR, Keltner, ROC) | 역추세 |
| BreakoutHunter | -10 ~ +10 | 5개 (Donchian, ADX, Squeeze, OBV, Range) | 돌파매매 |

## 6. 개발 규칙

- 새 전략 추가 시: `strategy/` 아래에 파일 생성 → `analyze()` 구현 → `__init__.py`의 `STRATEGIES` dict에 등록
- 모든 전략의 `analyze()` 반환값은 `{signal, scores, total, details}` 형식 유지
- 거래소 관련 호출은 반드시 `exchange/client.py`를 통해서만 수행
- `.env`에 시크릿 저장, 코드에 하드코딩 금지
- 커밋 전 `feature/` 또는 `fix/` 브랜치 생성 필수
