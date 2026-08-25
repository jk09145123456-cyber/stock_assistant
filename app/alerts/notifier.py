"""17장 알림 - 상태가 바뀔 때만 알림을 생성. 이전 상태는 data/state.json에 저장."""
from __future__ import annotations

import json
from pathlib import Path

from app.decision.engine import Decision, DecisionResult

STATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "decision_state.json"


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_and_record_transition(symbol: str, name: str, result: DecisionResult, risk_score: int) -> str | None:
    """이전 판단과 다르면 알림 문자열을 반환하고 상태를 갱신. 동일하면 None."""
    state = _load_state()
    prev = state.get(symbol)
    prev_decision = prev.get("decision") if prev else None
    prev_risk_score = prev.get("risk_score") if prev else None

    message = None
    if prev_decision is not None and prev_decision != result.decision.value:
        message = _format_alert(name, prev_decision, result, prev_risk_score, risk_score)

    state[symbol] = {"decision": result.decision.value, "risk_score": risk_score}
    _save_state(state)
    return message


def _format_alert(name: str, prev_decision: str, result: DecisionResult, prev_risk_score, risk_score: int) -> str:
    lines = [f"[{name} 위험 상태 변경]", "", f"이전: {prev_decision}", f"현재: {result.decision.value}"]
    if prev_risk_score is not None:
        lines.append(f"위험 점수: {prev_risk_score} -> {risk_score}  (= 100 - 정규화 점수)")
    else:
        lines.append(f"위험 점수: {risk_score}  (= 100 - 정규화 점수)")

    if result.reasons:
        lines += ["", "변경 원인:"] + [f"- {r}" for r in result.reasons]
    if result.release_conditions:
        lines += ["", "확인 사항:"] + [f"- {r}" for r in result.release_conditions]
    return "\n".join(lines)
