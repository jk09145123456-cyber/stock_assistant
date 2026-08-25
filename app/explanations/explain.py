"""1장 설명 포맷 - 판단/점수/신뢰도/근거/반대근거/해제조건을 사람이 읽을 문장으로."""
from __future__ import annotations

from app.decision.engine import DecisionResult


def format_decision(symbol: str, name: str, result: DecisionResult) -> str:
    lines = [f"[{name}({symbol})]", f"판단: {result.decision.value}"]
    lines.append(f"종합점수: {result.score}/100")
    lines.append(f"신뢰도: {result.confidence}/100")
    if result.sell_fraction:
        lines.append(f"권장 매도 비중: {result.sell_fraction:.0%}")

    if result.key_levels:
        lines.append("")
        lines.append("참고 가격대 ('직접 설정, 고정' 표시는 확정값 - 나머지는 매일 조금씩 바뀌는 근사치):")
        for label, value in result.key_levels.items():
            lines.append(f"- {label}: {value:,.0f}")

    if result.reasons:
        lines.append("")
        lines.append("근거:")
        lines += [f"- {r}" for r in result.reasons]

    if result.counter_reasons:
        lines.append("")
        lines.append("반대 근거:")
        lines += [f"- {r}" for r in result.counter_reasons]

    if result.release_conditions:
        lines.append("")
        lines.append("해제 조건:")
        lines += [f"- {r}" for r in result.release_conditions]

    return "\n".join(lines)
