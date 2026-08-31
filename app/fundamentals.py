"""재무 펀더멘털 - yfinance .info 기반. 국내 종목도 .KS/.KQ 접미사로 일부 조회 가능.

주의: 비(非)미국 종목은 yfinance의 재무 필드가 비어있거나(trailingPE/PBR 등)
부정확할 수 있다(회계 기준 차이, 갱신 지연 등). 참고용으로만 쓰고 뉴스와
같이 봐야 한다. 데이터와 최신 공시·뉴스의 내용이 다를 수 있다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "fundamentals_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

KR_SUFFIX_BY_MARKET_HINT = ".KS"  # 코스피 기준(코스닥은 .KQ) - 종목마다 다를 수 있어 실패 시 폴백


@dataclass
class Fundamentals:
    forward_pe: float | None
    trailing_pe: float | None
    price_to_book: float | None
    return_on_equity: float | None
    profit_margins: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    dividend_yield: float | None
    market_cap: float | None
    data_quality_note: str = ""

    def as_text(self) -> str:
        def fmt_pct(v):
            return f"{v:+.1%}" if v is not None else "N/A"

        def fmt_num(v):
            return f"{v:.2f}" if v is not None else "N/A"

        # dividendYield는 yfinance가 이미 %단위 숫자로 준다(0.53 == 0.53%),
        # 다른 필드(ROE/마진/성장률)는 비율(0.3 == 30%)이라 :.1% 포맷이 맞다 - 헷갈리기 쉬움.
        div_text = f"{self.dividend_yield:.2f}%" if self.dividend_yield is not None else "N/A"

        return (
            f"forwardPE={fmt_num(self.forward_pe)}, trailingPE={fmt_num(self.trailing_pe)}, "
            f"PBR={fmt_num(self.price_to_book)}, ROE={fmt_pct(self.return_on_equity)}, "
            f"영업이익률={fmt_pct(self.profit_margins)}, 매출성장률={fmt_pct(self.revenue_growth)}, "
            f"이익성장률={fmt_pct(self.earnings_growth)}, 배당수익률={div_text}"
        )


def _yf_symbol(symbol: str, market: str) -> str:
    if market == "KR":
        return f"{symbol}.KS"
    return symbol


def get_fundamentals(symbol: str, market: str, max_cache_hours: int = 24) -> Fundamentals | None:
    cache_path = CACHE_DIR / f"{market}_{symbol}.parquet"
    if cache_path.exists():
        age_hours = (dt.datetime.now().timestamp() - cache_path.stat().st_mtime) / 3600
        if age_hours <= max_cache_hours:
            row = pd.read_parquet(cache_path).iloc[0].to_dict()
            return Fundamentals(**row)

    import yfinance as yf

    yf_symbol = _yf_symbol(symbol, market)
    info = yf.Ticker(yf_symbol).info

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        # .KS로 안 붙는 종목(코스닥 등)은 .KQ로 한 번 더 시도
        if market == "KR":
            info = yf.Ticker(f"{symbol}.KQ").info
        if not info:
            return None

    result = Fundamentals(
        forward_pe=info.get("forwardPE"),
        trailing_pe=info.get("trailingPE"),
        price_to_book=info.get("priceToBook"),
        return_on_equity=info.get("returnOnEquity"),
        profit_margins=info.get("profitMargins"),
        revenue_growth=info.get("revenueGrowth"),
        earnings_growth=info.get("earningsGrowth"),
        dividend_yield=info.get("dividendYield"),
        market_cap=info.get("marketCap"),
        data_quality_note="국내 종목은 일부 항목이 비거나 회계기준 차이로 뉴스와 다르게 보일 수 있음",
    )
    pd.DataFrame([result.__dict__]).to_parquet(cache_path)
    return result
