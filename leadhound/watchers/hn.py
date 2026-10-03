"""Hacker News watcher — the monthly "Freelancer? Seeking freelancer?" thread.

Uses HN's public Algolia API (https://hn.algolia.com/api) — no login, no
scraping, one search + one thread fetch per poll. Top-level comments in the
thread are the gig posts.

ToS-safe: public API with a polite UA, designed for low-frequency polling.
"""

from __future__ import annotations

import html
import re

import requests

from . import UA

API = "https://hn.algolia.com/api/v1"
THREAD_HINT = "freelancer"


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def pick_thread(hits: list[dict]) -> dict | None:
    """Newest story whose title mentions the freelancer thread (hits are
    already date-sorted newest-first by search_by_date)."""
    for h in hits:
        if THREAD_HINT in (h.get("title") or "").lower():
            return h
    return None


def parse_thread(item: dict) -> list[dict]:
    """Top-level comments -> normalized gig dicts. Children (replies) are ignored:
    a reply is a conversation, not a gig post."""
    out = []
    for c in item.get("children") or []:
        text = _strip_html(c.get("text") or "")
        if not text:
            continue
        first_line = text.split(". ")[0][:140]
        out.append({
            "guid": f"hn-{c.get('id')}",
            "source": "hackernews",
            "title": first_line if len(first_line) > 12 else text[:140],
            "url": f"https://news.ycombinator.com/item?id={c.get('id')}",
            "body": text,
            "tags": [],
            "posted_at": c.get("created_at"),
        })
    return out


def fetch() -> list[dict]:
    """Find the latest freelancer thread and harvest its top-level comments."""
    r = requests.get(
        f"{API}/search_by_date",
        params={"tags": "story", "query": f'"{THREAD_HINT}"', "hitsPerPage": 20},
        headers=UA,
        timeout=20,
    )
    r.raise_for_status()
    story = pick_thread(r.json().get("hits", []))
    if not story:
        return []
    r2 = requests.get(f"{API}/items/{story['objectID']}", headers=UA, timeout=20)
    r2.raise_for_status()
    return parse_thread(r2.json())
