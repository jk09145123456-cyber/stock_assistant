"""13장 전략 공통 타입."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Vote(IntEnum):
    SELL = -1
    NEUTRAL = 0
    BUY = 1


@dataclass
class StrategyResult:
    name: str
    vote: Vote
    reasons: list[str]
