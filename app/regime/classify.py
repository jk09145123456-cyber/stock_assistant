"""6장 시장 국면 분류 - 상승/횡보/하락/급락."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from app.indicators import core as ind


class Regime(str, Enum):
    UP = "상승"
    SIDEWAYS = "횡보"
    DOWN = "하락"
    CRASH = "급락"


@dataclass
class RegimeResult:
    regime: Regime
    reasons: list[str] = field(default_factory=list)
    crash_conditions_met: int = 0
    details: dict = field(default_factory=dict)


def classify_regime(index_df: pd.DataFrame, risk_cfg: dict, strategy_cfg: dict) -> RegimeResult:
    close = index_df["close"]
    ema20 = ind.ema(close, 20)
    ema60 = ind.ema(close, 60)
    ema120 = ind.ema(close, 120) if len(close) >= 120 else ema60

    slope_lb = strategy_cfg["slope"]["lookback_days"]
    up_th = strategy_cfg["slope"]["up_threshold"]
    down_th = strategy_cfg["slope"]["down_threshold"]

    slope20 = ind.ema_slope(ema20, slope_lb).iloc[-1]
    slope60 = ind.ema_slope(ema60, slope_lb).iloc[-1]

    price = close.iloc[-1]
    e20, e60, e120 = ema20.iloc[-1], ema60.iloc[-1], ema120.iloc[-1]

    higher_hl = ind.higher_highs_lows(index_df, 20)
    lower_hl = _lower_highs_lows(index_df, 20)

    crash_conditions, crash_reasons = _check_crash_conditions(index_df, risk_cfg)
    crash_met = sum(crash_conditions.values())

    details = {
        "price": price, "ema20": e20, "ema60": e60, "ema120": e120,
        "slope20": slope20, "slope60": slope60,
        "crash_conditions": crash_conditions,
    }

    if crash_met >= risk_cfg["crash_conditions_required"]:
        return RegimeResult(Regime.CRASH, crash_reasons, crash_met, details)

    if price > e20 > e60 > e120 and slope20 > up_th and slope60 > up_th and higher_hl:
        reasons = [
            "시장지수 > EMA20 > EMA60 > EMA120",
            "EMA20·EMA60 기울기 상승",
            "최근 고점·저점이 함께 상승",
        ]
        return RegimeResult(Regime.UP, reasons, crash_met, details)

    if price < e20 < e60 and slope20 < down_th and slope60 < down_th and lower_hl:
        reasons = [
            "시장지수 < EMA20 < EMA60",
            "EMA20·EMA60 기울기 하락",
            "고점·저점이 함께 낮아짐",
        ]
        return RegimeResult(Regime.DOWN, reasons, crash_met, details)

    reasons = ["EMA20과 EMA60이 수평이거나 가격이 이를 반복 교차", "뚜렷한 방향성 없음"]
    return RegimeResult(Regime.SIDEWAYS, reasons, crash_met, details)


def _lower_highs_lows(df: pd.DataFrame, window: int = 20) -> bool:
    highs = df["high"].rolling(window).max()
    lows = df["low"].rolling(window).min()
    if len(highs.dropna()) < window + 1:
        return False
    return bool(highs.iloc[-1] < highs.iloc[-window - 1] and lows.iloc[-1] < lows.iloc[-window - 1])


def _check_crash_conditions(df: pd.DataFrame, risk_cfg: dict) -> tuple[dict[str, bool], list[str]]:
    """6장 급락 6개 조건 중 시세 데이터만으로 계산 가능한 5개를 판정.
    ("대부분의 종목이 동반 하락"은 유니버스 폭 데이터가 필요해 이 함수 밖,
    즉 보유·관심 종목 스캔 결과로 보강한다 - decision 엔진에서 결합.)
    """
    close = df["close"]
    daily_return = close.pct_change()
    vol = daily_return.rolling(60).std().iloc[-1]
    today_return = daily_return.iloc[-1]

    conditions = {}
    reasons = []

    # 1. 일간 수익률이 평소 변동성의 N배 이상 하락
    z = today_return / vol if vol else 0
    cond1 = bool(z <= -risk_cfg["crash_return_zscore"])
    conditions["return_zscore"] = cond1
    if cond1:
        reasons.append(f"당일 수익률({today_return:.1%})이 평소 변동성의 {abs(z):.1f}배 하락")

    # 2. ATR 급증
    atr14 = ind.atr(df, 14)
    atr_avg = atr14.rolling(60).mean().iloc[-1]
    cond2 = bool(atr_avg and atr14.iloc[-1] >= atr_avg * risk_cfg["crash_atr_spike_ratio"])
    conditions["atr_spike"] = cond2
    if cond2:
        reasons.append("ATR 급증")

    # 3. 지수 장기 EMA(120) 이탈
    ema120 = ind.ema(close, 120) if len(close) >= 120 else ind.ema(close, len(close))
    cond3 = bool(close.iloc[-1] < ema120.iloc[-1])
    conditions["long_ema_break"] = cond3
    if cond3:
        reasons.append("지수 장기 EMA120 이탈")

    # 4. 거래량 급증
    vol_ratio = ind.volume_ratio(df, 20)
    cond4 = bool(vol_ratio >= risk_cfg["crash_volume_spike_ratio"])
    conditions["volume_spike"] = cond4
    if cond4:
        reasons.append(f"거래량 급증 (평소 대비 {vol_ratio:.1f}배)")

    # 5. 갭 하락 후 저가권 마감
    open_, high, low, close_today = df["open"].iloc[-1], df["high"].iloc[-1], df["low"].iloc[-1], close.iloc[-1]
    prev_close = close.iloc[-2]
    gap_down = open_ < prev_close * 0.98
    day_range = high - low
    closed_near_low = (close_today - low) < (day_range * 0.25) if day_range else False
    cond5 = bool(gap_down and closed_near_low)
    conditions["gap_down_weak_close"] = cond5
    if cond5:
        reasons.append("갭 하락 후 저가권 마감")

    return conditions, reasons
