"""5장/10장 지표 - EMA, ATR, RSI, MACD, ADX, 볼린저, 기울기, 이격도, 상대강도."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def ema_slope(ema_series: pd.Series, lookback: int = 5) -> pd.Series:
    """5장: (현재 EMA - N일 전 EMA) / N일 전 EMA"""
    past = ema_series.shift(lookback)
    return (ema_series - past) / past.replace(0, np.nan)


def disparity(price: pd.Series, ema_series: pd.Series) -> pd.Series:
    """5장: (현재가 / EMA - 1) * 100"""
    return (price / ema_series.replace(0, np.nan) - 1) * 100


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    # avg_loss == 0: 하락이 전혀 없었으면 과매수 극단(100)이지, 중립(50)이 아니다.
    # avg_gain도 0(가격 변화 없음)일 때만 중립으로 채운다.
    result = result.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    return pd.Series(result, index=series.index).fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_smooth = true_range.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    return upper, mid, lower, width


def rolling_return(series: pd.Series, period: int) -> pd.Series:
    return series.pct_change(period)


def relative_strength(stock_return: float, market_return: float) -> float:
    """10장: 20일 상대강도 = 종목 수익률 - 시장지수 수익률"""
    return stock_return - market_return


def drawdown_from_high(series: pd.Series, window: int | None = None) -> pd.Series:
    rolling_max = series.rolling(window).max() if window else series.cummax()
    return (series - rolling_max) / rolling_max.replace(0, np.nan)


def higher_highs_lows(df: pd.DataFrame, window: int = 20) -> bool:
    """8장/11장: 최근 고점/저점이 함께 상승했는지 (단순화된 판정)."""
    highs = df["high"].rolling(window).max()
    lows = df["low"].rolling(window).min()
    if len(highs.dropna()) < window + 1:
        return False
    recent_high, prev_high = highs.iloc[-1], highs.iloc[-window - 1]
    recent_low, prev_low = lows.iloc[-1], lows.iloc[-window - 1]
    return bool(recent_high > prev_high and recent_low > prev_low)


def recent_low_break(df: pd.DataFrame, window: int = 20) -> bool:
    """직전 window 기간 저점을 최근 종가가 하향 이탈했는지."""
    if len(df) < window + 1:
        return False
    prior_low = df["low"].iloc[-window - 1 : -1].min()
    return bool(df["close"].iloc[-1] < prior_low)


def recent_high_break(df: pd.DataFrame, window: int = 20) -> bool:
    """직전 window 기간 고점을 최근 종가가 상향 돌파했는지 (돌파 전략용)."""
    if len(df) < window + 1:
        return False
    prior_high = df["high"].iloc[-window - 1 : -1].max()
    return bool(df["close"].iloc[-1] > prior_high)


def oversold_recovery_stats(
    close: pd.Series, rsi_series: pd.Series, recovery_level: pd.Series,
    oversold_threshold: float = 35, max_wait_days: int = 60,
) -> dict:
    """13장 평균회귀 근거 통계: 이 종목이 과거에 RSI가 이 임계값 밑으로 떨어졌던 시점마다
    실제로 recovery_level(보통 EMA중기선) 위로 회복하기까지 며칠 걸렸는지 전부 세어
    평균/중앙값/표본수를 낸다. 미래를 예측하는 고정값이 아니라 이 종목 스스로가 과거에
    보인 패턴을 매번 다시 요약한 값 - 종목마다 변동성이 달라서 회복 소요일도 다르게 나온다.
    표본이 적으면(예: 3회 미만) 통계적으로 근거가 약하니 호출부에서 sample_count로 걸러야 한다.
    """
    is_oversold = rsi_series < oversold_threshold
    streak_start = is_oversold & ~is_oversold.shift(1, fill_value=False)
    start_positions = np.where(streak_start.to_numpy())[0]

    durations: list[int] = []
    for pos in start_positions:
        for offset in range(1, max_wait_days + 1):
            idx = pos + offset
            if idx >= len(close):
                break
            if close.iloc[idx] >= recovery_level.iloc[idx]:
                durations.append(offset)
                break

    if not durations:
        return {"avg_days": None, "median_days": None, "sample_count": 0}
    return {
        "avg_days": float(np.mean(durations)),
        "median_days": float(np.median(durations)),
        "sample_count": len(durations),
    }


def volume_ratio(df: pd.DataFrame, window: int = 20) -> float:
    avg_vol = df["volume"].iloc[-window - 1 : -1].mean()
    if not avg_vol:
        return 1.0
    return float(df["volume"].iloc[-1] / avg_vol)


def compute_indicator_bundle(df: pd.DataFrame, ema_periods: list[int], strategy_cfg: dict) -> dict:
    """한 종목의 지표를 한 번에 계산해 dict로 반환. scoring/strategies/regime에서 재사용."""
    close = df["close"]
    emas = {p: ema(close, p) for p in ema_periods}
    slopes = {
        p: ema_slope(emas[p], strategy_cfg["slope"]["lookback_days"]) for p in ema_periods
    }
    disparities = {p: disparity(close, emas[p]) for p in ema_periods}

    macd_line, signal_line, hist = macd(
        close,
        strategy_cfg["macd"]["fast"],
        strategy_cfg["macd"]["slow"],
        strategy_cfg["macd"]["signal"],
    )
    bb_upper, bb_mid, bb_lower, bb_width = bollinger(
        close, strategy_cfg["bollinger"]["period"], strategy_cfg["bollinger"]["num_std"]
    )

    return {
        "close": close,
        "ema": emas,
        "ema_slope": slopes,
        "disparity": disparities,
        "atr": atr(df, strategy_cfg["atr"]["period"]),
        "rsi": rsi(close, strategy_cfg["rsi"]["period"]),
        "adx": adx(df, strategy_cfg["adx"]["period"]),
        "macd_line": macd_line,
        "macd_signal": signal_line,
        "macd_hist": hist,
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "return_5d": rolling_return(close, 5),
        "return_20d": rolling_return(close, 20),
        "return_60d": rolling_return(close, 60),
        "volume_ratio_20d": volume_ratio(df, 20),
        "higher_highs_lows_20d": higher_highs_lows(df, 20),
        "recent_low_break_20d": recent_low_break(df, 20),
        "recent_high_break_20d": recent_high_break(df, 20),
        "recent_high_break_60d": recent_high_break(df, 60),
        "low_20d": float(df["low"].iloc[-21:-1].min()) if len(df) >= 21 else float(df["low"].min()),
        "ath": float(df["high"].max()),  # 조회 기간 내 전고점 (평생보유 종목 손절 기준에 사용)
        "drawdown_from_ath": float(close.iloc[-1] / df["high"].max() - 1),
        # 조회 기간 내 이 종목이 실제로 겪은 최악의 낙폭(전고점 대비, 음수) - 종목마다
        # 원래 변동성이 다르므로 "역대 최악보다 더 나쁜지"를 종목별로 다르게 판단하는 데 쓴다.
        "max_historical_drawdown": float(drawdown_from_high(close).min()),
    }
