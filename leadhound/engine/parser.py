"""Parser — squeeze signals out of raw job text: skills, money, red flags."""

from __future__ import annotations

import re

# Symbols the regex understands, with rough USD conversion for normalization.
CURRENCY_RATES = {"$": 1.0, "€": 1.10, "£": 1.27}
MONEY_RE = re.compile(r"([$€£])\s?(\d{1,3}(?:,\d{3})+|\d{2,6})")
RANGE_RE = re.compile(
    r"([$€£])\s?(\d{1,3}(?:,\d{3})+|\d{2,6})\s?(?:-|–|—|to)\s?([$€£])?\s?(\d{1,3}(?:,\d{3})+|\d{2,6})"  # noqa: RUF001
)
HOURLY_RE = re.compile(
    r"([$€£])\s?(\d[\d,]*)(?:\s?(?:/|per\s?)\s?h(?:our|r)?|/hr)", re.IGNORECASE
)

QUALITY_SIGNALS = [
    ("payment verified", 4),
    ("payment method verified", 4),
    ("verified payment", 4),
]


def _to_f(x: str) -> float:
    return float(x.replace(",", ""))


def _usd(symbol: str, value: float) -> float:
    """Normalize a quoted amount to USD (rough constants, stated as such)."""
    return round(value * CURRENCY_RATES.get(symbol, 1.0), 2)


def extract_money(text: str) -> tuple[float | None, float | None, float | None]:
    """Returns (budget_min, budget_max, hourly) — all normalized to USD.

    € and £ quotes are converted with rough public-average rates so floors
    compare fairly across sources; the raw symbol is never silently ignored.
    """
    hourly = None
    m = HOURLY_RE.search(text)
    if m:
        hourly = _usd(m.group(1), _to_f(m.group(2)))
        return None, None, hourly

    m = RANGE_RE.search(text)
    if m:
        lo = _usd(m.group(1), _to_f(m.group(2)))
        hi = _usd(m.group(3) or m.group(1), _to_f(m.group(4)))
        if hi >= lo:
            return lo, hi, None
    m = MONEY_RE.search(text)
    if m:
        v = _usd(m.group(1), _to_f(m.group(2)))
        return v, v, None
    return None, None, None


def money_confidence(text: str, *, structured: bool) -> str:
    """How much to trust the money read: structured fields > regex > silence."""
    if structured:
        return "high"
    if HOURLY_RE.search(text) or RANGE_RE.search(text) or MONEY_RE.search(text):
        return "medium"
    return "low"


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
