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

from ..presets import channel as _channel
from . import UA as _UA
from . import hn as _hn

UA = _UA


def _strip_tags(raw: str) -> str:
    """HTML -> plain text (shared with the connectors package)."""
    return re.sub(r"<[^>]+>", " ", raw or "")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------- conditional GET cache
# url -> {"etag": str|None, "modified": str|None}. Process-local on purpose:
# a restart just means one full poll again — no stale-cache surprises.
_cond: dict[str, dict] = {}


def _cond_headers(url: str) -> dict:
    """UA + conditional-GET headers from the last response we kept."""
    hit = _cond.get(url) or {}
    h = dict(UA)
    if hit.get("etag"):
        h["If-None-Match"] = hit["etag"]
    if hit.get("modified"):
        h["If-Modified-Since"] = hit["modified"]
    return h


def _remember_cond(url: str, headers) -> None:
    etag = headers.get("ETag")
    modified = headers.get("Last-Modified")
    if etag or modified:
        _cond[url] = {"etag": etag, "modified": modified}


# ---------------------------------------------------------------- RSS sources
def weworkremotely(settings: dict | None = None) -> list[dict]:
    """WeWorkRemotely — remote jobs RSS. `settings['preset']` picks the
    category channel (see presets.CHANNELS); default is the freelance feed.
    Conditional GET: unchanged feeds answer 304 and we return empty fast."""
    slug = _channel("weworkremotely", (settings or {}).get("preset")) or "remote-freelance-jobs"
    url = f"https://weworkremotely.com/categories/{slug}.rss"
    hit = _cond.get(url) or {}
    feed = feedparser.parse(
        url,
        request_headers=UA,
        etag=hit.get("etag"),
        modified=hit.get("modified"),
    )
    if getattr(feed, "status", None) == 304:
        return []
    if getattr(feed, "etag", None) or getattr(feed, "modified", None):
        _cond[url] = {
            "etag": getattr(feed, "etag", None),
            "modified": getattr(feed, "modified", None),
        }
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
    """RemoteOK public API (their docs allow it with attribution + UA).
    Conditional GET: a 304 costs nothing on the 2-minute fast lane."""
    url = "https://remoteok.com/api"
    r = requests.get(url, headers=_cond_headers(url), timeout=20)
    if r.status_code == 304:
        return []
    r.raise_for_status()
    _remember_cond(url, r.headers)
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


def remotive(settings: dict | None = None) -> list[dict]:
    """Remotive public jobs API. `settings['preset']` picks the category
    (see presets.CHANNELS); default is software-dev. Conditional GET."""
    cat = _channel("remotive", (settings or {}).get("preset")) or "software-dev"
    url = f"https://remotive.com/api/remote-jobs?category={cat}"
    r = requests.get(url, headers=_cond_headers(url), timeout=20)
    if r.status_code == 304:
        return []
    r.raise_for_status()
    _remember_cond(url, r.headers)
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
    "hackernews": _hn.fetch,
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
