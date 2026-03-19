# Project Overview

## Goal
- 암호화폐 트레이딩 봇 & 분석 도구
- 자동매매, 백테스트, 포트폴리오 추적

## Scope
- 포함: 거래소 연동, 자동매매 전략, 백테스트, P&L 분석
- 제외: 프론트엔드 UI (텔레그램 봇으로 조작)

## Stack
- Language: Python 3.11+
- Exchange API: ccxt (멀티 거래소)
- Data: pandas, numpy
- Visualization: plotly

## Architecture
- `main.py` — 엔트리포인트
- `config.py` — 설정 로더
- `exchange/` — 거래소 API 래퍼
- `strategy/` — 트레이딩 전략
- `backtest/` — 백테스트 엔진
- `telegram_bot/` — 텔레그램 조작 인터페이스
- `utils/` — 유틸리티

## Constraints
- 실거래 시 API 키 보안 최우선
- 거래소 rate limit 준수
- 손실 방지용 안전장치 필수 (stop-loss, max position size)

## Working Rules
- 실행: `python main.py`
- 백테스트: `python run_backtest.py`
- 환경변수: `.env`에 API 키 관리
- 전략 추가 시 `strategy/base.py` 상속

## Known Issues
- (현재 없음)

## Priorities
- 기본 전략 구현 및 백테스트 검증
- 텔레그램 봇 연동으로 원격 제어
