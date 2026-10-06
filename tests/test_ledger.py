"""Money ledger tests — quoted-over-budget preference, in-play vs banked,
monthly rollup, scoping, the quote endpoint and the /api/money surface."""

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
                    json={"email": "money@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()
    yield


def _job(guid, *, budget_max=None, quoted=None, status="pending",
         outcome=None, user_id=None, month_offset=0) -> int:
    rid, _ = db.upsert_job(
        {"guid": guid, "source": "freelancer", "title": f"gig {guid}",
         "url": "u", "body": "b", "tags": [], "budget_max": budget_max},
        80, {}, "", user_id=user_id,
    )
    if quoted is not None:
        db.set_quote(rid, quoted)
    if status != "pending":
        db.set_status(rid, status)
    if outcome:
        if month_offset:
            c = db._conn()
            c.execute(
                "UPDATE jobs SET outcome = ?, outcome_at = "
                "datetime('now', ?) WHERE id = ?",
                (outcome, f"{month_offset:+d} days", rid),
            )
            c.commit()
            c.close()
        else:
            db.set_outcome(rid, outcome)
            # set_outcome snapshots memory + cancels bumps; fine here
    return rid


def test_quote_prefers_your_number_over_posted_budget():
    _job("m1", budget_max=1000.0, quoted=2500.0, status="sent", outcome="won")
    led = db.ledger(None)
    assert led["won_value"] == 2500.0          # your quote, not their budget
    assert led["won_n"] == 1
    assert led["avg_won"] == 2500.0


def test_budget_fallback_when_no_quote():
    _job("m2", budget_max=1800.0, status="sent", outcome="won")
    led = db.ledger(None)
    assert led["won_value"] == 1800.0


def test_inplay_counts_sent_without_verdict():
    _job("m3", budget_max=500.0, quoted=700.0, status="sent")
    _job("m4", budget_max=900.0, status="sent", outcome="lost")  # resolved, not in play
    led = db.ledger(None)
    assert led["inplay_n"] == 1
    assert led["inplay_value"] == 700.0


def test_monthly_rollup_recent_only():
    _job("m5", quoted=1200.0, status="sent", outcome="won", month_offset=-200)
    _job("m6", quoted=3000.0, status="sent", outcome="won", month_offset=-3)
    led = db.ledger(None)
    assert sum(m["v"] for m in led["monthly"]) == 3000.0   # 200-day-old win is out
    assert all(m["n"] >= 1 for m in led["monthly"])


def test_ledger_scoped_per_account():
    _job("m7", quoted=999.0, status="sent", outcome="won", user_id=21)
    assert db.ledger(21)["won_value"] == 999.0
    assert db.ledger(22)["won_value"] == 0
    assert db.ledger(22)["won_n"] == 0


def test_negative_quote_rejected():
    rid, _ = db.upsert_job(
        {"guid": "m8", "source": "s", "title": "t", "url": "u", "body": "b", "tags": []},
        50, {}, "",
    )
    with pytest.raises(ValueError):
        db.set_quote(rid, -5)


def test_hint_nudges_quotes_when_none_set():
    _job("m9", budget_max=700.0, status="sent", outcome="won")
    led = db.ledger(None)
    assert "quote" in led["hint"]


# ---------------------------------------------------------------- api

def test_quote_and_money_endpoints(authed):
    uid = db.user_by_email("money@test.dev")["id"]
    rid = _job("m10", budget_max=1000.0, status="sent", user_id=uid)
    r = authed.post(f"/api/jobs/{rid}/quote", json={"amount": 1500.0})
    assert r.status_code == 200
    assert r.json()["quoted"] == 1500.0
    r = authed.post(f"/api/jobs/{rid}/quote", json={"amount": -3})
    assert r.status_code == 400
    r = authed.get("/api/money")
    led = r.json()["ledger"]
    assert led["inplay_value"] == 1500.0
    assert led["quotes_set"] >= 1


def test_money_requires_auth(client):
    assert client.get("/api/money").status_code == 401
