"""12장 규칙 엔진 - 우선순위에 따른 최종 판단.

1순위: 데이터 오류        -> 판단 중지
2순위: 전체 시스템 위험 제한 -> 신규·추가매수 금지
3순위: 포트폴리오 비중 제한  -> 비중 축소 검토(일부 매도 검토)
4순위: 시장 급락 여부      -> 추가매수 금지
5순위: 종목 추세
6순위: 매수·매도 세부 조건 (8장 익절 / 9장 손절·논리 무효화 / 7장 추가매수)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.indicators.core import oversold_recovery_stats
from app.portfolio.models import Position
from app.regime.classify import Regime, RegimeResult
from app.risk.engine import PortfolioRiskCheck
from app.scoring.score import ScoreBreakdown
from app.strategies.ensemble import EnsembleResult
from app.strategies.base import Vote


class Decision(str, Enum):
    HALTED = "판단 중지"
    WATCH = "관심"
    HOLD = "보유"
    PARTIAL_SELL_REVIEW = "일부 매도 검토"
    FULL_SELL_REVIEW = "전량 매도 검토"
    ADD_BUY_REVIEW = "추가매수 검토"
    ADD_BUY_FORBIDDEN = "추가매수 금지"


@dataclass
class DecisionResult:
    decision: Decision
    score: int
    confidence: int
    reasons: list[str] = field(default_factory=list)
    counter_reasons: list[str] = field(default_factory=list)
    release_conditions: list[str] = field(default_factory=list)
    sell_fraction: float | None = None
    key_levels: dict[str, float] = field(default_factory=dict)  # "얼마면 회복/확정손절"처럼 구체적 가격


def decide(
    *,
    data_valid: bool,
    data_invalid_reasons: list[str],
    portfolio_risk: PortfolioRiskCheck,
    market_regime: RegimeResult,
    position: Position | None,
    current_price: float,
    highest_price_since_buy: float | None,
    bundle: dict,
    ema_periods: list[int],
    ensemble: EnsembleResult,
    score: ScoreBreakdown,
    risk_cfg: dict,
    purpose: str = "스윙",
) -> DecisionResult:
    if not data_valid:
        return DecisionResult(Decision.HALTED, score.normalized, ensemble.confidence, data_invalid_reasons)

    if market_regime.regime == Regime.CRASH and position is None:
        return DecisionResult(
            Decision.WATCH, score.normalized, ensemble.confidence,
            ["시장이 급락 국면 - 신규 매수 금지"] + market_regime.reasons,
            release_conditions=["급락 국면 해제 (crash 조건 미충족)"],
        )

    # 12장 우선순위 2/3순위(전체 현금 부족, 비중 초과)는 "매수 금지" 성격의 규칙이지,
    # "이미 보유한 종목을 평가하지 말라"는 규칙이 아니다. 그래서 종목 단위 추세/손절/익절
    # 평가(5순위·6순위)는 항상 먼저 계산하고, 그 결과가 더 급하지 않을 때만 이 상위 규칙으로
    # 대체한다 (그렇지 않으면 -50% 손실 종목이 "현금 부족"에 가려 매도 검토가 묻힌다).
    stock_result = _evaluate_stock_level(
        position=position,
        current_price=current_price,
        highest_price_since_buy=highest_price_since_buy,
        bundle=bundle,
        ema_periods=ema_periods,
        ensemble=ensemble,
        score=score,
        market_regime=market_regime,
        risk_cfg=risk_cfg,
        portfolio_risk=portfolio_risk,
        purpose=purpose,
    )

    final = _apply_portfolio_gates(stock_result, portfolio_risk, position, score, ensemble)

    short, mid, _ = _sorted_periods(ema_periods)
    final.counter_reasons = final.counter_reasons + _build_counter_reasons(final.decision, bundle, ensemble, short, mid)
    return final


def _build_counter_reasons(decision: Decision, bundle: dict, ensemble: EnsembleResult, short: int, mid: int) -> list[str]:
    """TradingAgents류 멀티에이전트 논문의 핵심 아이디어(강세/약세를 일부러 반박시킨다)를
    LLM 토론 없이 결정론적으로 흉내낸다: 앙상블에서 반대표를 던진 전략의 근거 +
    RSI/거래량/신저가 여부 같은 반대 신호를 최종 판단과 반대 방향으로 모아 보여준다.
    """
    reasons: list[str] = []
    sell_like = decision in (Decision.FULL_SELL_REVIEW, Decision.PARTIAL_SELL_REVIEW)
    buy_like = decision == Decision.ADD_BUY_REVIEW
    if not sell_like and not buy_like:
        return reasons

    opposite_vote = Vote.BUY if sell_like else Vote.SELL
    for s in ensemble.strategies:
        if s.vote == opposite_vote:
            reasons.append(f"[{s.name} 관점 - 반대] {', '.join(s.reasons)}")

    rsi_val = bundle["rsi"].iloc[-1]
    if sell_like:
        if rsi_val < 35:
            reasons.append(_oversold_rebound_note(bundle, mid, rsi_val))
        if not bundle["recent_low_break_20d"]:
            reasons.append("최근 20일 신저가는 아직 갱신하지 않음 - 추가 하락이 확정된 건 아님")
        if bundle["volume_ratio_20d"] < 1.0:
            reasons.append(f"거래량이 평소 대비 {bundle['volume_ratio_20d']:.1f}배로 낮음 - 투매보다는 관망에 가까움")
    if buy_like:
        if rsi_val > 65:
            reasons.append(f"RSI {rsi_val:.0f} - 과열 구간, 단기 조정 위험")
        disparity_short = bundle["disparity"][short].iloc[-1]
        if disparity_short > 8:
            reasons.append(f"EMA{short} 대비 이격도 +{disparity_short:.1f}% - 추격 매수 위험")

    return reasons


def _oversold_rebound_note(bundle: dict, mid: int, rsi_val: float) -> str:
    """RSI 과매도 상태일 때 "이 정도 빠졌으면 저점"이라는 감(느낌)이 아니라, 이 종목이
    과거에 같은 상태에서 실제로 며칠 만에 EMA{mid}까지 되돌렸는지 직접 세어서 붙인다."""
    stats = oversold_recovery_stats(bundle["close"], bundle["rsi"], bundle["ema"][mid])
    target = float(bundle["ema"][mid].iloc[-1])
    if stats["sample_count"] >= 3:
        return (
            f"RSI {rsi_val:.0f} - 과매도 구간, 과거 유사 상황 {stats['sample_count']}회 중"
            f" 평균 {stats['avg_days']:.0f}일(중앙값 {stats['median_days']:.0f}일) 만에"
            f" EMA{mid}({target:,.0f}) 회복"
        )
    return (
        f"RSI {rsi_val:.0f} - 과매도 구간, 기술적 반등 가능성 있음"
        f" (과거 유사 사례가 {stats['sample_count']}회뿐이라 회복 소요일 추정 근거는 부족)"
    )


_SEVERITY = {
    Decision.HALTED: 100,
    Decision.FULL_SELL_REVIEW: 90,
    Decision.PARTIAL_SELL_REVIEW: 80,
    Decision.ADD_BUY_FORBIDDEN: 70,
    Decision.HOLD: 50,
    Decision.WATCH: 50,
    Decision.ADD_BUY_REVIEW: 40,
}


def _apply_portfolio_gates(
    stock_result: DecisionResult,
    portfolio_risk: PortfolioRiskCheck,
    position: Position | None,
    score: ScoreBreakdown,
    ensemble: EnsembleResult,
) -> DecisionResult:
    candidates = [stock_result]

    if not portfolio_risk.cash_ratio_ok:
        if stock_result.decision == Decision.ADD_BUY_REVIEW:
            candidates.append(DecisionResult(
                Decision.ADD_BUY_FORBIDDEN, score.normalized, ensemble.confidence,
                stock_result.reasons + portfolio_risk.reasons,
                release_conditions=["현금 비율이 최소 기준 이상으로 회복될 것"],
                key_levels=stock_result.key_levels,
            ))
        else:
            stock_result.reasons = stock_result.reasons + ["(참고) 전체 현금 비율 부족 - 신규·추가매수는 어차피 불가"]

    if position is not None and (not portfolio_risk.weight_ok or not portfolio_risk.sector_weight_ok):
        candidates.append(DecisionResult(
            Decision.PARTIAL_SELL_REVIEW, score.normalized, ensemble.confidence,
            stock_result.reasons + portfolio_risk.reasons,
            release_conditions=["비중이 한도 이내로 축소될 것"],
            key_levels=stock_result.key_levels,
        ))

    return max(candidates, key=lambda r: _SEVERITY[r.decision])


def _sorted_periods(ema_periods: list[int]) -> tuple[int, int, int]:
    s = sorted(ema_periods)[:3] if len(ema_periods) >= 3 else (ema_periods[0],) * 3
    return s[0], s[1], s[2]


def _dynamic_long_horizon_threshold(bundle: dict, risk_cfg: dict) -> float:
    """손절 임계낙폭 = max(설정된 최소 기준, 이 종목이 조회 기간 내 실제로 겪은 최악의 낙폭).

    변동성이 원래 큰 종목에 획일적인 기준을 적용하면 평소 변동 범위에서도 손절 신호가
    발생할 수 있다. 그래서 그 종목 자신의 역대 최악 낙폭보다
    더 나빠질 때만 신호가 뜨도록, 설정값과 실측값 중 더 관대한(=낙폭이 더 큰) 쪽을 쓴다.
    """
    config_threshold = risk_cfg.get("long_horizon_severe_drawdown", 0.50)
    historical_worst = abs(bundle.get("max_historical_drawdown", 0.0))
    return max(config_threshold, historical_worst)


def _dynamic_long_horizon_stop(bundle: dict, risk_cfg: dict) -> float:
    """평생보유 종목의 매번 재계산되는 손절 기준가 = 전고점 * (1 - 임계낙폭).
    사람이 숫자를 못박지 않아도 전고점/역대 최악낙폭이 갱신되면 이 값도 같이 움직인다."""
    threshold = _dynamic_long_horizon_threshold(bundle, risk_cfg)
    return float(bundle["ath"]) * (1 - threshold)


def _compute_key_levels(
    bundle: dict, short: int, mid: int, current_price: float, risk_cfg: dict,
    stop_loss_price: float | None = None, target_price: float | None = None, is_long_horizon: bool = False,
) -> dict[str, float]:
    """"얼마 위로 오면/밑으로 가면"에 쓸 구체적 가격.

    stop_loss_price/target_price(4장 "직접 정한 손실 제한"/"직접 정한 목표가")를 사람이
    명시적으로 박아뒀으면 그 고정값을 쓴다. 없으면:
    - 중장기/배당: 전고점 대비 임계낙폭(기본 -50%) 기준으로 매번 재계산되는 동적 손절가
    - 그 외(단기/스윙): 최근 20일 저점(더 짧은 호흡)
    목표가는 매입가 기준 손익비(R-multiple)로 계산해봤지만(2026-08-24), 이미 크게
    물린 장기보유 종목에서는 매입가의 2배 이상으로 튀어서 비현실적이라는 지적을 받고
    되돌렸다(2026-08-25) - 그냥 추세 반전 참고선인 EMA{mid}를 보여준다. 실제 "팔 가치
    있는 수익률" 판단은 take_profit_tiers(8장, 매입가 대비 +10%/+20%)가 담당한다.
    """
    levels = {"현재가": float(current_price)}
    if stop_loss_price:
        stop_label, stop_val = "손절선(직접 설정, 고정)", float(stop_loss_price)
    elif is_long_horizon:
        threshold_pct = _dynamic_long_horizon_threshold(bundle, risk_cfg)
        stop_label = f"손절선(자동계산: 전고점 대비 -{threshold_pct:.0%})"
        stop_val = _dynamic_long_horizon_stop(bundle, risk_cfg)
    else:
        stop_label, stop_val = "손절선(참고, 최근 20일 저점)", float(bundle["low_20d"])
    levels[stop_label] = stop_val

    levels[f"약한경고 해제가(EMA{short})"] = float(bundle["ema"][short].iloc[-1])
    levels["목표가/추세반전" + ("(직접 설정, 고정)" if target_price else f"(참고, EMA{mid})")] = (
        float(target_price) if target_price else float(bundle["ema"][mid].iloc[-1])
    )
    return levels


_LONG_HORIZON_PURPOSES = ("중장기", "배당")


def _evaluate_stock_level(
    *, position, current_price, highest_price_since_buy, bundle, ema_periods,
    ensemble, score, market_regime, risk_cfg, portfolio_risk, purpose="스윙",
) -> DecisionResult:
    short, mid, long = _sorted_periods(ema_periods)
    is_long_horizon = purpose in _LONG_HORIZON_PURPOSES
    close_below_short = bundle["close"].iloc[-1] < bundle["ema"][short].iloc[-1]
    ema_short_below_mid = bundle["ema"][short].iloc[-1] < bundle["ema"][mid].iloc[-1]
    recent_low_break = bundle["recent_low_break_20d"]
    slope_mid_down = bundle["ema_slope"][mid].iloc[-1] < 0

    reasons: list[str] = []
    counter: list[str] = []
    release: list[str] = []

    if position is not None:
        unrealized = position.unrealized_return(current_price)
        key_levels = _compute_key_levels(
            bundle, short, mid, current_price, risk_cfg,
            position.stop_loss_price, position.target_price, is_long_horizon,
        )

        # 4장: 직접 정한 손절선/목표가 - 매일 바뀌는 지표 기반 근사치가 아니라 본인이
        # 못박은 고정 기준선이므로, 다른 어떤 신호보다 우선해서 확정적으로 처리한다.
        if position.stop_loss_price is not None and current_price <= position.stop_loss_price:
            return DecisionResult(
                Decision.FULL_SELL_REVIEW, score.normalized, ensemble.confidence,
                [f"직접 설정한 손절선({position.stop_loss_price:,.0f}) 도달 또는 이탈"],
                counter, release_conditions=[], key_levels=key_levels,
            )
        if position.target_price is not None and current_price >= position.target_price:
            return DecisionResult(
                Decision.PARTIAL_SELL_REVIEW, score.normalized, ensemble.confidence,
                [f"직접 설정한 목표가({position.target_price:,.0f}) 도달"],
                counter, release_conditions=["추세가 계속 살아있다면 나머지는 보유 검토"],
                sell_fraction=0.5, key_levels=key_levels,
            )

        # 4장(자동): 사람이 직접 안 박아뒀어도 중장기/배당 종목은 "전고점 대비 임계낙폭
        # + 장기추세선(EMA_long) 이탈"을 매번 새로 계산해서 같은 역할을 한다 - 이 값은
        # 전고점이 갱신되면 같이 움직이는 완전히 동적인 값이다.
        if position.stop_loss_price is None and is_long_horizon:
            dynamic_stop = _dynamic_long_horizon_stop(bundle, risk_cfg)
            below_long_trend = bundle["close"].iloc[-1] < bundle["ema"][long].iloc[-1]
            if current_price <= dynamic_stop and below_long_trend:
                threshold_pct = _dynamic_long_horizon_threshold(bundle, risk_cfg)
                return DecisionResult(
                    Decision.FULL_SELL_REVIEW, score.normalized, ensemble.confidence,
                    [
                        f"전고점({bundle['ath']:,.0f}) 대비 -{threshold_pct:.0%} 이상 하락"
                        f" + EMA{long} 장기추세선 이탈 (자동계산, 매번 재산정됨)",
                    ],
                    counter, release_conditions=[f"EMA{long} 위로 회복"], key_levels=key_levels,
                )

        # 9장: 강한 손절 경고 - 추세 완전 훼손
        strong_sell_warning = ema_short_below_mid and recent_low_break and market_regime.regime in (
            Regime.DOWN, Regime.CRASH,
        )
        if strong_sell_warning:
            reasons += [
                f"종가가 EMA{short} < EMA{mid}", "거래량을 동반한 직전 저점 이탈 가능성",
                f"시장 국면: {market_regime.regime.value}",
            ]
            release = [
                f"종가가 EMA{short} 위에서 2일 연속 마감",
                f"EMA{short} 기울기가 양수로 전환",
                "거래량을 동반한 직전 저점 돌파",
            ]
            return DecisionResult(Decision.FULL_SELL_REVIEW, score.normalized, ensemble.confidence, reasons, counter, release, key_levels=key_levels)

        # 트레일링 스톱 (8장)
        if highest_price_since_buy:
            trailing_price = highest_price_since_buy - bundle["atr"].iloc[-1] * risk_cfg["trailing_atr_multiple"]
            key_levels["트레일링 기준가"] = trailing_price
            if current_price < trailing_price:
                reasons.append(
                    f"트레일링 기준가({trailing_price:,.0f}) 이탈 (보유 후 최고가 {highest_price_since_buy:,.0f})"
                )
                # 중장기/배당(평생 보유 목적)은 "고점 대비 많이 빠졌다"만으로 전량매도까지
                # 안 올린다 - 트레일링 스톱은 원래 액티브 트레이딩용 리스크 관리 규칙이라
                # 투자기간이 긴 자금에는 안 맞는다. 신저가를 실제로 갱신 중일 때만(=지금도
                # 계속 나빠지고 있다는 뜻) 격상한다.
                escalate = recent_low_break if is_long_horizon else (ema_short_below_mid or recent_low_break)
                if escalate:
                    reasons.append("추세 경고와 동시 발생 -> 전량 매도 검토로 격상")
                    return DecisionResult(Decision.FULL_SELL_REVIEW, score.normalized, ensemble.confidence, reasons, counter, release, key_levels=key_levels)
                if is_long_horizon:
                    counter.append("중장기 보유 목적 - 신저가 갱신 전까지는 전량매도로 격상하지 않음")
                return DecisionResult(
                    Decision.PARTIAL_SELL_REVIEW, score.normalized, ensemble.confidence, reasons, counter,
                    release_conditions=["가격이 트레일링 기준가 위로 회복"], sell_fraction=0.5, key_levels=key_levels,
                )

        # 8장: 목표 수익률 기반 분할 익절
        for tier in sorted(risk_cfg["take_profit_tiers"], key=lambda t: -t["gain"]):
            if unrealized >= tier["gain"]:
                reasons.append(f"수익률 {unrealized:.1%} >= 목표 {tier['gain']:.0%}")
                counter.append("추세가 살아있다면 나머지는 계속 보유 검토")
                return DecisionResult(
                    Decision.PARTIAL_SELL_REVIEW, score.normalized, ensemble.confidence, reasons, counter,
                    release_conditions=["추세 강한 경고 발생 시 전량 매도로 전환"],
                    sell_fraction=tier["sell_fraction"], key_levels=key_levels,
                )

        # 9장: 매수 논리 무효화 근사 (박스권/추세 이탈 + 기울기 하락)
        if slope_mid_down and recent_low_break:
            reasons += [f"EMA{mid} 기울기 하락 전환", "거래량을 동반한 저점 이탈", "최초 매수 논리 훼손 가능성"]
            release = [f"EMA{mid} 기울기 재상승 전환", "직전 저점 재돌파"]
            return DecisionResult(Decision.PARTIAL_SELL_REVIEW, score.normalized, ensemble.confidence, reasons, counter, release, sell_fraction=0.25, key_levels=key_levels)

        # 약한 경고 (참고용, 보유 유지)
        if close_below_short:
            reasons.append(f"약한 경고: 종가가 EMA{short} 아래 마감 (관찰 필요)")

        # 7장: 추가매수 검토
        if ensemble.direction == Vote.BUY and not ensemble.dampened:
            if portfolio_risk.additional_buys_ok and market_regime.regime != Regime.CRASH:
                reasons += [f"{s.name}: {', '.join(s.reasons)}" for s in ensemble.strategies if s.vote == Vote.BUY]
                return DecisionResult(Decision.ADD_BUY_REVIEW, score.normalized, ensemble.confidence, reasons, counter,
                                       release_conditions=["추세 훼손 시 추가매수 중단"], key_levels=key_levels)
            else:
                reasons.append("전략상 매수 신호이나 추가매수 횟수 한도 또는 급락 국면으로 금지")
                return DecisionResult(Decision.ADD_BUY_FORBIDDEN, score.normalized, ensemble.confidence, reasons, counter, key_levels=key_levels)

        if score.normalized < strategy_low_score_threshold():
            reasons.append(f"종합점수 {score.normalized} - 위험 경고 구간")
            return DecisionResult(Decision.ADD_BUY_FORBIDDEN, score.normalized, ensemble.confidence, reasons, counter, key_levels=key_levels)

        reasons.append("뚜렷한 매도/매수 신호 없음 - 기존 보유 유지")
        return DecisionResult(Decision.HOLD, score.normalized, ensemble.confidence, reasons, counter, key_levels=key_levels)

    # 보유하지 않은 관심 종목
    if ensemble.direction == Vote.BUY and not ensemble.dampened and market_regime.regime != Regime.CRASH:
        reasons += [f"{s.name}: {', '.join(s.reasons)}" for s in ensemble.strategies if s.vote == Vote.BUY]
        return DecisionResult(Decision.ADD_BUY_REVIEW, score.normalized, ensemble.confidence, reasons, counter,
                               release_conditions=["매수 후 트레일링/추세 이탈 시 재검토"])
    reasons.append("신규 매수 조건 미충족 - 관찰 지속")
    return DecisionResult(Decision.WATCH, score.normalized, ensemble.confidence, reasons, counter)


def strategy_low_score_threshold() -> int:
    return 35
