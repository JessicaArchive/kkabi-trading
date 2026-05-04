# Kkabi 페이퍼 트레이딩 앱 — Phase 1 Design

**작성일**: 2026-05-04
**Phase**: 1 (MVP — Day-1 빠른 빌드)
**상태**: 빌드 중

## 개요

매일 AI(Claude)가 BTC/KRW 트레이딩 전략 후보 3개를 한국어 설명과 함께 생성한다. 사용자는 텔레그램으로 1개를 선택하고, 선택된 전략은 가상 자본 ₩100,000으로 페이퍼 트레이딩에 합류한다. 결과는 PWA 모바일 웹앱(다크 스타일)에서 Tailscale을 통해 어디서든 볼 수 있다.

## Day-1 MVP Scope (오늘 빌드 — 자정 데드라인)

**포함**:
- DB 4 테이블 + SQLAlchemy 모델
- 페이퍼 엔진 (BUY/SELL/HOLD 시뮬레이션, compound 자본, 수수료 0.05% × 2)
- AI 후보 생성 (Anthropic SDK + 기본 보안 검증)
- 텔레그램 명령어: `/candidates`, `/select`, `/skip`, `/generate`
- crontab: 8AM 후보 생성, 매시 정각 사이클
- Flask 단일 페이지 웹앱 (전략 목록, 모바일 반응형, Tailwind CDN, 다크)
- PWA manifest.json + 단순 아이콘 (홈화면 설치 가능)
- Tailscale IP (100.85.76.9:5000) 바인딩
- E2E 한 사이클 수동 검증

**제외 (phase 2로)**:
- 단위 테스트 — E2E 수동 검증으로 대체
- 전략 상세 페이지 — 목록 row에 펼쳐서 표시 (or 클릭 expand)
- HTMX 5초 폴링 — 수동 새로고침
- 정렬 옵션 — 수익률 desc 고정
- 디자인 미세 조정 — 못생김 OK
- AST 위험 호출 패턴 차단 — phase 2 (import 화이트리스트만)
- 거래 내역 별도 화면 — 목록에 최근 1건만 표시

**시간 분배 (~6시간)**:
| 시간 | 단계 |
|---|---|
| 1h | DB 모델 + alembic 없이 create_all() |
| 1.5h | 페이퍼 엔진 (engine.py + 시뮬레이션 함수들) |
| 1.5h | AI 후보 생성 + 보안 검증 + 텔레그램 핸들러 |
| 0.5h | crontab 등록 (`crontab -e`로 단순) |
| 1h | Flask 단일 페이지 + PWA |
| 0.5h | E2E 한 사이클 검증 + 핸드폰 PWA 설치 |

## 비기능 요구사항

| 항목 | 결정 |
|---|---|
| 사용자 수 | 1명 (본인) |
| 인증 | 없음. Tailscale VPN으로 네트워크 격리 |
| 호스트 | 맥미니 (24/7 가동) |
| 외부 접속 | Tailscale (개인 VPN, 무료) |
| 모바일 | PWA — 홈화면 설치, 풀스크린 |
| 페이퍼 트레이딩 시그널 주기 | 1시간 (BTC/KRW 1시간봉) |
| 평가손익 갱신 | 5초 폴링 (HTMX) |
| 자본 모델 | 각 전략 독립 ₩100,000, compound (매도 후 잔액 누적) |
| 시뮬레이션 | ticker.last 기준, 수수료 0.05% × 2회, SL/TP 없음 |
| AI 후보 생성 시각 | 매일 오전 8시 KST |
| 페이퍼 대상 | 선택된 새 전략들만 (기존 100개 라이브러리는 제외) |

## 아키텍처

