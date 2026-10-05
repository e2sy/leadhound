"""Closer's scoreboard tests — funnel math, per-source + per-method stats,
account scoping, the interview outcome and the /api/stats endpoint."""

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
                    json={"email": "closer@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def _seed(guid: str, source: str = "freelancer", score: int = 80,
          budget_max: float | None = 500.0, user_id: int | None = None) -> int:
    rid, _ = db.upsert_job(
        {
            "guid": guid, "source": source, "title": f"Gig {guid}",
            "url": f"https://example.com/{guid}", "body": "react work", "tags": [],
            "budget_max": budget_max,
        },
        score, {}, "", user_id=user_id,
    )
    return rid


def _sniped(guid: str, method: str = "kit", source: str = "freelancer",
            score: int = 80, budget_max: float | None = 500.0,
            user_id: int | None = None) -> int:
    rid = _seed(guid, source=source, score=score, budget_max=budget_max, user_id=user_id)
    db.mark_sniped(rid, method, "test shot")
    return rid


class TestFunnel:
    def test_empty_account_has_zeroed_funnel(self):
        config.init_files()
        f = db.funnel_stats()
        assert f["sniped"] == 0 and f["replies"] == 0 and f["wins"] == 0
        assert f["reply_rate"] is None and f["win_rate"] is None
        assert f["by_source"] == [] and f["by_method"] == {}

    def test_counts_and_rates(self):
        config.init_files()
        a = _sniped("f1", method="kit")
        b = _sniped("f2", method="freelancer-api")
        c = _sniped("f3", method="kit")
        d = _sniped("f4", method="kit")
        db.set_outcome(a, "replied")
        db.set_outcome(b, "interview")
        db.set_outcome(c, "won")
        db.set_outcome(d, "lost")
        f = db.funnel_stats()
        assert f["sniped"] == 4
        assert f["replies"] == 3          # replied + interview + won
        assert f["interviews"] == 1
        assert f["wins"] == 1 and f["losses"] == 1
        assert f["reply_rate"] == 75.0
        assert f["win_rate"] == 50.0      # 1 win of 2 resolved
        assert f["won_value"] == 500.0

    def test_unresolved_shots_have_win_rate_none(self):
        config.init_files()
        _sniped("u1")
        _sniped("u2")
        f = db.funnel_stats()
        assert f["sniped"] == 2 and f["win_rate"] is None
        assert f["reply_rate"] == 0.0

    def test_pending_never_leaks_into_funnel(self):
        config.init_files()
        _seed("p1")  # pending, never sniped
        f = db.funnel_stats()
        assert f["sniped"] == 0

    def test_by_source_rows(self):
        config.init_files()
        _sniped("s1", source="freelancer")
        _sniped("s2", source="freelancer")
        r = _sniped("s3", source="remoteok")
        db.set_outcome(r, "won")
        f = db.funnel_stats()
        rows = {row["source"]: row for row in f["by_source"]}
        assert rows["freelancer"]["sent"] == 2 and rows["freelancer"]["tracked"] == 2
        assert rows["freelancer"]["reply_rate"] == 0.0
        assert rows["remoteok"]["sent"] == 1 and rows["remoteok"]["wins"] == 1
        assert rows["remoteok"]["reply_rate"] == 100.0
        assert rows["remoteok"]["won_value"] == 500.0

    def test_by_method_split(self):
        config.init_files()
        a = _sniped("m1", method="freelancer-api")
        b = _sniped("m2", method="kit")
        db.set_outcome(a, "replied")
        db.set_outcome(b, "lost")
        f = db.funnel_stats()
        assert f["by_method"]["freelancer-api"]["sent"] == 1
        assert f["by_method"]["freelancer-api"]["replies"] == 1
        assert f["by_method"]["kit"]["sent"] == 1
        assert f["by_method"]["kit"]["replies"] == 0


class TestInterviewOutcome:
    def test_interview_is_a_valid_outcome(self):
        config.init_files()
        rid = _sniped("i1")
        db.set_outcome(rid, "interview")
        assert db.get_job(rid).outcome == "interview"

    def test_interview_counts_as_reply_in_snipe_stats(self):
        config.init_files()
        rid = _sniped("i2")
        db.set_outcome(rid, "interview")
        s = db.snipe_stats()
        assert s["replies"] == 1 and s["reply_rate"] == 100.0

    def test_invalid_outcome_still_rejected(self):
        config.init_files()
        rid = _sniped("i3")
        with pytest.raises(ValueError):
            db.set_outcome(rid, "ghosted")


class TestScoping:
    def test_stats_are_account_scoped(self):
        config.init_files()
        mine = _sniped("sc1", user_id=1)
        db.set_outcome(mine, "won")
        _sniped("sc2", user_id=2)
        db.set_outcome(_sniped("sc3", user_id=2), "lost")

        mine_f = db.funnel_stats(user_id=1)
        assert mine_f["sniped"] == 1 and mine_f["wins"] == 1 and mine_f["losses"] == 0
        assert mine_f["win_rate"] == 100.0

        theirs_f = db.funnel_stats(user_id=2)
        assert theirs_f["sniped"] == 2 and theirs_f["wins"] == 0

        # pipeline stats are scoped the same way
        assert db.stats(user_id=1)["sent"] == 1
        assert db.stats(user_id=2)["sent"] == 2
        assert db.stats()["sent"] == 3  # CLI pool sees everything (local-first)

        cal = db.calibration(user_id=1)
        assert cal["won"]["n"] == 1 and "lost" not in cal


class TestStatsEndpoint:
    def test_stats_requires_auth(self, client):
        assert client.get("/api/stats").status_code == 401

    def test_stats_shape(self, authed):
        _sniped("e1", user_id=1)
        db.set_outcome(1, "replied")
        r = authed.get("/api/stats")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert {"funnel", "pipeline", "calibration"} <= set(d)
        assert d["funnel"]["sniped"] == 1
        assert d["pipeline"]["sent"] == 1
