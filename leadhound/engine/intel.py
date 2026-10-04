"""Client intel — who is really behind this gig?

Lead generation has a golden rule: know the poster. intel extracts a
stable poster token (email domain or company URL domain) from the gig
body and cross-references it against your local gig history, surfacing
patterns like repeat lowballers.

Local-only: the "intel" is your own observed history, nothing else.
"""

from __future__ import annotations

import re

from .. import db

EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
URL_RE = re.compile(r"https?://([\w-]+(?:\.[\w-]+)+)")

# Domains that appear in almost every gig body — never a poster identity.
IGNORED_DOMAINS = {
    "remoteok.com", "weworkremotely.com", "remotive.com",
    "news.ycombinator.com", "hn.algolia.com",
    "github.com", "gitlab.com", "linkedin.com", "twitter.com", "x.com",
    "t.me", "discord.gg", "upwork.com", "www.upwork.com", "figma.com",
    "notion.so", "google.com", "docs.google.com", "zoom.us", "calendly.com",
}


def client_token(body: str) -> str | None:
    """The poster's identity as a domain: email contact > company URL."""
    m = EMAIL_RE.search(body or "")
    if m and m.group(1).lower() not in IGNORED_DOMAINS:
        return m.group(1).lower()
    for m in URL_RE.finditer(body or ""):
        dom = m.group(1).lower()
        if dom not in IGNORED_DOMAINS:
            return dom
    return None


def poster_history(token: str, exclude_id: int = -1) -> tuple[int, float]:
    """(n, avg_score) of prior gigs from the same poster in YOUR database."""
    c = db._conn()
    row = c.execute(
        "SELECT COUNT(*) AS n, AVG(score) AS avg_score FROM jobs "
        "WHERE body LIKE ? AND id != ?",
        (f"%{token}%", exclude_id),
    ).fetchone()
    c.close()
    return row["n"], row["avg_score"] or 0.0


def intel_for(job: db.Job) -> str | None:
    """One human line about the poster, or None when nothing to add."""
    token = client_token(job.body)
    if not token:
        return None
    n, avg = poster_history(token, exclude_id=job.id)
    if n == 0:
        return None
    if avg < 50:
        return f"poster ({token}) has {n} prior gig(s) here, avg {avg:.0f} — repeat lowballer"
    return f"poster ({token}) has {n} prior gig(s) here, avg {avg:.0f}"
