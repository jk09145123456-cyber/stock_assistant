"""4장 사용자 입력 - 보유 종목/관심 종목 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

PURPOSES = ("단기", "스윙", "중장기", "배당")


@dataclass
class Position:
    symbol: str
    market: str  # "KR" | "US"
    name: str
    quantity: float
    avg_price: float
    first_buy_date: date
    purpose: str = "스윙"
    target_holding_period_days: Optional[int] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    sector: Optional[str] = None
    additional_buys_used: int = 0
    thesis: list[str] = field(default_factory=list)
    account: Optional[str] = None  # 예: "단독", "ISA" - 계좌 간 현금은 서로 못 옮겨쓴다는 점 표시용

    @property
    def currency(self) -> str:
        return "KRW" if self.market == "KR" else "USD"

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price

    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    def unrealized_return(self, current_price: float) -> float:
        if self.avg_price == 0:
            return 0.0
        return (current_price - self.avg_price) / self.avg_price


@dataclass
class WatchItem:
    symbol: str
    market: str
    name: str
    purpose: str = "스윙"
    sector: Optional[str] = None


@dataclass
class Portfolio:
    cash: float
    account_currency: str
    positions: list[Position]
    watchlist: list[WatchItem]
    cash_by_account: dict[str, float] = field(default_factory=dict)

    def _fx(self, currency: str, fx_table: dict[str, float] | None) -> float:
        if fx_table is None or currency == self.account_currency:
            return 1.0
        return fx_table.get(currency, 1.0)

    def _position_value_in_account_currency(
        self, p: Position, price_lookup: dict[str, float], fx_table: dict[str, float] | None
    ) -> float:
        return p.market_value(price_lookup.get(p.symbol, p.avg_price)) * self._fx(p.currency, fx_table)

    def total_position_value(self, price_lookup: dict[str, float], fx_table: dict[str, float] | None = None) -> float:
        return sum(self._position_value_in_account_currency(p, price_lookup, fx_table) for p in self.positions)

    def total_assets(self, price_lookup: dict[str, float], fx_table: dict[str, float] | None = None) -> float:
        return self.cash + self.total_position_value(price_lookup, fx_table)

    def position_weight(
        self, symbol: str, price_lookup: dict[str, float], fx_table: dict[str, float] | None = None
    ) -> float:
        total = self.total_assets(price_lookup, fx_table)
        if total <= 0:
            return 0.0
        pos = next((p for p in self.positions if p.symbol == symbol), None)
        if pos is None:
            return 0.0
        return self._position_value_in_account_currency(pos, price_lookup, fx_table) / total

    def sector_weight(
        self, sector: str, price_lookup: dict[str, float], fx_table: dict[str, float] | None = None
    ) -> float:
        total = self.total_assets(price_lookup, fx_table)
        if total <= 0:
            return 0.0
        value = sum(
            self._position_value_in_account_currency(p, price_lookup, fx_table)
            for p in self.positions
            if p.sector == sector
        )
        return value / total

    def cash_ratio(self, price_lookup: dict[str, float], fx_table: dict[str, float] | None = None) -> float:
        total = self.total_assets(price_lookup, fx_table)
        if total <= 0:
            return 1.0
        return self.cash / total


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_portfolio(raw: dict) -> Portfolio:
    positions = [
        Position(
            symbol=str(p["symbol"]),
            market=p["market"],
            name=p["name"],
            quantity=float(p["quantity"]),
            avg_price=float(p["avg_price"]),
            first_buy_date=_parse_date(p["first_buy_date"]),
            purpose=p.get("purpose", "스윙"),
            target_holding_period_days=p.get("target_holding_period_days"),
            target_price=p.get("target_price"),
            stop_loss_price=p.get("stop_loss_price"),
            sector=p.get("sector"),
            additional_buys_used=int(p.get("additional_buys_used", 0)),
            thesis=list(p.get("thesis") or []),
            account=p.get("account"),
        )
        for p in raw.get("positions", [])
    ]
    watchlist = [
        WatchItem(
            symbol=str(w["symbol"]),
            market=w["market"],
            name=w["name"],
            purpose=w.get("purpose", "스윙"),
            sector=w.get("sector"),
        )
        for w in raw.get("watchlist", [])
    ]
    raw_cash = raw.get("cash", 0)
    if isinstance(raw_cash, dict):
        cash_by_account = {k: float(v) for k, v in raw_cash.items()}
        total_cash = sum(cash_by_account.values())
    else:
        cash_by_account = {}
        total_cash = float(raw_cash)

    return Portfolio(
        cash=total_cash,
        account_currency=raw.get("account_currency", "KRW"),
        positions=positions,
        watchlist=watchlist,
        cash_by_account=cash_by_account,
    )
