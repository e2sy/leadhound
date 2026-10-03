"""Watchers — the eyes. Each source yields NormalizedJob dicts.

v1 ships with three ToS-friendly sources (public RSS/JSON feeds).
New sources are welcome as plugins: write an async-safe function that
yields the same dict shape and register it in SOURCES.
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime

import feedparser
import requests

UA = {"User-Agent": "leadhound/0.1 (+https://github.com/YOUR_GITHUB_USERNAME/leadhound)"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------- RSS sources
def weworkremotely() -> list[dict]:
    """WeWorkRemotely — remote freelance jobs RSS feed."""
    feed = feedparser.parse(
        "https://weworkremotely.com/categories/remote-freelance-jobs.rss",
        request_headers=UA,
    )
    out = []
    for e in feed.entries:
        body = e.get("summary", "")
        out.append(
            {
                "guid": e.get("id", e.get("link", "")),
                "source": "weworkremotely",
                "title": e.get("title", "").strip(),
                "url": e.get("link", ""),
                "body": re.sub(r"<[^>]+>", " ", body),
                "tags": [t.get("term", "") for t in e.get("tags", []) if t.get("term")],
                "posted_at": _struct_to_iso(e.get("published_parsed")),
            }
        )
    return out


def _struct_to_iso(st) -> str | None:
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=UTC).isoformat(timespec="seconds")
    except Exception:
        return None


# --------------------------------------------------------------- JSON sources
def remoteok() -> list[dict]:
    """RemoteOK public API (their docs allow it with attribution + UA)."""
    r = requests.get("https://remoteok.com/api", headers=UA, timeout=20)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in data[1:]:  # first element is their legal notice
        posted = None
        if item.get("date"):
            with contextlib.suppress(Exception):
                posted = datetime.fromtimestamp(
                    int(item["date"]), tz=UTC
                ).isoformat(timespec="seconds")
        out.append(
            {
                "guid": f"remoteok-{item.get('id', item.get('slug', item.get('url', '')))}",
                "source": "remoteok",
                "title": (item.get("position") or "").strip(),
                "url": item.get("url") or f"https://remoteok.com{item.get('slug', '')}",
                "body": re.sub(r"<[^>]+>", " ", item.get("description", "")),
                "tags": [str(t) for t in item.get("tags", [])],
                "posted_at": posted,
            }
        )
    return out


def remotive() -> list[dict]:
    """Remotive public jobs API."""
    r = requests.get(
        "https://remotive.com/api/remote-jobs?category=software-dev",
        headers=UA,
        timeout=20,
    )
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(
            {
                "guid": f"remotive-{j.get('id')}",
                "source": "remotive",
                "title": (j.get("title") or "").strip(),
                "url": j.get("url", ""),
                "body": re.sub(r"<[^>]+>", " ", j.get("description", "")),
                "tags": [str(t) for t in (j.get("tags") or [])],
                "posted_at": j.get("publication_date"),
            }
        )
    return out


SOURCES = {
    "weworkremotely": weworkremotely,
    "remoteok": remoteok,
    "remotive": remotive,
}


def poll(source_names: list[str]) -> tuple[list[dict], list[str]]:
    """Poll all requested sources. Returns (jobs, warnings)."""
    jobs: list[dict] = []
    warnings: list[str] = []
    for name in source_names:
        fn = SOURCES.get(name)
        if not fn:
            warnings.append(f"unknown source: {name}")
            continue
        try:
            got = fn()
            jobs.extend(got)
        except Exception as exc:  # network down, API change, etc.
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")
    return jobs, warnings
