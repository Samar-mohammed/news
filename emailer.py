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

_FONT_STACK = "'Segoe UI', Tahoma, 'Noto Naskh Arabic', 'Dubai', Arial, sans-serif"

# محاذاة يمينية صريحة، لأن بعض عملاء البريد يتجاهلون سمة dir على <html>.
_RTL = "direction:rtl;text-align:right;"

# Gmail يتجاهل وسوم <style> في كثير من الحالات، لذا كل التنسيق سطري.
_BODY_STYLE = f"margin:0;padding:0;background-color:#eef1f6;font-family:{_FONT_STACK};{_RTL}"
_WARNING_STYLE = (
    "margin:0 0 16px 0;padding:14px 18px;background-color:#fff8df;"
    "border:1px solid #f2d47a;border-radius:12px;font-size:14px;line-height:1.8;"
    f"color:#75570a;{_RTL}"
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
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 14px 0;background-color:#ffffff;border:1px solid #e4e8f0;border-radius:16px;border-collapse:separate;">
        <tr><td style="padding:22px 22px 20px 22px;{_RTL}">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
            <td valign="middle" style="font-size:12px;color:#7a8496;{_RTL}"><span style="display:inline-block;padding:5px 10px;background-color:#f0f3ff;border-radius:999px;color:#465bd8;font-weight:700;">{_escape(item.source)}</span></td>
            <td width="42" valign="middle" align="left"><span style="display:inline-block;width:34px;height:34px;line-height:34px;background-color:#5b67e8;border-radius:10px;color:#ffffff;font-size:14px;font-weight:800;text-align:center;">{index:02d}</span></td>
          </tr></table>
          <h2 style="margin:16px 0 10px 0;font-size:18px;line-height:1.55;font-weight:750;direction:ltr;text-align:right;"><a href="{_escape(item.url)}" style="color:#17203a;text-decoration:none;">{_escape(item.title_en)}</a></h2>
          <p style="margin:0 0 17px 0;font-size:15px;line-height:1.95;color:#4d5668;{_RTL}">{_escape(item.summary_ar)}</p>
          <a href="{_escape(item.url)}" style="display:inline-block;padding:9px 15px;background-color:#eef0ff;border-radius:9px;color:#4655cc;font-size:13px;font-weight:700;text-decoration:none;">اقرأ الخبر&nbsp; ←</a>
        </td></tr>
      </table>"""


def render_html(
    items: list[DigestItem],
    intro: str = "",
    warning: str = "",
    github_items: list[DigestItem] | None = None,
    huggingface_items: list[DigestItem] | None = None,
    product_hunt_items: list[DigestItem] | None = None,
) -> str:
    cards = "".join(_render_card(i, item) for i, item in enumerate(items, start=1))

    item_count = len(items)
    github_items = github_items or []
    huggingface_items = huggingface_items or []
    product_hunt_items = product_hunt_items or []
    def section(title: str, section_items: list[DigestItem]) -> str:
        if not section_items:
            return ""
        section_cards = "".join(_render_card(i, item) for i, item in enumerate(section_items, 1))
        return f'<h2 style="margin:30px 4px 14px;color:#17203a;font-size:21px;{_RTL}">{_escape(title)}</h2>{section_cards}'
    project_sections = (section("أبرز 5 مشاريع GitHub هذا الأسبوع", github_items)
                        + section("أبرز 3 عناصر من Hugging Face هذا الأسبوع", huggingface_items)
                        + section("أبرز 5 منتجات AI من Product Hunt هذا الأسبوع", product_hunt_items))
    intro_block = (f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 18px 0;"><tr><td width="4" style="background-color:#6f78f2;border-radius:4px;"></td><td style="padding:2px 16px 2px 0;font-size:15px;line-height:1.95;color:#465064;{_RTL}">{_escape(intro)}</td></tr></table>""" if intro else "")

    warning_block = (
        f"""<p style="{_WARNING_STYLE}">⚠️&nbsp; {_escape(warning)}</p>"""
        if warning
        else ""
    )

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>نشرة أخبار الذكاء الاصطناعي</title>
  <style>
    /* يمنع Gmail على iOS من تحويل النص الأبيض إلى أسود في الوضع الداكن. */
    u + .email-body .gmail-blend-screen {{ background:#000;mix-blend-mode:screen; }}
    u + .email-body .gmail-blend-difference {{ background:#000;mix-blend-mode:difference; }}
  </style>
</head>
<body class="email-body" style="{_BODY_STYLE}">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">أهم {item_count} أخبار في الذكاء الاصطناعي، مختصرة لك بالعربية.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#eef1f6;"><tr><td align="center" style="padding:26px 12px;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:660px;">
      <tr><td style="padding:32px 28px 28px;background-color:#17203a;background-image:linear-gradient(135deg,#17203a 0%,#343b78 100%);border-radius:20px 20px 0 0;text-align:right;direction:rtl;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 18px 0;"><tr>
          <td align="right"><span style="display:inline-block;padding:6px 11px;background-color:#303a5c;border:1px solid #59617f;border-radius:999px;color:#dce1ff;font-size:11px;font-weight:700;letter-spacing:.5px;">AI DAILY BRIEF</span></td>
          <td align="left"><span style="display:inline-block;padding:6px 11px;background-color:#303a5c;border:1px solid #59617f;border-radius:999px;color:#dce1ff;font-size:11px;font-weight:700;letter-spacing:.5px;">{item_count} أخبار مختارة</span></td>
        </tr></table>
        <div class="gmail-blend-screen"><div class="gmail-blend-difference" style="color:#ffffff !important;">
          <h1 style="margin:0;color:#ffffff !important;font-size:27px;line-height:1.35;font-weight:800;" color="#ffffff"><font color="#ffffff" style="color:#ffffff !important;">جرعتك اليومية من أخبار الذكاء الاصطناعي</font></h1>
        </div></div>
      </td></tr>
      <tr><td style="padding:24px 22px 25px 22px;background-color:#f8f9fc;border:1px solid #e0e4ed;border-top:0;border-radius:0 0 20px 20px;">
        {warning_block}{intro_block}{cards}{project_sections}
        <p style="margin:14px 8px 0 8px;text-align:center;font-size:12px;line-height:1.8;color:#929aab;">صُنعت هذه النشرة لتختصر عليك زحام الأخبار.<br>التلخيص آلي؛ راجع المصدر الأصلي قبل اتخاذ أي قرار.</p>
      </td></tr>
    </table>
  </td></tr></table>
</body>
</html>"""


def render_text(items: list[DigestItem], intro: str = "", github_items: list[DigestItem] | None = None, huggingface_items: list[DigestItem] | None = None, product_hunt_items: list[DigestItem] | None = None) -> str:
    lines = ["نشرة أخبار الذكاء الاصطناعي", ""]
    if intro:
        lines += [intro, ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.title_en}")
        if item.summary_ar:
            lines.append(f"   {item.summary_ar}")
        lines += [f"   المصدر: {item.source}", f"   {item.url}", ""]
    for title, section_items in (("أبرز مشاريع GitHub هذا الأسبوع", github_items or []), ("أبرز عناصر Hugging Face هذا الأسبوع", huggingface_items or []), ("أبرز منتجات AI من Product Hunt هذا الأسبوع", product_hunt_items or [])):
        if section_items:
            lines += [title, ""]
            for index, item in enumerate(section_items, 1):
                lines += [f"{index}. {item.title_en}", f"   {item.summary_ar}", f"   {item.source}", f"   {item.url}", ""]
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
