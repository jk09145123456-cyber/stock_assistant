"""13장 전략 B: 눌림목 - 장기 상승 추세 + EMA20/60 조정 + 저점 갱신 중단 + 거래량 감소 + 반등."""
from __future__ import annotations

import pandas as pd

from .base import StrategyResult, Vote


def evaluate(df: pd.DataFrame, bundle: dict, ema_periods: list[int]) -> StrategyResult:
    short, mid, long = sorted(ema_periods)[:3] if len(ema_periods) >= 3 else (ema_periods[0],) * 3
    close = bundle["close"].iloc[-1]
    e_mid = bundle["ema"][mid].iloc[-1]
    e_long = bundle["ema"][long].iloc[-1]
    slope_long = bundle["ema_slope"][long].iloc[-1]

    long_uptrend = e_mid > e_long and slope_long > 0
    near_support = close <= bundle["ema"][short].iloc[-1] * 1.02 or close <= e_mid * 1.02
    low_stopped_falling = not bundle["recent_low_break_20d"]
    volume_declining = bundle["volume_ratio_20d"] < 1.0

    last_bar_bullish = df["close"].iloc[-1] > df["open"].iloc[-1]
    rebound_candle = last_bar_bullish and df["close"].iloc[-1] > df["close"].iloc[-2]

    if long_uptrend and near_support and low_stopped_falling and volume_declining and rebound_candle:
        return StrategyResult(
            "눌림목", Vote.BUY,
            ["장기 상승 추세 유지", "EMA 부근까지 조정", "저점 갱신 중단", "거래량 감소", "반등 캔들 확인"],
        )
    if not long_uptrend:
        return StrategyResult("눌림목", Vote.NEUTRAL, ["장기 상승 추세가 아니라 눌림목 조건 성립 불가"])
    return StrategyResult("눌림목", Vote.NEUTRAL, ["조정 또는 반등 조건 일부 미충족"])