```
┌─────────────────────── 맥미니 (24/7) ────────────────────────┐
│                                                                │
│  ┌─────────────────┐   ┌─────────────────┐                   │
│  │ paper engine    │   │  Flask + HTMX   │                   │
│  │ (1h cron)       │   │  + Tailwind     │                   │
│  └────────┬────────┘   └────────┬────────┘                   │
│           │                     │                              │
│           └──────────┬──────────┘                             │
│                      ↓                                         │
│              ┌──────────────┐                                 │
│              │  kkabi.db    │  (SQLite)                       │
│              └──────────────┘                                 │
│                                                                │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │ candidates cron (8AM)    │  │  Telegram bot             │ │
│  │ → Anthropic SDK          │  │  /candidates /select      │ │
│  └──────────────────────────┘  └──────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                              ↓ Tailscale
                  ┌─── 핸드폰 (PWA) ────┐
                  │ 홈화면 → 풀스크린     │
                  │ Tailscale IP:5000   │
                  └──────────────────────┘
```

### 기존 시스템과의 격리

- `strategy/` (5개 전략, 자동매매용) — **건드리지 않음**
- `strategies/` (100개 전략 라이브러리) — **건드리지 않음**
- `run_auto_trade.py` (실거래 자동매매) — **건드리지 않음**
- 페이퍼 트레이딩은 `paper/`, `webapp/`, `strategies_generated/`에 신규 모듈로 격리

## 컴포넌트

### 디렉토리 구조 (신규 추가분만)

```
kkabi-trading/
├── paper/
│   ├── __init__.py
│   ├── engine.py              # 페이퍼 트레이딩 엔진
│   ├── candidates.py          # AI 후보 생성 (Anthropic SDK)
│   ├── strategy_loader.py     # AI 전략 동적 로드
│   ├── security.py            # 코드 검증 정책 (화이트리스트, AST 룰)
│   └── models.py              # SQLAlchemy 모델
├── webapp/
│   ├── app.py                 # Flask 앱
│   ├── routes.py              # 라우트 핸들러
│   ├── templates/
│   │   ├── base.html          # 다크 + 모바일-first
│   │   ├── strategies.html    # 목록 화면
│   │   ├── strategy_detail.html
│   │   └── partials/
│   │       ├── strategy_row.html  # HTMX 부분 갱신용
│   │       └── pnl_cell.html
│   └── static/
│       ├── manifest.json      # PWA
│       ├── icon-192.png
│       ├── icon-512.png
│       └── styles.css         # Tailwind 빌드 결과
├── strategies_generated/      # 선택된 AI 전략 코드 (날짜_id_name.py)
├── telegram_bot/
│   └── bot.py                 # /candidates, /select, /skip 명령 추가
├── data/
│   └── kkabi.db               # 새 테이블 4개 추가
└── run_paper.py                # 페이퍼 시스템 entry (cron + Flask 동시 실행)
```

### 모듈별 책임

#### `paper/engine.py`
- `tick()`: 1시간 사이클 — 모든 활성 전략에 대해 분석/시뮬레이션
- `simulate_buy(strategy, price, score)`: 가상 KRW로 시장가 매수, 수수료 차감
- `simulate_sell(strategy, price, score)`: 보유 BTC 매도, 실현 PnL 계산
- `mark_to_market(strategy, current_price)` → 평가손익 (호출 시 계산, DB 저장 X)

#### `paper/candidates.py`
- `generate_daily_candidates()`: `claude --print --output-format json` subprocess 호출 → 3개 전략 코드+설명+가설 반환
- API 키 X — 사용자의 Claude Code 인증(OAuth/Keychain) 사용
- 도구 사용 차단: `--disallowedTools "Bash Edit Write Read"` (텍스트 생성만)
- JSON Schema로 응답 형식 강제
- 코드 검증은 `paper/security.py`로 위임
- 호출 실패 시 텔레그램 알림 + 10분 후 1회 재시도

#### `paper/security.py`
- `validate_strategy_code(code) -> (ok, reason)`: AST 파싱 + 화이트리스트 + 위험 노드 차단
- `ALLOWED_IMPORTS`: 허용 모듈 상수 (`numpy`, `pandas`, `ccxt`, `datetime`, `logging`, `typing`, `math`)
- `BLOCKED_AST_PATTERNS`: 차단할 호출 패턴 (시스템/IO/동적 코드 실행 관련, 정확한 목록은 코드)

