"""워크포워드 백테스트 CLI.

사용법:
    .venv/Scripts/python run_backtest.py YOUR_SYMBOL KR
    .venv/Scripts/python run_backtest.py AAPL US
"""
from __future__ import annotations

import sys

from app.backtest.engine import run_walkforward
from app.backtest.report import build_report, signal_forward_returns
from app.config import get_settings

PERIOD_LABELS = {"development": "개발 구간", "validation": "검증 구간", "final": "최종 평가 구간"}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 3:
        print("사용법: python run_backtest.py <symbol> <KR|US>")
        sys.exit(1)

    symbol, market = sys.argv[1], sys.argv[2]
    settings = get_settings()

    print(f"{symbol} ({market}) 워크포워드 백테스트")
    print("=" * 60)

    results = run_walkforward(symbol, market, settings.backtest)
    for period_key, label in PERIOD_LABELS.items():
        res = results.get(period_key)
        if not res or res["error"]:
            print(f"\n=== {label} ===")
            print(f"실행 불가: {res['error'] if res else '결과 없음'}")
            continue
        report = build_report(label, res["stats"], res["trades"])
        print()
        print(report.as_text())
        fwd = signal_forward_returns(res["trades"], res["stats"]["_equity_curve"])
        print(f"신호 발생 후 평균 수익률: " + ", ".join(f"{h}일 {v:+.2f}%" for h, v in fwd.items()))


if __name__ == "__main__":
    main()
