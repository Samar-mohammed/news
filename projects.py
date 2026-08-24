"""جلب أبرز مشاريع GitHub وعناصر Hugging Face للتقرير الأسبوعي."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import config


@dataclass
class Project:
    name: str
    url: str
    source: str
    description: str
    metrics: str


def _get_json(url: str, token: str = ""):
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=config.PROJECT_API_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_github(exclude: set[str]) -> list[Project]:
    since = (datetime.now(timezone.utc) - timedelta(days=config.PROJECT_LOOKBACK_DAYS)).date()
    query = f"created:>={since}"
    url = "https://api.github.com/search/repositories?" + urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": 30}
    )
    data = _get_json(url, os.environ.get("GITHUB_TOKEN", ""))
    projects = []
    for item in data.get("items", []):
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
    candidates: list[tuple[int, Project]] = []
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
            candidates.append((int(item.get("trendingScore") or 0), Project(
                name=item_id,
                url=project_url,
                source=f"Hugging Face {label}",
                description=(description + (f"\nTags: {tags}" if tags else ""))[:1200] or "لا يوجد وصف متاح.",
                metrics=f"♥ {likes:,}" + (f" · Downloads {downloads:,}" if downloads else ""),
            )))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [project for _, project in candidates[: config.HUGGINGFACE_PROJECT_COUNT]]


def fetch_weekly_projects(exclude: set[str]) -> tuple[list[Project], list[str]]:
    projects: list[Project] = []
    warnings: list[str] = []
    for name, fetch in (("GitHub", fetch_github), ("Hugging Face", fetch_huggingface)):
        try:
            found = fetch(exclude)
            projects.extend(found)
            print(f"جُلب {len(found)} عنصر من {name}")
        except Exception as exc:
            warnings.append(f"تعذّر جلب قسم {name}: {exc}")
            print(warnings[-1])
    return projects, warnings
