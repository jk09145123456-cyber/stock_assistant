"""16장 화면 구성 - Streamlit 대시보드.

실행: .venv/Scripts/python -m streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.decision.engine import Decision
from app.fundamentals import get_fundamentals
from app.indicators.core import ema
from app.journal import append_entry, load_entries
from app.market_data.providers import get_ohlcv
from app.news.fetcher import get_recent_news
from app.opinion import get_symbol_opinion, load_opinion
from app.pipeline import analyze_portfolio
from app.portfolio.models import load_portfolio

st.set_page_config(page_title="주식 보조 시스템", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: rgba(128,128,128,0.06);
        border-radius: 10px;
        padding: 12px 14px 6px 14px;
    }
    div[data-testid="stMetricLabel"] { font-size: 0.85rem; opacity: 0.75; }
    h4 { margin-bottom: 0.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=900, show_spinner="시세 조회 및 분석 중...")
def _run_analysis(_settings):
    return analyze_portfolio(_settings)


def main() -> None:
    st.title("📊 보유·관심 종목 분석 대시보드")
    st.caption("🔒 이 화면은 매수/매도를 실행하지 않습니다. 실제 주문은 증권사 앱에서 직접 하세요.")

    settings = get_settings()
    portfolio = load_portfolio(settings.portfolio)

    if st.button("새로고침 (시세·뉴스 다시 조회 + AI 의견 갱신)"):
        _run_analysis.clear()
        outcomes = _run_analysis(settings)
        refresh_ai_opinion(portfolio, {o.symbol: o for o in outcomes})

    outcomes = _run_analysis(settings)
    outcome_by_symbol = {o.symbol: o for o in outcomes}
    opinion = load_opinion()

    render_summary(portfolio, outcomes)
    st.divider()
    render_position_table(portfolio, outcome_by_symbol, opinion)
    st.divider()
    render_detail(portfolio, outcome_by_symbol, opinion, settings)
    st.divider()
    render_journal(outcome_by_symbol)
    st.divider()
    render_final_summary(portfolio, outcome_by_symbol, opinion)


def refresh_ai_opinion(portfolio, outcome_by_symbol: dict) -> None:
    """새로고침 버튼 - 제미나이로 보유종목 뉴스+수치 해석을 다시 생성해 data/ai_opinion.yaml 갱신."""
    positions_data = []
    for p in portfolio.positions:
        o = outcome_by_symbol.get(p.symbol)
        if not o or not o.current_price:
            continue
        positions_data.append({
            "symbol": p.symbol, "name": p.name, "current_price": o.current_price,
            "avg_price": p.avg_price, "return_pct": p.unrealized_return(o.current_price) * 100,
            "decision": o.decision.decision.value, "score": o.decision.score,
            "key_levels": o.decision.key_levels, "sector": p.sector,
            "counter_reasons": o.decision.counter_reasons,
        })
    if not positions_data:
        return

    price_lookup = {sym: o.current_price for sym, o in outcome_by_symbol.items() if o.current_price}
    cash_ratio = portfolio.cash_ratio(price_lookup)

    macro = None
    try:
        from app.market_data.fx import get_usd_krw_rate
        from app.market_data.providers import get_index_ohlcv
        from app.regime.classify import classify_regime
        from app.config import get_settings as _get_settings

        _settings = _get_settings()
        kospi = classify_regime(get_index_ohlcv("KOSPI", 300), _settings.risk, _settings.strategy)
        kosdaq = classify_regime(get_index_ohlcv("KOSDAQ", 300), _settings.risk, _settings.strategy)
        macro = {
            "regime_summary": f"코스피 {kospi.regime.value} / 코스닥 {kosdaq.regime.value}",
            "usd_krw": get_usd_krw_rate(),
        }
    except Exception:
        pass  # 거시 데이터는 있으면 좋은 것 - 실패해도 종목 분석 자체는 진행

    with st.spinner("Gemini로 뉴스 해석 + 의견 갱신 중..."):
        try:
            from app.llm.gemini_opinion import generate_opinion, save_opinion

            parsed = generate_opinion(positions_data, cash_ratio, macro)
            save_opinion(parsed, load_opinion())
            st.success("AI 의견을 갱신했습니다.")
        except Exception as e:
            st.warning(f"AI 의견 갱신 실패 (기존 의견 유지): {e}")


def render_summary(portfolio, outcomes) -> None:
    st.subheader("🗓️ 오늘의 요약")

    price_lookup = {o.symbol: o.current_price for o in outcomes if o.current_price}
    total_position_value = portfolio.total_position_value(price_lookup)
    total_assets = portfolio.total_assets(price_lookup)
    cash_ratio = portfolio.cash_ratio(price_lookup)

    total_cost = sum(p.cost_basis for p in portfolio.positions)
    total_pnl_pct = (total_position_value / total_cost - 1) * 100 if total_cost else 0.0

    warn_count = sum(
        1 for o in outcomes
        if o.decision.decision in (Decision.PARTIAL_SELL_REVIEW, Decision.FULL_SELL_REVIEW, Decision.ADD_BUY_FORBIDDEN)
    )
    add_buy_candidates = sum(1 for o in outcomes if o.decision.decision == Decision.ADD_BUY_REVIEW)
    take_profit_candidates = sum(
        1 for o in outcomes if o.decision.decision == Decision.PARTIAL_SELL_REVIEW and o.decision.sell_fraction
    )

    with st.container(border=True):
        cols = st.columns(6)
        cols[0].metric("💰 보유 평가액", f"{total_position_value:,.0f}")
        cols[1].metric("📈 보유 손익률", f"{total_pnl_pct:+.1f}%")
        cols[2].metric("💵 현금 비중", f"{cash_ratio:.1%}")
        cols[3].metric("🚨 위험 경고", f"{warn_count}건")
        cols[4].metric("🟢 추가매수 후보", f"{add_buy_candidates}건")
        cols[5].metric("🎯 익절 검토", f"{take_profit_candidates}건")
        st.caption(f"총자산(현금+평가액) 기준: {total_assets:,.0f} {portfolio.account_currency}")


DECISION_COLOR = {
    Decision.HALTED: "⚪",
    Decision.WATCH: "🔵",
    Decision.HOLD: "🟢",
    Decision.PARTIAL_SELL_REVIEW: "🟠",
    Decision.FULL_SELL_REVIEW: "🔴",
    Decision.ADD_BUY_REVIEW: "🟢",
    Decision.ADD_BUY_FORBIDDEN: "🟠",
}

# 배지 배경/글자색 - 라이트/다크 테마 둘 다에서 읽히도록 반투명 배경 + 진한 글자색 사용
BADGE_HEX = {
    "red": ("#e74c3c", "rgba(231,76,60,0.15)"),
    "orange": ("#e67e22", "rgba(230,126,34,0.15)"),
    "green": ("#27ae60", "rgba(39,174,96,0.15)"),
    "blue": ("#2980b9", "rgba(41,128,185,0.15)"),
    "gray": ("#7f8c8d", "rgba(127,140,141,0.15)"),
}


def _badge_span(text: str, color: str) -> str:
    fg, bg = BADGE_HEX.get(color, BADGE_HEX["gray"])
    return (
        f"<span style='background:{bg};color:{fg};border:1px solid {fg}55;"
        f"border-radius:6px;padding:2px 8px;font-size:0.85rem;font-weight:600;white-space:nowrap;'>{text}</span>"
    )


def _score_bar(value: int, color: str) -> str:
    fg, _ = BADGE_HEX.get(color, BADGE_HEX["gray"])
    return (
        f"<div style='display:flex;align-items:center;gap:6px;'>"
        f"<div style='flex:1;background:rgba(128,128,128,0.15);border-radius:4px;height:8px;'>"
        f"<div style='width:{max(0, min(100, value))}%;background:{fg};height:8px;border-radius:4px;'></div></div>"
        f"<span style='font-size:0.85rem;min-width:2em;text-align:right;'>{value}</span></div>"
    )


def _addbuy_badge(o) -> str:
    if o.decision.decision == Decision.ADD_BUY_REVIEW:
        return _badge_span("가능", "green")
    blocked_reason = next(
        (r for r in o.decision.reasons if any(k in r for k in ("현금", "추가매수", "급락"))), None
    )
    label = "불가" + (f" ({blocked_reason[:14]}…)" if blocked_reason else "")
    return _badge_span(label, "gray")


def render_position_table(portfolio, outcome_by_symbol: dict, opinion: dict | None) -> None:
    st.subheader("📋 종목 목록")
    all_rows = [(p, False) for p in portfolio.positions] + [(w, True) for w in portfolio.watchlist]
    if not all_rows:
        st.info("표시할 종목이 없습니다. config/portfolio.yaml을 확인하세요.")
        return

    header = ["종목", "수익률", "종합점수", "판단(시스템)", "AI 의견", "추가매수"]
    html = [
        "<div style='overflow-x:auto;border:1px solid rgba(128,128,128,0.25);border-radius:10px;'>",
        "<table style='width:100%;border-collapse:collapse;font-size:0.92rem;'>",
        "<thead><tr>" + "".join(
            f"<th style='text-align:left;padding:10px 12px;background:rgba(128,128,128,0.10);"
            f"border-bottom:2px solid rgba(128,128,128,0.25);'>{h}</th>" for h in header
        ) + "</tr></thead><tbody>",
    ]

    for i, (item, is_watch) in enumerate(all_rows):
        o = outcome_by_symbol.get(item.symbol)
        if not o:
            continue
        row_bg = "rgba(128,128,128,0.04)" if i % 2 else "transparent"
        ret_txt = "-"
        if not is_watch and o.current_price:
            ret = item.unrealized_return(o.current_price)
            ret_txt = f"{ret:+.1%}"
        sym_op = get_symbol_opinion(opinion, item.symbol)
        name_txt = f"{item.name}({item.symbol})" + (" <span style='opacity:0.55;'>[관심]</span>" if is_watch else "")

        decision_badge = _badge_span(o.decision.decision.value, BADGE_COLOR.get(o.decision.decision, "gray"))
        if sym_op:
            outlook_short = sym_op["outlook"].split(" - ")[0].split(":")[0][:10]
            outlook_color = "green" if "긍정" in sym_op["outlook"] else "red" if "부정" in sym_op["outlook"] else "orange"
            ai_badge = _badge_span(outlook_short, outlook_color) + (
                f" <span style='opacity:0.6;font-size:0.8rem;'>· {sym_op.get('attractiveness', '')}</span>" if not is_watch else ""
            )
        else:
            ai_badge = "<span style='opacity:0.4;'>-</span>"

        ret_color = "#e74c3c" if ret_txt.startswith("+") else "#2980b9" if ret_txt.startswith("-") else "inherit"
        ret_cell = f"<span style='color:{ret_color};font-weight:600;'>{ret_txt}</span>" if ret_txt != "-" else "-"

        cells = [
            name_txt,
            ret_cell,
            _score_bar(o.decision.score, BADGE_COLOR.get(o.decision.decision, "gray")),
            decision_badge,
            ai_badge,
            _addbuy_badge(o) if not is_watch else "-",
        ]
        html.append(
            f"<tr style='background:{row_bg};'>" +
            "".join(f"<td style='padding:9px 12px;border-bottom:1px solid rgba(128,128,128,0.12);vertical-align:middle;'>{c}</td>" for c in cells) +
            "</tr>"
        )

    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.caption("**판단(시스템)** = 규칙 기반 기계적 신호 · **AI 의견** = 뉴스·재무까지 종합한 참고 의견 · **추가매수** = 지금 추가매수 검토 조건을 충족하는지")
    if opinion:
        st.caption(f"🕐 AI 의견 마지막 작성: {opinion.get('generated_at', '?')}")


def render_detail(portfolio, outcome_by_symbol: dict, opinion: dict | None, settings) -> None:
    st.subheader("🔍 종목 상세")
    all_items = [(p.symbol, f"{p.name}({p.symbol})", p.market, p.purpose) for p in portfolio.positions] + \
                [(w.symbol, f"{w.name}({w.symbol}) [관심]", w.market, w.purpose) for w in portfolio.watchlist]
    if not all_items:
        return
    symbol_map = {s: label for s, label, _, _ in all_items}
    meta_map = {s: (market, purpose) for s, _, market, purpose in all_items}
    position_map = {p.symbol: p for p in portfolio.positions}
    selected = st.selectbox("종목 선택", options=list(symbol_map.keys()), format_func=lambda s: symbol_map[s])

    o = outcome_by_symbol.get(selected)
    if not o:
        st.warning("분석 결과가 없습니다.")
        return

    render_verdict_card(symbol_map[selected], selected, o, opinion, position_map.get(selected), settings.risk)

    market, purpose = meta_map[selected]
    render_chart(selected, market, purpose, settings, o)
    render_scenario(o)
    render_fundamentals(selected, market)
    render_ai_opinion(selected, opinion)
    render_news(symbol_map[selected].split("(")[0].strip())


BADGE_COLOR = {
    Decision.HALTED: "gray",
    Decision.WATCH: "blue",
    Decision.HOLD: "green",
    Decision.PARTIAL_SELL_REVIEW: "orange",
    Decision.FULL_SELL_REVIEW: "red",
    Decision.ADD_BUY_REVIEW: "green",
    Decision.ADD_BUY_FORBIDDEN: "orange",
}


def _find_level(levels: dict, *keywords: str):
    for k, v in levels.items():
        if any(kw in k for kw in keywords):
            return k, v
    return None, None


def render_action_thresholds(o, position=None, risk_cfg=None) -> None:
    """"얼마 밑이면 판다 / 얼마 위면 됐다"를 스캔 안 해도 바로 보이게 큰 숫자로 뽑는다."""
    levels = o.decision.key_levels
    if not levels or not o.current_price:
        return
    stop_label, stop_price = _find_level(levels, "손절")
    recover_label, recover_price = _find_level(levels, "추세반전", "확인가")

    stop_is_fixed = bool(stop_label and "직접 설정" in stop_label)
    stop_is_dynamic = bool(stop_label and "자동계산" in stop_label)
    target_is_fixed = bool(recover_label and "직접 설정" in recover_label)

    take_profit_price = None
    take_profit_fraction = None
    if not target_is_fixed and position and risk_cfg and risk_cfg.get("take_profit_tiers"):
        first_tier = sorted(risk_cfg["take_profit_tiers"], key=lambda t: t["gain"])[0]
        take_profit_price = position.avg_price * (1 + first_tier["gain"])
        take_profit_fraction = first_tier["sell_fraction"]

    st.markdown("##### 🚦 매매 기준선 (한눈에 보기)")
    cols = st.columns(4 if take_profit_price else 3)
    tc1, tc2, tc3 = cols[0], cols[1], cols[2]
    with tc1:
        if stop_price:
            pct = (stop_price / o.current_price - 1) * 100
            if stop_is_fixed:
                stop_caption = "🔴 이 밑이면 즉시 손절 (직접 설정)"
            elif stop_is_dynamic:
                stop_caption = "🔴 이 밑이면 즉시 손절 (자동계산·매번 갱신)"
            else:
                stop_caption = "🔴 이 밑으로 가면 매도 강도↑ (참고)"
            st.markdown(
                f"<div style='background:rgba(231,76,60,0.10);border-radius:10px;padding:10px 14px;height:100%;'>"
                f"<span style='color:#e74c3c;font-weight:600;'>{stop_caption}</span><br>"
                f"<span style='font-size:1.6rem;font-weight:700;'>{stop_price:,.0f}</span>"
                f"<span style='opacity:0.6;'> ({pct:+.1f}%)</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("손절 기준가 정보 없음")
    with tc2:
        if recover_price:
            pct = (recover_price / o.current_price - 1) * 100
            recover_caption = "🟢 이 위면 목표가 도달 (직접 설정)" if target_is_fixed else "🟢 이 위로 회복하면 추세 반전 신호 (참고)"
            st.markdown(
                f"<div style='background:rgba(39,174,96,0.10);border-radius:10px;padding:10px 14px;height:100%;'>"
                f"<span style='color:#27ae60;font-weight:600;'>{recover_caption}</span><br>"
                f"<span style='font-size:1.6rem;font-weight:700;'>{recover_price:,.0f}</span>"
                f"<span style='opacity:0.6;'> ({pct:+.1f}%)</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("회복 확인가 정보 없음")
    with tc3:
        render_addbuy_box(o)
    if take_profit_price:
        with cols[3]:
            pct = (take_profit_price / o.current_price - 1) * 100
            st.markdown(
                f"<div style='background:rgba(41,128,185,0.10);border-radius:10px;padding:10px 14px;height:100%;'>"
                f"<span style='color:#2980b9;font-weight:600;'>🎯 이 위로 오르면 익절 검토({take_profit_fraction:.0%})</span><br>"
                f"<span style='font-size:1.6rem;font-weight:700;'>{take_profit_price:,.0f}</span>"
                f"<span style='opacity:0.6;'> ({pct:+.1f}%)</span></div>",
                unsafe_allow_html=True,
            )
    notes = []
    if stop_is_fixed or target_is_fixed:
        notes.append("'(직접 설정)'은 config/portfolio.yaml에 못박아둔 고정값 - 재계산되지 않습니다.")
    if stop_is_dynamic:
        notes.append("'(자동계산)'은 전고점 대비 낙폭 기준으로 매번 다시 계산됩니다 - 전고점이 갱신되면 이 값도 같이 움직입니다.")
    if not notes:
        notes.append("이 값들은 매일 조금씩 바뀌는 근사치(이평선/최근저점 재계산)입니다. 절대적인 확정선이 아닙니다.")
    st.caption("⚠️ " + " ".join(notes))


def render_addbuy_box(o) -> None:
    """추가매수(7장) 조건 충족 여부 - 시나리오 콜아웃 3번째 칸으로 항상 눈에 띄게."""
    if o.decision.decision == Decision.ADD_BUY_REVIEW:
        st.markdown(
            "<div style='background:rgba(39,174,96,0.10);border-radius:10px;padding:10px 14px;height:100%;'>"
            "<span style='color:#27ae60;font-weight:600;'>🔵 추가매수 조건 충족</span><br>"
            "<span style='font-size:1.1rem;font-weight:700;'>지금 검토 가능</span></div>",
            unsafe_allow_html=True,
        )
        return

    blocked_reason = next(
        (r for r in o.decision.reasons if any(k in r for k in ("현금", "추가매수", "급락", "한도"))), None
    )
    reason_txt = blocked_reason or "전략 신호(매수 합의) 미충족"
    st.markdown(
        f"<div style='background:rgba(127,140,141,0.10);border-radius:10px;padding:10px 14px;height:100%;'>"
        f"<span style='color:#7f8c8d;font-weight:600;'>🔵 추가매수 지금 불가</span><br>"
        f"<span style='font-size:0.95rem;'>{reason_txt}</span></div>",
        unsafe_allow_html=True,
    )


def render_verdict_card(label: str, symbol: str, o, opinion: dict | None, position=None, risk_cfg=None) -> None:
    """시스템의 기계적 판단과 AI의 종합 의견을 한 카드에 나란히 보여준다 -
    둘이 다를 수 있다는 걸 스크롤 안 해도 바로 알 수 있게 하기 위함."""
    sym_op = get_symbol_opinion(opinion, symbol)

    with st.container(border=True):
        top1, top2, top3 = st.columns([2, 1.3, 1])
        with top1:
            st.markdown(f"#### {label}")
            if o.current_price:
                st.caption(f"현재가 {o.current_price:,.0f}")
        with top2:
            st.caption("판단(시스템 규칙)")
            st.badge(o.decision.decision.value, color=BADGE_COLOR.get(o.decision.decision, "gray"))
        with top3:
            st.caption("종합점수 / 신뢰도")
            st.markdown(f"**{o.decision.score}**/100 · {o.decision.confidence}%")

        render_action_thresholds(o, position, risk_cfg)

        if sym_op:
            st.divider()
            oc1, oc2 = st.columns([1, 4])
            with oc1:
                st.caption("AI 의견(참고)")
                outlook_color = "green" if "긍정" in sym_op["outlook"] else "red" if "부정" in sym_op["outlook"] else "orange"
                st.badge(sym_op["outlook"].split(" - ")[0].split(":")[0][:12], color=outlook_color)
            with oc2:
                st.caption(f"매력도: {sym_op.get('attractiveness', '-')}")
                st.write(sym_op["summary"].strip())

        if o.decision.sell_fraction:
            st.info(f"권장 매도 비중: {o.decision.sell_fraction:.0%}")
        if o.alert:
            st.warning(f"⚠️ 상태 변경: {o.alert.splitlines()[2] if len(o.alert.splitlines()) > 2 else ''}")
        if not o.data_ok:
            st.error("데이터 품질 경고:\n" + "\n".join(o.data_reasons))

        rc1, rc2 = st.columns(2)
        with rc1:
            st.markdown("**🔻 근거 (시스템)**")
            for r in o.decision.reasons:
                st.markdown(f"- {r}")
        with rc2:
            st.markdown("**⚖️ 반대 근거**")
            if o.decision.counter_reasons:
                for r in o.decision.counter_reasons:
                    st.markdown(f"- {r}")
            else:
                st.caption("해당 없음")

        if o.decision.release_conditions:
            st.markdown("**🔓 해제 조건**")
            for r in o.decision.release_conditions:
                st.markdown(f"- {r}")


def render_chart(symbol: str, market: str, purpose: str, settings, o) -> None:
    try:
        ema_periods = settings.strategy["ema_sets"].get(purpose, settings.strategy["ema_sets"][settings.strategy["default_purpose"]])
        df = get_ohlcv(symbol, market, lookback_days=250)
    except Exception as e:
        st.caption(f"차트를 불러오지 못했습니다: {e}")
        return
    if df.empty:
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="가격", increasing_line_color="#e74c3c", decreasing_line_color="#3498db",
    ))
    colors = ["#f39c12", "#8e44ad", "#16a085"]
    for period, color in zip(sorted(ema_periods)[:3], colors):
        fig.add_trace(go.Scatter(
            x=df.index, y=ema(df["close"], period), mode="lines",
            name=f"EMA{period}", line=dict(width=1.5, color=color),
        ))

    for label, price in o.decision.key_levels.items():
        if label == "현재가":
            continue
        fig.add_hline(
            y=price, line_dash="dot", line_color="gray", opacity=0.6,
            annotation_text=label, annotation_position="right",
        )

    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        template="plotly_white",
    )
    st.plotly_chart(fig, width="stretch")


def render_fundamentals(symbol: str, market: str) -> None:
    try:
        fund = get_fundamentals(symbol, market)
    except Exception:
        fund = None
    if not fund:
        return
    st.markdown("**💼 재무 지표** (참고용 - 국내 종목은 뉴스와 다를 수 있음)")
    cols = st.columns(4)
    cols[0].metric("Forward PER", f"{fund.forward_pe:.1f}" if fund.forward_pe else "N/A")
    cols[1].metric("ROE", f"{fund.return_on_equity:+.1%}" if fund.return_on_equity is not None else "N/A")
    cols[2].metric("영업이익률", f"{fund.profit_margins:+.1%}" if fund.profit_margins is not None else "N/A")
    cols[3].metric("매출성장률", f"{fund.revenue_growth:+.1%}" if fund.revenue_growth is not None else "N/A")

