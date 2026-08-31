"""종목별 최신 뉴스 헤드라인 - 구글 뉴스 RSS (API 키 불필요, 무료).

LLM이 이 뉴스를 읽고 해석/요약하는 건 이 모듈의 역할이 아니다. 여기서는
헤드라인·링크·시각만 수집하며, 해석은 별도의 AI 의견 생성 모듈이 담당한다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import feedparser
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "news_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: dt.datetime | None


def get_recent_news(query: str, max_items: int = 5, max_cache_minutes: int = 60) -> list[NewsItem]:
    cache_path = CACHE_DIR / f"{query}.parquet"
    if cache_path.exists():
        age_minutes = (dt.datetime.now().timestamp() - cache_path.stat().st_mtime) / 60
        if age_minutes <= max_cache_minutes:
            df = pd.read_parquet(cache_path)
            return [
                NewsItem(r.title, r.link, r.source, r.published if pd.notna(r.published) else None)
                for r in df.itertuples()
            ]

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(url)

    items = []
    for entry in feed.entries[:max_items]:
        published = None
        if getattr(entry, "published_parsed", None):
            published = dt.datetime(*entry.published_parsed[:6])
        source = entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else ""
        items.append(NewsItem(title=entry.title, link=entry.link, source=source, published=published))

    df = pd.DataFrame([{"title": i.title, "link": i.link, "source": i.source, "published": i.published} for i in items])
    df.to_parquet(cache_path)
    return items
