"""Qualification checklist — the pre-flight read before you approve a gig.

Six honest yes/no/unknown lines distilled from what the scope already
knows: stack fit, money reality, client signals, red flags and freshness.
"Unknown" is a first-class answer — a missing budget is not a pass.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

_FRESH_HOURS = 24


def _age_hours(posted: str | None, now: datetime) -> float | None:
    if not posted:
        return None
    with contextlib.suppress(Exception):
        t = datetime.fromisoformat(str(posted))
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return (now - t).total_seconds() / 3600
    return None


def checklist(job: dict, breakdown: dict, profile, *, now: datetime | None = None) -> list[dict]:
    """Return [{label, ok: True|False|None, detail}] — ok=None means unknown."""
    b = breakdown or {}
    matched = (b.get("skills") or {}).get("matched") or []
    budget = b.get("budget") or {}
    quality = b.get("client_quality") or {}
    red = b.get("red_flags") or []
    now = now or datetime.now(UTC)
    items: list[dict] = []

    denom = min(6, max(1, len(profile.skills)))
    items.append({
        "label": "your stack fits",
        "ok": len(matched) > 0,
        "detail": (
            f"{len(matched)}/{denom} core skills: " + ", ".join(matched[:4])
            if matched else "none of your skills appear in the post"
        ),
    })

    conf = budget.get("confidence")
    pts = budget.get("points")
    if conf == "low" or pts is None:
        items.append({
            "label": "budget is real",
            "ok": None,
            "detail": "no budget stated — ask before writing the proposal",
        })
    elif pts >= 25:
        items.append({"label": "budget is real", "ok": True,
                      "detail": "meets your floor"})
    elif pts >= 15:
        items.append({"label": "budget is real", "ok": None,
                      "detail": "close to your floor — negotiable?"})
    else:
        items.append({"label": "budget is real", "ok": False,
                      "detail": budget.get("note") or "below your floor"})

    signals = quality.get("signals") or []
    items.append({
        "label": "client checks out",
        "ok": True if signals else None,
        "detail": ", ".join(signals) if signals
        else "no public signals — open the client profile",
    })

    items.append({
        "label": "no red flags",
        "ok": len(red) == 0,
        "detail": "clean" if not red else "⚑ " + ", ".join(red),
    })

    age = _age_hours(job.get("posted_at"), now)
    if age is None:
        items.append({"label": "still fresh", "ok": None,
                      "detail": "posting time unknown"})
    else:
        fresh = age <= _FRESH_HOURS
        items.append({
            "label": "still fresh",
            "ok": fresh,
            "detail": f"posted {age:.0f}h ago"
            + ("" if fresh else f" — sniper window is { _FRESH_HOURS }h"),
        })

    return items
