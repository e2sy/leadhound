"""Follow-up bump tests — auto-schedule on fire, human-gated sending,
outcome cancels the chase, scoping, the voice template and the API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.config import Profile
from leadhound.engine.voice import followup_draft


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()
    yield


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "bump@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def _sent_job(guid: str = "fu-1", user_id: int | None = None) -> int:
    rid, _ = db.upsert_job(
        {"guid": guid, "source": "freelancer", "title": "React dashboard rebuild",
         "url": f"https://example.com/{guid}", "body": "react work",
         "tags": ["react"]},
        82, {"skills": {"matched": ["react"]}}, "the proposal", user_id=user_id,
    )
    db.mark_sniped(rid, "kit", "test shot")
    return rid


# ---------------------------------------------------------------- db layer

def test_firing_auto_schedules_a_bump():
    rid = _sent_job("fu-auto")
    fu = db.followup_for_job(rid)
    assert fu is not None
    assert fu["status"] == "scheduled"
    assert fu["count"] == 0


def test_refire_does_not_duplicate_the_bump():
    rid = _sent_job("fu-dup")
    db.mark_sniped(rid, "kit", "second record")  # refetch/refire path
    rows = db.followups_for(None)
    assert len([f for f in rows if f["job_id"] == rid]) == 1


def test_schedule_reschedules_and_sent_blocks():
    rid = _sent_job("fu-resched")
    assert db.schedule_followup(rid, days=5) is True
    fu = db.followup_for_job(rid)
    assert fu["status"] == "scheduled"
    db.followup_mark_sent(fu["id"])
    assert db.schedule_followup(rid, days=5) is False  # already fired once
    assert db.followup_for_job(rid)["count"] == 1


def test_outcome_cancels_pending_bump():
    rid = _sent_job("fu-cancel")
    db.set_outcome(rid, "won")
    assert db.followup_for_job(rid)["status"] == "cancelled"


def test_due_only_filters_by_time():
    rid = _sent_job("fu-due")
    c = db._conn()  # poke due_at into the past — sqlite owns the clock
    c.execute("UPDATE followups SET due_at = datetime('now', '-1 day') WHERE job_id = ?", (rid,))
    c.commit()
    c.close()
    due = db.followups_for(None, due_only=True)
    assert [f["job_id"] for f in due] == [rid]


def test_followups_scoped_per_account():
    rid = _sent_job("fu-scope", user_id=11)
    assert len(db.followups_for(11)) == 1
    assert db.followups_for(12) == []


# ---------------------------------------------------------------- voice

def test_bump_template_is_short_and_honest():
    p = Profile(name="Mayank")
    text = followup_draft({"title": "React dashboard rebuild", "_matched": ["react"]}, p)
    assert "React dashboard" in text
    assert "react" in text
    assert "yes/no" in text
    assert text.endswith("— Mayank")
    assert len(text) < 600


def test_second_bump_sounds_different():
    p = Profile(name="Mayank")
    a = followup_draft({"title": "Gig"}, p, count=0)
    b = followup_draft({"title": "Gig"}, p, count=1)
    assert "last" in b and "last" not in a


# ---------------------------------------------------------------- api

def test_followup_endpoints(authed):
    uid = db.user_by_email("bump@test.dev")["id"]
    rid = _sent_job("fu-api", user_id=uid)
    r = authed.post(f"/api/jobs/{rid}/followup", json={"days": 2})
    assert r.status_code == 200
    fid = r.json()["followup"]["id"]
    r = authed.post(f"/api/followups/{fid}/fire")
    assert r.status_code == 200
    text = r.json()["text"]
    assert "React dashboard" in text
    r = authed.get("/api/followups")
    assert r.json()["due"] == []  # fired one is no longer scheduled


def test_followup_requires_ownership(authed):
    rid = _sent_job("fu-owner", user_id=987)  # someone else's gig
    authed.post("/api/auth/register",
                json={"email": "intruder@test.dev", "password": "pw123456"})
    c2 = TestClient(create_app(start_poller=False))
    c2.post("/api/auth/login", json={"email": "intruder@test.dev", "password": "pw123456"})
    r = c2.post(f"/api/jobs/{rid}/followup", json={"days": 2})
    assert r.status_code in (403, 404)


def test_followup_rejected_on_non_sent_gig(authed):
    uid = db.user_by_email("bump@test.dev")["id"]
    rid, _ = db.upsert_job(
        {"guid": "fu-pending", "source": "guru", "title": "pending gig",
         "url": "u", "body": "b", "tags": []},
        50, {}, "", user_id=uid,
    )
    r = authed.post(f"/api/jobs/{rid}/followup", json={"days": 2})
    assert r.status_code == 400
