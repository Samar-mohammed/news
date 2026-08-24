"""سحب أخبار الذكاء الاصطناعي من مصادر RSS وتنظيفها."""

from __future__ import annotations

import calendar
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser

import config

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

# معاملات التتبع في الروابط تختلف بين المصادر لنفس المقال، فنحذفها قبل المقارنة.
_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source")


@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str
    published: datetime

    def age_hours(self, now: datetime) -> float:
        return (now - self.published).total_seconds() / 3600


def _strip_html(raw: str) -> str:
    return _WHITESPACE_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def canonical_url(url: str) -> str:
    """صيغة موحّدة للرابط تُستخدم في إزالة المكرر وفي ذاكرة ما أُرسل سابقًا."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url.strip().lower()
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query)
        if not k.lower().startswith(_TRACKING_PARAMS)
    ]
    return urllib.parse.urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/"),
            urllib.parse.urlencode(query),
            "",
        )
    )


def _canonical_title(title: str) -> str:
    return _WHITESPACE_RE.sub(" ", _PUNCT_RE.sub(" ", title.lower())).strip()


def _entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return None


def download(url: str, timeout: int, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.HTTP_USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_one(source: str, url: str, cutoff: datetime) -> list[Article]:
    try:
        payload = download(
            url,
            config.FEED_TIMEOUT,
            "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"  تعذّر سحب {source}: {exc}")
        return []

    parsed = feedparser.parse(payload)
    articles: list[Article] = []
    for entry in parsed.entries:
        title = _strip_html(entry.get("title", ""))
        link = (entry.get("link") or "").strip()
        published = _entry_published(entry)
        if not title or not link or published is None or published < cutoff:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                source=source,
                summary=_strip_html(entry.get("summary") or entry.get("description") or ""),
                published=published,
            )
        )

    articles.sort(key=lambda a: a.published, reverse=True)
    print(f"  {source}: {len(articles)} خبر")
    return articles


def _deduplicate(articles: list[Article]) -> list[Article]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        url_key = canonical_url(article.url)
        title_key = _canonical_title(article.title)
        if url_key in seen_urls or (title_key and title_key in seen_titles):
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(article)
    return unique


def _cap_per_feed(articles: list[Article]) -> list[Article]:
    """يمنع مصدرًا نشيطًا من ابتلاع النشرة، مع الحفاظ على ترتيب الحداثة."""
    counts: dict[str, int] = {}
    kept: list[Article] = []
    for article in articles:
        count = counts.get(article.source, 0)
        if count >= config.MAX_ENTRIES_PER_FEED:
            continue
        counts[article.source] = count + 1
        kept.append(article)
    return kept


def fetch_articles(
    now: datetime | None = None,
    exclude: set[str] | None = None,
) -> tuple[list[Article], int]:
    """يرجع (الأخبار، عدد ساعات النافذة المستخدمة فعليًا)، بدون تكرار، الأحدث أولًا.

    exclude هي روابط موحّدة سبق إرسالها، وتُستبعد حتى لا تتكرر الأخبار.
    """
    now = now or datetime.now(timezone.utc)
    hard_cutoff = now - timedelta(hours=config.LOOKBACK_HOURS)

    print(f"سحب {len(config.FEEDS)} مصدر (آخر {config.LOOKBACK_HOURS} ساعة)...")
    with ThreadPoolExecutor(max_workers=len(config.FEEDS)) as pool:
        results = pool.map(
            lambda feed: _fetch_one(feed[0], feed[1], hard_cutoff), config.FEEDS
        )

    collected = [article for batch in results for article in batch]
    collected.sort(key=lambda a: a.published, reverse=True)
    unique = _deduplicate(collected)
    print(f"الإجمالي: {len(collected)} خبر، بعد إزالة المكرر: {len(unique)}")

    if exclude:
        before = len(unique)
        unique = [a for a in unique if canonical_url(a.url) not in exclude]
        if before != len(unique):
            print(f"استُبعد {before - len(unique)} خبرًا سبق إرساله في نشرة سابقة")

    window = config.LOOKBACK_HOURS
    selected = [a for a in unique if a.age_hours(now) <= window]
    selected = _cap_per_feed(selected)
    print(f"المختار: {len(selected)} خبر ضمن آخر {window} ساعة")
    return selected[: config.MAX_ENTRIES_TO_MODEL], window
