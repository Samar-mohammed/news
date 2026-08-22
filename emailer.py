"""بناء نشرة HTML عربية وإرسالها عبر Gmail SMTP."""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from summarizer import DigestItem

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

_FONT_STACK = (
    "'Segoe UI', Tahoma, 'Noto Naskh Arabic', 'Dubai', Arial, sans-serif"
)

# محاذاة يمينية صريحة، لأن بعض عملاء البريد يتجاهلون سمة dir على <html>.
_RTL = "direction:rtl;text-align:right;"

# Gmail يتجاهل وسوم <style> في كثير من الحالات، لذا كل التنسيق سطري.
_BODY_STYLE = (
    f"margin:0;padding:24px 12px;background:#f4f5f7;font-family:{_FONT_STACK};{_RTL}"
)
_CARD_BASE = (
    "background:#ffffff;border:1px solid #e4e6eb;border-radius:10px;"
    "padding:18px 20px;margin:0 0 14px 0;"
)
_CARD_STYLE = f"{_CARD_BASE}{_RTL}"
_HEADER_STYLE = f"{_CARD_BASE}direction:rtl;text-align:center;"
# العنوان إنجليزي فيبقى ترتيب كلماته ltr، لكن محاذاته يمين ليطابق حافة النص العربي.
_TITLE_STYLE = (
    "display:block;direction:ltr;text-align:right;font-size:16px;line-height:1.5;"
    "font-weight:600;color:#1a4fd6;text-decoration:none;margin:0 0 10px 0;"
)
_SUMMARY_STYLE = (
    f"margin:0 0 12px 0;font-size:15px;line-height:1.9;color:#2b2f36;{_RTL}"
)
_SOURCE_STYLE = f"margin:0;font-size:13px;color:#6b7280;{_RTL}"
_BADGE_STYLE = (
    "display:inline-block;min-width:22px;padding:1px 7px;margin:0 0 10px 0;"
    "background:#eef2ff;border-radius:999px;font-size:12px;font-weight:700;"
    "color:#1a4fd6;text-align:center;"
)
_WARNING_STYLE = (
    "background:#fff8e1;border:1px solid #f2d98c;border-radius:10px;"
    f"padding:14px 20px;margin:0 0 14px 0;font-size:14px;line-height:1.8;color:#7a5c00;{_RTL}"
)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_card(index: int, item: DigestItem) -> str:
    return f"""
      <div style="{_CARD_STYLE}">
        <span style="{_BADGE_STYLE}">{index}</span>
        <a href="{_escape(item.url)}" style="{_TITLE_STYLE}">{_escape(item.title_en)}</a>
        <p style="{_SUMMARY_STYLE}">{_escape(item.summary_ar)}</p>
        <p style="{_SOURCE_STYLE}">المصدر: {_escape(item.source)}</p>
      </div>"""


def render_html(
    items: list[DigestItem],
    date_label: str,
    intro: str = "",
    warning: str = "",
    coverage: str = "",
) -> str:
    cards = "".join(_render_card(i, item) for i, item in enumerate(items, start=1))

    intro_block = (
        f"""<p style="margin:0 4px 18px 4px;font-size:15px;line-height:1.9;color:#3c4149;{_RTL}">{_escape(intro)}</p>"""
        if intro
        else ""
    )

    warning_block = (
        f"""<p style="{_WARNING_STYLE}">{_escape(warning)}</p>"""
        if warning
        else ""
    )

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="{_BODY_STYLE}">
  <div style="max-width:640px;margin:0 auto;">
    <div style="{_HEADER_STYLE}">
      <h1 style="margin:0 0 6px 0;font-size:21px;color:#12141a;">نشرة أخبار الذكاء الاصطناعي</h1>
      <p style="margin:0;font-size:14px;color:#6b7280;">{_escape(date_label)}</p>
      {f'<p style="margin:4px 0 0 0;font-size:12px;color:#9099a6;">{_escape(coverage)}</p>' if coverage else ''}
    </div>
    {warning_block}
    {intro_block}
    {cards}
    <p style="margin:18px 0 0 0;text-align:center;font-size:12px;line-height:1.8;color:#9099a6;">
      نشرة آلية تُجمع يوميًا من مصادر تقنية مفتوحة وتُلخَّص آليًا.<br>
      راجع الرابط الأصلي قبل الاعتماد على أي خبر.
    </p>
  </div>
</body>
</html>"""


def render_text(items: list[DigestItem], date_label: str, intro: str = "") -> str:
    lines = [f"نشرة أخبار الذكاء الاصطناعي - {date_label}", ""]
    if intro:
        lines += [intro, ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.title_en}")
        if item.summary_ar:
            lines.append(f"   {item.summary_ar}")
        lines += [f"   المصدر: {item.source}", f"   {item.url}", ""]
    return "\n".join(lines)


def send_email(subject: str, html_body: str, text_body: str) -> None:
    sender = (os.environ.get("GMAIL_USER") or "").strip()
    # Google تعرض كلمة مرور التطبيق في أربع مجموعات مفصولة بمسافات، والمسافات ليست جزءًا منها.
    password = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    recipients_raw = (os.environ.get("MAIL_TO") or sender or "").strip()

    missing = [
        name
        for name, value in (
            ("GMAIL_USER", sender),
            ("GMAIL_APP_PASSWORD", password),
            ("MAIL_TO", recipients_raw),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"متغيرات البيئة الناقصة: {', '.join(missing)}")

    recipients = [addr.strip() for addr in recipients_raw.split(",") if addr.strip()]

    message = MIMEMultipart("alternative")
    message["Subject"] = str(Header(subject, "utf-8"))
    message["From"] = formataddr((str(Header("نشرة الذكاء الاصطناعي", "utf-8")), sender))
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"إرسال الإيميل إلى {', '.join(recipients)}...")
    with smtplib.SMTP_SSL(
        SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30
    ) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, message.as_string())
    print("تم الإرسال بنجاح")


def format_date_label(now: datetime, timezone_label: str) -> str:
    weekdays = [
        "الاثنين",
        "الثلاثاء",
        "الأربعاء",
        "الخميس",
        "الجمعة",
        "السبت",
        "الأحد",
    ]
    return f"{weekdays[now.weekday()]} {now:%Y-%m-%d} {timezone_label}"
