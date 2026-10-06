"""Shared plumbing for job-board RSS feeds (Guru, PeoplePerHour, ...).

These boards sit behind bot protection (Incapsula and friends), so the
honesty rule matters extra here: if the server answers with an HTML wall
instead of XML, the connector says exactly that instead of pretending
the feed was empty. From a residential/self-hosted box it usually just
works; from a datacenter IP it often won't — now you know why.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import feedparser
import requests

from ..watchers import UA


def _looks_like_html(payload: bytes) -> bool:
    head = payload[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"incapsula" in head


def _iso(st) -> str | None:
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=UTC).isoformat(timespec="seconds")
    except Exception:
        return None


def fetch_feed(
    url: str, source: str, *, timeout: int = 25
) -> tuple[list[dict], dict | None]:
    """Fetch one board RSS feed -> normalized jobs or an honest error."""
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    if _looks_like_html(r.content):
        return [], {
            "error": (
                f"{source}: the feed answered with a web page, not XML — "
                "the site's bot protection is blocking this server's IP. "
                "Self-hosting from a residential machine usually fixes it."
            )
        }
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        return [], {
            "error": f"{source}: feed could not be parsed "
                     f"({type(feed.bozo_exception).__name__})"
        }
    out = []
    for e in feed.entries:
        title = str(e.get("title") or "").strip()
        if not title:
            continue
        summary = str(e.get("summary") or e.get("description") or "")
        link = e.get("link", "")
        out.append(
            {
                "guid": e.get("id") or link or f"{source}-{len(out)}",
                "source": source,
                "title": title,
                "url": link,
                "body": re.sub(r"<[^>]+>", " ", summary).strip()[:4000],
                "tags": [t.get("term", "") for t in e.get("tags", []) if t.get("term")],
                "posted_at": _iso(e.get("published_parsed")),
            }
        )
    return out, None
