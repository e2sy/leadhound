"""Interview kit — when a gig reaches the interview stage, show up prepared.

Everything here is derived from data you already have (the gig text, the
scope's read, your profile): the questions to ask, the money frame, the
talking points, and the lines you refuse to cross. No LLM, no invented
facts — the same honesty rule as the proposal drafter.
"""

from __future__ import annotations


def _has_timeline(text: str) -> bool:
    low = text.lower()
    return any(
        w in low for w in ("week", "month", "day", "deadline", "timeline", "by ")
    )


def _has_deliverables(text: str) -> bool:
    low = text.lower()
    return any(
        w in low
        for w in ("deliver", "scope", "milestone", "requirement", "feature",
                  "page", "screen", "api", "integration")
    )


def build_kit(job: dict, profile, breakdown: dict | None = None) -> dict:
    """Assemble the interview kit for one gig."""
    b = breakdown or {}
    body = job.get("body") or ""
    title = (job.get("title") or "the project").strip()
    matched = (b.get("skills") or {}).get("matched") or []

    # --- questions the gig leaves open -------------------------------------
    questions: list[str] = []
    if (b.get("budget") or {}).get("confidence") in (None, "low") and not (
        job.get("hourly") or job.get("budget_min") or job.get("budget_max")
    ):
        questions.append(
            "What budget range are you working with? (the post didn't say)"
        )
    if not _has_timeline(body):
        questions.append("When do you need this live — is there a hard date?")
    if not _has_deliverables(body):
        questions.append(
            "Can you walk me through the deliverables for the first milestone?"
        )
    questions.append(
        "Who owns feedback and sign-off on your side — one person or a chain?"
    )
    if job.get("hourly"):
        questions.append("Roughly how many hours per week do you expect?")
    else:
        questions.append("Is this fixed-price per milestone, or one lump?")

    # --- the money frame ----------------------------------------------------
    if job.get("hourly"):
        floor = float(profile.min_hourly)
        opening = round(floor * 1.25)
        money = {
            "opening": opening,
            "floor": floor,
            "note": (
                f"open at ${opening:g}/hr, settle no lower than your "
                f"${floor:g}/hr floor — they already saw your rate"
            ),
        }
    elif job.get("budget_max") or job.get("budget_min"):
        base = float(job.get("budget_max") or job.get("budget_min") or 0)
        opening = round(base * 1.15)
        money = {
            "opening": opening,
            "floor": round(float(profile.min_fixed_budget)),
            "note": (
                f"their range tops at ${base:,.0f} — asking ${opening:,.0f} "
                "with a scope carve-back is normal; name milestones so a "
                "reduced number still lands as smaller scope, not a discount"
            ),
        }
    else:
        money = {
            "opening": None,
            "floor": float(profile.min_fixed_budget),
            "note": "no budget on record — make THEM name a number first",
        }

    # --- talking points: your skills x your real highlights -----------------
    highlights = list(profile.highlights or [])
    points = [
        f"{skill}: tie it to one shipped result" for skill in matched[:3]
    ]
    for h in highlights[:2]:
        points.append(str(h))

    # --- red lines ----------------------------------------------------------
    red = b.get("red_flags") or []
    red_lines = [
        f"the post mentioned '{flag}' — do not accept it as a working condition"
        for flag in red[:3]
    ]

    return {
        "title": title,
        "questions": questions,
        "money": money,
        "talking_points": points,
        "red_lines": red_lines,
    }


def format_kit(kit: dict) -> str:
    """Plain-text rendering (pocket bot / kit blocks)."""
    lines = [f"🎤 interview kit — {kit['title']}"]
    lines.append("")
    lines.append("ask:")
    for q in kit["questions"]:
        lines.append(f"  • {q}")
    m = kit["money"]
    lines.append("")
    if m.get("opening"):
        lines.append(f"money: open ${m['opening']:,.0f} · floor ${m['floor']:,.0f}")
    else:
        lines.append(f"money: floor ${m['floor']:,.0f}")
    lines.append(f"  {m['note']}")
    if kit["talking_points"]:
        lines.append("")
        lines.append("say:")
        for p in kit["talking_points"]:
            lines.append(f"  • {p}")
    if kit["red_lines"]:
        lines.append("")
        lines.append("don't:")
        for r in kit["red_lines"]:
            lines.append(f"  • {r}")
    return "\n".join(lines)
