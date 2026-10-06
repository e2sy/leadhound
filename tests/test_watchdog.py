"""The watchdog — a dead poller gets restarted with exponential backoff,
dead pocket bots get respawned from the db's own arm-state, and every
restart lands in the vitals. The supervisor must never itself fall."""

from __future__ import annotations

import threading
import time

import pytest

from leadhound import api as api_mod
from leadhound.api import (
    _backoff_delay,
    _listeners,
    _poller_state,
    _watch_loop,
    _watchdog_cfg,
    _watchdog_state,
    create_app,
    poller_health,
)


@pytest.fixture(autouse=True)
def clean_state():
    before_poller = dict(_poller_state)
    before_wd = dict(_watchdog_state)
    before_cfg = dict(_watchdog_cfg)
    before_listeners = dict(_listeners)
    _listeners.clear()
    yield
    _poller_state.clear()
    _poller_state.update(before_poller)
    _watchdog_state.clear()
    _watchdog_state.update(before_wd)
    _watchdog_cfg.clear()
    _watchdog_cfg.update(before_cfg)
    _listeners.clear()
    _listeners.update(before_listeners)


def test_backoff_doubles_and_caps():
    assert _backoff_delay(0) == 1
    assert _backoff_delay(1) == 2
    assert _backoff_delay(3) == 8
    assert _backoff_delay(30) == 900  # cap: never more than 15 min


def test_dead_poller_is_restarted(monkeypatch):
    db = api_mod.db
    monkeypatch.setattr(db, "enabled_connector_rows", lambda: [])
    api_mod.db.ensure_db()
    stop_event = threading.Event()
    _watchdog_cfg.update({"stop": stop_event, "interval_min": 5})
    _poller_state["running"] = True
    # a corpse: the thread has finished, but the flag still claims hunting
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    _poller_state["thread"] = dead

    watch_stop = threading.Event()
    w = threading.Thread(target=_watch_loop, args=(watch_stop, 0.05), daemon=True)
    w.start()
    deadline = time.time() + 5
    while _watchdog_state["restarts"] < 1 and time.time() < deadline:
        time.sleep(0.02)
    watch_stop.set()
    w.join(timeout=5)
    assert _watchdog_state["restarts"] >= 1
    assert _watchdog_state["last_reason"] == "poller thread died mid-hunt"
    assert poller_health()["thread_alive"] is True  # fresh thread on duty
    stop_event.set()  # retire the replacement quietly


def test_restarts_stay_off_during_shutdown():
    # stop event already set: the watchdog must not resurrect anything
    stop_event = threading.Event()
    stop_event.set()
    _watchdog_cfg.update({"stop": stop_event, "interval_min": 5})
    _poller_state["running"] = True
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    _poller_state["thread"] = dead
    before = _watchdog_state["restarts"]
    watch_stop = threading.Event()
    w = threading.Thread(target=_watch_loop, args=(watch_stop, 0.02), daemon=True)
    w.start()
    time.sleep(0.15)
    watch_stop.set()
    w.join(timeout=5)
    assert _watchdog_state["restarts"] == before  # no restarts during shutdown


def test_dead_listener_is_respawned(monkeypatch):
    db = api_mod.db
    spawned: list[int] = []
    alive = threading.Thread(target=lambda: None)
    alive.start()
    alive.join()  # not alive — but for the FIRST pass we use a live fake

    def fake_spawn(**kw):
        spawned.append(kw["user_id"])
        live = threading.Event()
        t = threading.Thread(target=live.wait, daemon=True)
        t.start()
        return None, t

    monkeypatch.setattr(api_mod.tgbot, "spawn", fake_spawn)
    monkeypatch.setattr(db, "listen_enabled_rows", lambda: [42])
    monkeypatch.setattr(
        db, "notify_cfg",
        lambda uid: {"telegram_token": "1:2", "telegram_chat_id": "3",
                     "listen_enabled": 1},
    )
    _watchdog_cfg["deps_factory"] = lambda uid: {"user_id": uid}

    watch_stop = threading.Event()
    w = threading.Thread(target=_watch_loop, args=(watch_stop, 0.05), daemon=True)
    w.start()
    deadline = time.time() + 5
    while 42 not in _listeners and time.time() < deadline:
        time.sleep(0.02)
    # let a second pass run: the live bot must NOT be respawned again
    time.sleep(0.2)
    watch_stop.set()
    w.join(timeout=5)
    assert spawned.count(42) == 1  # respawned once, then left alone
    assert _watchdog_state["listener_restarts"] >= 1


def test_watchdog_vitals_in_health():
    from fastapi.testclient import TestClient

    from leadhound import config as config_mod

    config_mod.init_files()
    body = TestClient(create_app(start_poller=False)).get("/api/health").json()
    wd = body["poller"]["watchdog"]
    assert wd["running"] is False
    assert wd["restarts"] == 0
    assert "thread" not in wd  # never leak thread objects into the API


def test_watchdog_survives_own_crashes(monkeypatch):
    _watchdog_cfg["deps_factory"] = lambda uid: {}  # reach the crashing path
    monkeypatch.setattr(
        api_mod.db, "listen_enabled_rows",
        lambda: (_ for _ in ()).throw(RuntimeError("db gone")),
    )
    watch_stop = threading.Event()
    w = threading.Thread(target=_watch_loop, args=(watch_stop, 0.02), daemon=True)
    w.start()
    time.sleep(0.15)
    watch_stop.set()
    w.join(timeout=5)
    assert not w.is_alive()  # the supervisor itself never dies
    assert "db gone" in (_watchdog_state["last_error"] or "")
