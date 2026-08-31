"""제미나이로 보유종목 뉴스+수치를 해석해 data/ai_opinion.yaml을 갱신.

검색 자체는 app.news.fetcher(구글 뉴스 RSS, 무료)가 하고, 제미나이는 이미
가져온 뉴스 텍스트를 근거로 "해석"만 한다 (그라운딩 도구는 무료 티어에서
쿼터가 없어서 안 씀 - 2026-08-24 확인). 이렇게 하면 검색·해석 둘 다 무료.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app.fundamentals import get_fundamentals
from app.news.fetcher import get_recent_news

OPINION_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ai_opinion.yaml"

# Gemini Developer API의 구조화 출력은 딕셔너리(임의 키)를 지원하지 않아
# (additionalProperties 미지원) 종목별 객체 대신 배열 형태로 받는다.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "outlook": {"type": "string"},
                    "attractiveness": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["symbol", "outlook", "attractiveness", "summary"],
            },
        },
        "final_summary": {"type": "string"},
    },
    "required": ["positions", "final_summary"],
}

PROMPT_TEMPLATE = """\
당신은 개인 투자자를 위한 참고용 분석을 작성합니다. 절대 확정적 예측("반드시 오른다" 등)을
하지 말고, 근거(뉴스/수치)와 불확실성을 함께 제시하세요. 최종 매매 결정은 사용자 몫입니다.

아래는 거시 환경(시장 국면·환율), 보유 종목의 계산된 지표, 재무 지표, 시스템이 뽑은
"반대 근거"(현재 판단과 반대되는 신호), 종목별/업종별 최근 뉴스 헤드라인입니다.
반드시 "반대 근거"를 무시하지 말고 summary에서 왜 그럼에도 지금 판단이 유지되는지
또는 반대 근거가 실제로 무게 있는지 판단해서 언급하세요 (강세/약세 양쪽을 다 검토한 뒤
결론 내리는 방식). 재무 지표가 뉴스 논조와 어긋나면(예: 재무상 적자인데 뉴스는 사상최대
실적) 그 불일치도 언급하고 뉴스 쪽에 더 무게를 두세요(재무 API 데이터가 회계기준 차이로
부정확할 수 있음). 이 정보만 근거로 판단하세요.
각 종목마다 symbol(아래 헤더의 괄호 안 6자리 코드), outlook(긍정적/부정적/중립/혼조 중 하나 +
한 줄 이유), attractiveness(낮음/중간/높음), summary(3~4문장, 뉴스와 수치를 함께 언급)를
작성하고, 마지막에 전체 포트폴리오에 대한 final_summary(어떤 순서로 검토하면 좋을지, 현금
여력 고려)를 작성하세요.

{context}
"""


def _build_context(positions_data: list[dict], macro: dict | None = None, force_refresh: bool = False) -> str:
    news_cache_minutes = 0 if force_refresh else 60

    blocks = []
    if macro:
        blocks.append(
            "### 거시 환경\n"
            f"  - 시장 국면: {macro.get('regime_summary', '?')}\n"
            f"  - 원/달러 환율: {macro.get('usd_krw', 0):,.0f}원\n"
        )

    for p in positions_data:
        news_items = get_recent_news(f"{p['name']} 주가", max_items=4, max_cache_minutes=news_cache_minutes)
        news_text = "\n".join(f"  - ({n.published.strftime('%m/%d') if n.published else '?'}) {n.title}" for n in news_items) or "  (뉴스 없음)"

        sector_text = ""
        if p.get("sector"):
            sector_items = get_recent_news(f"{p['sector']} 업황 전망", max_items=3, max_cache_minutes=news_cache_minutes)
            sector_text = "\n".join(f"  - ({n.published.strftime('%m/%d') if n.published else '?'}) {n.title}" for n in sector_items)
            sector_text = f"{p['sector']} 업종 전반 뉴스:\n{sector_text}\n" if sector_text else ""

        fundamentals_text = ""
        try:
            fund = get_fundamentals(p["symbol"], "KR")
            if fund:
                fundamentals_text = f"재무 지표(참고용, 뉴스와 다를 수 있음): {fund.as_text()}\n"
        except Exception:
            pass

        counter_text = ""
        if p.get("counter_reasons"):
            counter_text = "반대 근거(시스템이 뽑은 것):\n" + "\n".join(f"  - {r}" for r in p["counter_reasons"]) + "\n"

        levels_text = "\n".join(f"  - {k}: {v:,.0f}" for k, v in p["key_levels"].items())
        blocks.append(
            f"### {p['name']}({p['symbol']})\n"
            f"현재가: {p['current_price']:,.0f} / 평단: {p['avg_price']:,.0f} / 수익률: {p['return_pct']:+.1f}%\n"
            f"시스템 판단: {p['decision']} / 종합점수: {p['score']}/100\n"
            f"참고 가격대:\n{levels_text}\n"
            f"{fundamentals_text}"
            f"{counter_text}"
            f"최근 종목 뉴스:\n{news_text}\n"
            f"{sector_text}"
        )
    return "\n".join(blocks)


def generate_opinion(
    positions_data: list[dict], cash_ratio: float, macro: dict | None = None, force_refresh: bool = True
) -> dict:
    """force_refresh가 참이면 뉴스 캐시를 사용하지 않고 최신 데이터를 조회한다."""
    load_dotenv()
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 .env에 없습니다.")

    context = _build_context(positions_data, macro, force_refresh)
    context += f"\n\n전체 현금 비율: {cash_ratio:.1%}\n"

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=PROMPT_TEMPLATE.format(context=context),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )
    raw = json.loads(resp.text)

    # 응답은 리스트 -> 우리 저장 포맷(심볼 키 딕셔너리)으로 변환.
    positions_by_symbol = {}
    for item in raw["positions"]:
        sym = item.pop("symbol")
        positions_by_symbol[sym] = item

    # 뉴스 링크는 LLM이 지어내지 않게 우리가 직접 붙인다.
    # (_build_context에서 이미 방금 fresh하게 받아 캐시에 써놨으므로 여기선 그 캐시를 그대로 씀)
    for p in positions_data:
        sym = p["symbol"]
        if sym in positions_by_symbol:
            news_items = get_recent_news(f"{p['name']} 주가", max_items=3, max_cache_minutes=60)
            positions_by_symbol[sym]["news_refs"] = [n.title for n in news_items]

    return {"positions": positions_by_symbol, "final_summary": raw["final_summary"]}


def save_opinion(parsed: dict, existing: dict | None = None) -> None:
    result = existing.copy() if existing else {}
    result["generated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M") + " (Gemini 자동 생성)"
    result["disclaimer"] = (
        "예측이 아니라 참고 의견입니다. 뉴스는 검색 시점 기준이고, 주가를 맞힌다는 보장은 없습니다. "
        "최종 매매 결정과 책임은 본인에게 있습니다."
    )
    result["positions"] = parsed["positions"]
    result["final_summary"] = parsed["final_summary"]
    # candidates(신규후보)는 자동 생성 대상이 아니므로 기존 값을 유지한다.
    OPINION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPINION_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False, width=100)
