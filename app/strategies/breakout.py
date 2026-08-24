"""13장 전략 C: 돌파 - 20일/60일 고점 돌파 + 거래량 증가 + 시장·업종 상승."""
from __future__ import annotations

from app.regime.classify import Regime

from .base import StrategyResult, Vote


def evaluate(bundle: dict, market_regime: Regime) -> StrategyResult:
    breakout_20 = bundle["recent_high_break_20d"]
    breakout_60 = bundle["recent_high_break_60d"]
    volume_up = bundle["volume_ratio_20d"] > 1.3
    market_up = market_regime == Regime.UP

    if (breakout_20 or breakout_60) and volume_up and market_up:
        window = "60일" if breakout_60 else "20일"
        return StrategyResult(
            "돌파", Vote.BUY,
            [f"{window} 고점 돌파", "거래량 증가", "시장 국면 상승"],
        )
    if (breakout_20 or breakout_60) and not market_up:
        return StrategyResult("돌파", Vote.NEUTRAL, ["가격은 돌파했으나 시장이 상승 국면이 아님"])
    return StrategyResult("돌파", Vote.NEUTRAL, ["고점 돌파 조건 미충족"])
