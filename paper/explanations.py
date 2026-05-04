"""
초심자용 전략 설명 자동 생성.

기존 strategies/ 클래스의 quant 스타일 docstring을 읽어, Claude CLI로
초심자가 이해할 수 있는 한국어 마크다운으로 변환한다.

생성된 설명은 paper_strategies.beginner_explanation 에 저장 (한 번 생성 후 영구).
페이지 로드 시 즉시 표시 — Claude 호출은 generate 명령 실행 시에만.

사용법:
    python3 -m paper.explanations generate <strategy_id>      # 1개
    python3 -m paper.explanations generate-all               # 미생성 전부
    python3 -m paper.explanations regenerate <strategy_id>   # 강제 재생성
    python3 -m paper.explanations show <strategy_id>         # 저장된 설명 보기
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap

from paper.models import PaperStrategy, SessionLocal


PROMPT_TEMPLATE = """\
당신은 트레이딩 초보자에게 전략을 설명하는 한국어 교육자입니다.
아래 전문가용 docstring을 받아 **암호화폐 트레이딩을 처음 배우는 사람**도
이해할 수 있는 한국어 설명을 만들어주세요.

## 입력
전략 이름: {strategy_name}
카테고리: {category}
BUY 임계값: {buy_threshold} (점수 이 이상이면 매수)
SELL 임계값: {sell_threshold} (점수 이 이하이면 매도)

전문가용 docstring:
---
{docstring}
---

## 출력 (마크다운, 각 섹션 짧고 명확하게)

### 한 줄 요약
이 전략이 뭘 하는지 한 문장으로 (수식·전문 용어 없이)

### 무엇을 보고 결정하나
어떤 시장 신호/지표를 보는지, 비전공자에게 직관적으로 (예: "가격이 평균에서 얼마나 멀어졌는지", "최근 거래량이 평소보다 많은지")

### 언제 사는가 🟢
점수가 BUY 임계값을 넘는 시장 상황을 일상 언어로 (예: "최근 3일간 가격이 빠르게 떨어진 후 반등 신호가 보일 때")

### 언제 파는가 🔴
SELL 임계값 도달 시점을 일상 언어로

### 왜 이게 통할 거라고 생각하나
시장 가설을 1-2문장으로. 왜 과거에 이런 패턴이 수익을 줬는지

### 위험한 시장 ⚠️
이 전략이 실패하기 쉬운 시장 상황 (예: "방향성 없이 좁은 폭으로 횡보할 때 가짜 신호가 잦음")

### 핵심 용어
이 전략에 쓰이는 전문 용어 2-3개를 각 한 줄로 풀이 (예: "RSI: 최근 며칠간 오른 폭과 내린 폭의 비율로 과열/침체를 측정")

