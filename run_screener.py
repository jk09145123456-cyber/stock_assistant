"""신규 매수 후보 스크리닝 CLI + 보유종목 대비 비교표.

사용법:
    .venv/Scripts/python run_screener.py
"""
from __future__ import annotations

import sys

import yaml

from app.config import CONFIG_DIR, get_settings
from app.portfolio.models import load_portfolio
from app.screening.screener import scan_universe


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    portfolio = load_portfolio(settings.portfolio)

    universe_path = CONFIG_DIR / "screening_universe.yaml"
    if not universe_path.exists():
        raise FileNotFoundError(
            "config/screening_universe.example.yaml을 "
            "config/screening_universe.yaml로 복사한 뒤 분석할 종목을 입력하세요."
        )
    with open(universe_path, "r", encoding="utf-8") as f:
        universe_cfg = yaml.safe_load(f)
    universe = universe_cfg["tickers"]

    print(f"{len(universe)}개 종목 스캔 중 (KRX 개별 종목 조회라 시간이 좀 걸립니다)...")

    def progress(i, total, name):
        print(f"  [{i}/{total}] {name}", end="\r")

    results = scan_universe(universe, portfolio, settings, progress_callback=progress)
    print(" " * 40, end="\r")

    print("\n=== 보유 종목 (참고용) ===")
    price_lookup = {}
    for p in portfolio.positions:
        try:
            from app.market_data.providers import get_ohlcv
            price = float(get_ohlcv(p.symbol, p.market, lookback_days=5)["close"].iloc[-1])
        except Exception:
            price = p.avg_price
        price_lookup[p.symbol] = price
        ret = p.unrealized_return(price)
        print(f"  {p.name}({p.symbol}) 수익률 {ret:+.1%}")

    print("\n=== 신규 매수 후보 상위 15개 (점수순) ===")
    print(f"{'종목':16}{'현재가':>12}{'종합점수':>8}{'신뢰도':>8}  판단")
    print("-" * 60)
    for r in results[:15]:
        price_str = f"{r.current_price:,.0f}" if r.current_price else "-"
        print(f"{r.name+'('+r.symbol+')':16}{price_str:>12}{r.score:>8}{r.confidence:>8}  {r.decision.value}")

    buy_candidates = [r for r in results if r.decision.value == "추가매수 검토"]
    if buy_candidates:
        print(f"\n실제 '추가매수 검토'로 뜬 종목: {len(buy_candidates)}개")
        for r in buy_candidates:
            print(f"  - {r.name}({r.symbol}): {', '.join(r.reasons[:2])}")
    else:
        print("\n지금 기준으로 '추가매수 검토'까지 뜨는 종목은 없습니다 (전략 4개 중 3개 이상 동시에 매수 신호가 일치해야 함).")


if __name__ == "__main__":
    main()
