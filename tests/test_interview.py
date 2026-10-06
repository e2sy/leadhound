"""Interview kit tests — questions from gaps, honest money frame,
talking points from your own highlights, red lines, formatting + API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.config import Profile
from leadhound.engine.interview import build_kit, format_kit


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "kit@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def profile():
    return Profile(
        name="Mayank",
        skills=["react", "stripe"],
        min_hourly=40.0,
        min_fixed_budget=1000.0,
        highlights=["Shipped 10 apps to production"],
        red_flags=["unpaid trial"],
    )


BD = {"skills": {"matched": ["react", "stripe"]}, "red_flags": []}


def test_questions_target_the_gaps(profile):
    job = {"title": "React app", "body": "we need a react app"}  # no money/date/scope
    kit = build_kit(job, profile, BD)
    qs = " ".join(kit["questions"])
    assert "budget range" in qs          # money missing
    assert "hard date" in qs             # no timeline words
    assert "deliverables" in qs          # no scope words
    assert "sign-off" in qs              # always ask who decides


def test_complete_post_skips_obvious_questions(profile):
    job = {
        "title": "React app",
        "body": "budget $3000, deliverable is a dashboard, timeline 3 weeks, "
                "milestone based",
        "budget_min": 3000.0,
        "budget_max": 3000.0,
    }
    kit = build_kit(job, profile, BD)
    qs = " ".join(kit["questions"])
    assert "budget range" not in qs
    assert "hard date" not in qs
    assert "deliverables for the first milestone" not in qs


def test_hourly_money_frame(profile):
    job = {"title": "T", "body": "x", "hourly": 55.0}
    kit = build_kit(job, profile, BD)
    assert kit["money"]["floor"] == 40.0
    assert kit["money"]["opening"] == 50.0   # 1.25 x floor
    assert "floor" in kit["money"]["note"]


def test_fixed_money_frame_anchors_on_their_range(profile):
    job = {"title": "T", "body": "x", "budget_max": 2000.0}
    kit = build_kit(job, profile, BD)
    assert kit["money"]["opening"] == 2300.0  # 1.15 x top
    assert "milestone" in kit["money"]["note"]


def test_no_budget_means_they_name_a_number(profile):
    kit = build_kit({"title": "T", "body": "x"}, profile, BD)
    assert kit["money"]["opening"] is None
    assert "THEM" in kit["money"]["note"]


def test_talking_points_come_from_your_profile(profile):
    job = {"title": "T", "body": "x"}
    kit = build_kit(job, profile, BD)
    assert any("react" in p for p in kit["talking_points"])
    assert "Shipped 10 apps to production" in kit["talking_points"]


def test_red_lines_naming(profile):
    bd = {"skills": {"matched": []}, "red_flags": ["unpaid trial"]}
    kit = build_kit({"title": "T", "body": "x"}, profile, bd)
    assert any("unpaid trial" in r for r in kit["red_lines"])


def test_format_kit_renders_all_sections(profile):
    kit = build_kit({"title": "React app", "body": "x", "hourly": 50}, profile, BD)
    text = format_kit(kit)
    assert "interview kit" in text
    assert "ask:" in text and "money:" in text and "say:" in text


# ---------------------------------------------------------------- api

def test_kit_endpoint_generates_and_caches(authed):
    uid = db.user_by_email("kit@test.dev")["id"]
    rid, _ = db.upsert_job(
        {"guid": "kit-1", "source": "freelancer", "title": "React dash",
         "url": "u", "body": "react work", "tags": [], "hourly": 60.0},
        85, BD, "", user_id=uid,
    )
    r = authed.get(f"/api/jobs/{rid}/kit")
    assert r.status_code == 200
    kit = r.json()["kit"]
    assert kit["title"] == "React dash"
    assert db.interview_kit(rid) is not None      # cached
    r2 = authed.post(f"/api/jobs/{rid}/kit")      # explicit rebuild
    assert r2.status_code == 200


def test_kit_404_and_ownership(authed):
    assert authed.get("/api/jobs/99999/kit").status_code == 404
    rid, _ = db.upsert_job(
        {"guid": "kit-2", "source": "guru", "title": "X", "url": "u",
         "body": "b", "tags": []},
        50, {}, "", user_id=321,
    )
    assert authed.get(f"/api/jobs/{rid}/kit").status_code in (403, 404)
