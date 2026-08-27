"""신규 매수 후보 스크리닝 - 기존 관심종목 분석 파이프라인을 유니버스 전체에 재사용.

새로운 판단 로직을 따로 만들지 않는다. 종목 하나하나를 '관심종목'처럼
app.pipeline.analyze_item에 태워서 같은 점수/전략/위험 규칙으로 평가하고,
결과를 점수순으로 정렬해서 보여줄 뿐이다. 시스템이 "이거 사라"고 확정하지
않는다 - 순위만 매기고 최종 선택은 사람이 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.decision.engine import Decision
from app.pipeline import analyze_item
from app.portfolio.models import Portfolio


@dataclass
class ScreeningResult:
    symbol: str
    name: str
    sector: str | None
    score: int
    confidence: int
    decision: Decision
    current_price: float | None
    reasons: list[str]


def scan_universe(
    universe: list[dict],
    portfolio: Portfolio,
    settings,
    progress_callback=None,
) -> list[ScreeningResult]:
    results = []
    for i, item in enumerate(universe):
        if progress_callback:
            progress_callback(i + 1, len(universe), item["name"])
        try:
            outcome = analyze_item(
                symbol=item["symbol"], name=item["name"], market="KR", purpose="스윙",
                portfolio=portfolio, position=None, settings=settings,
            )
        except Exception as e:  # noqa: BLE001 - 종목 하나 실패해도 스캔 전체는 계속
            results.append(ScreeningResult(
                item["symbol"], item["name"], item.get("sector"), 0, 0,
                Decision.HALTED, None, [f"조회 실패: {e}"],
            ))
            continue

        results.append(ScreeningResult(
            symbol=item["symbol"], name=item["name"], sector=item.get("sector"),
            score=outcome.decision.score, confidence=outcome.decision.confidence,
            decision=outcome.decision.decision, current_price=outcome.current_price,
            reasons=outcome.decision.reasons,
        ))

    def sort_key(r: ScreeningResult):
        buy_priority = 1 if r.decision == Decision.ADD_BUY_REVIEW else 0
        return (buy_priority, r.score, r.confidence)

    return sorted(results, key=sort_key, reverse=True)
