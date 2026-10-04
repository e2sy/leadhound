"""API tests — real HTTP round-trips through FastAPI's TestClient.

Covers the auth gate, account-scoped board data, pipeline mutations, demo
seeding and the connectors endpoints (with a stubbed connector so no test
touches the network).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import build_state, create_app
from leadhound.connectors import REGISTRY, Connector, Field


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


def _seed(guid: str, score: int, title: str, status: str = "pending",
          outcome: str | None = None, user_id: int | None = None) -> int:
    db.upsert_job(
        {
            "guid": guid,
            "source": "remoteok",
            "title": title,
            "url": f"https://example.com/{guid}",
            "body": "We need a react developer with stripe experience.",
            "tags": ["react", "stripe"],
        },
        score,
        {
            "budget": {"hourly": 60, "fixed_min": None, "note": "above your minimum"},
            "skills": {"matched": ["react", "stripe"]},
            "red_flags": [] if score > 50 else ["unpaid test gig"],
        },
        f"Draft for {title}.",
        user_id=user_id,
    )
    jid = next(j.id for j in db.all_jobs() if j.guid == guid)
    if status != "pending":
        db.set_status(jid, status)
    if outcome:
        db.set_outcome(jid, outcome)
    return jid


# ----------------------------------------------------------------- health/faq
class TestHealth:
    def test_health_no_auth(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["version"]

    def test_radar_requires_login(self, client):
        assert client.get("/api/radar").status_code == 401

    def test_radar_status_shape(self, authed):
        r = authed.get("/api/radar")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["running"] is False  # TestClient boots without the poller
        assert "interval_minutes" in d and "enabled_sources" in d
        assert d["enabled_sources"] == 0

    def test_root_serves_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "LEADHOUND" in r.text and "/api/state" in r.text

    def test_favicon(self, client):
        assert client.get("/favicon.ico").status_code == 204


# ---------------------------------------------------------------------- auth
class TestAuthGate:
    def test_state_requires_login(self, client):
        assert client.get("/api/state").status_code == 401
        assert client.get("/api/connectors").status_code == 401
        assert client.post("/api/demo").status_code == 401

    def test_register_login_logout_flow(self, client):
        r = client.post("/api/auth/register",
                        json={"email": "flow@test.dev", "password": "hunter2boogaloo"})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "flow@test.dev"
        assert client.get("/api/state").status_code == 200

        client.post("/api/auth/logout")
        assert client.get("/api/state").status_code == 401

        r = client.post("/api/auth/login",
                        json={"email": "flow@test.dev", "password": "hunter2boogaloo"})
        assert r.status_code == 200
        assert client.get("/api/state").status_code == 200

    def test_register_duplicate_conflict(self, authed):
        r = authed.post("/api/auth/register",
                        json={"email": "sniper@test.dev", "password": "hunter2boogaloo"})
        assert r.status_code == 409

    def test_register_weak_password(self, client):
        r = client.post("/api/auth/register", json={"email": "w@test.dev", "password": "short"})
        assert r.status_code == 400

    def test_login_wrong_password(self, authed):
        r = authed.post("/api/auth/login",
                        json={"email": "sniper@test.dev", "password": "totally-wrong"})
        assert r.status_code == 401


# ---------------------------------------------------------------------- board
class TestBoard:
    def test_state_shape_and_demo_flag(self, authed):
        _seed("s1", 90, "Hot gig")
        st = authed.get("/api/state").json()
        assert set(st) == {"stats", "calibration", "jobs", "demo", "user"}
        assert st["demo"] is False
        assert st["stats"]["total"] == 1
        assert st["jobs"][0]["title"] == "Hot gig"
        assert st["jobs"][0]["matched"] == ["react", "stripe"]
        assert st["user"]["email"] == "sniper@test.dev"

    def test_body_preview_truncated(self, authed):
        db.upsert_job(
            {"guid": "long", "source": "x", "title": "Long", "url": "https://e.com",
             "body": "x" * 5000, "tags": []},
            50, {}, "",
        )
        j = authed.get("/api/state").json()["jobs"][0]
        assert len(j["body"]) <= 401 and j["body"].endswith("…")

    def test_account_scoping(self, authed):
        _seed("mine", 80, "Mine", user_id=1)          # account 1 = first user
        _seed("theirs", 80, "Theirs", user_id=42)     # another account
        _seed("cli", 70, "CliPool")                   # CLI pool (user_id NULL)
        titles = [j["title"] for j in authed.get("/api/state").json()["jobs"]]
        assert "Mine" in titles and "CliPool" in titles
        assert "Theirs" not in titles

    def test_empty_board_is_200(self, authed):
        d = authed.get("/api/state").json()
        assert d["jobs"] == []


class TestMutations:
    def test_status_transition(self, authed):
        jid = _seed("m1", 77, "Move me", user_id=1)
        r = authed.post("/api/status", json={"id": jid, "status": "approved"})
        assert r.status_code == 200
        assert db.get_job(jid).status == "approved"

    def test_status_rejects_bad_value(self, authed):
        jid = _seed("m2", 60, "Bad status", user_id=1)
        assert authed.post("/api/status",
                           json={"id": jid, "status": "won"}).status_code == 400

    def test_status_unknown_job_404(self, authed):
        assert authed.post("/api/status",
                           json={"id": 9999, "status": "sent"}).status_code == 404

    def test_cannot_touch_other_accounts_job(self, authed):
        jid = _seed("foreign", 66, "Not yours", user_id=42)
        r = authed.post("/api/status", json={"id": jid, "status": "approved"})
        assert r.status_code == 404

    def test_draft_edit(self, authed):
        jid = _seed("m3", 70, "Edit draft", user_id=1)
        assert authed.post("/api/draft",
                           json={"id": jid, "text": "Rewritten!"}).status_code == 200
        assert db.get_job(jid).draft == "Rewritten!"

    def test_outcome_set_and_clear(self, authed):
        jid = _seed("m4", 88, "Outcome me", status="sent", user_id=1)
        assert authed.post("/api/outcome", json={"id": jid, "outcome": "won"}).status_code == 200
        assert db.get_job(jid).outcome == "won"
        assert authed.post("/api/outcome", json={"id": jid, "outcome": "none"}).status_code == 200
        assert db.get_job(jid).outcome is None

    def test_outcome_rejects_bad_value(self, authed):
        jid = _seed("m5", 66, "Bad outcome", status="sent", user_id=1)
        assert authed.post("/api/outcome",
                           json={"id": jid, "outcome": "yolo"}).status_code == 400


class TestDemo:
    def test_demo_seeds_sample_gigs(self, authed):
        r = authed.post("/api/demo")
        assert r.status_code == 200
        assert r.json()["added"] == 4
        st = authed.get("/api/state").json()
        assert st["demo"] is True
        assert st["stats"]["total"] == 4

    def test_demo_idempotent(self, authed):
        authed.post("/api/demo")
        assert authed.post("/api/demo").json()["added"] == 0


# ----------------------------------------------------------------- connectors
class TestConnectors:
    def test_list_includes_all_sources(self, authed):
        data = authed.get("/api/connectors").json()
        ids = {c["id"] for c in data["connectors"]}
        assert {"remoteok", "remotive", "weworkremotely", "hackernews",
                "freelancer", "upwork", "fiverr", "rss"} <= ids
        up = next(c for c in data["connectors"] if c["id"] == "upwork")
        assert up["kind"] == "keys" and up["setup_url"]

    def test_save_settings_and_secret_masking(self, authed):
        r = authed.post("/api/connectors/upwork",
                        json={"settings": {"client_id": "cid-1",
                                           "client_secret": "super-secret",
                                           "query": "react native"}})
        assert r.status_code == 200
        up = next(c for c in r.json()["connectors"] if c["id"] == "upwork")
        assert up["settings"]["client_id"] == "cid-1"
        assert up["settings"]["client_secret"] == "•••"  # masked in the API
        stored = db.connector_cfg(1, "upwork")
        assert stored["settings"]["client_secret"] == "super-secret"  # real value kept

        # re-save with masked value -> stored secret survives
        r2 = authed.post("/api/connectors/upwork",
                         json={"settings": {"client_id": "cid-2",
                                            "client_secret": "•••",
                                            "query": "react"}})
        stored2 = db.connector_cfg(1, "upwork")
        assert stored2["settings"]["client_id"] == "cid-2"
        assert stored2["settings"]["client_secret"] == "super-secret"
        assert r2.status_code == 200

    def test_save_rejects_unknown_fields(self, authed):
        r = authed.post("/api/connectors/remoteok", json={"settings": {"nope": 1}})
        assert r.status_code == 400

    def test_save_unknown_connector_404(self, authed):
        assert authed.post("/api/connectors/ghost",
                           json={"enabled": True}).status_code == 404

    def test_enable_toggle(self, authed):
        authed.post("/api/connectors/remoteok", json={"enabled": True})
        assert db.connector_cfg(1, "remoteok")["enabled"] in (True, 1)
        authed.post("/api/connectors/remoteok", json={"enabled": False})
        assert db.connector_cfg(1, "remoteok")["enabled"] in (False, 0)

    def _install_stub(self, monkeypatch, *, error: str | None = None):
        def fake_fetch(settings):
            if error:
                raise RuntimeError(error)
            return ([{"guid": "stub-1", "source": "stubsource", "title": "Stub gig",
                      "url": "https://e.com/1", "body": "react + stripe", "tags": []}], None)

        monkeypatch.setitem(REGISTRY, "stub", Connector(
            id="stub", label="Stub", kind="public", blurb="stub",
            fields=[Field("query", "Query")], fetch=fake_fetch))

    def test_run_connector_ingests(self, authed, monkeypatch):
        self._install_stub(monkeypatch)
        authed.post("/api/connectors/stub", json={"enabled": True})
        r = authed.post("/api/connectors/stub/run")
        assert r.status_code == 200
        assert r.json()["new"] == 1
        titles = [j["title"] for j in authed.get("/api/state").json()["jobs"]]
        assert "Stub gig" in titles

    def test_run_connector_records_errors_honestly(self, authed, monkeypatch):
        self._install_stub(monkeypatch, error="site exploded")
        authed.post("/api/connectors/stub", json={"enabled": True})
        r = authed.post("/api/connectors/stub/run")
        assert r.status_code == 502
        assert "site exploded" in r.json()["error"]
        data = authed.get("/api/connectors").json()
        stub = next(c for c in data["connectors"] if c["id"] == "stub")
        assert stub["status"]["last_status"] == "error"
        assert "site exploded" in stub["status"]["last_error"]

    def test_fetch_all_with_none_enabled_gives_hint(self, authed):
        r = authed.post("/api/fetch")
        assert r.status_code == 200
        assert "hint" in r.json()

    def test_fetch_all_runs_enabled_sources(self, authed, monkeypatch):
        self._install_stub(monkeypatch)
        authed.post("/api/connectors/stub", json={"enabled": True})
        r = authed.post("/api/fetch")
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 1 and results[0]["new"] == 1

    def test_upwork_auth_start_requires_client_id(self, authed):
        assert authed.post("/api/connectors/upwork/auth/start").status_code == 400

    def test_upwork_auth_start_returns_authorize_url(self, authed):
        authed.post("/api/connectors/upwork",
                    json={"settings": {"client_id": "cid-1", "client_secret": "sec"}})
        r = authed.post("/api/connectors/upwork/auth/start")
        assert r.status_code == 200
        assert r.json()["authorize_url"].startswith("https://www.upwork.com/")
        assert "state=" in r.json()["authorize_url"]
        stored = db.connector_cfg(1, "upwork")["settings"]
        assert stored.get("oauth_state")

    def test_upwork_callback_rejects_bad_state(self, authed):
        r = authed.get("/api/connectors/upwork/callback",
                       params={"code": "abc", "state": "wrong"})
        assert r.status_code == 400


# ------------------------------------------------------------------ build_state
class TestBuildState:
    def test_shape_no_auth_context(self):
        config.init_files()
        _seed("s1", 90, "Hot gig")
        st = build_state()
        assert set(st) == {"stats", "calibration", "jobs", "demo"}
        assert json.dumps(st["stats"])  # serializable
        assert st["jobs"][0]["draft"] == "Draft for Hot gig."
