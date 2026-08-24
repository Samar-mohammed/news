"""اختيار أهم الأخبار وتلخيصها بالعربي عبر OpenAI.

العملية على مرحلتين: الأولى تختار الأهم من العناوين والمقتطفات فقط (رخيصة)،
والثانية تلخص المختار بعد جلب نصه الكامل. هذا يمنع إرسال نص كل الأخبار للنموذج.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from openai import OpenAI

import config
from fetcher import Article
from projects import Project

SELECT_PROMPT = """أنت محرر نشرة أخبار متخصص في الذكاء الاصطناعي، تكتب لقارئ عربي مهتم بالتقنية.

ستصلك قائمة أخبار خام من مصادر مختلفة، كل خبر له رقم id.

مهمتك اختيار كل الأخبار الجيدة والمرتبطة فعليًا بالذكاء الاصطناعي:
1. استبعد الأخبار المكررة التي تغطي نفس الحدث، واحتفظ بالنسخة الأوضح فقط.
2. استبعد المحتوى الترويجي والإعلانات وقوائم العروض والمقالات غير المرتبطة فعليًا بالذكاء الاصطناعي.
3. لا يوجد عدد مستهدف أو حد أدنى؛ أرجع كل ما يستحق الإرسال مهما كان العدد قليلًا.

معايير الأهمية: إطلاق نماذج أو منتجات كبيرة، نتائج بحثية مؤثرة، تحركات تنظيمية وقانونية، صفقات واستحواذات كبرى، ثم ما دون ذلك.

أرجع حقل ids فقط: مصفوفة أرقام id مرتبة من الأهم إلى الأقل أهمية، بدون تكرار، ومن الأرقام الموجودة في المدخلات حصرًا."""

SUMMARIZE_PROMPT = """أنت محرر نشرة أخبار متخصص في الذكاء الاصطناعي، تكتب لقارئ عربي مهتم بالتقنية.

ستصلك الأخبار المختارة لنشرة اليوم، ومع أغلبها نص المقال الكامل. اعتمد على النص الكامل في فهم الخبر، ولا تكتفِ بالعنوان.

لكل خبر:
- id: نفس الرقم الذي وصلك، بدون تغيير.
- title_en: العنوان الإنجليزي الأصلي حرفيًا كما وصلك، بدون أي تعديل أو ترجمة.
- summary_ar: جملتان اثنتان فقط بالعربية الفصحى المبسطة، ولا تتجاوزان 45 كلمة إجمالًا. هذا الحد إلزامي: إن زاد الملخص فاحذف التفاصيل الأقل أهمية حتى يلتزم به. الجملة الأولى تذكر ما حدث مع أهم رقم أو اسم ورد في النص، والثانية تشرح لماذا يهم.
  ابدأ مباشرة بالخبر نفسه. ممنوع منعًا تامًا أن تبدأ بوصف المقال مثل "مقال يتناول" أو "يتحدث المقال عن" أو "تقرير يستعرض". اكتب أسماء الشركات والمنتجات بالإنجليزية كما هي داخل النص العربي، ونوّع صياغة الجملة الثانية بدل تكرار "يهم هذا الخبر لأن" في كل مرة.

لا تذكر في الملخص معلومة غير موجودة في النص المرفق. إن كان النص الكامل غير متوفر لخبر ما، لخّص من العنوان والمقتطف دون تخمين تفاصيل.

أما حقل intro_ar فاكتب فيه جملة عربية واحدة من تأليفك تلخص أبرز ما في نشرة اليوم، مستندة إلى الأخبار التي وصلتك فعليًا، مثل: "أنثروبيك تطلق Opus 5، واختراق أمني يهز أوساط نماذج الذكاء المفتوحة." لا تنسخ هذا المثال ولا تصف الحقل نفسه.

