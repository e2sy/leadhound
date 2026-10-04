"""Parser — squeeze signals out of raw job text: skills, money, red flags."""

from __future__ import annotations

import re

MONEY_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{2,6})")
RANGE_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d{2,6})\s?(?:-|–|—|to)\s?\$?\s?(\d{1,3}(?:,\d{3})+|\d{2,6})"  # noqa: RUF001
)
HOURLY_RE = re.compile(r"(\$\s?\d[\d,]*)(?:\s?(?:/|per\s?)\s?h(?:our|r)?|/hr)", re.IGNORECASE)

QUALITY_SIGNALS = [
    ("payment verified", 4),
    ("payment method verified", 4),
    ("verified payment", 4),
]


def _to_f(x: str) -> float:
    return float(x.replace(",", ""))


def extract_money(text: str) -> tuple[float | None, float | None, float | None]:
    """Returns (budget_min, budget_max, hourly)."""
    hourly = None
    m = HOURLY_RE.search(text)
    if m:
        hourly = _to_f(MONEY_RE.search(m.group(1)).group(1))
        return None, None, hourly

    m = RANGE_RE.search(text)
    if m:
        lo, hi = _to_f(m.group(1)), _to_f(m.group(2))
        if hi >= lo:
            return lo, hi, None
    m = MONEY_RE.search(text)
    if m:
        v = _to_f(m.group(1))
        return v, v, None
    return None, None, None


def extract_quality(text: str) -> tuple[int, list[str]]:
    """Client-quality points (0-15) + human-readable signals."""
    pts, signals = 8, []
    low = text.lower()
    for phrase, p in QUALITY_SIGNALS:
        if phrase in low:
            pts += p
            signals.append("payment verified")
            break
    m = re.search(r"(\d+)\+?\s*hires?", low)
    if m:
        n = int(m.group(1))
        if n >= 3:
            pts += 3
            signals.append(f"{n} past hires")
    if re.search(r"5\.0\d*\s*(?:rating|stars)|top rated", low):
        pts += 3
        signals.append("top-rated client")
    return min(pts, 15), signals


def find_red_flags(text: str, red_flags: list[str]) -> list[str]:
    low = text.lower()
    return [rf for rf in red_flags if rf in low]


def match_skills(text: str, skills: list[str]) -> list[str]:
    low = f" {text.lower()} "
    return [s for s in skills if s in low]
