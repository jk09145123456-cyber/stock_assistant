"""13장 전략 D: 평균회귀 - 장기 상승 추세 + 단기 과매도 + EMA/볼린저 중심 복귀 가능성.

하락 추세에서 쓰면 위험하므로 장기 상승 조건을 먼저 통과해야 한다.
"""
from __future__ import annotations

from .base import StrategyResult, Vote


def evaluate(bundle: dict, ema_periods: list[int], strategy_cfg: dict) -> StrategyResult:
    _, mid, long = sorted(ema_periods)[:3] if len(ema_periods) >= 3 else (ema_periods[0],) * 3
    slope_long = bundle["ema_slope"][long].iloc[-1]
    e_long = bundle["ema"][long].iloc[-1]
    e_mid = bundle["ema"][mid].iloc[-1]

    long_uptrend = e_mid > e_long and slope_long > 0
    if not long_uptrend:
        return StrategyResult("평균회귀", Vote.NEUTRAL, ["장기 상승 추세가 아니어서 평균회귀 전략 미적용"])

    disparity_short = bundle["disparity"][sorted(ema_periods)[0]].iloc[-1]
    rsi_val = bundle["rsi"].iloc[-1]
    below_bb_lower = bundle["close"].iloc[-1] < bundle["bb_lower"].iloc[-1]

    oversold = (
        disparity_short <= strategy_cfg["disparity"]["weak_threshold"] * 100
        or rsi_val < 35
        or below_bb_lower
    )

    if oversold:
        return StrategyResult(
            "평균회귀", Vote.BUY,
            ["장기 상승 추세 유지", "단기 과매도 (이격도/RSI/볼린저 하단)", "중심선 복귀 가능성"],
        )
    return StrategyResult("평균회귀", Vote.NEUTRAL, ["장기 상승이나 단기 과매도 상태 아님"])
