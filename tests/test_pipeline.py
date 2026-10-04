"""Pipeline tests — the shared ingest path used by CLI, API and poller."""

from __future__ import annotations

from leadhound import db
from leadhound.config import LLMConfig, Profile
from leadhound.pipeline import ingest_jobs

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

HOT = {
    "guid": "p-hot",
    "source": "remoteok",
    "title": "Senior React dev for fintech dashboard",
    "url": "https://x/1",
    "body": "We need a react + stripe developer. Budget $3,000 fixed.",
    "tags": ["react", "stripe"],
}
COLD = {
    "guid": "p-cold",
    "source": "remoteok",
    "title": "Python script tiny task",
    "url": "https://x/2",
    "body": "Need a quick python script. Budget $40.",
    "tags": ["python"],
}


def _llm() -> LLMConfig:
    return LLMConfig(enabled=False)


def test_ingest_scores_drafts_and_scopes():
    db.ensure_db()
    results = ingest_jobs([HOT, COLD], profile=PROFILE, llm_cfg=_llm(), min_score=50,
                          user_id=7)
    assert [r.is_new for r in results] == [True, True]
    hot = next(r for r in results if r.job["guid"] == "p-hot")
    cold = next(r for r in results if r.job["guid"] == "p-cold")
    assert hot.draft and hot.mode == "template"
    assert not cold.draft  # below min_score
    assert db.get_job(hot.rid).user_id == 7
    assert db.get_job(cold.rid).user_id == 7


def test_ingest_dedupes_by_guid():
    db.ensure_db()
    first = ingest_jobs([HOT], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
    second = ingest_jobs([dict(HOT)], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
    assert first[0].is_new and not second[0].is_new
    assert db.stats()["total"] == 1


def test_ingest_cli_pool_when_no_user():
    db.ensure_db()
    results = ingest_jobs([HOT], profile=PROFILE, llm_cfg=_llm(), min_score=0)
    assert db.get_job(results[0].rid).user_id is None
