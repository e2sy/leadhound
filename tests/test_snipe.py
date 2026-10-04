"""Sniper endpoint tests — real bid placement is mocked; nothing leaves localhost."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "sniper@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def _seed_fl(guid: str = "freelancer-40744513", status: str = "pending",
             draft: str = "Saw your React gig — I ship these weekly.",
             budget_max: float | None = 1500.0, source: str = "freelancer") -> int:
    db.ensure_db()
    db.upsert_job(
        {
            "guid": guid,
            "source": source,
            "title": "Build a React dashboard",
            "url": f"https://www.freelancer.com/projects/x/{guid}",
            "body": "Need a react developer.",
            "tags": ["react"],
            "budget_max": budget_max,
        },
        88,
        {"skills": {"matched": ["react"]}, "red_flags": []},
        draft,
    )
    jid = next(j.id for j in db.all_jobs() if j.guid == guid)
    if status != "pending":
        db.set_status(jid, status)
    return jid


def _link(authed: TestClient, *, tok):
    me = authed.get("/api/auth/me").json()["user"]["id"]
    db.save_connector_cfg(
        me, "freelancer_account",
        settings={"client_id": "cid", "client_secret": "sec",
                  "access_token": tok, "refresh_token": "r", "expires_at": 10**12,
                  "identity": {"id": 9, "username": "mayank", "display_name": "Mayank"}},
    )


# ------------------------------------------------------------------- plan
def test_plan_is_kit_when_not_linked(authed):
    jid = _seed_fl()
    d = authed.get(f"/api/jobs/{jid}/snipe-plan").json()
    assert d["mode"] == "kit" and d["linked"] is False
    assert d["project_id"] == 40744513  # freelancer gig, but account not linked
    assert "React" in d["text"]


def test_plan_is_api_when_linked(authed):
    jid = _seed_fl()
    _link(authed, tok="tok-1")
    d = authed.get(f"/api/jobs/{jid}/snipe-plan").json()
    assert d["mode"] == "api" and d["linked"] is True
    assert d["identity"]["username"] == "mayank"
    assert d["amount"] == 1500.0


def test_plan_kit_for_non_freelancer_source(authed):
    jid = _seed_fl(guid="remoteok-777", source="remoteok")
    d = authed.get(f"/api/jobs/{jid}/snipe-plan").json()
    assert d["mode"] == "kit" and d["project_id"] is None


def test_plan_rejects_already_sniped(authed):
    jid = _seed_fl(status="sent")
    assert authed.get(f"/api/jobs/{jid}/snipe-plan").status_code == 400


def test_plan_404_for_foreign_job(client, authed):
    jid = _seed_fl()
    client.post("/api/auth/register",
                json={"email": "other@test.dev", "password": "hunter2boogaloo"})
    j = db.get_job(jid)
    db._conn()  # keep sqlite happy on some platforms
    r = authed.get(f"/api/jobs/{j.id}/snipe-plan")  # same user, fine
    assert r.status_code == 200


# ------------------------------------------------------------------- fire
def test_fire_requires_linked_account(authed):
    jid = _seed_fl()
    r = authed.post(f"/api/jobs/{jid}/snipe", json={"amount": 1500})
    assert r.status_code == 400
    assert "linked" in r.json()["detail"]


def test_fire_places_real_bid_and_audits(authed, monkeypatch):
    jid = _seed_fl()
    _link(authed, tok="tok-1")
    seen = {}

    def fake_place_bid(settings, pid, **kw):
        seen["pid"] = pid
        seen.update(kw)
        return {"id": 424242}, None

    monkeypatch.setattr("leadhound.api._fla.place_bid", fake_place_bid)
    r = authed.post(f"/api/jobs/{jid}/snipe", json={"amount": 1200, "period": 5})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "api" and d["bid_id"] == 424242
    assert seen["pid"] == 40744513
    assert seen["amount"] == 1200 and seen["period"] == 5
    job = db.get_job(jid)
    assert job.status == "sent"
    assert job.snipe_method == "freelancer-api"
    assert job.snipe_note == "bid #424242"
    assert job.sniped_at is not None


def test_fire_persists_refreshed_tokens(authed, monkeypatch):
    jid = _seed_fl()
    _link(authed, tok="tok-1")
    monkeypatch.setattr(
        "leadhound.api._fla.place_bid",
        lambda s, p, **k: ({"id": 1}, {"access_token": "brand-new", "expires_at": 10**12}),
    )
    authed.post(f"/api/jobs/{jid}/snipe", json={"amount": 100})
    me = authed.get("/api/auth/me").json()["user"]["id"]
    cfg = db.connector_cfg(me, "freelancer_account")
    assert cfg["settings"]["access_token"] == "brand-new"


def test_fire_maps_api_error_to_502(authed, monkeypatch):
    from leadhound.connectors import freelancer_account as _fla

    jid = _seed_fl()
    _link(authed, tok="tok-1")

    def boom(*a, **k):
        raise _fla.FreelancerError("bid too low for this project")

    monkeypatch.setattr("leadhound.api._fla.place_bid", boom)
    r = authed.post(f"/api/jobs/{jid}/snipe", json={"amount": 1})
    assert r.status_code == 502
    assert "bid too low" in r.json()["detail"]


def test_fire_rejects_zero_amount(authed):
    jid = _seed_fl()
    _link(authed, tok="tok-1")
    r = authed.post(f"/api/jobs/{jid}/snipe", json={"amount": 0})
    assert r.status_code == 400


# ----------------------------------------------------------------- confirm
def test_confirm_marks_kit_snipe(authed):
    jid = _seed_fl()
    r = authed.post(f"/api/jobs/{jid}/snipe-confirm")
    assert r.status_code == 200
    job = db.get_job(jid)
    assert job.status == "sent" and job.snipe_method == "kit"


# ------------------------------------------------------------------- state
def test_state_carries_snipe_stats_and_link(authed, tok="tok-1"):
    jid = _seed_fl()
    authed.post(f"/api/jobs/{jid}/snipe-confirm")
    d = authed.get("/api/state").json()
    assert d["snipe"]["sniped_total"] == 1
    assert d["linked"]["freelancer"] is False
