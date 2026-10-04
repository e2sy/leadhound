"""Victory banner + pipeline-value stats tests."""

import pytest

from leadhound import config, db
from leadhound.victory import build_victory_text, gig_money


@pytest.fixture(autouse=True)
def _db():
    config.init_files()


def _seed(guid: str, title: str, *, status: str = "pending", outcome: str | None = None,
          budget_max: float | None = 2000.0, budget_min: float | None = None,
          hourly: float | None = None) -> int:
    db.upsert_job(
        {
            "guid": guid,
            "source": "remoteok",
            "title": title,
            "url": f"https://example.com/{guid}",
            "body": "react",
            "tags": ["react"],
            "hourly": hourly,
            "budget_max": budget_max,
            "budget_min": budget_min,
        },
        85,
        {"budget": {"hourly": hourly}, "skills": {"matched": ["react"]}, "red_flags": []},
        "draft",
    )
    rid = next(j.id for j in db.all_jobs() if j.guid == guid)
    if status != "pending":
        db.set_status(rid, status)
    if outcome:
        db.set_outcome(rid, outcome)
    return rid


class TestMoney:
    def test_prefers_hourly(self):
        j = db.get_job(_seed("v1", "H", hourly=75.5, budget_max=100.0))
        assert gig_money(j) == "$75.5/hr"

    def test_fixed_max_then_min(self):
        j = db.get_job(_seed("v2", "F", budget_max=4500.0))
        assert "$4,500" in gig_money(j)
        j = db.get_job(_seed("v3", "M", budget_max=None, budget_min=900.0))
        assert "$900+" in gig_money(j)

    def test_no_budget(self):
        j = db.get_job(_seed("v4", "N", budget_max=None, budget_min=None))
        assert gig_money(j) == "budget not posted"


class TestVictoryText:
    def test_contains_title_and_value(self):
        j = db.get_job(_seed("v5", "React dashboard rebuild", budget_max=3200.0))
        text = build_victory_text(j)
        assert "React dashboard rebuild" in text
        assert "$3,200" in text
        assert "GIG WON" in text
        assert "remoteok" in text


class TestPipelineValue:
    def test_stats_counts_inplay_and_won(self):
        _seed("p1", "A", status="sent", outcome=None, budget_max=1000.0)
        _seed("p2", "B", status="approved", outcome=None, budget_max=2500.0)
        _seed("p3", "C", status="sent", outcome="won", budget_max=4000.0)
        _seed("p4", "D", status="sent", outcome="lost", budget_max=9999.0)
        _seed("p5", "E", status="pending", outcome=None, budget_max=500.0)
        s = db.stats()
        assert s["inplay_n"] == 2          # A + B (sent/approved, no outcome yet)
        assert s["inplay_value"] == 3500.0
        assert s["won_n"] == 1 and s["won_value"] == 4000.0
        # pending/rejected never count as in play; lost never counts as won