#### `paper/strategy_loader.py`
- `load_strategy(file_path)`: 파일 동적 import + 인스턴스화 (캐시)
- `register_strategy(candidate_id)`: candidate → strategies_generated 파일 저장 → DB.strategies INSERT

#### `paper/models.py`
- SQLAlchemy ORM 모델 (Candidate, Strategy, PaperTrade, Signal)
- `data/kkabi.db` 공유, alembic 없이 단순 `Base.metadata.create_all()`로 시작

#### `webapp/app.py` + `routes.py`
- Flask 앱 인스턴스 + 라우트 등록
- HTMX 부분 갱신을 위해 partial 템플릿 분리

#### `telegram_bot/bot.py` (기존 파일에 추가)
- `/candidates`: 오늘의 후보 다시 보여주기
- `/select <1|2|3>`: 후보 선택 → 페이퍼 트레이딩 등록
- `/skip`: 오늘은 0개 선택
- `/generate`: AI 후보 수동 생성 (8AM cron 실패 시 fallback)
- 8AM cron이 새 후보 생성하면 자동으로 텔레그램 push

## 데이터 흐름

### A. 매일 아침 8시 — AI 후보 생성

```
1. cron (또는 macOS launchd) → run_paper.py --candidates
2. paper.candidates.generate_daily_candidates()
   - Anthropic SDK 호출 (Claude Sonnet 4.6)
   - 프롬프트: "BTC/KRW 1시간봉 전략 3개를 서로 다른 시장 가설로 생성"
3. 각 후보:
   - paper.security.validate_strategy_code(code)
   - 통과하면 DB.candidates INSERT (status=pending)
   - 실패하면 reject + 다른 후보 재시도 (최대 5회)
4. Telegram bot이 채널에 push:
   "🤖 오늘의 후보 3개 도착
    1) MeanRevert-RSI-21 — RSI 과매도 반등
    2) TrendFollow-Vol-Burst — 거래량 급증 추세 추종
    3) BB-Squeeze-Breakout — 볼린저 수축 후 돌파
    /select 1|2|3 또는 /skip"
```

### B. 사용자 선택 (텔레그램)

```
1. /select 2 → bot 핸들러
2. DB.candidates UPDATE: 선택=selected, 나머지=rejected
3. paper.strategy_loader.register_strategy(candidate_id=2):
   - code → strategies_generated/<YYYY-MM-DD>_<candidate_id>_<safe_name>.py 저장
   - DB.strategies INSERT (initial_krw=100000, cash_krw=100000, btc=0, status=active)
4. 텔레그램 응답: "✅ TrendFollow-Vol-Burst 등록 — 다음 정각부터 페이퍼 트레이딩 시작"
```

### C. 매시간 정각 — 페이퍼 트레이딩 사이클

```
1. cron (매시 정각 +5초) → run_paper.py --tick
2. paper.engine.tick():
   a. ccxt로 BTC/KRW 1시간봉 OHLCV (200캔들) + 현재가 fetch
   b. DB.strategies WHERE status='active' SELECT
   c. for each strategy:
      - load_strategy(file_path) → instance.analyze("1h") → {signal, total, ...}
      - DB.signals INSERT (signal=BUY/SELL/HOLD, score, price)
      - if signal==BUY and btc==0:
          simulate_buy(strategy, price, score) → DB.paper_trades INSERT
          DB.strategies UPDATE (cash_krw, btc, avg_entry_price)
      - elif signal==SELL and btc>0:
          simulate_sell(strategy, price, score) → DB.paper_trades INSERT (with realized_pnl)
          DB.strategies UPDATE (cash_krw=cash+net_proceeds, btc=0, avg_entry_price=0)
   d. try/except로 한 전략 예외 시 다른 전략 진행
3. ~5초 정도 걸림 (24개 strategies 기준)
```

### D. 사용자 웹앱 보기 (PWA, 어디서든)

