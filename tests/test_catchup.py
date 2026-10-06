"""Downtime catch-up — gigs that dropped while the hound slept get flagged,
not lost. The late badge is honest: only NEW gigs posted before the reboot
get it, and the catch-up sweep runs exactly once."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from leadhound import api as api_mod
from leadhound import config, db
from leadhound.api import (
    _catchup,
    _listeners,
    _poll_loop,
    _poller_state,
    create_app,
    job_to_dict,
)
from leadhound.config import LLMConfig, Profile
from leadhound.db import Job
from leadhound.pipeline import _is_late, ingest_jobs

PROFILE = Profile(
    name="Test Sniper",
    headline="Full-stack dev",
    skills=["react", "stripe", "python"],
    min_hourly=30.0,
    min_fixed_budget=800.0,
    red_flags=["unpaid"],
    highlights=["Shipped 10 apps"],
    tone_samples=[],
)

OLD = {
    "guid": "c-old",
    "source": "remoteok",
    "title": "Senior React dev for fintech dashboard",
    "url": "https://x/old",
    "body": "We need a react + stripe developer. Budget $3,000 fixed.",
    "tags": ["react", "stripe"],
    "posted_at": "2026-10-06T10:00:00+00:00",
}
FRESH = {
    "guid": "c-fresh",
    "source": "remoteok",
    "title": "React dashboard gig posted after reboot",
    "url": "https://x/fresh",
    "body": "React + stripe again. Budget $4,000 fixed.",
    "tags": ["react", "stripe"],
    "posted_at": "2026-10-06T12:00:00+00:00",
}


@pytest.fixture(autouse=True)
def clean_state():
    before_state = dict(_poller_state)
    before_catchup = dict(_catchup)
    before_listeners = dict(_listeners)
    _listeners.clear()
    yield
    _poller_state.clear()
    _poller_state.update(before_state)
    _catchup.clear()
    _catchup.update(before_catchup)
    _listeners.clear()
    _listeners.update(before_listeners)


def _ingest(jobs, late_before=None, user_id=7):
    return ingest_jobs(
        jobs, profile=PROFILE, llm_cfg=LLMConfig(enabled=False),
        min_score=0, user_id=user_id, late_before=late_before,
    )


def test_late_column_migrates():
    db.ensure_db()
    rid, is_new = db.upsert_job(OLD, 90, {}, "draft", user_id=7, late=True)
    assert is_new
    assert db.get_job(rid).late == 1
    rid2, _ = db.upsert_job(FRESH, 90, {}, "draft", user_id=7)
    assert db.get_job(rid2).late == 0  # default stays clean


def test_is_late_handles_format_trap():
    # naive 'before' vs tz-aware ISO 'posted': string compare would lie here
    assert _is_late("2026-10-06T10:00:00+00:00", "2026-10-06 11:00:00") is True
    assert _is_late("2026-10-06T12:00:00+00:00", "2026-10-06 11:00:00") is False
    assert _is_late("2026-10-06 10:00:00", "2026-10-06 11:00:00") is True
    assert _is_late(None, "2026-10-06 11:00:00") is False
    assert _is_late("not-a-date", "2026-10-06 11:00:00") is False


def test_ingest_flags_late_only_new():
    db.ensure_db()
    results = _ingest([OLD, FRESH], late_before="2026-10-06 11:00:00")
    assert all(r.is_new for r in results)
    old_row = db.get_job(next(r for r in results if r.job["guid"] == "c-old").rid)
    fresh_row = db.get_job(next(r for r in results if r.job["guid"] == "c-fresh").rid)
    assert old_row.late == 1   # posted during the blackout
    assert fresh_row.late == 0  # posted after the hound woke up


def test_reingest_never_reflags():
    db.ensure_db()
    _ingest([OLD], late_before=None)  # seen while awake
    _ingest([OLD], late_before="2020-01-01 00:00:00")  # catch-up runs later
    rid = next(r for r in db.all_jobs(limit=10) if r.guid == "c-old").id
    assert db.get_job(rid).late == 0  # dedupe wins — already seen is not late


def test_poll_loop_consumes_catchup_once(monkeypatch):
    db.ensure_db()
    calls: list[dict] = []

    def spy(uid, cid, *, late_before=None):
        calls.append({"uid": uid, "cid": cid, "late_before": late_before})
        return {"connector": cid, "new": 0}

    monkeypatch.setattr(api_mod, "run_connector_for", spy)
    monkeypatch.setattr(api_mod.db, "enabled_connector_rows",
                        lambda: [(1, "remoteok")])
    _catchup["pending"] = True
    _catchup["late_before"] = "2026-10-06 11:00:00"
    stop = threading.Event()
    t = threading.Thread(target=_poll_loop, args=(stop, 5, 0.05), daemon=True)
    t.start()
    deadline = time.time() + 5
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    t.join(timeout=5)
    assert len(calls) >= 2
    assert calls[0]["late_before"] == "2026-10-06 11:00:00"  # first sweep catches up
    assert calls[1]["late_before"] is None                    # then back to routine
    assert _catchup["pending"] is False


def test_boot_arms_catchup_after_real_gap(monkeypatch):
    config.init_files()
    monkeypatch.setattr(api_mod.db, "latest_connector_run",
                        lambda: "2000-01-01 00:00:00")
    with TestClient(create_app(start_poller=True)) as _:
        assert _catchup["pending"] is True
        assert _catchup["late_before"] is not None


def test_fresh_boot_arms_nothing(monkeypatch):
    config.init_files()
    monkeypatch.setattr(api_mod.db, "latest_connector_run", lambda: None)
    with TestClient(create_app(start_poller=True)) as _:
        assert _catchup["pending"] is False


def test_radar_exposes_catchup():
    config.init_files()
    client = TestClient(create_app(start_poller=False))
    client.post("/api/auth/register",
                json={"email": "late@test.dev", "password": "hunter2boogaloo"})
    body = client.get("/api/radar").json()
    assert body["catchup"] == {"pending": False, "late_before": None}


def test_job_to_dict_carries_late():
    j = Job(id=1, guid="g", source="remoteok", title="t", url="u", body="",
            budget_min=None, budget_max=None, hourly=None, tags="",
            posted_at=None, late=1)
    assert job_to_dict(j)["late"] is True
    j.late = 0
    assert job_to_dict(j)["late"] is False
