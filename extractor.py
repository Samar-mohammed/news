"""جلب نص المقال الكامل ليحصل النموذج على سياق أغنى من مقتطف RSS."""

from __future__ import annotations

import urllib.error
from concurrent.futures import ThreadPoolExecutor

import trafilatura

import config
from fetcher import Article, download


def _extract_one(article: Article) -> tuple[str, str | None]:
    try:
        payload = download(article.url, config.ARTICLE_TIMEOUT, "text/html,*/*;q=0.8")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"  تعذّر جلب نص المقال من {article.source}: {exc}")
        return article.url, None

    text = trafilatura.extract(
        payload,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )

    # نص قصير جدًا يعني عادةً جدار دفع أو صفحة تُبنى بجافاسكربت.
    if not text or len(text) < config.MIN_ARTICLE_CHARS:
        print(f"  نص غير كافٍ من {article.source}، سيُستخدم مقتطف RSS")
        return article.url, None

    return article.url, text[: config.MAX_ARTICLE_CHARS]


def fetch_full_texts(articles: list[Article]) -> dict[str, str]:
    """يرجع خريطة رابط -> نص المقال. الروابط الفاشلة لا تظهر في الخريطة."""
    if not articles:
        return {}

    print(f"جلب النص الكامل لـ {len(articles)} مقال...")
    workers = min(len(articles), config.ARTICLE_FETCH_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_extract_one, articles)

    texts = {url: text for url, text in results if text}
    print(f"نجح استخراج {len(texts)} من {len(articles)} مقال")
    return texts
