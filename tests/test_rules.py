"""Auto-snipe rules — guardrailed automation for the approval queue.

A rule can auto-APPROVE a gig that clears its score bar (plus keyword,
source and budget caps). It can NEVER fire a bid: firing stays behind a
human click, in the board dialog or /snipe in the pocket. These tests pin
the matcher, the pipeline hook, the API surface and that guardrail.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
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

GIG = {
    "guid": "rule-hot",
    "source": "freelancer",
    "title": "Build a React dashboard with Stripe billing",
    "url": "https://example.com/rule-hot",
    "body": "We need a react + stripe developer. Budget $2,500 fixed.",
    "tags": ["react", "stripe"],
    "budget_max": 2500,
}


def _llm() -> LLMConfig:
    return LLMConfig(enabled=False)


def _client() -> TestClient:
    config.init_files()
    c = TestClient(create_app(start_poller=False))
    c.post("/api/auth/register",
           json={"email": "rules@test.dev", "password": "hunter2boogaloo"})
    return c


# ------------------------------------------------------------------- db layer
class TestRuleDb:
    def test_add_and_list_roundtrip(self):
        db.ensure_db()
        r = db.add_snipe_rule(7, "react dashboards", min_score=85, keywords="react, dashboard")
        assert r["name"] == "react dashboards" and r["min_score"] == 85
        assert r["enabled"] == 1
        assert [x["id"] for x in db.snipe_rules_for(7)] == [r["id"]]

    def test_score_clamped_60_99(self):
        db.ensure_db()
        assert db.add_snipe_rule(7, "too low", min_score=10)["min_score"] == 60
        assert db.add_snipe_rule(7, "too high", min_score=100)["min_score"] == 99

    def test_toggle_and_delete_scoped_to_user(self):
        db.ensure_db()
        r = db.add_snipe_rule(7, "mine")
        assert db.set_snipe_rule_enabled(8, r["id"], False) is False  # not the owner
        assert db.set_snipe_rule_enabled(7, r["id"], False) is True
        assert db.snipe_rule(7, r["id"])["enabled"] == 0
        assert db.delete_snipe_rule(8, r["id"]) is False
        assert db.delete_snipe_rule(7, r["id"]) is True
        assert db.snipe_rule(7, r["id"]) is None


class TestMatcher:
    def test_min_score_gate(self):
        db.ensure_db()
        db.add_snipe_rule(7, "bar", min_score=90)
        assert db.match_snipe_rules(7, 89, GIG) == []
        assert len(db.match_snipe_rules(7, 90, GIG)) == 1

    def test_keyword_any_match_case_insensitive(self):
        db.ensure_db()
        db.add_snipe_rule(7, "kw", min_score=60, keywords="Stripe, invoice")
        assert len(db.match_snipe_rules(7, 90, GIG)) == 1
        cold = dict(GIG, title="Logo redraw", body="simple vector job")
        assert db.match_snipe_rules(7, 90, cold) == []

    def test_source_filter(self):
        db.ensure_db()
        db.add_snipe_rule(7, "wrong src", min_score=60, source="upwork")
        assert db.match_snipe_rules(7, 90, GIG) == []
        db.add_snipe_rule(7, "right src", min_score=60, source="Freelancer")
        assert len(db.match_snipe_rules(7, 90, GIG)) == 1  # case-insensitive

    def test_budget_caps_reject_over_budget(self):
        db.ensure_db()
        db.add_snipe_rule(7, "cap fixed", min_score=60, max_fixed=2000)
        db.add_snipe_rule(7, "cap hourly", min_score=60, max_hourly=100)
        # 2500 fixed exceeds the fixed cap -> "cap fixed" out
        hits = db.match_snipe_rules(7, 90, GIG)
        assert [h["name"] for h in hits] == ["cap hourly"]
        under = dict(GIG, budget_max=1500)
        assert len(db.match_snipe_rules(7, 90, under)) == 2  # both caps pass
        hourly_gig = dict(GIG, hourly=120, budget_max=None)
        hits = db.match_snipe_rules(7, 90, hourly_gig)
        assert [h["name"] for h in hits] == ["cap fixed"]  # hourly cap rejects, fixed cap n/a

    def test_disabled_rules_never_match(self):
        db.ensure_db()
        r = db.add_snipe_rule(7, "off duty", min_score=60)
        db.set_snipe_rule_enabled(7, r["id"], False)
        assert db.match_snipe_rules(7, 99, GIG) == []


# ------------------------------------------------------------------- pipeline
class TestPipelineHook:
    def test_matching_new_gig_auto_approves(self):
        db.ensure_db()
        db.add_snipe_rule(7, "hot react", min_score=60, keywords="react")
        res = ingest_jobs([GIG], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
        assert res[0].auto_rule == "hot react"
        stored = db.get_job(res[0].rid)
        assert stored.status == "approved"
        assert stored.auto_rule == "hot react"

    def test_no_match_stays_pending(self):
        db.ensure_db()
        db.add_snipe_rule(7, "unreachable", min_score=99, keywords="cobol")
        res = ingest_jobs([GIG], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
        assert res[0].auto_rule is None
        assert db.get_job(res[0].rid).status == "pending"

    def test_not_reapplied_on_refetch(self):
        db.ensure_db()
        db.add_snipe_rule(7, "hot react", min_score=60)
        first = ingest_jobs([GIG], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
        db.set_status(first[0].rid, "pending")  # the user demotes it manually
        second = ingest_jobs([dict(GIG)], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=7)
        assert not second[0].is_new
        assert db.get_job(first[0].rid).status == "pending"  # human decision wins

    def test_pool_jobs_without_user_never_auto_arm(self):
        db.ensure_db()
        db.add_snipe_rule(7, "user 7 only", min_score=60)
        res = ingest_jobs([GIG], profile=PROFILE, llm_cfg=_llm(), min_score=0, user_id=None)
        assert res[0].auto_rule is None
        assert db.get_job(res[0].rid).status == "pending"


# ------------------------------------------------------------------------ api
class TestRulesApi:
    def test_requires_auth(self):
        config.init_files()
        c = TestClient(create_app(start_poller=False))
        assert c.get("/api/rules").status_code == 401
        assert c.post("/api/rules", json={"name": "x"}).status_code == 401

    def test_create_list_delete_flow(self):
        c = _client()
        r = c.post("/api/rules", json={"name": "stripe work", "min_score": 80, "keywords": "stripe"})
        assert r.status_code == 200 and r.json()["rule"]["name"] == "stripe work"
        rules = c.get("/api/rules").json()["rules"]
        assert len(rules) == 1
        rid = rules[0]["id"]
        assert c.post(f"/api/rules/{rid}/enabled", json={"enabled": False}).status_code == 200
        assert c.delete(f"/api/rules/{rid}").status_code == 200
        assert c.get("/api/rules").json()["rules"] == []

    def test_create_rejects_empty_name(self):
        c = _client()
        assert c.post("/api/rules", json={"name": "   "}).status_code == 422

    def test_delete_unknown_404(self):
        c = _client()
        assert c.delete("/api/rules/9999").status_code == 404

    def test_toggle_unknown_404(self):
        c = _client()
        assert c.post("/api/rules/9999/enabled", json={"enabled": True}).status_code == 404
