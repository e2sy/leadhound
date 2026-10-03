"""Learning loop tests — migration, outcome marking, calibration hints."""

import sqlite3

from leadhound import config, db


def _seed(guid: str, score: int) -> int:
    rid, _ = db.upsert_job(
        {
            "guid": guid, "source": "remoteok", "title": f"Gig {guid}",
            "url": f"https://example.com/{guid}", "body": "react", "tags": [],
        },
        score, {}, "",
    )
    return rid


class TestMigration:
    def test_old_db_without_outcome_columns_gets_upgraded(self):
        # simulate a v0.1.0 database
        p = config.db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, guid TEXT, score INTEGER)")
        c.commit()
        c.close()

        db.ensure_db()  # should ALTER, not crash
        c = sqlite3.connect(p)
        cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
        c.close()
        assert {"outcome", "outcome_at"} <= cols

    def test_fresh_db_has_outcome_columns(self):
        config.init_files()
        rid = _seed("m1", 90)
        db.set_outcome(rid, "won")  # would crash if columns were missing
        assert db.get_job(rid).outcome == "won"


class TestOutcomes:
    def test_set_and_read_outcome(self):
        config.init_files()
        rid = _seed("o1", 85)
        db.set_outcome(rid, "replied")
        job = db.get_job(rid)
        assert job.outcome == "replied"
        assert job.outcome_at is not None

    def test_invalid_outcome_rejected(self):
        config.init_files()
        rid = _seed("o2", 80)
        try:
            db.set_outcome(rid, "ghosted")
            raised = False
        except ValueError:
            raised = True
        assert raised


class TestCalibration:
    def test_empty_state_hint(self):
        config.init_files()
        cal = db.calibration()
        assert "No outcomes" in cal["hint"]

    def test_winners_outscore_losers_is_calibrated(self):
        config.init_files()
        for guid, score in (("w1", 95), ("w2", 90), ("l1", 40), ("l2", 50)):
            db.set_outcome(_seed(guid, score), "won" if guid.startswith("w") else "lost")
        cal = db.calibration()
        assert cal["won"]["avg_score"] == 92.5
        assert cal["lost"]["avg_score"] == 45.0
        assert "calibrated" in cal["hint"].lower()

    def test_losers_outscoring_warns(self):
        config.init_files()
        for guid, score in (("w1", 30), ("l1", 90), ("l2", 80)):
            db.set_outcome(_seed(guid, score), "won" if guid.startswith("w") else "lost")
        cal = db.calibration()
        assert "tighten" in cal["hint"].lower()

    def test_low_scoring_winner_suggests_lower_min_score(self):
        config.init_files()
        db.set_outcome(_seed("w1", 45), "won")
        cal = db.calibration()
        assert "min_score" in cal["hint"]
