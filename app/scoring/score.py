"""11장 판단 점수 - 카테고리별 원점수 -> 0~100 정규화, 위험 점수(100-정규화)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.regime.classify import Regime, RegimeResult


@dataclass
class ScoreBreakdown:
    trend_raw: int
    momentum_raw: int
    supply_demand_raw: int
    market_raw: int
    risk_raw: int
    raw_total: int
    normalized: int
    risk_score: int
    band_label: str
    contributions: list[str] = field(default_factory=list)


def _sorted_periods(ema_periods: list[int]) -> tuple[int, int, int]:
    s = sorted(ema_periods)[:3] if len(ema_periods) >= 3 else (ema_periods[0],) * 3
    return s[0], s[1], s[2]


def compute_score(
    bundle: dict,
    ema_periods: list[int],
    market_regime_result: RegimeResult,
    strategy_cfg: dict,
    position_weight: float,
    max_position_weight: float,
    earnings_risk: bool = False,
    institutional_flow_positive: bool | None = None,
    sector_index_up: bool | None = None,
) -> ScoreBreakdown:
    w = strategy_cfg["scoring"]
    short, mid, long = _sorted_periods(ema_periods)
    contributions: list[str] = []

    close = bundle["close"].iloc[-1]
    e_short, e_mid, e_long = bundle["ema"][short].iloc[-1], bundle["ema"][mid].iloc[-1], bundle["ema"][long].iloc[-1]
    slope_short = bundle["ema_slope"][short].iloc[-1]
    slope_mid = bundle["ema_slope"][mid].iloc[-1]

    # 추세
    trend = 0
    if close > e_short:
        trend += w["trend"]["price_above_ema20"]; contributions.append(f"현재가>EMA{short}")
    if e_short > e_mid:
        trend += w["trend"]["ema20_above_ema60"]; contributions.append(f"EMA{short}>EMA{mid}")
    if e_mid > e_long:
        trend += w["trend"]["ema60_above_ema120"]; contributions.append(f"EMA{mid}>EMA{long}")
    if slope_short > 0:
        trend += w["trend"]["ema20_slope_up"]; contributions.append(f"EMA{short} 기울기 상승")
    if slope_mid > 0:
        trend += w["trend"]["ema60_slope_up"]; contributions.append(f"EMA{mid} 기울기 상승")
    if bundle["higher_highs_lows_20d"]:
        trend += w["trend"]["higher_highs_lows"]; contributions.append("고점·저점 상승")

    # 모멘텀
    momentum = 0
    if bundle["return_20d"].iloc[-1] > 0:
        momentum += w["momentum"]["return_20d_positive"]; contributions.append("20일 수익률 양수")
    if bundle["return_60d"].iloc[-1] > 0:
        momentum += w["momentum"]["return_60d_positive"]; contributions.append("60일 수익률 양수")
    rsi_cfg = strategy_cfg["rsi"]
    if rsi_cfg["healthy_low"] <= bundle["rsi"].iloc[-1] <= rsi_cfg["healthy_high"]:
        momentum += w["momentum"]["rsi_healthy"]; contributions.append("RSI 정상 구간")
    if bundle["macd_hist"].iloc[-1] > bundle["macd_hist"].iloc[-2]:
        momentum += w["momentum"]["macd_hist_rising"]; contributions.append("MACD 히스토그램 상승")

    # 수급
    supply = 0
    price_up_today = bundle["close"].iloc[-1] > bundle["close"].iloc[-2]
    vol_ratio = bundle["volume_ratio_20d"]
    if price_up_today and vol_ratio > 1.0:
        supply += w["supply_demand"]["volume_up_on_rally"]; contributions.append("상승 시 거래량 증가")
    if not price_up_today and vol_ratio < 1.0:
        supply += w["supply_demand"]["volume_down_on_decline"]; contributions.append("하락 시 거래량 감소")
    if vol_ratio > 1.3:
        supply += w["supply_demand"]["relative_volume_up"]; contributions.append("시장 대비 거래량 증가")
    if institutional_flow_positive:
        supply += w["supply_demand"]["institutional_flow_positive"]; contributions.append("외국인·기관 수급 양호")

    # 시장
    market = 0
    d = market_regime_result.details
    if d.get("price", 0) > d.get("ema60", 0):
        market += w["market"]["index_above_ema60"]; contributions.append("시장지수>EMA60")
    if d.get("slope60", 0) > 0:
        market += w["market"]["index_ema60_slope_up"]; contributions.append("시장 EMA60 기울기 상승")
    if sector_index_up:
        market += w["market"]["sector_index_up"]; contributions.append("업종지수 상승")
    if market_regime_result.regime != Regime.CRASH:
        market += w["market"]["market_volatility_stable"]; contributions.append("시장 변동성 안정")

    # 위험
    risk = 0
    aligned_down = close < e_short < e_mid < e_long
    if aligned_down:
        risk += w["risk_penalty"]["ema_reverse_alignment"]; contributions.append("[위험] EMA 역배열")
    if bundle["recent_low_break_20d"]:
        risk += w["risk_penalty"]["recent_low_break"]; contributions.append("[위험] 최근 저점 이탈")
    atr_series = bundle["atr"]
    if len(atr_series) > 60 and atr_series.iloc[-1] > atr_series.rolling(60).mean().iloc[-1] * 1.5:
        risk += w["risk_penalty"]["atr_spike"]; contributions.append("[위험] ATR 급증")
    bearish_bar = bundle["close"].iloc[-1] < bundle["close"].iloc[-2] and vol_ratio > 1.5
    if bearish_bar:
        risk += w["risk_penalty"]["bearish_candle_with_volume"]; contributions.append("[위험] 거래량 동반 음봉")
    if earnings_risk:
        risk += w["risk_penalty"]["earnings_disclosure_risk"]; contributions.append("[위험] 실적·공시 위험")
    if position_weight > max_position_weight:
        risk += w["risk_penalty"]["position_weight_exceeded"]; contributions.append("[위험] 종목 최대 비중 초과")

    raw_total = trend + momentum + supply + market + risk
    norm_cfg = strategy_cfg["normalization"]
    normalized = max(0, min(100, round((raw_total / norm_cfg["max_positive_raw"]) * 100)))

    band_label = "강한 위험 경고"
    for band in strategy_cfg["score_bands"]:
        if normalized >= band["min"]:
            band_label = band["label"]
            break

    return ScoreBreakdown(
        trend_raw=trend, momentum_raw=momentum, supply_demand_raw=supply,
        market_raw=market, risk_raw=risk, raw_total=raw_total,
        normalized=normalized, risk_score=100 - normalized,
        band_label=band_label, contributions=contributions,
    )
