"""13장 앙상블 집계 - 전략 4개 투표 합산, 신뢰도 산출, 시장 국면에 따른 보수화."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.regime.classify import Regime

from . import breakout, mean_reversion, pullback, trend_following
from .base import StrategyResult, Vote


@dataclass
class EnsembleResult:
    strategies: list[StrategyResult]
    raw_sum: int
    direction: Vote
    confidence: int
    conflicted: bool
    dampened: bool = False
    notes: list[str] = field(default_factory=list)


def run_ensemble(
    df, bundle: dict, ema_periods: list[int], market_regime: Regime, strategy_cfg: dict
) -> EnsembleResult:
    results = [
        trend_following.evaluate(bundle, ema_periods),
        pullback.evaluate(df, bundle, ema_periods),
        breakout.evaluate(bundle, market_regime),
        mean_reversion.evaluate(bundle, ema_periods, strategy_cfg),
    ]

    votes = [r.vote for r in results]
    raw_sum = int(sum(votes))
    agree_threshold = strategy_cfg["ensemble"]["agree_threshold"]

    buy_votes = sum(1 for v in votes if v == Vote.BUY)
    sell_votes = sum(1 for v in votes if v == Vote.SELL)

    conflicted = False
    if buy_votes >= agree_threshold:
        direction = Vote.BUY
        confidence = strategy_cfg["ensemble"]["high_confidence"]
    elif sell_votes >= agree_threshold:
        direction = Vote.SELL
        confidence = strategy_cfg["ensemble"]["high_confidence"]
    else:
        conflicted = True
        direction = Vote.BUY if raw_sum > 0 else (Vote.SELL if raw_sum < 0 else Vote.NEUTRAL)
        confidence = strategy_cfg["ensemble"]["low_confidence"]

    notes = []
    dampened = False
    if market_regime in (Regime.DOWN, Regime.CRASH) and direction != Vote.SELL:
        dampened = True
        downgrade = {Vote.BUY: Vote.NEUTRAL, Vote.NEUTRAL: Vote.SELL}
        before = direction
        direction = downgrade[direction]
        notes.append(f"시장 국면이 하락/급락이라 판단을 한 단계 보수화 ({before.name} → {direction.name})")

    return EnsembleResult(results, raw_sum, direction, confidence, conflicted, dampened, notes)
