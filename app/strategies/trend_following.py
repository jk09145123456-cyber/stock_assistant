"""13장 전략 A: 추세 추종 - EMA 정배열, EMA 기울기 상승, 고점과 저점 상승."""
from __future__ import annotations

from .base import StrategyResult, Vote


def evaluate(bundle: dict, ema_periods: list[int]) -> StrategyResult:
    short, mid, long = sorted(ema_periods)[:3] if len(ema_periods) >= 3 else (ema_periods[0],) * 3
    close = bundle["close"].iloc[-1]
    e_short = bundle["ema"][short].iloc[-1]
    e_mid = bundle["ema"][mid].iloc[-1]
    e_long = bundle["ema"][long].iloc[-1]
    slope_short = bundle["ema_slope"][short].iloc[-1]
    slope_mid = bundle["ema_slope"][mid].iloc[-1]
    higher_hl = bundle["higher_highs_lows_20d"]

    aligned_up = close > e_short > e_mid > e_long
    aligned_down = close < e_short < e_mid < e_long
    slopes_up = slope_short > 0 and slope_mid > 0
    slopes_down = slope_short < 0 and slope_mid < 0

    if aligned_up and slopes_up and higher_hl:
        return StrategyResult(
            "추세추종", Vote.BUY,
            [f"정배열: 현재가>EMA{short}>EMA{mid}>EMA{long}", "EMA 기울기 상승", "고점·저점 상승"],
        )
    if aligned_down and slopes_down:
        return StrategyResult(
            "추세추종", Vote.SELL,
            [f"역배열: 현재가<EMA{short}<EMA{mid}<EMA{long}", "EMA 기울기 하락"],
        )
    return StrategyResult("추세추종", Vote.NEUTRAL, ["정배열/역배열 조건 미충족"])
