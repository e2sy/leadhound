"""Webhook tests — payload builders are pure; network is monkeypatched."""

import requests

from leadhound.config import WebhookConfig
from leadhound.notify import webhooks


def _job(score=85, draft="Hey — I can start Monday."):
    class J:
        pass

    j = J()
    j.title = "Build a Stripe checkout flow"
    j.url = "https://example.com/gig"
    j.score = score
    j.source = "remoteok"
    j.draft = draft
    return j


BREAKDOWN = {
    "budget": {"hourly": 55, "fixed_min": None},
    "skills": {"matched": ["react", "stripe"]},
    "red_flags": [],
}


class TestPayloads:
    def test_discord_embed_shape(self):
        p = webhooks.discord_payload(_job(), BREAKDOWN)
        e = p["embeds"][0]
        assert e["title"].startswith("Build a Stripe")
        assert e["url"] == "https://example.com/gig"
        assert "Score 85/100" in e["description"]
        assert "$55/hr" in e["description"]
        assert e["color"] == webhooks.GREEN

    def test_discord_color_bands(self):
        assert webhooks._score_color(90) == webhooks.GREEN
        assert webhooks._score_color(70) == webhooks.YELLOW
        assert webhooks._score_color(30) == webhooks.GREY

    def test_discord_shows_red_flags(self):
        bd = {**BREAKDOWN, "red_flags": ["unpaid"]}
        p = webhooks.discord_payload(_job(), bd)
        assert "unpaid" in p["embeds"][0]["description"]

    def test_slack_text_shape(self):
        p = webhooks.slack_payload(_job(), BREAKDOWN)
        assert "Score 85/100" in p["text"]
        assert "https://example.com/gig" in p["text"]
        assert "react" in p["text"]

    def test_money_falls_back_to_fixed_then_unstated(self):
        fixed = {"budget": {"hourly": None, "fixed_min": 1500}, "skills": {"matched": []}}
        assert "$1,500" in webhooks.discord_payload(_job(), fixed)["embeds"][0]["description"]
        none = {"budget": {"hourly": None, "fixed_min": None}, "skills": {"matched": []}}
        assert "not stated" in webhooks.slack_payload(_job(), none)["text"]


class TestSend:
    def test_only_configured_urls_are_posted(self, monkeypatch):
        calls = []

        def fake_post(url, **kw):
            calls.append(url)
            class R:
                status_code = 204
            return R()

        monkeypatch.setattr(webhooks.requests, "post", fake_post)
        cfg = WebhookConfig(discord_webhook_url="https://discord.com/api/webhooks/x", slack_webhook_url="")
        results = webhooks.send_webhooks(_job(), BREAKDOWN, cfg)
        assert [r[0] for r in results] == ["discord"]
        assert "https://discord.com/api/webhooks/x" in calls

    def test_network_failure_reports_false_not_crash(self, monkeypatch):
        def boom(url, **kw):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(webhooks.requests, "post", boom)
        cfg = WebhookConfig(discord_webhook_url="https://discord.com/api/webhooks/x")
        results = webhooks.send_webhooks(_job(), BREAKDOWN, cfg)
        assert results == [("discord", False)]

    def test_both_targets_when_configured(self, monkeypatch):
        calls = []

        def fake_post(url, **kw):
            calls.append(url)
            class R:
                status_code = 200
            return R()

        monkeypatch.setattr(webhooks.requests, "post", fake_post)
        cfg = WebhookConfig(
            discord_webhook_url="https://discord.com/api/webhooks/x",
            slack_webhook_url="https://hooks.slack.com/services/T/B/X",
        )
        results = webhooks.send_webhooks(_job(), BREAKDOWN, cfg)
        assert dict(results) == {"discord": True, "slack": True}
