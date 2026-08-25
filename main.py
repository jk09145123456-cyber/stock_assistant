"""CLI 진입점: 보유·관심 종목을 분석하고 판단/알림을 출력한다.

사용법:
    .venv/Scripts/python main.py
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.pipeline import analyze_portfolio


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    outcomes = analyze_portfolio(settings)

    print("=" * 60)
    print("오늘의 분석 결과")
    print("=" * 60)
    for outcome in outcomes:
        print()
        print(outcome.explanation)
        if outcome.alert:
            print()
            print(">>> 알림 <<<")
            print(outcome.alert)
        print("-" * 60)


if __name__ == "__main__":
    main()
