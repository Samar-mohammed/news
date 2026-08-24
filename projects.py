"""جلب أبرز مشاريع GitHub وعناصر Hugging Face للتقرير الأسبوعي."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import config


@dataclass
class Project:
    name: str
    url: str
    source: str
    description: str
    metrics: str
    memory_key: str = ""


_VARIANT_MARKERS = re.compile(
    r"(?:[-_.](?:gguf|mlx|fp8|fp16|bf16|awq|gptq|exl2|4bit|8bit|uncensored|abliterated|"
    r"obliterated|quantized|quant))(?:[-_.].*)?$",
    re.IGNORECASE,
)


def _model_family(item_id: str) -> str:
    """يرد اسم عائلة ثابتًا يجمع النسخة الأصلية ونسخ الضغط والتعديل."""
    model_name = item_id.rsplit("/", 1)[-1]
    previous = ""
    while previous != model_name:
        previous = model_name
        model_name = _VARIANT_MARKERS.sub("", model_name)
    return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")


def _variant_penalty(item_id: str) -> int:
    return 1 if _VARIANT_MARKERS.search(item_id.rsplit("/", 1)[-1]) else 0


def _get_json(url: str, token: str = ""):
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=config.PROJECT_API_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": config.HTTP_USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urlopen(request, timeout=config.PROJECT_API_TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", "GraphQL error"))
    return data


def fetch_github(exclude: set[str]) -> list[Project]:
    since = (datetime.now(timezone.utc) - timedelta(days=config.PROJECT_LOOKBACK_DAYS)).date()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GIT_TOKEN", "")
    repositories: dict[str, dict] = {}
    for topic in config.GITHUB_AI_TOPICS:
        url = "https://api.github.com/search/repositories?" + urlencode(
            {
                "q": f"created:>={since} topic:{topic}",
                "sort": "stars",
                "order": "desc",
                "per_page": 15,
            }
        )
        for item in _get_json(url, token).get("items", []):
            if item.get("html_url"):
                repositories[item["html_url"]] = item

    ranked = sorted(
        repositories.values(),
        key=lambda item: item.get("stargazers_count", 0),
        reverse=True,
    )
    projects = []
    for item in ranked:
        project_url = item.get("html_url", "")
        if not project_url or project_url in exclude:
            continue
        topics = ", ".join(item.get("topics") or [])
        description = item.get("description") or "لا يوجد وصف متاح."
        if topics:
            description += f"\nTopics: {topics}"
        projects.append(Project(
            name=item.get("full_name") or item.get("name", "GitHub project"),
            url=project_url,
            source="GitHub",
            description=description[:1200],
            metrics=f"★ {item.get('stargazers_count', 0):,} · Forks {item.get('forks_count', 0):,}",
        ))
        if len(projects) >= config.GITHUB_PROJECT_COUNT:
            break
    return projects


def fetch_huggingface(exclude: set[str]) -> list[Project]:
    # ترحيل تلقائي للذاكرة القديمة التي كانت تحفظ رابط النموذج دون مفتاح العائلة.
    excluded_families = set(exclude)
    for saved in exclude:
        parts = urlsplit(saved)
        path_parts = [part for part in parts.path.split("/") if part]
        if parts.netloc == "huggingface.co" and len(path_parts) == 2:
            excluded_families.add(f"hf-family:{_model_family(path_parts[-1])}")
    candidates: dict[str, list[tuple[int, int, Project]]] = {
        "model": [], "dataset": [], "space": []
    }
    token = os.environ.get("HF_TOKEN", "")
    for kind, path, label in (
        ("model", "models", "Model"),
        ("dataset", "datasets", "Dataset"),
        ("space", "spaces", "Space"),
    ):
        url = f"https://huggingface.co/api/{path}?" + urlencode(
            {"sort": "trendingScore", "direction": -1, "limit": 15, "full": "true"}
        )
        for item in _get_json(url, token):
            item_id = item.get("id") or item.get("modelId")
            if not item_id:
                continue
            project_url = f"https://huggingface.co/{'datasets/' if kind == 'dataset' else 'spaces/' if kind == 'space' else ''}{item_id}"
            if project_url in exclude:
                continue
            likes = int(item.get("likes") or 0)
            downloads = int(item.get("downloads") or 0)
            description = item.get("description") or ""
            tags = ", ".join((item.get("tags") or [])[:12])
            family = _model_family(item_id) if kind == "model" else ""
            memory_key = f"hf-family:{family}" if family else ""
            if memory_key and memory_key in excluded_families:
                continue
            candidates[kind].append((int(item.get("trendingScore") or 0), _variant_penalty(item_id), Project(
                name=item_id,
                url=project_url,
                source=f"Hugging Face {label}",
                description=(description + (f"\nTags: {tags}" if tags else ""))[:1200] or "لا يوجد وصف متاح.",
                metrics=f"♥ {likes:,}" + (f" · Downloads {downloads:,}" if downloads else ""),
                memory_key=memory_key,
            )))

    # النسخة الأصلية تتقدم على GGUF/MLX/FP8 ونحوها، ثم يحسم trendingScore.
    for entries in candidates.values():
        entries.sort(key=lambda pair: (pair[1], -pair[0]))

    selected: list[Project] = []
    used_families: set[str] = set()

    def take(kind: str, count: int) -> None:
        for _, _, project in candidates[kind]:
            if len([p for p in selected if p.source.endswith(kind.title())]) >= count:
                break
            if project.memory_key and project.memory_key in used_families:
                continue
            selected.append(project)
            if project.memory_key:
                used_families.add(project.memory_key)

    take("model", 1)
    take("dataset", 1)
    take("space", 1)

    remaining = sorted(
        (entry for entries in candidates.values() for entry in entries),
        key=lambda pair: (pair[1], -pair[0]),
    )
    selected_urls = {project.url for project in selected}
    for _, _, project in remaining:
        if len(selected) >= config.HUGGINGFACE_PROJECT_COUNT:
            break
        if project.url in selected_urls or (project.memory_key and project.memory_key in used_families):
            continue
        selected.append(project)
        selected_urls.add(project.url)
        if project.memory_key:
            used_families.add(project.memory_key)
    return selected


def fetch_product_hunt(exclude: set[str]) -> list[Project]:
    token = (os.environ.get("PRODUCT_HUNT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("المتغير PRODUCT_HUNT_TOKEN غير موجود")
    posted_after = (
        datetime.now(timezone.utc) - timedelta(days=config.PROJECT_LOOKBACK_DAYS)
    ).isoformat()
    query = f"""
      query WeeklyAIProducts($postedAfter: DateTime!) {{
        posts(first: 20, order: VOTES, featured: true,
              topic: \"{config.PRODUCT_HUNT_AI_TOPIC}\", postedAfter: $postedAfter) {{
          nodes {{ name tagline description url website votesCount commentsCount }}
        }}
      }}
    """
    data = _post_json(
        "https://api.producthunt.com/v2/api/graphql",
        {"query": query, "variables": {"postedAfter": posted_after}},
        token,
    )
    projects = []
    for item in data.get("data", {}).get("posts", {}).get("nodes", []):
        project_url = item.get("url") or item.get("website") or ""
        if not project_url or project_url in exclude:
            continue
        parts = [text.strip() for text in (item.get("tagline") or "", item.get("description") or "") if text.strip()]
        projects.append(Project(
            name=item.get("name") or "Product Hunt product",
            url=project_url,
            source="Product Hunt",
            description=(" — ".join(parts) or "لا يوجد وصف متاح.")[:1200],
            metrics=f"▲ {int(item.get('votesCount') or 0):,} · Comments {int(item.get('commentsCount') or 0):,}",
        ))
        if len(projects) >= config.PRODUCT_HUNT_COUNT:
            break
    return projects


def fetch_weekly_projects(exclude: set[str]) -> tuple[list[Project], list[str]]:
    projects: list[Project] = []
    warnings: list[str] = []
    for name, fetch in (
        ("GitHub", fetch_github),
        ("Hugging Face", fetch_huggingface),
        ("Product Hunt", fetch_product_hunt),
    ):
        try:
            found = fetch(exclude)
            projects.extend(found)
            print(f"جُلب {len(found)} عنصر من {name}")
        except Exception as exc:
            warnings.append(f"تعذّر جلب قسم {name}: {exc}")
            print(warnings[-1])
    return projects, warnings