```
1. 핸드폰 PWA 아이콘 탭 → Tailscale → http://<mac-mini>.tail-net.ts.net:5000/
2. Flask /strategies (목록 화면):
   - DB.strategies WHERE status='active' SELECT
   - ccxt로 현재가 1번 fetch (cache 5초)
   - mark_to_market 모든 전략
   - 정렬 (default: 수익률 desc)
   - 렌더링 → strategies.html
3. 5초마다 HTMX 폴링:
   - hx-get="/api/strategies/pnl" hx-trigger="every 5s"
   - partials/pnl_cell.html을 모든 row에 swap
4. 카드 탭 → /strategy/<id>:
   - DB.strategies, DB.paper_trades, DB.candidates JOIN
   - 포지션 + 거래내역 + AI 메모 렌더링
```

## DB 스키마 (SQLite, kkabi.db에 신규 추가)

```sql
-- AI 생성 후보
CREATE TABLE paper_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    name TEXT NOT NULL,                    -- "MeanRevert-RSI-21"
    description_ko TEXT NOT NULL,          -- AI가 만든 한국어 설명
    code TEXT NOT NULL,                    -- 전략 클래스 Python 코드
    hypothesis_ko TEXT NOT NULL,           -- 시장 가설 한 줄
    status TEXT NOT NULL DEFAULT 'pending', -- pending|selected|rejected
    selected_at TIMESTAMP,
    rejection_reason TEXT                  -- 자동 reject 시 사유
);

-- 활성 전략
CREATE TABLE paper_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES paper_candidates(id),
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,               -- strategies_generated/<file>.py
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_krw REAL NOT NULL DEFAULT 100000,
    cash_krw REAL NOT NULL DEFAULT 100000,
    btc REAL NOT NULL DEFAULT 0,
    avg_entry_price REAL NOT NULL DEFAULT 0,  -- 매수 평균가 (BTC > 0일 때)
    status TEXT NOT NULL DEFAULT 'active'    -- active|paused|stopped
);

-- 거래 내역
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL REFERENCES paper_strategies(id),
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    side TEXT NOT NULL,                    -- buy|sell
    price REAL NOT NULL,
    btc REAL NOT NULL,
    krw_gross REAL NOT NULL,               -- 수수료 전 거래 금액
    fee REAL NOT NULL,                     -- 수수료
    krw_net REAL NOT NULL,                 -- 수수료 반영 (buy: 차감, sell: 차감)
    realized_pnl REAL,                     -- 매도 시만, 매수는 NULL
    score INTEGER NOT NULL,                -- 시그널 시 점수
    note TEXT
);

-- 시그널 로그 (HOLD 포함)
CREATE TABLE paper_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL REFERENCES paper_strategies(id),
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signal TEXT NOT NULL,                  -- BUY|SELL|HOLD|NO_DATA|ERROR
    score INTEGER,
    price REAL
);

CREATE INDEX idx_trades_strategy_time ON paper_trades(strategy_id, time);
CREATE INDEX idx_signals_strategy_time ON paper_signals(strategy_id, time);
```

테이블 prefix `paper_`로 기존 테이블과 격리.

## AI 후보 생성 프롬프트 (개략)

```
시스템: 당신은 BTC/KRW 1시간봉 트레이딩 전략을 설계하는 한국어 quant 어시스턴트입니다.

사용자: 다음 조건에 맞는 전략 3개를 만들어주세요.

조건:
- 1시간봉 캔들 200개 이내의 데이터로 평가 가능
- analyze(timeframe) → {"signal": "BUY"|"SELL"|"HOLD", "total": int, "details": dict} 반환
- BaseStrategy 패턴 (인터페이스는 첨부 참고)
- 3개는 서로 다른 시장 가설을 표현 (예: 추세추종/평균회귀/돌파/모멘텀/볼륨)
- 허용 import: numpy, pandas, ccxt (그 외 X)
- numpy/pandas로 지표 계산, ccxt는 self.client 통해서만

출력 형식 (JSON):
[
  {
    "name": "이름-가설형식 (예: MeanRevert-RSI-Lower-30)",
    "hypothesis_ko": "한 줄로 시장 가설",
    "description_ko": "왜 이 전략이 BTC/KRW 1시간봉에서 의미 있는지 한국어 3-5줄",
    "code": "from numpy import ...\nclass <Name>:\n    def __init__(self, client, symbol):\n        ...\n    def analyze(self, timeframe):\n        ..."
  },
  ... (3개)
]

[기존 BaseStrategy 인터페이스 첨부]
```

