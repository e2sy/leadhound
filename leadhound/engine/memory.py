"""Win-memory — the hound remembers which gigs actually paid.

Every marked outcome (won / lost) snapshots the gig's shape. When a new
gig lands, we fuzzy-compare it against that memory: gigs that look like
ones you WON nudge the score up, gigs shaped like ones you LOST drag it
down. Similarity is rapidfuzz when available, difflib otherwise — the
engine never hard-depends on a wheel being present.

The influence is deliberately capped: memory is a nudge, not a veto.
The scope (skills/budget/quality) still does the heavy lifting.
"""

from __future__ import annotations

try:  # pragma: no cover - import guard exercised via the fallback test
    from rapidfuzz import fuzz

    def _sim(a: str, b: str) -> float:
        return float(fuzz.token_set_ratio(a, b))

except ImportError:  # difflib fallback: slower, close enough
    from difflib import SequenceMatcher

    def _sim(a: str, b: str) -> float:
        return 100 * SequenceMatcher(None, a.lower(), b.lower()).ratio()


#: minimum token similarity before a memory counts as "same kind of gig"
WIN_RATIO = 70.0
#: max points a single memory can move the total
WEIGHT = 6.0
#: max absolute total influence of memory on one gig
CAP = 10.0


def memory_adjust(job: dict, memories: list[dict]) -> tuple[int, list[str]]:
    """Score delta + human notes from past won/lost gigs.

    memories: rows with at least {outcome, title, tags}. Won memories pull
    up, lost memories pull down, unknown outcomes are ignored.
    """
    text = f"{job.get('title', '')} {' '.join(job.get('tags') or [])}".strip()
    if not text or not memories:
        return 0, []

    delta = 0.0
    won_hits: list[int] = []
    lost_hits: list[int] = []
    for m in memories:
        sim = _sim(text, f"{m.get('title', '')} {m.get('tags') or ''}".strip())
        if sim < WIN_RATIO:
            continue
        strength = (sim - WIN_RATIO) / (100.0 - WIN_RATIO)  # 0..1
        outcome = (m.get("outcome") or "").lower()
        if outcome == "won":
            delta += WEIGHT * strength
            won_hits.append(int(sim))
        elif outcome == "lost":
            delta -= WEIGHT * strength
            lost_hits.append(int(sim))

    delta = max(-CAP, min(CAP, delta))
    notes: list[str] = []
    if won_hits:
        notes.append(f"matches a gig you WON ({max(won_hits)}% alike) — leaning in")
    if lost_hits:
        notes.append(f"resembles a gig you LOST ({max(lost_hits)}% alike) — careful")
    return round(delta), notes
