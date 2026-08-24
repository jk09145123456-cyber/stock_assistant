"""4장: 환율 - 계좌 통화와 다른 시장의 포지션을 합산할 때 필요한 최소 FX 변환."""
from __future__ import annotations

from app.market_data.providers import get_ohlcv

CURRENCY_BY_MARKET = {"KR": "KRW", "US": "USD"}


def get_usd_krw_rate() -> float:
    df = get_ohlcv("KRW=X", "US", lookback_days=5, max_cache_minutes=60)
    return float(df["close"].iloc[-1])


def build_fx_table(account_currency: str) -> dict[str, float]:
    """{통화: 1단위를 account_currency로 바꿀 때 곱할 배율}"""
    table = {account_currency: 1.0}
    if account_currency == "KRW" and "USD" not in table:
        table["USD"] = get_usd_krw_rate()
    elif account_currency == "USD" and "KRW" not in table:
        table["KRW"] = 1.0 / get_usd_krw_rate()
    return table
