"""Improve-draft — one-click rewrite of the proposal being edited.

LLM mode rewrites in the freelancer's voice (any OpenAI-compatible
endpoint); template mode sharpens deterministically with zero config.
Both paths tested here — the LLM is monkeypatched, CI stays offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.config import LLMConfig, Profile
from leadhound.engine.voice import improve_draft, improve_template

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

JOB = {
    "title": "React dashboard with Stripe billing",
    "body": "Need a react + stripe developer, $2,000 fixed.",
    "hourly": None,
    "budget_min": None,
    "budget_max": 2000,
}


class TestTemplateImprove:
    def test_plain_draft_gets_question_plan_budget(self):
        draft = "I have built many dashboards before. Hire me."
        text, changes = improve_template(JOB, PROFILE, draft, ["react", "stripe"])
        assert text.startswith("I have built many dashboards before.")
        assert "Worth a quick chat?" in text
        assert "Quick plan:" in text
        assert "budget works for me" in text
        assert len(changes) == 3

    def test_complete_draft_untouched(self):
        draft = (
            "Saw your Stripe dashboard post.\n\n"
            "Quick plan:\n1) build components\n2) wire payments\n\n"
            "Your budget works for me. Worth a quick chat?"
        )
        text, changes = improve_template(JOB, PROFILE, draft, ["react"])
        assert text == draft and changes == []

    def test_custom_lines_are_never_removed(self):
        custom = "PS: I already built this exact funnel for a fintech client last year."
        text, _ = improve_template(JOB, PROFILE, f"Intro line.\n{custom}", ["react"])
        assert custom in text

    def test_empty_draft_gets_fresh_template(self):
        text, changes = improve_template(JOB, PROFILE, "", ["react", "stripe"])
        assert text and "Quick plan:" not in text  # template has its own structure
        assert changes == ["empty draft — started a fresh template"]

    def test_blank_lines_collapsed(self):
        text, _ = improve_template(JOB, PROFILE, "Line one.\n\n\n\n\nLine two?", ["react"])
        assert "\n\n\n" not in text


class TestImproveDispatch:
    def test_llm_path_used_when_configured(self, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            r = MagicMock()
            r.raise_for_status.return_value = None
            r.json.return_value = {"choices": [{"message": {"content": " Rewritten by LLM. Reply?"}}]}
            return r

        monkeypatch.setattr("leadhound.engine.voice.requests.post", fake_post)
        llm = LLMConfig(enabled=True, api_key="sk-test", base_url="https://llm.test/v1")
        text, mode, _changes = improve_draft(JOB, PROFILE, llm, "old draft", ["react"])
        assert text == "Rewritten by LLM. Reply?" and mode == "llm"
        assert "old draft" in captured["payload"]["messages"][1]["content"]
        assert "/chat/completions" in captured["url"]

    def test_llm_failure_falls_back_to_template(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("llm down")

        monkeypatch.setattr("leadhound.engine.voice.requests.post", boom)
        llm = LLMConfig(enabled=True, api_key="sk-test", base_url="https://llm.test/v1")
        text, mode, changes = improve_draft(JOB, PROFILE, llm, "plain draft", ["react"])
        assert mode == "template"
        assert "Worth a quick chat?" in text and changes

    def test_llm_disabled_goes_straight_to_template(self):
        text, mode, _ = improve_draft(
            JOB, PROFILE, LLMConfig(enabled=False), "plain draft", ["react"]
        )
        assert mode == "template" and text.startswith("plain draft")


# ------------------------------------------------------------------------ api
def _client() -> TestClient:
    config.init_files()
    c = TestClient(create_app(start_poller=False))
    c.post("/api/auth/register",
           json={"email": "improve@test.dev", "password": "hunter2boogaloo"})
    return c


def _seed_job(user_id: int) -> int:
    db.ensure_db()
    rid, _ = db.upsert_job(
        {
            "guid": "imp-1",
            "source": "freelancer",
            "title": "React dashboard with Stripe billing",
            "url": "https://example.com/imp-1",
            "body": "Need a react + stripe developer.",
            "tags": ["react"],
        },
        85,
        {"skills": {"matched": ["react", "stripe"]}, "red_flags": [], "budget": {"note": ""}},
        "",
        user_id=user_id,
    )
    return rid


class TestImproveApi:
    def test_requires_auth(self):
        config.init_files()
        c = TestClient(create_app(start_poller=False))
        assert c.post("/api/jobs/1/improve", json={"text": "x"}).status_code == 401

    def test_improve_roundtrip(self):
        c = _client()
        jid = _seed_job(1)
        r = c.post(f"/api/jobs/{jid}/improve", json={"text": "Hire me, I am good."})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] and d["mode"] in ("template", "llm")
        assert "Worth a quick chat?" in d["text"]

    def test_empty_text_422(self):
        c = _client()
        jid = _seed_job(1)
        assert c.post(f"/api/jobs/{jid}/improve", json={"text": "   "}).status_code == 422

    def test_cannot_touch_other_accounts_job(self):
        c = _client()
        _seed_job(999)  # someone else's gig
        assert c.post("/api/jobs/1/improve", json={"text": "x"}).status_code == 404
