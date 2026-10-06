"""Reddit connector — [Hiring] posts from freelance subreddits.

Uses Reddit's public JSON listings with an honest descriptive User-Agent
(theirs to allow or rate-limit; no auth, no scraping of private pages).
Only posts tagged [Hiring] count as gigs — [For Hire] posts are people
selling their own labor, not work for you.
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime

import requests

from ..watchers import UA

# Reddit asks for a UA that identifies the caller honestly.
REDDIT_UA = {
    **UA,
    "User-Agent": "leadhound/1.3 (self-hosted gig radar; github.com/e2sy/leadhound)",
}

DEFAULT_SUBS = "forhire,hiring,jobbit"
HIRING_RE = re.compile(r"^\[?\s*hiring\s*\]?", re.IGNORECASE)
FOR_HIRE_RE = re.compile(r"^\[?\s*for\s*hire\s*\]?", re.IGNORECASE)


def _iso(ts) -> str | None:
    with contextlib.suppress(Exception):
        return datetime.fromtimestamp(float(ts), tz=UTC).isoformat(timespec="seconds")
    return None


def parse_subreddits(settings: dict) -> list[str]:
    """'forhire, hiring' -> ['forhire', 'hiring'] — max 5, deduped, safe slugs."""
    raw = str((settings or {}).get("subreddits") or DEFAULT_SUBS)
    subs: list[str] = []
    for s in raw.split(","):
        slug = re.sub(r"[^A-Za-z0-9_]", "", s.strip())
        if slug and slug.lower() not in [x.lower() for x in subs]:
            subs.append(slug)
    return subs[:5]


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    subs = parse_subreddits(settings)
    out: list[dict] = []
    errors: list[str] = []
    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/new.json"
        try:
            r = requests.get(
                url, params={"limit": 50}, headers=REDDIT_UA, timeout=25
            )
            r.raise_for_status()
            children = (r.json().get("data") or {}).get("children") or []
        except Exception as exc:
            errors.append(f"r/{sub}: {type(exc).__name__}: {exc}")
            continue
        for ch in children:
            d = ch.get("data") or {}
            title = str(d.get("title") or "").strip()
            if FOR_HIRE_RE.match(title) or not HIRING_RE.match(title):
                continue  # [For Hire] = a freelancer advertising; skip
            body = re.sub(r"<[^>]+>", " ", str(d.get("selftext") or ""))
            permalink = d.get("permalink") or ""
            out.append(
                {
                    "guid": f"reddit-{d.get('id', permalink)}",
                    "source": f"reddit/{sub.lower()}",
                    "title": title,
                    "url": f"https://www.reddit.com{permalink}" if permalink else "",
                    "body": body.strip()[:4000],
                    "tags": [d.get("link_flair_text", "")] if d.get("link_flair_text") else [],
                    "posted_at": _iso(d.get("created_utc")),
                }
            )
    if errors and not out:
        return [], {"error": "; ".join(errors)}
    return out, ({"warning": "; ".join(errors)} if errors else None)
