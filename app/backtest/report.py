"""15장 평가 지표 - 승률보다 최대 낙폭/손익비를 강조해서 보여준다."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestReport:
    period_label: str
    cumulative_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    num_trades: int
    avg_holding_days: float
    excess_return_vs_buy_hold_pct: float
    sharpe: float

    def as_text(self) -> str:
        lines = [
            f"=== {self.period_label} ===",
            f"누적 수익률: {self.cumulative_return_pct:.2f}%",
            f"연환산 수익률: {self.annualized_return_pct:.2f}%",
            f"최대 낙폭(MDD): {self.max_drawdown_pct:.2f}%  <- 승률보다 이 값이 중요 (15장)",
            f"승률: {self.win_rate_pct:.1f}%",
            f"평균 이익: {self.avg_win_pct:.2f}% / 평균 손실: {self.avg_loss_pct:.2f}%",
            f"손익비(Profit Factor): {self.profit_factor:.2f}",
            f"거래 횟수: {self.num_trades}",
            f"평균 보유 기간: {self.avg_holding_days:.1f}일",
            f"시장 대비 초과수익: {self.excess_return_vs_buy_hold_pct:+.2f}%p",
            f"Sharpe: {self.sharpe:.2f}",
        ]
        return "\n".join(lines)


def build_report(period_label: str, stats: pd.Series, trades: pd.DataFrame) -> BacktestReport:
    wins = trades[trades["ReturnPct"] > 0]["ReturnPct"] if len(trades) else pd.Series(dtype=float)
    losses = trades[trades["ReturnPct"] <= 0]["ReturnPct"] if len(trades) else pd.Series(dtype=float)

    avg_win = float(wins.mean() * 100) if len(wins) else 0.0
    avg_loss = float(losses.mean() * 100) if len(losses) else 0.0
    avg_days = float(trades["Duration"].dt.days.mean()) if len(trades) else 0.0

    return BacktestReport(
        period_label=period_label,
        cumulative_return_pct=float(stats["Return [%]"]),
        annualized_return_pct=float(stats["CAGR [%]"]),
        max_drawdown_pct=float(stats["Max. Drawdown [%]"]),
        win_rate_pct=float(stats["Win Rate [%]"]) if pd.notna(stats["Win Rate [%]"]) else 0.0,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        profit_factor=float(stats["Profit Factor"]) if pd.notna(stats["Profit Factor"]) else 0.0,
        num_trades=int(stats["# Trades"]),
        avg_holding_days=avg_days,
        excess_return_vs_buy_hold_pct=float(stats["Return [%]"] - stats["Buy & Hold Return [%]"]),
        sharpe=float(stats["Sharpe Ratio"]) if pd.notna(stats["Sharpe Ratio"]) else 0.0,
    )


def signal_forward_returns(trades: pd.DataFrame, equity_curve: pd.DataFrame, horizons=(5, 10, 20)) -> dict[int, float]:
    """15장: 신호 발생(진입) 후 N일 수익률 - equity curve 기준 평균."""
    if trades.empty:
        return {h: 0.0 for h in horizons}
    results = {}
    equity = equity_curve["Equity"]
    for h in horizons:
        rets = []
        for entry_bar in trades["EntryBar"]:
            if entry_bar + h < len(equity):
                rets.append(equity.iloc[entry_bar + h] / equity.iloc[entry_bar] - 1)
        results[h] = float(pd.Series(rets).mean() * 100) if rets else 0.0
    return results
