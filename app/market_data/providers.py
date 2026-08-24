"""4장 데이터 구성 - 한국(pykrx)/미국(yfinance) 시세 + 지수 수집.

개인용 첫 버전은 가격·거래량·시장지수만 다룬다 (4장). 한국투자증권 Open API로
교체하려면 이 모듈의 함수 시그니처(get_ohlcv, get_last_price)만 맞춰 provider를
바꿔 끼우면 된다.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# pykrx의 지수 API(get_index_ohlcv)는 KRX 서버 사정으로 자주 실패해
# 지수는 시장 구분 없이 yfinance 티커로 통일해서 받는다. 개별 종목은 계속
# pykrx(KR)/yfinance(US)를 그대로 쓴다.
INDEX_MAP = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}

OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.parquet"


def _read_cache(key: str, max_age_minutes: int) -> pd.DataFrame | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    age_minutes = (dt.datetime.now().timestamp() - path.stat().st_mtime) / 60
    if age_minutes > max_age_minutes:
        return None
    return pd.read_parquet(path)


def _write_cache(key: str, df: pd.DataFrame) -> None:
    df.to_parquet(_cache_path(key))


def get_ohlcv(
    symbol: str,
    market: str,
    lookback_days: int = 500,
    interval: str = "1d",
    max_cache_minutes: int = 60,
) -> pd.DataFrame:
    """일봉(기본) OHLCV. columns: open, high, low, close, volume, index=date(UTC naive)."""
    cache_key = f"{market}_{symbol}_{interval}_{lookback_days}"
    cached = _read_cache(cache_key, max_cache_minutes)
    if cached is not None:
        return cached

    end = dt.date.today()
    start = end - dt.timedelta(days=int(lookback_days * 1.6) + 10)  # 영업일 감안 여유

    if market == "KR":
        df = _get_kr_ohlcv(symbol, start, end)
    elif market == "US":
        df = _get_us_ohlcv(symbol, start, end, interval)
    else:
        raise ValueError(f"unknown market: {market}")

    df = df.tail(lookback_days)
    _write_cache(cache_key, df)
    return df


def _get_kr_ohlcv(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    from pykrx import stock

    raw = stock.get_market_ohlcv(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), symbol
    )
    raw = raw.rename(
        columns={"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}
    )
    df = raw[OHLCV_COLS].copy()
    df.index.name = "date"
    return _sanitize_ohlcv(df)


def _sanitize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """액면분할/거래정지 등으로 생기는 명백한 이상치를 정리한다.

    액면분할이나 거래정지 구간에는 시가·고가·저가·거래량이 전부 0인데 종가만 남아있는
    비정상 봉이 들어올 수 있다. 이런 봉이 섞이면 지표 계산(EMA/ATR 등)이
    이런 봉이 섞이면 왜곡되므로 아예 제거한다. 반올림 오차로 종가가 고가를 미세하게 넘는
    경우는 지우기엔 아깝고 왜곡도 미미하므로 고가/저가 범위 안으로 살짝 눌러준다.
    """
    valid = ~((df["open"] == 0) & (df["volume"] == 0))
    df = df[valid].copy()
    df["close"] = df["close"].clip(lower=df["low"], upper=df["high"])
    return df


def _get_us_ohlcv(symbol: str, start: dt.date, end: dt.date, interval: str) -> pd.DataFrame:
    import yfinance as yf

    yf_interval = {"1d": "1d", "60m": "60m", "15m": "15m"}.get(interval, "1d")
    raw = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=(end + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        interval=yf_interval,
        progress=False,
        auto_adjust=True,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.lower)
    df = raw[OHLCV_COLS].copy()
    df.index.name = "date"
    return _sanitize_ohlcv(df)


def get_index_ohlcv(index_name: str, lookback_days: int = 500) -> pd.DataFrame:
    """코스피/코스닥/S&P500/나스닥 지수 OHLCV (yfinance 티커로 통일)."""
    if index_name not in INDEX_MAP:
        raise ValueError(f"unknown index: {index_name}")
    return get_ohlcv(INDEX_MAP[index_name], "US", lookback_days)


def market_for_index(market: str) -> str:
    return "KOSPI" if market == "KR" else "S&P500"


def get_last_price(symbol: str, market: str) -> tuple[float, dt.datetime]:
    """현재가와 조회 시각. (5장/12장 staleness 체크에 사용)"""
    df = get_ohlcv(symbol, market, lookback_days=5, max_cache_minutes=5)
    last_ts = df.index[-1]
    if hasattr(last_ts, "to_pydatetime"):
        last_ts = last_ts.to_pydatetime()
    return float(df["close"].iloc[-1]), last_ts
