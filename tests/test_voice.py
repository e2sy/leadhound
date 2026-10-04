"""Voice engine tests — template mode must work with zero config, zero network."""

from leadhound.config import LLMConfig
from leadhound.engine.voice import draft_proposal

JOB = {
    "guid": "v-1",
    "source": "test",
    "title": "Build me a Stripe checkout app",
    "url": "https://example.com/x",
    "body": "react + stripe",
    "tags": [],
    "hourly": 50,
}


def test_template_mode_offline(profile):
    draft, mode = draft_proposal(JOB, profile, LLMConfig(), ["react", "stripe"])
    assert mode == "template"
    assert "Stripe checkout app" in draft
    assert profile.name in draft          # signs with the user's name
    assert "- Shipped 10 apps" in draft   # injects proof bullets
    assert "1)" in draft and "2)" in draft and "3)" in draft  # 3-step plan
    assert "$50/hr" in draft              # mirrors the budget


def test_llm_disabled_means_no_network_call(profile):
    llm = LLMConfig(enabled=False, api_key="")
    _, mode = draft_proposal(JOB, profile, llm, [])
    assert mode == "template"


def test_llm_failure_falls_back_to_template(profile):
    llm = LLMConfig(enabled=True, api_key="bad-key", base_url="http://127.0.0.1:9/v1")
    _, mode = draft_proposal(JOB, profile, llm, [])
    assert mode == "template"  # graceful fallback, never crashes the pipeline
