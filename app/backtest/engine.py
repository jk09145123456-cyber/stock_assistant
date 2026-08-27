"""15장 백테스트 - 추세추종+ATR 트레일링 전략을 backtesting.py로 워크포워드 검증.

승률보다 최대 낙폭/손익비가 중요하다는 15장 원칙에 따라 report.py에서
지표를 다시 계산해 강조한다. 여기서는 backtesting.py 엔진 실행만 담당한다.
"""
from __future__ import annotations

import pandas as pd
from backtesting import Backtest, Strategy

from app.indicators.core import atr as atr_func
from app.indicators.core import ema as ema_func
from app.market_data.providers import get_ohlcv


def _to_backtesting_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    return out[["Open", "High", "Low", "Close", "Volume"]]


class TrendFollowingATR(Strategy):
    """13장 전략 A(추세추종) 매수 + 9장 추세 훼손/8장 ATR 트레일링 매도."""

    ema_short = 20
    ema_mid = 60
    ema_long = 120
    atr_period = 14
    atr_mult = 2.5
    risk_per_trade = 0.005

    def init(self):
        close = pd.Series(self.data.Close, index=self.data.index)
        self.ema_s = self.I(lambda: ema_func(close, self.ema_short).values)
        self.ema_m = self.I(lambda: ema_func(close, self.ema_mid).values)
        self.ema_l = self.I(lambda: ema_func(close, self.ema_long).values)

        ohlc = pd.DataFrame(
            {"high": self.data.High, "low": self.data.Low, "close": self.data.Close}, index=self.data.index
        )
        self.atr = self.I(lambda: atr_func(ohlc, self.atr_period).values)
        self._trailing_stop = None

    def next(self):
        price = self.data.Close[-1]

        if not self.position:
            aligned_up = price > self.ema_s[-1] > self.ema_m[-1] > self.ema_l[-1]
            slope_up = len(self.ema_m) > 5 and self.ema_m[-1] > self.ema_m[-6]
            if aligned_up and slope_up:
                stop_price = price - self.atr[-1] * self.atr_mult
                risk_per_share = price - stop_price
                if risk_per_share > 0:
                    allowed_loss = self.equity * self.risk_per_trade
                    size = max(1, int(allowed_loss / risk_per_share))
                    max_affordable = int(self.equity // price)
                    size = min(size, max_affordable)
                    if size > 0:
                        self.buy(size=size)
                        self._trailing_stop = stop_price
        else:
            # 8장: 트레일링 기준가 = "매수 이후" 최고가 - ATR*배수.
            # entry_bar 이전 구간의 고점은 이 포지션과 무관하므로 반드시 제외해야 한다
            # (안 그러면 매수 직전의 더 높은 고점 때문에 진입 직후 바로 손절당할 수 있음).
            entry_bar = self.trades[-1].entry_bar
            period_high = max(self.data.High[entry_bar:])
            trailing = period_high - self.atr[-1] * self.atr_mult
            self._trailing_stop = max(self._trailing_stop or trailing, trailing)

            aligned_down = self.ema_s[-1] < self.ema_m[-1]
            if price < self._trailing_stop or aligned_down:
                self.position.close()
                self._trailing_stop = None


def run_backtest(
    symbol: str,
    market: str,
    start: str | None = None,
    end: str | None = None,
    cash: float = 10_000_000,
    commission_bps: float = 15,
    kr_sell_tax_bps: float = 18,
    slippage_bps: float = 5,
    lookback_days: int = 3000,
) -> tuple[pd.Series, pd.DataFrame, "Backtest"]:
    """단일 구간 백테스트. 반환: (stats, trades_df, Backtest 인스턴스)"""
    raw = get_ohlcv(symbol, market, lookback_days=lookback_days, max_cache_minutes=24 * 60)
    df = _to_backtesting_df(raw)

    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]

    if len(df) < 200:
        raise ValueError(f"백테스트에 필요한 데이터가 부족합니다 ({len(df)}행, 최소 200행)")

    commission = commission_bps / 10_000
    if market == "KR":
        commission += kr_sell_tax_bps / 10_000  # 매도세는 편도지만 근사로 합산
    spread = slippage_bps / 10_000

    bt = Backtest(df, TrendFollowingATR, cash=cash, commission=commission, spread=spread, finalize_trades=True)
    stats = bt.run()
    trades = stats["_trades"] if "_trades" in stats else pd.DataFrame()
    return stats, trades, bt


def run_walkforward(symbol: str, market: str, backtest_cfg: dict) -> dict[str, dict]:
    """15장: 개발/검증/최종평가 구간을 시간 순서대로 분리해 각각 실행."""
    results = {}
    for period_name, (start, end) in backtest_cfg["periods"].items():
        try:
            stats, trades, _ = run_backtest(
                symbol, market, start=start, end=end,
                cash=backtest_cfg["initial_cash"],
                commission_bps=backtest_cfg["costs"]["commission_bps"],
                kr_sell_tax_bps=backtest_cfg["costs"]["kr_sell_tax_bps"],
                slippage_bps=backtest_cfg["costs"]["slippage_bps"],
            )
            results[period_name] = {"stats": stats, "trades": trades, "error": None}
        except Exception as e:  # noqa: BLE001 - 기간별로 데이터 부족 등은 결과에 기록하고 계속 진행
            results[period_name] = {"stats": None, "trades": None, "error": str(e)}
    return results
