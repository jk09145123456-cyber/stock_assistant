"""3장/7장/12장 포트폴리오 위험관리 - 비중 제한, 매수 수량 계산, 종목 간 우선순위."""
from __future__ import annotations

from dataclasses import dataclass

from app.portfolio.models import Portfolio, Position


@dataclass
class SizingResult:
    allowed_loss_amount: float
    shares: int
    notes: list[str]


def position_size_by_risk(
    total_assets: float,
    risk_per_trade: float,
    planned_buy_price: float,
    stop_loss_price: float,
) -> SizingResult:
    """7장: 허용 손실금액 = 전체 자산 x 종목당 위험률
    매수 가능 수량 = 허용 손실금액 / (예상 매수가 - 손절 기준가)
    """
    notes = []
    allowed_loss = total_assets * risk_per_trade
    per_share_risk = planned_buy_price - stop_loss_price
    if per_share_risk <= 0:
        notes.append("손절가가 매수가보다 높거나 같아 위험률 기반 수량 계산 불가")
        return SizingResult(allowed_loss, 0, notes)
    shares = int(allowed_loss // per_share_risk)
    notes.append(f"허용손실 {allowed_loss:,.0f} / 주당위험 {per_share_risk:,.0f} = {shares}주")
    return SizingResult(allowed_loss, shares, notes)


@dataclass
class PortfolioRiskCheck:
    weight_ok: bool
    sector_weight_ok: bool
    cash_ratio_ok: bool
    additional_buys_ok: bool
    reasons: list[str]

    @property
    def all_ok(self) -> bool:
        return self.weight_ok and self.sector_weight_ok and self.cash_ratio_ok and self.additional_buys_ok


def check_portfolio_limits(
    portfolio: Portfolio,
    position: Position | None,
    price_lookup: dict[str, float],
    risk_cfg: dict,
    fx_table: dict[str, float] | None = None,
) -> PortfolioRiskCheck:
    reasons = []

    weight_ok = True
    if position is not None:
        w = portfolio.position_weight(position.symbol, price_lookup, fx_table)
        weight_ok = w <= risk_cfg["max_position_weight"]
        if not weight_ok:
            reasons.append(f"종목 비중 {w:.1%} > 한도 {risk_cfg['max_position_weight']:.0%}")

    sector_ok = True
    if position is not None and position.sector:
        sw = portfolio.sector_weight(position.sector, price_lookup, fx_table)
        sector_ok = sw <= risk_cfg["max_sector_weight"]
        if not sector_ok:
            reasons.append(f"업종 비중 {sw:.1%} > 한도 {risk_cfg['max_sector_weight']:.0%}")

    cash_ratio = portfolio.cash_ratio(price_lookup, fx_table)
    cash_ok = cash_ratio >= risk_cfg["minimum_cash_ratio"]
    if not cash_ok:
        reasons.append(f"현금 비율 {cash_ratio:.1%} < 최소 {risk_cfg['minimum_cash_ratio']:.0%}")

    buys_ok = True
    if position is not None:
        buys_ok = position.additional_buys_used < risk_cfg["max_additional_buys"]
        if not buys_ok:
            reasons.append(f"추가매수 횟수 {position.additional_buys_used}회로 한도 소진")

    return PortfolioRiskCheck(weight_ok, sector_ok, cash_ok, buys_ok, reasons)


@dataclass
class Candidate:
    symbol: str
    normalized_score: int
    confidence: int


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """12장: 현금이 부족할 때 정규화 점수 우선, 동점이면 신뢰도(13장) 우선."""
    return sorted(candidates, key=lambda c: (c.normalized_score, c.confidence), reverse=True)
