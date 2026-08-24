"""4장/12장 데이터 검증 - 누락 / 조회 지연 / 액면분할 / 비정상 가격."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ValidationResult:
    ok: bool
    is_stale: bool
    reasons: list[str]


def validate_ohlcv(
    df: pd.DataFrame,
    last_updated: dt.datetime,
    max_staleness_minutes: int | None = None,
    max_staleness_days: int = 4,
    min_rows: int = 60,
    split_jump_ratio: float = 1.8,
) -> ValidationResult:
    """데이터 품질 검증.

    일봉만 쓰는 무료 데이터소스(pykrx/yfinance)에서는 "몇 분 전 데이터인지"가
    아니라 "가장 최근 거래일 봉이 들어와 있는지"가 신선도의 의미다. 따라서
    기본값은 max_staleness_days(주말/공휴일 감안 4일)로 판정한다.
    실시간 체결가(예: 한국투자증권 WebSocket)로 교체하면 max_staleness_minutes를
    넘겨 분 단위로 판정할 수 있다 (12장: 30분 이상 지연 시 "판단 중지").
    """
    reasons: list[str] = []

    if df is None or df.empty or len(df) < min_rows:
        reasons.append(f"데이터 부족 (rows={0 if df is None else len(df)}, 최소 {min_rows})")

    if df is not None and not df.empty:
        if df[["open", "high", "low", "close"]].isna().any().any():
            reasons.append("가격 결측치 존재")
        if (df["close"] <= 0).any():
            reasons.append("비정상 가격(0 이하) 발견")
        if (df["volume"] < 0).any():
            reasons.append("비정상 거래량(음수) 발견")

        # 액면분할/병합 의심: 전일 대비 급격한 종가 배율 변화
        ratio = (df["close"] / df["close"].shift(1)).dropna()
        suspicious = ratio[(ratio > split_jump_ratio) | (ratio < 1 / split_jump_ratio)]
        if not suspicious.empty:
            reasons.append(
                f"액면분할/이상 가격 점프 의심: {len(suspicious)}건 (예: {suspicious.index[-1].date()})"
            )

        # 고가<저가, 종가가 고저 범위 밖 등 봉 자체의 논리적 결함
        bad_bars = df[(df["high"] < df["low"]) | (df["close"] > df["high"]) | (df["close"] < df["low"])]
        if not bad_bars.empty:
            reasons.append(f"봉 데이터 논리 오류 {len(bad_bars)}건")

    now = dt.datetime.now()
    last_updated = last_updated.replace(tzinfo=None)
    if max_staleness_minutes is not None:
        age_minutes = (now - last_updated).total_seconds() / 60
        is_stale = age_minutes > max_staleness_minutes
        if is_stale:
            reasons.append(f"조회 지연: 마지막 갱신 {age_minutes:.0f}분 전 (허용 {max_staleness_minutes}분)")
    else:
        age_days = (now.date() - last_updated.date()).days
        is_stale = age_days > max_staleness_days
        if is_stale:
            reasons.append(f"조회 지연: 마지막 봉이 {age_days}일 전 (허용 {max_staleness_days}일)")

    return ValidationResult(ok=(len(reasons) == 0), is_stale=is_stale, reasons=reasons)
