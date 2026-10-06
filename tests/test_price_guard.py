"""Price guard tests — currency normalization, lowball detection,
money-read confidence and the clamp so budget points stay 0-25."""

from __future__ import annotations

import pytest

from leadhound.config import Profile
from leadhound.engine import parser
from leadhound.engine.scorer import score_job


@pytest.fixture
def profile():
    return Profile(
        name="T", skills=["react"], min_hourly=30.0, min_fixed_budget=800.0,
    )


# ---------------------------------------------------------------- currencies

def test_usd_unchanged():
    lo, hi, hr = parser.extract_money("budget $1,500 for the build")
    assert (lo, hi) == (1500.0, 1500.0)
    assert hr is None


def test_eur_normalized_to_usd():
    lo, hi, _ = parser.extract_money("Budget: €800-€1,200")
    assert lo == 880.0   # 800 * 1.10
    assert hi == 1320.0  # 1200 * 1.10


def test_gbp_hourly_normalized():
    _, _, hr = parser.extract_money("we pay £40/hr")
    assert hr == 50.8    # 40 * 1.27


def test_range_with_one_symbol():
    lo, hi, _ = parser.extract_money("€500-700 depending on scope")
    assert lo == 550.0
    assert hi == 770.0   # second number inherits the euro symbol


# ---------------------------------------------------------------- confidence

def test_confidence_high_with_structured_fields():
    assert parser.money_confidence("no numbers here", structured=True) == "high"


def test_confidence_medium_from_regex():
    assert parser.money_confidence("around $500", structured=False) == "medium"


def test_confidence_low_when_silent():
    assert parser.money_confidence("lets discuss", structured=False) == "low"


# ---------------------------------------------------------------- guard

def _bd(job, profile):
    _, breakdown = score_job(job, profile)
    return breakdown


def test_lowball_hourly_penalized(profile):
    bd = _bd({"title": "React gig", "body": "$10/hr", "tags": []}, profile)
    assert bd["budget"]["points"] <= 20          # 5 base - 5 lowball, floored at 0
    assert "lowball rate" in bd["budget"]["note"]


def test_lowball_fixed_penalized(profile):
    bd = _bd({"title": "React gig", "body": "budget $100", "tags": []}, profile)
    assert "lowball fixed budget" in bd["budget"]["note"]


def test_suspiciously_high_rate_warns_not_penalized(profile):
    bd = _bd({"title": "React gig", "body": "$400/hr, urgent", "tags": []}, profile)
    assert "unusually high rate" in bd["budget"]["note"]
    # 400 >= 30 floor → base 25, guard delta 0 → still full points
    assert bd["budget"]["points"] == 25


def test_no_budget_gets_asking_hint(profile):
    bd = _bd({"title": "React gig", "body": "reach out", "tags": []}, profile)
    assert bd["budget"]["confidence"] == "low"
    assert "asking reply" in bd["budget"]["note"]


def test_budget_points_never_exceed_25_or_drop_below_0(profile):
    job = {"title": "React gig", "body": "$2/hr", "tags": []}
    pts = _bd(job, profile)["budget"]["points"]
    assert 0 <= pts <= 25


def test_healthy_gig_untouched_by_guard(profile):
    bd = _bd({"title": "React gig", "body": "$60/hr long term work", "tags": []}, profile)
    assert bd["budget"]["points"] == 25
    assert "lowball" not in bd["budget"]["note"]
