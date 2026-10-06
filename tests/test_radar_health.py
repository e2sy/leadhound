"""Radar honesty — the poller heartbeat, deep /api/health, stalled detection.

The contract: "running" must never be a lie. If the thread died, the radar
says so; if a sweep crashed, the error shows up in the vitals."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from leadhound import config
from leadhound.api import (
    _listeners,
    _poll_loop,
    _poller_state,
    create_app,
    poller_health,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Snapshot module state — earlier suites may have armed pocket listeners
    or ticked the radar; this suite starts from a clean pillbox every time."""
    before_state = dict(_poller_state)
    before_listeners = dict(_listeners)
    _listeners.clear()
    yield
    _poller_state.clear()
    _poller_state.update(before_state)
    _listeners.clear()
    _listeners.update(before_listeners)


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "radar@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def test_health_reports_vitals(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert body["listeners"] == 0
    p = body["poller"]
    assert p["running"] is False
    assert p["thread_alive"] is False
    assert p["stalled"] is False  # not running = not stalled, just off
    assert "version" in body


def test_health_leaks_no_user_data(client):
    # health is unauthenticated: it must stay aggregate-only
    client.post("/api/auth/register",
                json={"email": "secret@test.dev", "password": "hunter2boogaloo"})
    body = client.get("/api/health").text
    assert "secret@test.dev" not in body
    assert "email" not in body


def test_stalled_detection(clean_state):
    # running + a heartbeat older than 3x interval = stalled, honestly
    _poller_state.update({"running": True, "interval": 15, "thread": None,
                          "last_tick": "2000-01-01 00:00:00"})
    assert poller_health()["stalled"] is True
    assert poller_health()["thread_alive"] is False

    # fresh heartbeat → hunting, not stalled
    _poller_state["last_tick"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    _poller_state["thread"] = threading.Thread(target=lambda: None, daemon=True)
    _poller_state["thread"].start()
    _poller_state["thread"].join()
    h = poller_health()
    assert h["stalled"] is False
    assert h["last_tick_age_s"] < 60


def test_running_but_never_ticked_is_stalled(clean_state):
    _poller_state.update({"running": True, "interval": 5,
                          "last_tick": None, "started_at": None})
    h = poller_health()
    assert h["stalled"] is True  # promised to hunt, no heartbeat yet


def test_radar_includes_heartbeat(authed):
    r = authed.get("/api/radar")
    assert r.status_code == 200
    body = r.json()
    assert "stalled" in body
    assert "sweeps" in body
    assert body["poller"]["running"] is False


def test_poll_loop_survives_sweep_crashes(clean_state, monkeypatch):
    """A crashing sweep must not kill the radar: error recorded, tick still
    lands, next sweep still happens."""
    from leadhound import api as api_mod

    calls = {"n": 0}

    def boom(uid, cid, *, late_before=None):
        calls["n"] += 1
        raise RuntimeError("db vanished mid-sweep")

    monkeypatch.setattr(api_mod, "run_connector_for", boom)
    monkeypatch.setattr(api_mod.db, "enabled_connector_rows",
                        lambda: [(1, "remoteok")])
    api_mod.db.ensure_db()  # the sweep reads real per-connector configs
    stop = threading.Event()
    t = threading.Thread(target=_poll_loop,
                         args=(stop, 5, 0.05), daemon=True)  # fast first delay
    t.start()
    deadline = time.time() + 5
    while calls["n"] < 2 and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()  # the thread survived two crashes
    assert calls["n"] >= 2   # and kept sweeping
    h = poller_health()
    assert h["sweeps"] >= 2
    assert h["last_tick"] is not None
    assert "db vanished" in (h["last_error"] or "")


def test_poll_loop_records_started_at(clean_state, monkeypatch):
    from leadhound import api as api_mod

    monkeypatch.setattr(api_mod.db, "enabled_connector_rows", lambda: [])
    stop = threading.Event()
    t = threading.Thread(target=_poll_loop, args=(stop, 5, 0.05), daemon=True)
    t.start()
    deadline = time.time() + 5
    while _poller_state["sweeps"] < 1 and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    t.join(timeout=5)
    assert _poller_state["started_at"] is not None
    assert poller_health()["uptime_s"] >= 0