أرجع كل الأخبار التي وصلتك، بنفس ترتيبها."""

SELECT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ids"],
    "properties": {"ids": {"type": "array", "items": {"type": "integer"}}},
}

SUMMARIZE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intro_ar", "items"],
    "properties": {
        "intro_ar": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title_en", "summary_ar"],
                "properties": {
                    "id": {"type": "integer"},
                    "title_en": {"type": "string"},
                    "summary_ar": {"type": "string"},
                },
            },
        },
    },
}


@dataclass
class DigestItem:
    title_en: str
    summary_ar: str
    url: str
    source: str


class SummarizationError(RuntimeError):
    pass


PROJECT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "summary_ar"],
        "properties": {"id": {"type": "integer"}, "summary_ar": {"type": "string"}},
    }}},
}


def summarize_projects(projects: list[Project]) -> list[DigestItem]:
    if not projects:
        return []
    blocks = [
        f"id: {i}\nname: {p.name}\nsource: {p.source}\nmetrics: {p.metrics}\ndescription: {p.description}"
        for i, p in enumerate(projects)
    ]
    prompt = """اشرح كل مشروع لقارئ عربي مهتم بالتقنية في جملتين قصيرتين لا تتجاوزان 45 كلمة: ماذا يفعل، ولماذا يستحق الانتباه أو لمن يفيد. اعتمد حصراً على البيانات المرفقة ولا تخمّن. اذكر الأرقام المهمة إن وجدت. أرجع كل العناصر بنفس الترتيب."""
    payload = _call_model(_client(), prompt, "\n\n---\n\n".join(blocks),
                          "weekly_projects", PROJECT_SCHEMA, 4000, "تلخيص المشاريع")
    summaries = {x.get("id"): x.get("summary_ar", "") for x in payload.get("items", [])}
    return [DigestItem(p.name, summaries.get(i, "") or p.description[:220], p.url,
                       f"{p.source} · {p.metrics}") for i, p in enumerate(projects)]


_TOKEN_TOTALS = {"input": 0, "output": 0, "total": 0, "seconds": 0.0}


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SummarizationError("المتغير OPENAI_API_KEY غير موجود")
    return OpenAI(api_key=api_key)


def _log_usage(usage, elapsed: float, label: str) -> None:
    if usage is None:
        print(f"  {label}: اكتمل في {elapsed:.1f} ثانية (لا توجد بيانات استهلاك)")
        return

    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = (
        getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    )

    _TOKEN_TOTALS["input"] += usage.input_tokens
    _TOKEN_TOTALS["output"] += usage.output_tokens
    _TOKEN_TOTALS["total"] += usage.total_tokens
    _TOKEN_TOTALS["seconds"] += elapsed

    print(
        f"  {label}: {usage.input_tokens} إدخال (منها {cached} مخزّن) + "
        f"{usage.output_tokens} إخراج (منها {reasoning} تفكير) في {elapsed:.1f} ثانية"
    )


def log_token_total() -> None:
    """يطبع مجموع التوكنات عبر مرحلتي الاختيار والتلخيص."""
    if not _TOKEN_TOTALS["total"]:
        return
    print(f"--- توكنات {config.OPENAI_MODEL} ---")
    print(f"  الإدخال:  {_TOKEN_TOTALS['input']:>6}")
    print(f"  الإخراج:  {_TOKEN_TOTALS['output']:>6}")
    print(
        f"  الإجمالي: {_TOKEN_TOTALS['total']:>6} توكن "
        f"في {_TOKEN_TOTALS['seconds']:.1f} ثانية"
    )
    print("-" * 26)


def _call_model(
    client: OpenAI,
    system: str,
    user: str,
    schema_name: str,
    schema: dict,
    max_output_tokens: int,
    label: str,
    reasoning_effort: str = "low",
) -> dict:
    started = time.monotonic()
    try:
        response = client.responses.create(
            model=config.OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
            reasoning={"effort": reasoning_effort},
            max_output_tokens=max_output_tokens,
        )
    except Exception as exc:
        raise SummarizationError(f"فشل استدعاء OpenAI ({label}): {exc}") from exc
    elapsed = time.monotonic() - started

    if getattr(response, "status", None) == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", "غير معروف")
        raise SummarizationError(f"رد النموذج غير مكتمل في {label} ({reason})")

    raw = (response.output_text or "").strip()
    if not raw:
        raise SummarizationError(f"النموذج أرجع ردًا فارغًا في {label}")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SummarizationError(f"رد النموذج ليس JSON صالحًا في {label}: {exc}") from exc

    _log_usage(getattr(response, "usage", None), elapsed, label)
    return payload


def select_top(articles: list[Article]) -> list[Article]:
    """المرحلة الأولى: اختيار أهم الأخبار من العناوين والمقتطفات."""
    blocks = [
        f"id: {index}\nsource: {a.source}\ntitle: {a.title}\n"
        f"summary: {a.summary[: config.MAX_SUMMARY_CHARS]}"
        for index, a in enumerate(articles)
    ]
    print(f"المرحلة 1: اختيار الأهم من {len(articles)} خبر...")

    payload = _call_model(
        _client(),
        SELECT_PROMPT,
        "\n\n---\n\n".join(blocks),
        "ai_news_selection",
        SELECT_SCHEMA,
        2000,
        "الاختيار",
        "minimal",
    )

    selected: list[Article] = []
    used: set[int] = set()
    for index in payload.get("ids", []):
        if isinstance(index, int) and 0 <= index < len(articles) and index not in used:
            used.add(index)
            selected.append(articles[index])

    if not selected:
        raise SummarizationError("النموذج لم يختر أي خبر صالح")
    print(f"اختير {len(selected)} خبر")
    return selected


def summarize_selected(
    articles: list[Article], full_texts: dict[str, str]
) -> tuple[str, list[DigestItem]]:
    """المرحلة الثانية: تلخيص الأخبار المختارة بالاعتماد على نصها الكامل."""
    blocks = []
    for index, article in enumerate(articles):
        body = full_texts.get(article.url)
        block = f"id: {index}\nsource: {article.source}\ntitle: {article.title}"
        if body:
            block += f"\nfull_text:\n{body}"
        else:
            block += f"\nsummary: {article.summary[: config.MAX_SUMMARY_CHARS]}"
        blocks.append(block)

    print(f"المرحلة 2: تلخيص {len(articles)} خبر بالعربي...")
    payload = _call_model(
        _client(),
        SUMMARIZE_PROMPT,
        "\n\n---\n\n".join(blocks),
        "ai_news_digest",
        SUMMARIZE_SCHEMA,
        6000,
        "التلخيص",
    )

    by_id = {}
    for entry in payload.get("items", []):
        index = entry.get("id")
        if isinstance(index, int) and 0 <= index < len(articles):
            by_id.setdefault(index, entry)

    items: list[DigestItem] = []
    for index, article in enumerate(articles):
        entry = by_id.get(index)
        if entry is None:
            continue
        # الرابط والمصدر يُؤخذان من الخبر الأصلي لا من رد النموذج، منعًا للتلفيق.
        items.append(
            DigestItem(
                title_en=(entry.get("title_en") or article.title).strip(),
                summary_ar=(entry.get("summary_ar") or "").strip(),
                url=article.url,
                source=article.source,
            )
        )

    if not items:
        raise SummarizationError("النموذج لم يرجع أي خبر صالح")
    return (payload.get("intro_ar") or "").strip(), items
