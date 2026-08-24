"""نقطة تشغيل نشرة أخبار الذكاء الاصطناعي اليومية.

الاستخدام:
    python main.py            إرسال النشرة بالإيميل
    python main.py --dry-run  حفظ preview.html محليًا بدون إرسال
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

import config
import emailer
import state
from extractor import fetch_full_texts
from fetcher import Article, fetch_articles
from summarizer import (
    DigestItem,
    SummarizationError,
    log_token_total,
    select_top,
    summarize_selected,
)

FALLBACK_WARNING = (
    "تعذّر التلخيص الآلي هذه المرة، لذا وصلتك العناوين الخام كما هي من المصادر."
)


def _fallback_items(articles: list[Article]) -> list[DigestItem]:
    """نشرة احتياطية بالعناوين الخام عند تعذّر التلخيص."""
    return [
        DigestItem(
            title_en=article.title,
            summary_ar=article.summary[:220],
            url=article.url,
            source=article.source,
        )
        for article in articles
    ]


def build_digest(articles: list[Article]) -> tuple[list[DigestItem], str, str]:
    """يرجع (الأخبار، الجملة الافتتاحية، تحذير إن وُجد)."""
    selected = articles
    try:
        selected = select_top(articles)
        full_texts = fetch_full_texts(selected)
        intro, items = summarize_selected(selected, full_texts)
        return items, intro, ""
    except SummarizationError as exc:
        print(f"تحذير: {exc}", file=sys.stderr)
        print("التحويل إلى النشرة الاحتياطية بالعناوين الخام...", file=sys.stderr)
        return _fallback_items(selected), "", FALLBACK_WARNING


def run(dry_run: bool = False) -> int:
    load_dotenv()

    local_now = datetime.now(timezone.utc) + timedelta(
        hours=config.DISPLAY_TIMEZONE_OFFSET_HOURS
    )
    date_label = emailer.format_date_label(local_now, config.DISPLAY_TIMEZONE_LABEL)

    seen = state.load_seen()
    articles, window_hours = fetch_articles(exclude=set(seen))
    if not articles:
        print("لا توجد أخبار جديدة لم تُرسل من قبل. لن يُرسل إيميل.")
        return 0

    items, intro, warning = build_digest(articles)
    log_token_total()

    coverage = f"تغطية آخر {window_hours} ساعة"
    html_body = emailer.render_html(items, date_label, intro, warning, coverage)
    text_body = emailer.render_text(items, date_label, intro)
    subject = f"نشرة الذكاء الاصطناعي - {local_now:%Y-%m-%d} ({len(items)} أخبار)"

    if dry_run:
        preview = Path("preview.html")
        preview.write_text(html_body, encoding="utf-8")
        print(f"وضع المعاينة: تم حفظ {preview.resolve()} بدون إرسال")
        print("لم تُحدَّث ذاكرة الأخبار، فالمعاينة لا تُحتسب إرسالًا.")
        return 0

    emailer.send_email(subject, html_body, text_body)

    # الذاكرة تُحدَّث بعد نجاح الإرسال فقط، وإلا ضاعت أخبار لم تصل أصلًا.
    state.save_seen(state.remember([item.url for item in items], seen))
    return 0


def _force_utf8_output() -> None:
    """وحدة تحكم Windows تستخدم cp1252 افتراضيًا، فتفشل طباعة العربية في السجل.

    line_buffering يمنع اختلاط ترتيب رسائل stdout مع stderr في سجل GitHub Actions.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def main() -> int:
    _force_utf8_output()

    parser = argparse.ArgumentParser(description="نشرة أخبار الذكاء الاصطناعي اليومية")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="حفظ النشرة في preview.html بدل إرسالها بالإيميل",
    )
    args = parser.parse_args()

    try:
        return run(dry_run=args.dry_run)
    except Exception as exc:
        print(f"فشل التشغيل: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
