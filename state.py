"""ذاكرة الأخبار المرسلة سابقًا، حتى لا يتكرر الخبر نفسه في نشرات متتالية.

النافذة الزمنية تتوسع أحيانًا حتى 72 ساعة، فبدون هذه الذاكرة سيصلك خبر الأمس مرة أخرى.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from fetcher import canonical_url

STATE_PATH = Path("state") / "seen.json"
PROJECT_STATE_PATH = Path("state") / "seen-projects.json"


def load_seen_projects() -> dict[str, str]:
    try:
        raw = json.loads(PROJECT_STATE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_seen_projects(seen: dict[str, str]) -> None:
    PROJECT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_STATE_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def load_seen() -> dict[str, str]:
    """يرجع خريطة رابط موحّد -> تاريخ الإرسال. ملف مفقود أو تالف يعني ذاكرة فارغة."""
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("لا توجد ذاكرة سابقة، هذه أول تشغيلة.")
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"تعذّرت قراءة ذاكرة الأخبار ({exc})، سيُعاد بناؤها.")
        return {}

    if not isinstance(raw, dict):
        return {}
    print(f"الذاكرة تحتوي {len(raw)} خبرًا مرسلًا سابقًا")
    return raw


def remember(
    urls: list[str],
    seen: dict[str, str],
    now: datetime | None = None,
) -> dict[str, str]:
    """يضيف روابط الأخبار المرسلة للذاكرة ويحذف ما تجاوز مدة الاحتفاظ."""
    now = now or datetime.now(timezone.utc)
    updated = dict(seen)
    for url in urls:
        updated[canonical_url(url)] = now.isoformat()

    cutoff = now - timedelta(days=config.SEEN_RETENTION_DAYS)
    pruned = {}
    for url, stamp in updated.items():
        try:
            # الطوابع التالفة تُحذف بدل أن توقف التشغيل.
            if datetime.fromisoformat(stamp) >= cutoff:
                pruned[url] = stamp
        except (TypeError, ValueError):
            continue

    dropped = len(updated) - len(pruned)
    if dropped:
        print(f"حُذف {dropped} خبرًا تجاوز {config.SEEN_RETENTION_DAYS} يومًا من الذاكرة")
    return pruned


def save_seen(seen: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    print(f"حُفظت الذاكرة: {len(seen)} خبرًا في {STATE_PATH}")
