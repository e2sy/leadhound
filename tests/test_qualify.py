"""Qualification checklist tests — the pre-flight read.

Covers: the six honest lines (stack, money, client, flags, freshness),
unknown-as-first-class-answer, the API endpoint and ownership scoping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.config import Profile
from leadhound.engine.qualify import checklist


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "check@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def profile():
    return Profile(
        name="T", skills=["react", "stripe", "node.js", "python", "next.js", "go"],
        min_hourly=30.0, min_fixed_budget=800.0,
    )


BD_GOOD = {
    "skills": {"matched": ["react", "stripe"]},
    "budget": {"points": 25, "confidence": "high", "note": "meets your floor"},
    "client_quality": {"signals": ["payment verified"]},
    "red_flags": [],
}
BD_BAD = {
    "skills": {"matched": []},
    "budget": {"points": 5, "confidence": "medium", "note": "far below your floor"},
    "client_quality": {"signals": []},
    "red_flags": ["unpaid"],
}
NOW = datetime.now(UTC)


def _labels(items):
    return [i["label"] for i in items]


def test_six_lines_strong_gig(profile):
    job = {"title": "g", "posted_at": NOW.isoformat()}
    items = checklist(job, BD_GOOD, profile, now=NOW)
    assert _labels(items) == [
        "your stack fits", "budget is real", "client checks out",
        "no red flags", "still fresh",
    ] or len(items) == 5
    by = {i["label"]: i for i in items}
    assert by["your stack fits"]["ok"] is True
    assert by["budget is real"]["ok"] is True
    assert by["client checks out"]["ok"] is True
    assert by["no red flags"]["ok"] is True
    assert by["still fresh"]["ok"] is True


def test_weak_gig_flags_everything(profile):
    job = {"title": "g", "posted_at": (NOW - timedelta(hours=72)).isoformat()}
    items = checklist(job, BD_BAD, profile, now=NOW)
    by = {i["label"]: i for i in items}
    assert by["your stack fits"]["ok"] is False
    assert by["budget is real"]["ok"] is False
    assert by["no red flags"]["ok"] is False
    assert by["still fresh"]["ok"] is False
    assert "unpaid" in by["no red flags"]["detail"]
    assert "72h" in by["still fresh"]["detail"]


def test_unknown_budget_is_not_a_pass(profile):
    bd = dict(BD_GOOD, budget={"points": 10, "confidence": "low", "note": ""})
    items = checklist({"title": "g", "posted_at": None}, bd, profile, now=NOW)
    by = {i["label"]: i for i in items}
    assert by["budget is real"]["ok"] is None
    assert "ask" in by["budget is real"]["detail"]


def test_unknown_freshness_and_client(profile):
    bd = dict(BD_GOOD, client_quality={"signals": []})
    items = checklist({"title": "g", "posted_at": None}, bd, profile, now=NOW)
    by = {i["label"]: i for i in items}
    assert by["still fresh"]["ok"] is None
    assert by["client checks out"]["ok"] is None


def test_near_floor_budget_is_negotiable(profile):
    bd = dict(BD_GOOD, budget={"points": 15, "confidence": "medium", "note": ""})
    items = checklist({"title": "g"}, bd, profile, now=NOW)
    by = {i["label"]: i for i in items}
    assert by["budget is real"]["ok"] is None
    assert "negotiable" in by["budget is real"]["detail"]


def test_empty_breakdown_never_crashes(profile):
    items = checklist({"title": "g"}, {}, profile, now=NOW)
    assert len(items) == 5
    assert all(i["ok"] in (True, False, None) for i in items)


# ---------------------------------------------------------------- endpoint

def _seed(title: str = "React + Stripe dashboard", user_id: int | None = None) -> int:
    rid, _ = db.upsert_job(
        {"guid": f"ck-{title[:6]}-{user_id}", "source": "freelancer", "title": title,
         "url": "https://example.com/x", "body": "$900 fixed, react + stripe",
         "tags": ["react"]},
        85, BD_GOOD, "", user_id=user_id,
    )
    return rid


def test_checklist_endpoint(authed):
    rid = _seed(user_id=db.user_by_email("check@test.dev")["id"])
    r = authed.get(f"/api/jobs/{rid}/checklist")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert len(d["items"]) == 5
    assert {i["ok"] for i in d["items"]} <= {True, False, None}


def test_checklist_requires_ownership(authed):
    _seed(user_id=None)  # local-pool job, but a different account exists below
    other = authed.post("/api/auth/register",
                        json={"email": "other@test.dev", "password": "pw123456"})
    assert other.status_code == 200
    # fresh login as the other user on a new client instance
    config.init_files()
    c2 = TestClient(create_app(start_poller=False))
    c2.post("/api/auth/login", json={"email": "other@test.dev", "password": "pw123456"})
    rid = _seed(title="Someone else's gig", user_id=999)
    r = c2.get(f"/api/jobs/{rid}/checklist")
    assert r.status_code in (403, 404)


def test_checklist_404_on_missing(authed):
    r = authed.get("/api/jobs/424242/checklist")
    assert r.status_code == 404
