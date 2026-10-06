"""Fingerprinting — the same gig shows up on five boards wearing five hats.

normalize the title, bucket the money, hash the pair. Same fingerprint
across sources = one gig seen N times, not N gigs. Near-duplicate titles
with different punctuation get caught by the fuzz pass, not the hash.
"""

from __future__ import annotations

import hashlib
import re

try:  # same soft dependency as win-memory
    from rapidfuzz import fuzz

    def _ratio(a: str, b: str) -> float:
        return float(fuzz.ratio(a, b))

except ImportError:  # difflib fallback
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return 100 * SequenceMatcher(None, a, b).ratio()


_FILLER = re.compile(
    r"\b(looking|for|need|needed|want|wanted|seeking|freelancer|freelance|"
    r"developer|expert|required|urgently|help|with|the|a|an|to|and|of|me|my|us|our)\b",
    re.IGNORECASE,
)
_NOISE = re.compile(r"[^a-z0-9 ]+")


def normalize_title(title: str) -> str:
    """'URGENT: Need a React Developer!!' -> 'urgent react' — order kept,
    filler and punctuation gone, so cross-board wording noise drops out."""
    low = (title or "").lower()
    cleaned = _NOISE.sub(" ", low)
    cleaned = _FILLER.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def money_bucket(job: dict) -> str:
    """Coarse money shape: hourly vs fixed, rounded hard ($500 and $540 match)."""
    hourly = job.get("hourly")
    if hourly:
        return f"h{round(float(hourly) / 5) * 5:g}"
    lo = job.get("budget_min")
    hi = job.get("budget_max")
    if lo or hi:
        top = float(hi or lo or 0)
        return f"f{round(top / 100) * 100:g}"
    return "none"


def fingerprint(job: dict) -> str:
    """Stable short hash of (normalized title, money bucket)."""
    base = f"{normalize_title(str(job.get('title') or ''))}|{money_bucket(job)}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]  # noqa: S324 — not security


def near_duplicate(title_a: str, title_b: str, *, threshold: float = 92.0) -> bool:
    """Fuzz pass for the hats the hash misses ($5O0 vs $500, extra words)."""
    a, b = normalize_title(title_a), normalize_title(title_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return _ratio(a, b) >= threshold