호출 비용 추정: Sonnet 기준 입력 ~3K + 출력 ~3K tokens × 일 1회 ≈ 일 $0.05~0.15.

## 보안: AI 코드 검증 정책

`paper/security.py`의 `validate_strategy_code(code)`가 다음을 검증한다:

1. **AST parse** — 문법 오류면 reject
2. **Import 화이트리스트** — `numpy`, `pandas`, `ccxt`, `datetime`, `logging`, `typing`, `math`만 허용. 그 외 모든 모듈 import는 reject
3. **위험 호출 차단** — Python 빌트인의 동적 코드 실행 / 파일 IO / 임의 import / 외부 통신 관련 호출은 AST 단계에서 차단. 정확한 차단 패턴 목록은 `paper/security.py`의 `BLOCKED_AST_PATTERNS` 상수
4. **클래스 구조 검증**:
   - 정확히 1개 클래스 정의
   - `__init__(self, client, symbol)` 시그니처
   - `analyze(self, timeframe)` 메서드 존재
5. 통과하지 못하면 `paper_candidates.status='rejected'` + `rejection_reason` 기록

**3개 후보 채우기 흐름**: 1차 AI 호출에서 3개 받음 → 검증 → reject된 만큼 AI 재호출(다른 가설 요청)로 보충. 재호출 최대 5회까지. 5회 후에도 3개에 못 미치면 통과한 후보만 사용자에게 push (0~2개)

이 정책의 목표는 "AI가 생성한 코드가 트레이딩 분석 외의 동작을 하지 못하게 격리"이다. 더 강한 격리(별도 프로세스/RestrictedPython)는 phase 2 후보.

## 화면 디자인 (모바일 first)

### 색상 팔레트 (업비트 다크 컨벤션 + 한국식 빨강/파랑)

| 용도 | Hex |
|---|---|
| 배경 | `#1A1A1A` |
| 카드 배경 | `#222222` |
| 구분선 | `#333333` |
| 본문 텍스트 | `#E0E0E0` |
| 보조 텍스트 | `#888888` |
| 수익 (양수) | `#D24F45` (빨강) |
| 손실 (음수) | `#1261C4` (파랑) |
| 강조/포커스 | `#F2A900` (BTC 오렌지) |

### 타이포그래피
- 시스템 폰트 스택 (`-apple-system, BlinkMacSystemFont, "Pretendard", sans-serif`)
- 숫자: tabular-nums (자릿수 정렬)

### 화면 1: 전략 목록 (`/`)

```
┌───────────────────────────────────┐
│  Kkabi 페이퍼              ⚙ 설정 │
│ ───────────────────────────────── │
│  내 자산 (가상)                    │
│  ₩37,541,200      +12.4%          │
│  활성 전략 24개                    │
│ ───────────────────────────────── │
│  ▼ 정렬: 수익률 ▾                 │
│ ───────────────────────────────── │
│  ◯ MeanRevert-RSI-21              │
│    +18,420       +18.42%          │
│    보유: 0.00098 BTC               │
│  ─────────────────────────────── │
│  ◯ TrendFollow-Vol-Burst          │
│    +12,180       +12.18%          │
│    현금만                          │
│  ─────────────────────────────── │
│  ◯ MACD-Conservative              │
│    -3,450        -3.45%           │
│    보유: 0.00076 BTC              │
│  ─────────────────────────────── │
│         (무한 스크롤)              │
└───────────────────────────────────┘
```

각 row는 카드 형태, 탭하면 `/strategy/<id>`로 이동.

### 화면 2: 전략 상세 (`/strategy/<id>`)

