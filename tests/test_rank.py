"""Queue ranking v2 tests — freshness tiers, source trust, composite order
and the API surface (/api/queue, rank in /api/state)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import build_state, create_app
from leadhound.engine.rank import (
    REL_DEFAULT,
    freshness,
    rank_score,
    ranked_queue,
    reliability,
)


@pytest.fixture
def client():
    config.init_files()
    return TestClient(create_app(start_poller=False))


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/register",
                    json={"email": "rank@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


NOW = datetime.now(UTC)


def _posted(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


class _J:
    """Minimal stand-in for db.Job for ranking tests."""

    def __init__(self, score, posted_at, source="freelancer", late=0, id=1):
        self.score, self.posted_at, self.source = score, posted_at, source
        self.late, self.id = late, id
        self.title = f"gig {id}"


# ---------------------------------------------------------------- freshness

def test_freshness_tiers():
    assert freshness(_posted(0.2), now=NOW) == 1.0    # < 1h
    assert freshness(_posted(3), now=NOW) == 0.9      # < 6h
    assert freshness(_posted(12), now=NOW) == 0.75    # < 24h
    assert freshness(_posted(48), now=NOW) == 0.6     # < 72h
    assert freshness(_posted(100), now=NOW) == 0.45   # stale
    assert freshness(None, now=NOW) == 0.45


def test_freshness_garbage_timestamp_is_stale():
    assert freshness("not-a-date", now=NOW) == 0.45


# ---------------------------------------------------------------- reliability

def test_reliability_neutral_until_enough_sends():
    rel = reliability([{"source": "fiverr", "sent": 3, "replies": 3}])
    assert rel["fiverr"] == REL_DEFAULT


def test_reliability_computed_and_clamped():
    rel = reliability([
        {"source": "freelancer", "sent": 10, "replies": 8},   # 0.8
        {"source": "guru", "sent": 10, "replies": 1},         # max(0.2, 0.1)
    ])
    assert rel["freelancer"] == 0.8
    assert rel["guru"] == 0.2


# ---------------------------------------------------------------- composite

def test_fresh_gig_outranks_stale_one():
    fresh_rs, _, fresh_why = rank_score(80, _posted(0.5), 0.5, now=NOW)
    stale_rs, _, _ = rank_score(95, _posted(96), 0.5, now=NOW)
    assert fresh_rs > stale_rs
    assert "hot" in fresh_why


def test_proven_source_breaks_ties():
    a, _, why_a = rank_score(80, _posted(0.5), 0.8, now=NOW)
    b, _, why_b = rank_score(80, _posted(0.5), 0.3, now=NOW)
    assert a > b
    assert "proven" in why_a and "weak" in why_b


def test_late_gig_gets_freshness_floor():
    rs_late, f_late, _ = rank_score(90, _posted(96), 0.5, now=NOW, late=True)
    rs_old, f_old, _ = rank_score(90, _posted(96), 0.5, now=NOW, late=False)
    assert f_late == 0.9 > f_old
    assert rs_late > rs_old


def test_rank_score_stays_bounded():
    rs, _, _ = rank_score(100, _posted(0.1), 1.0, now=NOW)
    assert 0 < rs <= 100


# ---------------------------------------------------------------- queue

def test_ranked_queue_orders_best_first():
    jobs = [
        _J(95, _posted(96), "guru", id=1),
        _J(80, _posted(0.5), "freelancer", id=2),
        _J(60, _posted(2), "fiverr", id=3),
    ]
    rows = ranked_queue(jobs, [], now=NOW)
    assert [r["job"].id for r in rows] == [2, 3, 1]
    assert rows[0]["reason"].startswith("hot")


def test_ranked_queue_limit():
    jobs = [_J(50 + i, _posted(0.1), id=i) for i in range(10)]
    rows = ranked_queue(jobs, [], limit=3, now=NOW)
    assert len(rows) == 3


# ---------------------------------------------------------------- api

def test_queue_endpoint(authed):
    uid = db.user_by_email("rank@test.dev")["id"]
    rid, _ = db.upsert_job(
        {"guid": "rq-1", "source": "freelancer", "title": "React gig",
         "url": "https://x.example/1", "body": "react", "tags": [],
         "posted_at": _posted(0.5)},
        88, {}, "", user_id=uid,
    )
    db.set_status(rid, "approved")  # approved -> not in queue
    rid2, _ = db.upsert_job(
        {"guid": "rq-2", "source": "freelancer", "title": "Stripe gig",
         "url": "https://x.example/2", "body": "stripe", "tags": [],
         "posted_at": _posted(0.2)},
        91, {}, "", user_id=uid,
    )
    r = authed.get("/api/queue")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    ids = [q["id"] for q in d["queue"]]
    assert rid2 in ids and rid not in ids
    q = d["queue"][0]
    assert {"id", "title", "score", "rank_score", "freshness", "source", "reason"} <= set(q)


def test_state_includes_rank_for_pending(authed):
    uid = db.user_by_email("rank@test.dev")["id"]
    rid, _ = db.upsert_job(
        {"guid": "rq-3", "source": "freelancer", "title": "Next.js gig",
         "url": "https://x.example/3", "body": "next.js", "tags": [],
         "posted_at": _posted(0.3)},
        84, {}, "", user_id=uid,
    )
    state = build_state(uid)
    job = next(j for j in state["jobs"] if j["id"] == rid)
    assert job["status"] == "pending"
    assert isinstance(job["rank"], int)
    assert 0 < job["rank"] <= 100
