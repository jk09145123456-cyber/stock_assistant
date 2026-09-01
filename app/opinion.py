"""뉴스와 시장 지표를 바탕으로 생성된 AI 참고 의견 파일 로더."""
from __future__ import annotations

from pathlib import Path

import yaml

OPINION_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_opinion.yaml"


def load_opinion() -> dict | None:
    if not OPINION_PATH.exists():
        return None
    with open(OPINION_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_symbol_opinion(opinion: dict | None, symbol: str) -> dict | None:
    if not opinion:
        return None
    return (opinion.get("positions") or {}).get(symbol) or (opinion.get("candidates") or {}).get(symbol)