```
┌───────────────────────────────────┐
│  ← MeanRevert-RSI-21               │
│ ───────────────────────────────── │
│  평가손익  +18,420   (+18.42%)     │
│  현재가    ₩118,432,000           │
│ ───────────────────────────────── │
│  포지션                            │
│  보유 BTC  0.00098                │
│  매수가    ₩98,420,000            │
│  현금       ₩21,400               │
│ ───────────────────────────────── │
│  AI 메모 (생성 시)                 │
│  "RSI 30 이하 반등 매수, 거래량   │
│   1.5배 필터로 가짜 신호 제거..." │
│  가설: 단기 과매도 → 평균 회귀     │
│ ───────────────────────────────── │
│  거래 내역 (8건)                   │
│  ─────────────────────────────── │
│  05/04 14:00  매수                │
│    0.00098 BTC @ ₩98,420,000     │
│    수수료 ₩50                     │
│  ─────────────────────────────── │
│  05/03 09:00  매도                │
│    0.00102 BTC @ ₩102,100,000    │
│    +3,720 (+3.72%)                │
│  ─────────────────────────────── │
└───────────────────────────────────┘
```

### PWA manifest.json

```json
{
  "name": "Kkabi 페이퍼",
  "short_name": "Kkabi",
  "description": "BTC/KRW 페이퍼 트레이딩",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1A1A1A",
  "theme_color": "#1A1A1A",
  "icons": [
    {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

`<link rel="manifest" href="/static/manifest.json">` + iOS용 `<meta name="apple-mobile-web-app-capable" content="yes">` 등.

## API Endpoints

| Method | Path | 응답 | 비고 |
|---|---|---|---|
| GET | `/` | strategies.html | 전략 목록 |
| GET | `/strategy/<id>` | strategy_detail.html | 전략 상세 |
| GET | `/api/strategies/pnl` | partials/pnl_cells.html | HTMX 5초 폴링용 |
| GET | `/api/strategy/<id>/pnl` | partials/strategy_pnl.html | 상세 화면 폴링 |
| GET | `/static/manifest.json` | JSON | PWA |
| GET | `/api/health` | text "ok" | 헬스 체크 |

POST/PUT 없음 — 모든 상태 변경은 텔레그램 또는 cron으로만. 웹앱은 read-only.

## Error Handling

| 상황 | 처리 |
|---|---|
| AI 호출 실패 (Anthropic API down/rate limit/network) | 텔레그램 알림 + 10분 후 1회 재시도. 모두 실패 시 그날 0개 후보 + 사용자가 `/generate` 수동 호출 가능 |
| AI가 만든 코드 검증 실패 | `paper_candidates.status='rejected'` + `rejection_reason` 기록 → 다른 후보로 자동 재시도 (최대 5회 시도, 그래도 부족하면 가능한 만큼만 사용자에게 push) |
| 페이퍼 사이클 중 한 전략 분석 예외 | try/except → 그 전략만 skip + `paper_signals.signal='ERROR'` 기록 → 다른 전략 계속. 텔레그램 알림 (전략별 1일 1회 dedupe) |
| ccxt API 실패 | 1회 재시도 (5초 간격) → 실패 시 그 사이클 skip (현재가 없으면 평가 불가) |
| Tailscale 끊김 | 핸드폰 측 네트워크 문제, 시스템 영향 0 |
| 웹앱 5초 폴링 실패 | HTMX 자동 재시도, 텍스트 "갱신 실패" 표시 |
| SQLite 동시 쓰기 충돌 | WAL 모드 + 짧은 retry (이미 kkabi.db는 WAL 모드) |

## Testing 전략

### 단위 테스트 (`tests/paper/`)

- `test_engine.py`: 가짜 OHLCV/시그널 → 예상 trades/positions
  - BUY 시그널 + 현금만 → 매수 발생, btc 증가, cash 감소 (수수료 포함)
  - SELL 시그널 + 보유 → 매도, realized_pnl 정확
  - 수수료 0.05% × 2 검증
  - HOLD → 아무 변화 없음
- `test_security.py`: AI 코드 검증
  - 허용 코드 통과
  - 시스템/IO 모듈 import → reject
  - 동적 코드 실행 호출 → reject
  - 클래스 없음 → reject
  - `analyze` 메서드 없음 → reject
- `test_models.py`: SQLAlchemy 모델 round-trip

### E2E 수동 테스트
첫 1-2주는 자동화하지 않음 — 본인이 매일 텔레그램으로 후보 받고, 선택하고, 웹앱에서 결과 보면서 검증. 문제 발견 시 이슈로 추가.

### 격리 검증
기존 `run_auto_trade.py` 실거래 자동매매에 영향 0인지 매뉴얼 확인:
- `paper/`, `webapp/` 모듈은 `strategy/` 또는 `run_auto_trade.py`를 import하지 않음
- DB 테이블 prefix `paper_`로 격리

## 빌드 마일스톤 (1.5-2주)

1. **DB + 모델** (반나절) — `paper/models.py`, kkabi.db에 테이블 추가, alembic 없이 `create_all()`
2. **페이퍼 엔진** (1.5일) — `paper/engine.py` + 단위 테스트, 가짜 시그널로 검증
3. **AI 후보 생성** (2일) — `paper/candidates.py` + `paper/strategy_loader.py` + `paper/security.py` + AST 테스트
4. **Telegram 명령어** (반나절) — `/candidates`, `/select`, `/skip`, `/generate` 추가
5. **Cron 등록** (반나절) — macOS launchd plist 또는 cron, 8AM 후보 + 매시 정각 사이클
6. **Flask + HTMX 웹앱** (3일) — base.html (다크 + 모바일), 목록 화면, 상세 화면, 5초 폴링
7. **PWA 설정** (반나절) — manifest.json, 아이콘, iOS meta tags
8. **Tailscale 연동** (반나절) — 맥미니/핸드폰 Tailscale 설치, Flask 0.0.0.0 바인딩, 핸드폰 PWA 설치 검증
9. **E2E 검증 + 다듬기** (1-2일) — 첫 후보 받아 선택까지 흐름 검증, 디자인 미세 조정

총 ~12-14일.

## 비용 추정

| 항목 | 월 |
|---|---|
| Anthropic API (Claude Sonnet, 일 1회) | ~$3-9 |
| Tailscale | $0 (개인 무료) |
| 인프라 | $0 (맥미니 자가 호스팅) |
| **총** | **~$3-9 / 월** |

## Phase 2 후보 (이번 스펙 범위 밖)

- 업비트 본격 모방 — 호가창 자리 "전략 점수보드", 캔들 차트 + 시그널 마커
- 차트 라이브러리 도입 — TradingView lightweight-charts
- 일일/주간/월간 PnL 추이 그래프
- 전략 비교 화면 (여러 전략 PnL 곡선 한 화면)
- 전략 자동 정리 — 30일 누적 -50% 미만 자동 stopped 처리
- 통합 portfolio 모드 — 여러 전략의 신호를 단일 자본 ₩10,000,000으로 합쳐 운용
- 전략 백테스트 — 선택 전 historical OHLCV로 1년 backtest 결과 미리보기
- 100개 기존 전략 라이브러리 import — 본인이 선택해서 페이퍼에 추가
- 푸시 알림 (PWA Web Push) — 텔레그램 외 채널
- 전략 archive 정책 — paper_signals 1년치 후 압축
- 더 강한 코드 격리 (RestrictedPython, 별도 subprocess sandbox)

## 비결정 / 가정

- **AI 모델 선택**: Claude Sonnet 4.6 default. Opus는 비용 6배라 phase 1엔 과함. 변경 시 `Config.PAPER_AI_MODEL` 환경변수.
- **timezone**: 모든 timestamp는 UTC 저장, 표시 시 KST 변환 (서버=맥미니=한국이라 큰 이슈 없음).
- **데이터 retention**: paper_signals/paper_trades는 1년간 무삭제 가정. 그 후 archive 정책은 phase 2.

## Open Questions

- (없음) — 모든 결정 사항이 사용자와 합의됨.
