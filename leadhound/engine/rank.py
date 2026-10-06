"""Queue ranking v2 — score is what a gig is, rank is when it matters.

A 95-point gig posted four days ago is worth less than an 80-pointer
from ten minutes ago. Rank composes three honest factors:

  score       the sniper scope's verdict (unchanged)
  freshness   the sniper window decays fast — tiers, not smooth lies
  reliability per-source reply rate from YOUR funnel data (default
              neutral 0.5 until a source has enough shots on record)

Late catch-up gigs get a freshness floor: they are old, but you just
saw them, so they still deserve a fair shot at the top.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

#: (hours old cap, multiplier) — the sniper window decays in tiers
_TIERS: tuple[tuple[int, float], ...] = ((1, 1.0), (6, 0.9), (24, 0.75), (72, 0.6))
_STALE = 0.45
#: catch-up gigs never rank below this freshness (you just saw them)
_LATE_FLOOR = 0.9
#: per-source trust is clamped here; neutral until >= 5 sends on record
REL_FLOOR, REL_CAP, REL_DEFAULT = 0.2, 1.0, 0.5
_MIN_SENDS = 5
#: how much reliability moves the composite (0.75..1.0 multiplier band)
_REL_BAND = 0.25


def freshness(posted_at: str | None, *, now: datetime | None = None) -> float:
    """Tiered freshness multiplier from the posting timestamp."""
    if not posted_at:
        return _STALE
    now = now or datetime.now(UTC)
    with contextlib.suppress(Exception):
        t = datetime.fromisoformat(str(posted_at))
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        hours = max(0.0, (now - t).total_seconds() / 3600)
        for cap, mult in _TIERS:
            if hours < cap:
                return mult
        return _STALE
    return _STALE


def reliability(by_source: list[dict]) -> dict[str, float]:
    """Per-source trust from your own funnel: replies / sent.

    Sources with fewer than _MIN_SENDS shots keep the neutral default —
    one lucky reply must not crown a source, one silence must not bury it.
    """
    out: dict[str, float] = {}
    for r in by_source or []:
        sent = r.get("sent") or 0
        replies = r.get("replies") or 0
        if sent < _MIN_SENDS:
            out[str(r.get("source", ""))] = REL_DEFAULT
        else:
            out[str(r.get("source", ""))] = max(
                REL_FLOOR, min(REL_CAP, replies / sent)
            )
    return out


def _reason(f: float, rel: float) -> str:
    if f >= 0.9:
        base = "hot off the press"
    elif f >= 0.75:
        base = "fresh"
    elif f >= 0.6:
        base = "cooling"
    else:
        base = "stale — window closing"
    if rel >= 0.7:
        return base + " · proven source"
    if rel < 0.35:
        return base + " · weak source so far"
    return base


def rank_score(
    score: int,
    posted_at: str | None,
    rel: float,
    *,
    now: datetime | None = None,
    late: bool = False,
) -> tuple[int, float, str]:
    """Composite rank: score x freshness x (0.75 + 0.25 x trust)."""
    f = freshness(posted_at, now=now)
    if late and f < _LATE_FLOOR:
        f = _LATE_FLOOR
    raw = score * f * (1.0 - _REL_BAND + _REL_BAND * rel)
    return round(raw), f, _reason(f, rel)


def ranked_queue(
    pending_jobs, by_source: list[dict], *, limit: int = 30, now: datetime | None = None
) -> list[dict]:
    """Rank pending Jobs best-first. Returns rows of
    {job, rank_score, freshness, reason} — best at index 0."""
    rel = reliability(by_source)
    rows = []
    for j in pending_jobs:
        rs, f, why = rank_score(
            j.score, j.posted_at, rel.get(j.source, REL_DEFAULT),
            now=now, late=bool(getattr(j, "late", 0)),
        )
        rows.append({"job": j, "rank_score": rs, "freshness": f, "reason": why})
    rows.sort(key=lambda r: -r["rank_score"])
    return rows[:limit]
