"""Freelancer webhook receiver — instant detection over the front door.

Contract: HMAC or nothing (401), 503 until a secret is armed, 202 for
events with nothing to hunt, 200 with real ingest otherwise. The gig a
webhook delivers must look exactly like a gig the poller fetched."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import _hook_state, create_app
from leadhound.connectors import freelancer_hook as hook


@pytest.fixture(autouse=True)
def clean_hook_state():
    """Module counters survive across tests — reset them each run."""
    before = dict(_hook_state)
    _hook_state.update({"events": 0, "ingested": 0, "last_event_at": None,
                        "last_signature_ok": None})
    yield
    _hook_state.clear()
    _hook_state.update(before)


SECRET = "whsec_test_0123456789abcdef"

PROJECT = {
    "id": 4242,
    "title": "Build a <b>React</b> dashboard",
    "seo_url": "react-dashboard-4242",
    "preview_description": "Need react + stripe work. Budget $3,000.",
    "jobs": [{"name": "React.js"}, {"name": "Stripe"}],
    "budget": {"minimum": 2500, "maximum": 3000},
    "type": "fixed",
    "submitdate": 1767000000,
}


def _sign(raw: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _armed_client():
    config.init_files()
    client = TestClient(create_app())
    client.post("/api/auth/register",
                json={"email": "hook@test.dev", "password": "hunter2boogaloo"})
    uid = db.user_by_email("hook@test.dev")["id"]
    db.save_connector_cfg(
        uid, "freelancer",
        enabled=True,
        settings={"query": "react", "webhook_secret": SECRET},
    )
    return client


def test_verify_signature_accepts_and_rejects():
    raw = b'{"x": 1}'
    headers = {"X-Freelancer-Signature": _sign(raw)}
    assert hook.verify_signature(SECRET, raw, headers) is True
    # sha256= prefix + different casing + different common header name
    headers = {"X-Hub-Signature-256": "sha256=" + _sign(raw).upper()}
    assert hook.verify_signature(SECRET, raw, headers) is True
    assert hook.verify_signature(SECRET, raw, {"X-Freelancer-Signature": "nope"}) is False
    assert hook.verify_signature(SECRET, raw, {}) is False
    assert hook.verify_signature("", raw, {"X-Signature": _sign(raw)}) is False
    other = _sign(b'{"y": 2}')
    assert hook.verify_signature(SECRET, raw, {"X-Signature": other}) is False


def test_parse_event_shapes():
    jobs = hook.parse_event({"type": "project:posted", "data": {"project": PROJECT}})
    assert len(jobs) == 1
    j = jobs[0]
    assert j["guid"] == "freelancer-4242"
    assert j["source"] == "freelancer"
    assert j["title"] == "Build a React dashboard"  # tags stripped, spaces collapsed
    assert j["url"] == "https://www.freelancer.com/projects/react-dashboard-4242"
    assert j["budget_max"] == 3000
    assert j["hourly"] is None  # fixed project
    assert j["tags"] == ["React.js", "Stripe"]

    # project at the top level also works
    assert hook.parse_event({"project": PROJECT})[0]["guid"] == "freelancer-4242"
    # hourly projects carry the hourly floor
    hourly = dict(PROJECT, type="hourly")
    assert hook.parse_event({"project": hourly})[0]["hourly"] == 2500


def test_parse_event_rejects_junk():
    assert hook.parse_event({}) == []
    assert hook.parse_event({"data": {"project": {"id": 1}}}) == []  # no title
    assert hook.parse_event({"data": {"project": dict(PROJECT, deleted=True)}}) == []
    assert hook.parse_event({"data": {"project": dict(PROJECT, nonpublic=True)}}) == []
    assert hook.parse_event({"type": "user:login", "data": {}}) == []
    assert hook.parse_event("not-a-dict") == []


def test_receiver_full_shot():
    client = _armed_client()
    body = json.dumps({"type": "project:posted", "data": {"project": PROJECT}}).encode()
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Freelancer-Signature": _sign(body),
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["ingested"] == 1

    # the gig landed on the board, scored and scoped to its owner
    uid = db.user_by_email("hook@test.dev")["id"]
    jobs = [j for j in db.all_jobs(limit=50, user_id=uid) if j.source == "freelancer"]
    assert any(j.guid == "freelancer-4242" for j in jobs)

    # replay the same event: dedupe wins, nothing double-pushes
    r2 = client.post("/webhook/freelancer", content=body,
                     headers={"X-Freelancer-Signature": _sign(body)})
    assert r2.status_code == 200
    assert r2.json()["ingested"] == 0


def test_receiver_holds_the_line():
    client = _armed_client()
    body = b'{"data": {"project": ' + json.dumps(PROJECT).encode() + b"}}"

    # no signature at all
    r = client.post("/webhook/freelancer", content=body)
    assert r.status_code == 401
    # forged signature
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Signature": _sign(b"tampered")})
    assert r.status_code == 401
    # signature for a different secret (multi-tenant: other users' secrets
    # must not open this door)
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Signature": _sign(body, "whsec_other")})
    assert r.status_code == 401
    # garbage body
    r = client.post("/webhook/freelancer", content=b"not json",
                    headers={"X-Signature": _sign(b"not json")})
    assert r.status_code == 400


def test_receiver_503_until_armed():
    config.init_files()
    client = TestClient(create_app())
    body = json.dumps({"data": {"project": PROJECT}}).encode()
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Signature": _sign(body)})
    assert r.status_code == 503
    assert "not armed" in r.json()["error"]


def test_receiver_202_for_events_with_no_project():
    client = _armed_client()
    body = json.dumps({"type": "user:login", "data": {"user": {"id": 1}}}).encode()
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Signature": _sign(body)})
    assert r.status_code == 202
    assert r.json()["ingested"] == 0


def test_disabled_connector_hunts_nothing():
    config.init_files()
    client = TestClient(create_app())
    client.post("/api/auth/register",
                json={"email": "off@test.dev", "password": "hunter2boogaloo"})
    uid = db.user_by_email("off@test.dev")["id"]
    db.save_connector_cfg(uid, "freelancer", enabled=False,
                          settings={"webhook_secret": SECRET})
    body = json.dumps({"data": {"project": PROJECT}}).encode()
    r = client.post("/webhook/freelancer", content=body,
                    headers={"X-Signature": _sign(body)})
    assert r.status_code == 200
    assert r.json()["ingested"] == 0  # verified but the radar is off


def test_radar_reports_webhook_vitals():
    client = _armed_client()
    r = client.get("/api/radar")
    assert r.status_code == 200
    w = r.json()["webhook"]
    assert w["armed"] is True
    assert w["receiver"] == "/webhook/freelancer"
    assert w["events"] == 0 and w["ingested"] == 0
    assert "SECRET" not in r.text


def test_radar_counts_events_and_ingests():
    client = _armed_client()
    body = json.dumps({"data": {"project": PROJECT}}).encode()
    client.post("/webhook/freelancer", content=body,
                headers={"X-Signature": _sign(body)})
    w = client.get("/api/radar").json()["webhook"]
    assert w["events"] == 1
    assert w["ingested"] == 1
    assert w["last_event_at"] is not None
    assert w["last_signature_ok"] is True


def test_rotate_mints_a_fresh_secret():
    client = _armed_client()
    r = client.post("/api/webhook/freelancer/rotate")
    assert r.status_code == 200
    new = r.json()["secret"]
    assert len(new) >= 32
    # the old one is dead, the new one opens the door
    body = json.dumps({"data": {"project": PROJECT}}).encode()
    assert client.post("/webhook/freelancer", content=body,
                       headers={"X-Signature": _sign(body)}).status_code == 401
    assert client.post("/webhook/freelancer", content=body,
                       headers={"X-Signature": _sign(body, new)}).status_code == 200
    # rotation needs a login
    assert TestClient(create_app()).post(
        "/api/webhook/freelancer/rotate").status_code == 401


def test_rotate_secret_never_leaks_through_connectors():
    client = _armed_client()
    new = client.post("/api/webhook/freelancer/rotate").json()["secret"]
    r = client.get("/api/connectors")
    assert new not in r.text  # the raw secret stays out of every listing
    assert "•••" in r.text    # masked like every other secret
