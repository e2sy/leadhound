"""Freelancer.com connector — real search over their public projects API.

No credentials needed: the endpoint is documented at developers.freelancer.com;
anonymous reads are rate-limited but allowed. Budgets, dates and skill
categories come straight from the API, so the scorer gets real money data.
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime

import requests

from ..watchers import UA

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def _iso(ts) -> str | None:
    with contextlib.suppress(Exception):
        return datetime.fromtimestamp(int(ts), tz=UTC).isoformat(timespec="seconds")
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    query = str((settings or {}).get("query") or "").strip()
    params: dict = {
        "compact": "true",
        "limit": 50,
        "languages[]": "en",
        "active": "true",
    }
    if query:
        params["query"] = query
    r = requests.get(API, params=params, headers=UA, timeout=25)
    r.raise_for_status()
    projects = (r.json().get("result") or {}).get("projects") or []
    out = []
    for p in projects:
        if not p.get("title") or p.get("deleted") or p.get("nonpublic"):
            continue
        budget = p.get("budget") or {}
        hourly = p.get("type") == "hourly"
        out.append(
            {
                "guid": f"freelancer-{p.get('id')}",
                "source": "freelancer",
                "title": _clean(p["title"]),
                "url": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}".rstrip("/"),
                "body": _clean(p.get("preview_description", "")),
                "tags": [j.get("name", "") for j in (p.get("jobs") or []) if j.get("name")],
                "posted_at": _iso(p.get("submitdate") or p.get("time_submitted")),
                "budget_min": budget.get("minimum"),
                "budget_max": budget.get("maximum"),
                "hourly": budget.get("minimum") if hourly else None,
            }
        )
    return out, None
