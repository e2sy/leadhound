"""DB tests — upsert dedupe, status flow, notification marking, stats."""

from leadhound import db


def _job(guid: str, score: int = 90) -> dict:
    return {
        "guid": guid,
        "source": "test",
        "title": f"Gig {guid}",
        "url": f"https://example.com/{guid}",
        "body": "body text",
        "tags": ["react", "stripe"],
    }


class TestUpsert:
    def test_new_then_duplicate(self):
        db.ensure_db()
        rid, is_new = db.upsert_job(_job("g-1"), 90, {"why": 90}, "draft")
        assert is_new
        rid2, is_new2 = db.upsert_job(_job("g-1"), 50, {}, "other draft")
        assert rid2 == rid and not is_new2  # guid is the dedupe key

    def test_roundtrip_fields(self):
        db.ensure_db()
        rid, _ = db.upsert_job(_job("g-2", 77), 77, {"skills": {"matched": ["react"]}}, "hello draft")
        job = db.get_job(rid)
        assert job.score == 77
        assert job.tags == "react,stripe"
        assert job.status == "pending"


class TestStatusFlow:
    def test_approve_moves_queue(self):
        db.ensure_db()
        rid, _ = db.upsert_job(_job("g-3"), 85, {}, "")
        db.upsert_job(_job("g-4"), 95, {}, "")

        assert len(db.jobs_by_status("pending", min_score=0)) == 2
        db.set_status(rid, "approved")
        pend = db.jobs_by_status("pending", min_score=0)
        assert len(pend) == 1 and pend[0].guid == "g-4"

    def test_min_score_filter_and_ordering(self):
        db.ensure_db()
        db.upsert_job(_job("a", 50), 50, {}, "")
        db.upsert_job(_job("b", 90), 90, {}, "")
        db.upsert_job(_job("c", 70), 70, {}, "")
        hits = db.jobs_by_status("pending", min_score=60)
        assert [j.score for j in hits] == [90, 70]


class TestNotifications:
    def test_pending_unnotified_and_mark(self):
        db.ensure_db()
        rid, _ = db.upsert_job(_job("n-1"), 80, {}, "")
        db.upsert_job(_job("n-2", 60), 60, {}, "")

        hits = db.pending_unnotified(min_score=70)
        assert [j.guid for j in hits] == ["n-1"]

        db.mark_notified(rid)
        assert db.pending_unnotified(min_score=0)[0].guid == "n-2"


class TestStats:
    def test_counts_and_high_score(self):
        db.ensure_db()
        db.upsert_job(_job("s-1", 91), 91, {}, "")
        db.upsert_job(_job("s-2", 40), 40, {}, "")
        db.set_status(2, "rejected")
        s = db.stats()
        assert s["total"] == 2
        assert s["pending"] == 1 and s["rejected"] == 1
        assert s["highest_score"] == 91


class TestSnipes:
    def test_mark_sniped_writes_audit_trail(self):
        db.ensure_db()
        rid, _ = db.upsert_job(_job("sn-1"), 88, {}, "draft")
        db.mark_sniped(rid, "freelancer-api", "bid #424242")
        job = db.get_job(rid)
        assert job.status == "sent"
        assert job.snipe_method == "freelancer-api"
        assert job.snipe_note == "bid #424242"
        assert job.sniped_at is not None

    def test_snipe_stats_counts_and_rates(self):
        db.ensure_db()
        a, _ = db.upsert_job(_job("sn-a"), 90, {}, "")
        b, _ = db.upsert_job(_job("sn-b"), 85, {}, "")
        c, _ = db.upsert_job(_job("sn-c"), 80, {}, "")
        for rid in (a, b, c):
            db.mark_sniped(rid, "kit", "confirmed")
        db.set_outcome(b, "replied")
        db.set_outcome(c, "won")
        s = db.snipe_stats()
        assert s["sniped_total"] == 3
        assert s["sniped_7d"] == 3
        assert s["replies"] == 2  # replied + won
        assert s["wins"] == 1
        assert s["reply_rate"] == 66.7

    def test_snipe_stats_empty_scope(self):
        db.ensure_db()
        s = db.snipe_stats()
        assert s["sniped_total"] == 0 and s["reply_rate"] is None
