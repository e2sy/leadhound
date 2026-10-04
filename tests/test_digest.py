"""Digest tests — pure builder + recent_jobs query."""

from leadhound import config, db
from leadhound.digest import build_digest


def _seed(guid: str, score: int, title: str) -> None:
    db.upsert_job(
        {
            "guid": guid,
            "source": "remoteok",
            "title": title,
            "url": f"https://example.com/{guid}",
            "body": "react stripe",
            "tags": ["react"],
        },
        score,
        {"budget": {"hourly": 60, "fixed_min": None}, "skills": {"matched": ["react"]}, "red_flags": []},
        "Hey — I can start Monday.",
    )


class TestRecentJobs:
    def test_orders_by_score_and_respects_limit(self):
        config.init_files()
        _seed("d1", 70, "Mid gig")
        _seed("d2", 95, "Top gig")
        _seed("d3", 85, "Second gig")
        _seed("d4", 80, "Third gig")
        jobs = db.recent_jobs(hours=24, min_score=0, limit=2)
        assert [j.title for j in jobs] == ["Top gig", "Second gig"]

    def test_min_score_filter(self):
        config.init_files()
        _seed("e1", 40, "Weak gig")
        _seed("e2", 75, "Strong gig")
        jobs = db.recent_jobs(hours=24, min_score=60, limit=10)
        assert [j.title for j in jobs] == ["Strong gig"]


class TestBuildDigest:
    def test_empty_state_mentions_window_and_watch(self):
        out = build_digest([], "Mayank", 24)
        assert "Mayank" in out
        assert "24h" in out
        assert "leadhound watch" in out

    def test_lists_top_job_with_score_and_money(self):
        config.init_files()
        _seed("f1", 92, "Build a React Native app")
        jobs = db.recent_jobs(hours=24, min_score=0, limit=5)
        out = build_digest(jobs, "Mayank", 24)
        assert "1. [92] Build a React Native app" in out
        assert "$60/hr" in out
        assert "https://example.com/f1" in out
        assert "leadhound queue" in out

    def test_red_flags_surface_in_digest(self):
        config.init_files()
        db.upsert_job(
            {
                "guid": "f2", "source": "remoteok", "title": "Cheap gig",
                "url": "https://example.com/f2", "body": "unpaid exposure",
                "tags": [],
            },
            30,
            {
                "budget": {"hourly": None, "fixed_min": None},
                "skills": {"matched": []},
                "red_flags": ["unpaid"],
            },
            "",
        )
        jobs = db.recent_jobs(hours=24, min_score=0, limit=5)
        out = build_digest(jobs, "Mayank", 24)
        assert "🚩 unpaid" in out
        assert "budget not stated" in out
