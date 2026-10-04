"""Custom RSS / Atom feed connector — point leadhound at any job feed.

This is the escape hatch that covers everything without a public API:
third-party Upwork/Fiverr RSS mirrors, niche boards, agency feeds, anything
with an RSS or Atom URL. Credentials never leave your machine; the feed URL
is stored per-account in your local SQLite.
"""

from __future__ import annotations

from urllib.parse import urlparse

import feedparser

from ..watchers import UA
from ..watchers.rss import _strip_tags, _struct_to_iso  # reuse proven helpers


class FeedError(RuntimeError):
    pass


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    url = str((settings or {}).get("url") or "").strip()
    if not url:
        raise FeedError("add a feed URL first (Settings below)")
    if urlparse(url).scheme not in ("http", "https"):
        raise FeedError("feed URL must start with http:// or https://")
    feed = feedparser.parse(url, request_headers=UA)
    if feed.bozo and not feed.entries:
        raise FeedError(f"could not read that feed ({type(feed.bozo_exception).__name__})")
    host = urlparse(url).netloc or "rss"
    source_name = "rss:" + host
    out = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not title or not link:
            continue
        out.append(
            {
                "guid": f"rss:{host}:{e.get('id', link)}",
                "source": source_name,
                "title": title,
                "url": link,
                "body": _strip_tags(e.get("summary", "")).strip(),
                "tags": [t.get("term", "") for t in e.get("tags", []) if t.get("term")],
                "posted_at": _struct_to_iso(e.get("published_parsed")),
            }
        )
    if not out:
        raise FeedError("feed parsed but contained no usable entries")
    return out, None
