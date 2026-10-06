"""Scorer — the sniper scope. Turns a job + profile into a 0-100 fit score.

Score anatomy:
  skills   0-60   how much of your stack the gig touches
  budget   0-25   money fit vs your floors
  quality  0-15   client signals (verified, hires, rating)
  redflag  -15 ea  unpaid / exposure / equity-only nonsense
"""

from __future__ import annotations

from ..config import Profile
from . import memory, parser


def score_job(
    job: dict, profile: Profile, memories: list[dict] | None = None
) -> tuple[int, dict]:
    text = f"{job['title']}\n{job.get('body', '')}\n{' '.join(job.get('tags', []))}"
    text = text[:6000]

    matched = parser.match_skills(text, profile.skills)
    denom = min(6, max(1, len(profile.skills)))
    skill_pts = round(60 * min(1.0, len(matched) / denom))

    budget_min, budget_max, hourly = parser.extract_money(text)
    # RemoteOK/Remotive sometimes give structured salary fields
    structured = False
    if hourly is None and job.get("hourly"):
        hourly = job["hourly"]
        structured = True
    if budget_min is None and job.get("budget_min"):
        budget_min, budget_max = job["budget_min"], job.get("budget_max")
        structured = True
    confidence = parser.money_confidence(text, structured=structured)

    budget_pts, budget_note = _budget_points(profile, hourly, budget_min)
    guard_pts, guard_note = _price_guard(profile, hourly, budget_min, confidence)
    budget_pts = max(0, min(25, budget_pts + guard_pts))
    if guard_note:
        budget_note = f"{budget_note}; {guard_note}" if budget_note else guard_note
    quality_pts, signals = parser.extract_quality(text)
    red = parser.find_red_flags(text, profile.red_flags)

    total = max(0, min(100, skill_pts + budget_pts + quality_pts - 15 * len(red)))

    mem_delta, mem_notes = 0, []
    if memories:
        mem_delta, mem_notes = memory.memory_adjust(job, memories)
        total = max(0, min(100, total + mem_delta))

    breakdown = {
        "skills": {"points": skill_pts, "matched": matched},
        "budget": {
            "points": budget_pts,
            "hourly": hourly,
            "fixed_min": budget_min,
            "fixed_max": budget_max,
            "note": budget_note,
            "confidence": confidence,
        },
        "client_quality": {"points": quality_pts, "signals": signals},
        "red_flags": red,
        "memory": {"points": mem_delta, "notes": mem_notes},
    }
    return total, breakdown


def _budget_points(profile: Profile, hourly, budget_min) -> tuple[int, str]:
    if hourly is not None:
        if hourly >= profile.min_hourly:
            return 25, f"${hourly:g}/hr meets your ${profile.min_hourly:g}/hr floor"
        if hourly >= 0.8 * profile.min_hourly:
            return 15, f"${hourly:g}/hr is close to your floor"
        return 5, f"${hourly:g}/hr is below your floor"
    if budget_min is not None:
        if budget_min >= profile.min_fixed_budget:
            return 25, f"${budget_min:,.0f} fixed meets your floor"
        if budget_min >= 0.6 * profile.min_fixed_budget:
            return 15, f"${budget_min:,.0f} fixed is below your floor"
        return 5, f"${budget_min:,.0f} fixed is far below your floor"
    return 10, "no budget stated (neutral)"


def _price_guard(profile: Profile, hourly, budget_min, confidence: str) -> tuple[int, str]:
    """Lowball reality-check on top of the base budget fit.

    The scope already rates money fit; the guard punishes the specific
    shape of a waste-of-time gig (half your floor) and warns on reads
    that are too thin or too shiny to trust.
    """
    pts, notes = 0, []
    if hourly is not None:
        if hourly < 0.5 * profile.min_hourly:
            pts -= 5
            notes.append("lowball rate — half your floor")
        if hourly > 300:
            notes.append("unusually high rate — verify before celebrating")
    elif budget_min is not None and budget_min < 0.3 * profile.min_fixed_budget:
        pts -= 5
        notes.append("lowball fixed budget — a fraction of your floor")
    if confidence == "low":
        notes.append("no stated budget — worth an asking reply")
    return pts, "; ".join(notes)
