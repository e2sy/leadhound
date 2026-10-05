"""Proposal A/B testing — variant storage, per-variant snipe attribution,
the variants API and the by-variant duel stats."""

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
                    json={"email": "duelist@test.dev", "password": "hunter2boogaloo"})
    assert r.status_code == 200, r.text
    return client


def _seed(guid: str, score: int = 80, user_id: int | None = None) -> int:
    rid, _ = db.upsert_job(
        {
            "guid": guid, "source": "freelancer", "title": f"Gig {guid}",
            "url": f"https://example.com/{guid}", "body": "react work", "tags": [],
            "budget_max": 400.0,
        },
        score, {}, "main draft text", user_id=user_id,
    )
    return rid


class TestVariantStorage:
    def test_save_and_list(self):
        config.init_files()
        rid = _seed("ab1")
        db.save_variant(rid, "B", "punchier draft")
        assert db.variants_for(rid) == [
            {"label": "B", "text": "punchier draft", "created": db.variants_for(rid)[0]["created"]}
        ]

    def test_upsert_overwrites(self):
        config.init_files()
        rid = _seed("ab2")
        db.save_variant(rid, "B", "v1")
        db.save_variant(rid, "B", "v2")
        rows = db.variants_for(rid)
        assert len(rows) == 1 and rows[0]["text"] == "v2"

    def test_label_a_is_rejected(self):
        config.init_files()
        rid = _seed("ab3")
        with pytest.raises(ValueError):
            db.save_variant(rid, "A", "nope — A is the main draft")

    def test_bad_labels_rejected(self):
        config.init_files()
        rid = _seed("ab4")
        for bad in ("", "TOOLONG", "1", "B!"):
            with pytest.raises(ValueError):
                db.save_variant(rid, bad, "x")

    def test_all_variants_groups_by_job(self):
        config.init_files()
        a = _seed("ab5")
        b = _seed("ab6")
        db.save_variant(a, "B", "va")
        db.save_variant(b, "B", "vb")
        grouped = db.all_variants()
        assert grouped[a][0]["text"] == "va" and grouped[b][0]["text"] == "vb"

    def test_old_db_gets_sent_variant_column(self):
        import sqlite3

        p = config.db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, guid TEXT, score INTEGER)")
        c.commit()
        c.close()
        db.ensure_db()
        c = sqlite3.connect(p)
        cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
        c.close()
        assert "sent_variant" in cols


class TestSnipeAttribution:
    def test_mark_sniped_records_variant(self):
        config.init_files()
        rid = _seed("sa1")
        db.mark_sniped(rid, "kit", "sent B", variant="B")
        j = db.get_job(rid)
        assert j.status == "sent" and j.sent_variant == "B"

    def test_mark_sniped_default_is_main_draft(self):
        config.init_files()
        rid = _seed("sa2")
        db.mark_sniped(rid, "kit", "sent A")
        assert db.get_job(rid).sent_variant is None

    def test_by_variant_stats(self):
        config.init_files()
        a1, b1, b2 = _seed("sa3"), _seed("sa4"), _seed("sa5")
        db.mark_sniped(a1, "kit")               # A (sent_variant NULL)
        db.mark_sniped(b1, "kit", variant="B")
        db.mark_sniped(b2, "kit", variant="B")
        db.set_outcome(a1, "replied")
        db.set_outcome(b1, "replied")
        db.set_outcome(b2, "lost")
        f = db.funnel_stats()
        assert f["by_variant"]["A"] == {"sent": 1, "replies": 1, "wins": 0}
        assert f["by_variant"]["B"] == {"sent": 2, "replies": 1, "wins": 0}


class TestVariantsAPI:
    def test_requires_auth(self, client):
        assert client.get("/api/jobs/1/variants").status_code == 401
        assert client.post("/api/jobs/1/variants", json={"label": "B", "text": "x"}).status_code == 401

    def test_roundtrip(self, authed):
        rid = _seed("api1", user_id=1)
        r = authed.post(f"/api/jobs/{rid}/variants", json={"label": "b", "text": "variant text"})
        assert r.status_code == 200
        assert r.json()["variants"][0]["label"] == "B"
        # state carries variants for the board
        jobs = authed.get("/api/state").json()["jobs"]
        mine = next(j for j in jobs if j["id"] == rid)
        assert mine["variants"][0]["text"] == "variant text"

    def test_label_a_rejected_over_api(self, authed):
        rid = _seed("api2", user_id=1)
        r = authed.post(f"/api/jobs/{rid}/variants", json={"label": "A", "text": "x"})
        assert r.status_code == 400

    def test_foreign_job_404(self, authed):
        _seed("api3", user_id=None)  # shared pool is visible; make an invisible one
        _seed("api4", user_id=99)
        r = authed.post("/api/jobs/2/variants", json={"label": "B", "text": "x"})
        assert r.status_code == 404

    def test_confirm_with_unknown_variant_400(self, authed):
        rid = _seed("api5", user_id=1)
        r = authed.post(f"/api/jobs/{rid}/snipe-confirm", json={"variant": "Z"})
        assert r.status_code == 400

    def test_confirm_with_variant_records_it(self, authed):
        rid = _seed("api6", user_id=1)
        authed.post(f"/api/jobs/{rid}/variants", json={"label": "B", "text": "v"})
        r = authed.post(f"/api/jobs/{rid}/snipe-confirm", json={"variant": "B"})
        assert r.status_code == 200 and r.json()["variant"] == "B"
        assert db.get_job(rid).sent_variant == "B"

    def test_state_carries_sent_variant(self, authed):
        rid = _seed("api7", user_id=1)
        authed.post(f"/api/jobs/{rid}/variants", json={"label": "B", "text": "v"})
        authed.post(f"/api/jobs/{rid}/snipe-confirm", json={"variant": "B"})
        mine = next(j for j in authed.get("/api/state").json()["jobs"] if j["id"] == rid)
        assert mine["sent_variant"] == "B"

    def test_snipe_plan_includes_variants(self, authed):
        rid = _seed("api8", user_id=1)
        authed.post(f"/api/jobs/{rid}/variants", json={"label": "B", "text": "v"})
        p = authed.get(f"/api/jobs/{rid}/snipe-plan").json()
        assert p["variants"][0]["label"] == "B"
