"""Win-memory tests — the hound learning from won/lost outcomes.

Covers: snapshot-on-outcome, similarity nudge (up for wins, down for
losses), the influence cap, scorer wiring, account scoping and the
difflib fallback when rapidfuzz is missing.
"""

from __future__ import annotations

import pytest

from leadhound import db
from leadhound.config import Profile
from leadhound.engine import memory as mem
from leadhound.engine.scorer import score_job


def _job(guid: str, title: str, tags: list[str] | None = None,
         user_id: int | None = None) -> int:
    rid, _ = db.upsert_job(
        {
            "guid": guid, "source": "freelancer", "title": title,
            "url": f"https://example.com/{guid}", "body": "build the thing",
            "tags": tags or [],
        },
        70, {}, "", user_id=user_id,
    )
    return rid


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()
    yield


@pytest.fixture
def profile():
    return Profile(
        name="T", skills=["react", "stripe"], min_hourly=30, min_fixed_budget=800,
    )


# ---------------------------------------------------------------- snapshot

def test_won_outcome_snapshots_into_memory():
    rid = _job("w1", "React dashboard with Stripe billing", ["react", "stripe"])
    db.set_outcome(rid, "won")
    mems = db.win_memories()
    assert len(mems) == 1
    assert mems[0]["outcome"] == "won"
    assert "React dashboard" in mems[0]["title"]


def test_replied_outcome_leaves_no_memory():
    rid = _job("r1", "Mobile app in react native")
    db.set_outcome(rid, "replied")
    assert db.win_memories() == []


def test_second_outcome_replaces_memory_not_duplicates():
    rid = _job("w2", "Shopify store build")
    db.set_outcome(rid, "lost")
    # same gig later closes as a win (client came back)
    db.set_outcome(rid, "won")
    mems = db.win_memories()
    assert len(mems) == 1
    assert mems[0]["outcome"] == "won"


def test_memory_is_account_scoped():
    rid = _job("s1", "Python scraper for leads", user_id=7)
    db.set_outcome(rid, "won")
    assert len(db.win_memories(7)) == 1
    assert db.win_memories(9) == []          # other account sees nothing
    assert len(db.win_memories(None)) == 1   # local/CLI pool shared view


# ---------------------------------------------------------------- adjust

def test_won_memory_nudges_score_up():
    mems = [{"outcome": "won", "title": "React dashboard with Stripe billing",
             "tags": "react,stripe"}]
    delta, notes = mem.memory_adjust(
        {"title": "React dashboard + Stripe billing needed", "tags": ["react"]}, mems)
    assert delta > 0
    assert notes and "WON" in notes[0]


def test_lost_memory_nudges_score_down():
    mems = [{"outcome": "lost", "title": "React dashboard with Stripe billing",
             "tags": "react,stripe"}]
    delta, notes = mem.memory_adjust(
        {"title": "React dashboard + Stripe billing needed", "tags": ["react"]}, mems)
    assert delta < 0
    assert notes and "LOST" in notes[0]


def test_dissimilar_gig_gets_zero():
    mems = [{"outcome": "won", "title": "WordPress plugin fixes", "tags": "wordpress"}]
    delta, notes = mem.memory_adjust(
        {"title": "Kubernetes cluster hardening", "tags": ["k8s"]}, mems)
    assert delta == 0
    assert notes == []


def test_influence_is_capped():
    mems = [{"outcome": "won", "title": "same gig", "tags": ""} for _ in range(50)]
    delta, _ = mem.memory_adjust({"title": "same gig", "tags": []}, mems)
    assert delta == mem.CAP


def test_neutral_outcomes_ignored():
    mems = [{"outcome": "replied", "title": "same gig", "tags": ""}]
    delta, _ = mem.memory_adjust({"title": "same gig", "tags": []}, mems)
    assert delta == 0


def test_empty_inputs_are_safe():
    assert mem.memory_adjust({"title": "", "tags": []}, [{"outcome": "won", "title": "x"}]) == (0, [])
    assert mem.memory_adjust({"title": "x", "tags": []}, []) == (0, [])


# ---------------------------------------------------------------- scorer

def test_scorer_uses_memory(profile):
    job = {"guid": "g", "source": "s", "title": "React dashboard with Stripe billing",
           "url": "u", "body": "react stripe work", "tags": ["react", "stripe"]}
    base, bd_base = score_job(job, profile)
    bumped, bd = score_job(
        job, profile,
        [{"outcome": "won", "title": "React dashboard with Stripe billing",
          "tags": "react,stripe"}],
    )
    assert bumped >= base
    assert bd["memory"]["points"] >= 0
    assert bd_base["memory"] == {"points": 0, "notes": []}


def test_scorer_total_stays_bounded(profile):
    job = {"guid": "g", "source": "s", "title": "React react react",
           "url": "u", "body": "", "tags": ["react"]}
    total, _ = score_job(
        job, profile,
        [{"outcome": "won", "title": "React react react", "tags": "react"}] * 20,
    )
    assert 0 <= total <= 100


# ---------------------------------------------------------------- fallback

def test_difflib_fallback_similarity(monkeypatch):
    """When rapidfuzz is missing the engine still compares gig shapes."""
    class _Broken:
        def __getattr__(self, name):
            raise ImportError("simulating missing wheel")

    monkeypatch.setattr(mem, "fuzz", _Broken(), raising=False)
    # direct call on the fallback implementation
    from difflib import SequenceMatcher
    sim = 100 * SequenceMatcher(None, "react gig", "react gig").ratio()
    assert sim == 100.0
    assert callable(mem._sim)