## 작성 원칙
- 수식 X. 전공자만 아는 표기법 X (예: σ, Σ).
- 비유 사용 환영. 일상 예시 환영.
- 각 섹션 1-3문장으로 짧게.
- 마크다운 헤더(###)는 그대로 유지.
"""


def _build_prompt(strategy: PaperStrategy) -> str:
    """전략의 메타데이터로 프롬프트 작성."""
    if not strategy.source.startswith("registry:"):
        raise ValueError(f"registry: 전략만 지원: {strategy.source}")
    key = strategy.source.split(":", 1)[1]

    from strategies import STRATEGIES

    cls = STRATEGIES.get(key)
    if cls is None:
        raise ValueError(f"strategies/ 레지스트리에 없음: {key}")

    docstring = (cls.__doc__ or "").strip()
    if not docstring:
        raise ValueError(f"클래스 docstring 없음: {cls.__name__}")

    return PROMPT_TEMPLATE.format(
        strategy_name=getattr(cls, "STRATEGY_NAME", cls.__name__),
        category=getattr(cls, "CATEGORY", "?"),
        buy_threshold=getattr(cls, "BUY_THRESHOLD", "?"),
        sell_threshold=getattr(cls, "SELL_THRESHOLD", "?"),
        docstring=docstring,
    )


def _call_claude_cli(prompt: str, timeout: int = 120) -> str:
    """Claude CLI 호출 → 본문 텍스트 반환.

    --print: 비대화 모드, 응답 후 종료
    --disallowedTools: 안전 — 텍스트 생성만 허용 (파일/쉘/네트워크 X)
    --model: 모델 명시 (default 변경 대비)
    --no-session-persistence: 세션 저장 X (--print 모드 전용)
    """
    cmd = [
        "claude",
        "--print",
        "--no-session-persistence",
        "--model", "sonnet",
        "--disallowedTools", "Bash", "Edit", "Write", "Read", "WebFetch", "WebSearch",
        "--permission-mode", "default",
        prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude CLI 타임아웃 ({timeout}초)")
    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI 실패 (exit {result.returncode}): "
            f"stderr={result.stderr[:500]}"
        )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Claude CLI 빈 응답")
    return output


def generate_for_strategy(strategy_id: int, force: bool = False) -> str:
    """전략 1개에 대해 초심자 설명 생성 + DB 저장."""
    with SessionLocal() as session:
        strategy = session.get(PaperStrategy, strategy_id)
        if strategy is None:
            raise ValueError(f"전략 #{strategy_id} 없음")

        if strategy.beginner_explanation and not force:
            print(f"  [skip] #{strategy.id} {strategy.name}: 이미 생성됨 (--regenerate로 재생성)")
            return strategy.beginner_explanation

        prompt = _build_prompt(strategy)
        print(f"  [생성중] #{strategy.id} {strategy.name}... (Claude 호출)")
        explanation = _call_claude_cli(prompt)

        strategy.beginner_explanation = explanation
        session.commit()
        print(f"  ✅ 저장: #{strategy.id} ({len(explanation)}자)")
        return explanation


def cmd_generate(args):
    generate_for_strategy(args.id, force=False)


def cmd_regenerate(args):
    generate_for_strategy(args.id, force=True)


def cmd_generate_all(args):
    """beginner_explanation 비어있는 모든 활성 전략에 대해 생성."""
    with SessionLocal() as session:
        targets = (
            session.query(PaperStrategy)
            .filter(PaperStrategy.status == "active")
            .filter(
                (PaperStrategy.beginner_explanation.is_(None))
                | (PaperStrategy.beginner_explanation == "")
            )
            .order_by(PaperStrategy.id)
            .all()
        )
        ids = [s.id for s in targets]

    if not ids:
        print("(생성할 전략 없음)")
        return

    print(f"대상 {len(ids)}개: {ids}")
    for strategy_id in ids:
        try:
            generate_for_strategy(strategy_id, force=False)
        except Exception as e:
            print(f"  ❌ 실패: #{strategy_id} {e}")


def cmd_show(args):
    with SessionLocal() as session:
        strategy = session.get(PaperStrategy, args.id)
        if strategy is None:
            print(f"전략 #{args.id} 없음")
            return
        if not strategy.beginner_explanation:
            print(f"#{strategy.id} {strategy.name}: (설명 미생성)")
            return
        print(f"=== #{strategy.id} {strategy.name} ===\n")
        print(strategy.beginner_explanation)


def main():
    parser = argparse.ArgumentParser(description="초심자용 전략 설명 생성")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate", help="전략 1개 생성 (이미 있으면 skip)")
    p_gen.add_argument("id", type=int)
    p_gen.set_defaults(func=cmd_generate)

    p_regen = sub.add_parser("regenerate", help="전략 1개 강제 재생성")
    p_regen.add_argument("id", type=int)
    p_regen.set_defaults(func=cmd_regenerate)

    p_all = sub.add_parser("generate-all", help="미생성 활성 전략 전부 생성")
    p_all.set_defaults(func=cmd_generate_all)

    p_show = sub.add_parser("show", help="저장된 설명 보기")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
