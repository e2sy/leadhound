"""Email notifications — SMTP card formatting, honest send(), pipeline
wiring and config parsing. All SMTP traffic is faked via monkeypatch."""

from __future__ import annotations

from typing import ClassVar

import pytest

from leadhound import config
from leadhound.config import EmailConfig
from leadhound.notify import email as em
from leadhound.pipeline import ingest_jobs


@pytest.fixture
def profile(profile):
    return profile


class _FakeSMTP:
    """Records what send_email would put on the wire."""
    last_instance: ClassVar | None = None
    sent: ClassVar[list] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.log = []
        _FakeSMTP.last_instance = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.log.append("starttls")

    def login(self, u, p):
        self.log.append(f"login {u}")

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)
        self.log.append("sent")

    def quit(self):
        pass


class TestSendEmail:
    def test_sends_via_smtp_with_tls(self, monkeypatch):
        monkeypatch.setattr(em.smtplib, "SMTP", _FakeSMTP)
        cfg = EmailConfig(enabled=True, smtp_host="smtp.test.dev", smtp_port=465,
                          smtp_user="wolf@test.dev", smtp_pass="huff", to_addr="me@test.dev")
        assert em.send_email(cfg, "subject", "body") is True
        msg = _FakeSMTP.sent[-1]
        assert msg["To"] == "me@test.dev"
        assert msg["From"] == "wolf@test.dev"
        assert "body" in msg.get_content()
        assert "starttls" in _FakeSMTP.last_instance.log
        assert "login wolf@test.dev" in _FakeSMTP.last_instance.log

    def test_disabled_or_unconfigured_never_touches_smtp(self, monkeypatch):
        _FakeSMTP.sent.clear()
        monkeypatch.setattr(em.smtplib, "SMTP", _FakeSMTP)
        assert em.send_email(EmailConfig(enabled=False), "s", "b") is False
        assert em.send_email(EmailConfig(enabled=True, smtp_host="", to_addr="x@y.z"), "s", "b") is False
        assert em.send_email(EmailConfig(enabled=True, smtp_host="h", to_addr=""), "s", "b") is False
        assert _FakeSMTP.sent == []

    def test_smtp_failure_returns_false_not_raise(self, monkeypatch):
        class Boom:
            def __init__(self, *a, **k):
                raise OSError("connection refused")

        monkeypatch.setattr(em.smtplib, "SMTP", Boom)
        cfg = EmailConfig(enabled=True, smtp_host="smtp.test.dev", to_addr="me@test.dev")
        assert em.send_email(cfg, "s", "b") is False


class TestCardText:
    def _job(self, score=87):
        from leadhound.db import Job

        return Job(
            id=1, guid="g1", source="freelancer", title="Build a wolf dashboard",
            url="https://example.com/g1", body="react + stripe",
            budget_min=None, budget_max=1500.0, hourly=None, tags="react,stripe",
            posted_at=None, score=score, draft="Hey — I built 12 of these.",
        )

    def test_card_contains_score_money_draft(self):
        text = em.card_text(self._job(), {"budget": {"fixed_min": 800},
                                          "skills": {"matched": ["react", "stripe"]},
                                          "red_flags": []})
        assert "87/100" in text
        assert "$800" in text  # money comes from the parsed breakdown, not the raw job row
        assert "react, stripe" in text
        assert "Hey — I built 12 of these." in text
        assert "https://example.com/g1" in text

    def test_flags_shown(self):
        text = em.card_text(self._job(), {"budget": {}, "skills": {"matched": []},
                                          "red_flags": ["unpaid test"]})
        assert "unpaid test" in text


class TestPipelineWiring:
    def _jobs(self):
        return [{"guid": "em1", "source": "remoteok", "title": "React gig",
                 "url": "https://example.com/em1", "body": "react react react",
                 "tags": ["react"], "budget_max": 2000.0}]

    def test_enabled_config_sends_and_marks_notified(self, profile, monkeypatch):
        config.init_files()
        _FakeSMTP.sent.clear()
        monkeypatch.setattr(em.smtplib, "SMTP", _FakeSMTP)
        cfg = EmailConfig(enabled=True, smtp_host="smtp.test.dev", to_addr="me@test.dev")
        results = ingest_jobs(self._jobs(), profile=profile,
                              llm_cfg=config.LLMConfig(), min_score=0, em_cfg=cfg)
        assert results[0].notified is True
        assert len(_FakeSMTP.sent) == 1
        from leadhound import db

        assert db.get_job(results[0].rid).notified == 1

    def test_disabled_config_sends_nothing(self, profile, monkeypatch):
        config.init_files()
        _FakeSMTP.sent.clear()
        monkeypatch.setattr(em.smtplib, "SMTP", _FakeSMTP)
        results = ingest_jobs(self._jobs(), profile=profile,
                              llm_cfg=config.LLMConfig(), min_score=0,
                              em_cfg=EmailConfig(enabled=False))
        assert results[0].notified is False
        assert _FakeSMTP.sent == []

    def test_respects_min_score(self, profile):
        config.init_files()
        results = ingest_jobs(self._jobs(), profile=profile,
                              llm_cfg=config.LLMConfig(), min_score=99,
                              em_cfg=EmailConfig(enabled=True, smtp_host="h", to_addr="x@y.z"))
        assert results[0].notified is False  # no draft -> no email


class TestConfigParsing:
    def test_email_section_round_trips(self):
        config.init_files()
        config.config_path().write_text(
            '[watch]\nmin_score = 60\ninterval_minutes = 15\n'
            'sources = ["remoteok"]\n\n[email]\nenabled = true\n'
            'smtp_host = "smtp.fastmail.com"\nsmtp_port = 465\n'
            'smtp_user = "w@f.com"\nsmtp_pass = "pw"\nuse_tls = false\n'
            'to_addr = "me@here.dev"\n'
        )
        *_, emc = config.load_config()
        assert emc.enabled is True
        assert emc.smtp_host == "smtp.fastmail.com"
        assert emc.smtp_port == 465
        assert emc.use_tls is False
        assert emc.to_addr == "me@here.dev"

    def test_defaults_when_section_missing(self):
        config.init_files()
        *_, emc = config.load_config()
        assert emc.enabled is False and emc.smtp_port == 587
