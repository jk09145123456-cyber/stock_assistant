"""2장 전체 구조를 잇는 오케스트레이션 - 데이터 수집부터 판단·설명까지 한 종목 단위로 실행."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.alerts.notifier import check_and_record_transition
from app.decision.engine import DecisionResult, decide
from app.explanations.explain import format_decision
from app.indicators.core import compute_indicator_bundle
from app.market_data.fx import build_fx_table
from app.market_data.providers import get_index_ohlcv, get_ohlcv, market_for_index
from app.market_data.validate import validate_ohlcv
from app.portfolio.models import Portfolio, Position, WatchItem
from app.regime.classify import classify_regime
from app.risk.engine import check_portfolio_limits
from app.strategies.ensemble import run_ensemble


@dataclass
class AnalysisOutcome:
    symbol: str
    name: str
    decision: DecisionResult
    explanation: str
    alert: str | None
    current_price: float | None
    data_ok: bool
    data_reasons: list[str]


def analyze_item(
    *,
    symbol: str,
    name: str,
    market: str,
    purpose: str,
    portfolio: Portfolio,
    position: Position | None,
    settings,
    fx_table: dict[str, float] | None = None,
    portfolio_price_lookup: dict[str, float] | None = None,
) -> AnalysisOutcome:
    strategy_cfg = settings.strategy
    risk_cfg = settings.risk
    ema_periods = strategy_cfg["ema_sets"].get(purpose, strategy_cfg["ema_sets"][strategy_cfg["default_purpose"]])
    # 중장기/배당은 "전고점 대비 낙폭"으로 손절 기준을 동적 계산하는데(decision/engine.py),
    # 짧은 조회 기간이면 장기 고점을 놓쳐 손절 기준이 실제보다 타이트해질 수 있다.
    # 장기 보유 종목은 최대한 긴 히스토리를 본다.
    min_lookback = 2500 if purpose in ("중장기", "배당") else 500
    lookback = max(min_lookback, max(ema_periods) * 3)

    df = get_ohlcv(symbol, market, lookback_days=lookback)
    last_updated = df.index[-1].to_pydatetime() if hasattr(df.index[-1], "to_pydatetime") else df.index[-1]
    validation = validate_ohlcv(df, last_updated, min_rows=max(ema_periods) + 30)

    index_name = market_for_index(market)
    index_df = get_index_ohlcv(index_name, lookback_days=lookback)
    index_last_updated = index_df.index[-1].to_pydatetime() if hasattr(index_df.index[-1], "to_pydatetime") else index_df.index[-1]
    index_validation = validate_ohlcv(index_df, index_last_updated, min_rows=150)

    data_ok = validation.ok and index_validation.ok
    data_reasons = validation.reasons + index_validation.reasons

    # 종목/업종 비중, 현금비율 계산에는 "전체 포트폴리오"의 현재가가 다 필요하다.
    # portfolio_price_lookup이 없으면(단독 호출 등) 최소한 평단가로 채워 넣긴 하지만,
    # 이 경우 다른 보유종목들의 실제 현재가와는 다를 수 있다는 걸 호출자가 알아야 한다.
    price_lookup = dict(portfolio_price_lookup) if portfolio_price_lookup else {
        p.symbol: p.avg_price for p in portfolio.positions
    }
    current_price = float(df["close"].iloc[-1]) if not df.empty else None
    if current_price is not None:
        price_lookup[symbol] = current_price

    if not data_ok:
        # 데이터가 불완전해도 판단 중지 응답은 만들어야 하므로 최소 결과로 채움
        from app.decision.engine import Decision

        result = DecisionResult(Decision.HALTED, 0, 0, data_reasons)
        explanation = format_decision(symbol, name, result)
        alert = check_and_record_transition(symbol, name, result, 100 - result.score)
        return AnalysisOutcome(symbol, name, result, explanation, alert, current_price, data_ok, data_reasons)

    market_regime = classify_regime(index_df, risk_cfg, strategy_cfg)
    bundle = compute_indicator_bundle(df, ema_periods, strategy_cfg)
    ensemble = run_ensemble(df, bundle, ema_periods, market_regime.regime, strategy_cfg)

    from app.scoring.score import compute_score

    weight = portfolio.position_weight(symbol, price_lookup, fx_table) if position else 0.0
    score = compute_score(
        bundle, ema_periods, market_regime, strategy_cfg,
        position_weight=weight, max_position_weight=risk_cfg["max_position_weight"],
    )

    portfolio_risk = check_portfolio_limits(portfolio, position, price_lookup, risk_cfg, fx_table)

    highest_since_buy = None
    if position is not None:
        buy_date = pd.Timestamp(position.first_buy_date)
        since_buy = df[df.index >= buy_date]
        if not since_buy.empty:
            highest_since_buy = float(since_buy["high"].max())

    result = decide(
        data_valid=True, data_invalid_reasons=[],
        portfolio_risk=portfolio_risk, market_regime=market_regime,
        position=position, current_price=current_price,
        highest_price_since_buy=highest_since_buy,
        bundle=bundle, ema_periods=ema_periods,
        ensemble=ensemble, score=score, risk_cfg=risk_cfg, purpose=purpose,
    )

    explanation = format_decision(symbol, name, result)
    alert = check_and_record_transition(symbol, name, result, score.risk_score)

    return AnalysisOutcome(symbol, name, result, explanation, alert, current_price, data_ok, data_reasons)


def analyze_portfolio(settings) -> list[AnalysisOutcome]:
    from app.portfolio.models import load_portfolio

    portfolio = load_portfolio(settings.portfolio)
    needs_fx = any(p.currency != portfolio.account_currency for p in portfolio.positions)
    fx_table = build_fx_table(portfolio.account_currency) if needs_fx else None

    # 비중/현금비율 계산이 모든 보유종목의 "현재가"를 정확히 알아야 맞으므로,
    # 종목별로 따로 계산하지 않고 여기서 한 번에 미리 다 조회해서 공유한다.
    portfolio_price_lookup: dict[str, float] = {}
    for pos in portfolio.positions:
        try:
            df = get_ohlcv(pos.symbol, pos.market, lookback_days=5)
            portfolio_price_lookup[pos.symbol] = float(df["close"].iloc[-1])
        except Exception:
            portfolio_price_lookup[pos.symbol] = pos.avg_price  # 조회 실패 시에만 평단가로 대체

    outcomes = []
    for pos in portfolio.positions:
        outcomes.append(
            analyze_item(
                symbol=pos.symbol, name=pos.name, market=pos.market, purpose=pos.purpose,
                portfolio=portfolio, position=pos, settings=settings, fx_table=fx_table,
                portfolio_price_lookup=portfolio_price_lookup,
            )
        )
    for w in portfolio.watchlist:
        outcomes.append(
            analyze_item(
                symbol=w.symbol, name=w.name, market=w.market, purpose=w.purpose,
                portfolio=portfolio, position=None, settings=settings, fx_table=fx_table,
                portfolio_price_lookup=portfolio_price_lookup,
            )
        )
    return outcomes
