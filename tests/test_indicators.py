import numpy as np
import pandas as pd
import pytest

from app.indicators import core as ind


def make_trend_df(n=200, start=100.0, daily_return=0.005, seed=0):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.002, n)
    close = start * np.cumprod(1 + daily_return + noise)
    high = close * 1.005
    low = close * 0.995
    open_ = close * (1 - daily_return / 2)
    volume = rng.integers(1000, 2000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_ema_tracks_uptrend():
    df = make_trend_df()
    e20 = ind.ema(df["close"], 20)
    assert e20.iloc[-1] > e20.iloc[-30]


def test_ema_slope_positive_in_uptrend():
    df = make_trend_df()
    e20 = ind.ema(df["close"], 20)
    slope = ind.ema_slope(e20, 5)
    assert slope.iloc[-1] > 0


def test_disparity_sign():
    price = pd.Series([110.0])
    ema_val = pd.Series([100.0])
    assert ind.disparity(price, ema_val).iloc[0] == pytest.approx(10.0)


def test_rsi_bounds():
    df = make_trend_df()
    rsi = ind.rsi(df["close"])
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_rsi_high_in_strong_uptrend():
    df = make_trend_df(daily_return=0.02, seed=1)
    rsi = ind.rsi(df["close"])
    assert rsi.iloc[-1] > 60


def test_atr_nonnegative():
    df = make_trend_df()
    atr = ind.atr(df)
    assert (atr.dropna() >= 0).all()


def test_macd_hist_positive_in_uptrend():
    df = make_trend_df(daily_return=0.01, seed=2)
    _, _, hist = ind.macd(df["close"])
    assert hist.iloc[-1] > 0


def test_higher_highs_lows_true_in_uptrend():
    df = make_trend_df()
    assert ind.higher_highs_lows(df, 20) is True


def test_recent_low_break_false_in_clean_uptrend():
    df = make_trend_df(daily_return=0.01, seed=3)
    assert ind.recent_low_break(df, 20) is False


def test_recent_low_break_true_after_drop():
    df = make_trend_df(daily_return=0.01, seed=4)
    df.loc[df.index[-1], "close"] = df["low"].iloc[-21:-1].min() * 0.9
    assert ind.recent_low_break(df, 20) is True
