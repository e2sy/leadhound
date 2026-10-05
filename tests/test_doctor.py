"""Doctor tests — offline checks only, no network."""

import requests

from leadhound import config, doctor
from leadhound.doctor import run_checks


def _by_name(checks):
    return {c.name: c for c in checks}


class TestDoctor:
    def test_fresh_init_passes_offline(self):
        config.init_files()
        checks = run_checks(offline=True)
        named = _by_name(checks)
        assert named["home"].ok is True
        assert named["profile: parse"].ok is True
        assert named["config: parse"].ok is True
        assert named["database"].ok is True

    def test_empty_skills_fails(self):
        config.init_files()
        path = config.profile_path()
        path.write_text(path.read_text().replace(
            'skills = [\n'
            '  "react native", "next.js", "react", "stripe", "node.js",\n'
            '  "python", "fastapi", "postgresql", "openai", "typescript",\n'
            ']',
            'skills = []',
        ))
        checks = run_checks(offline=True)
        named = _by_name(checks)
        assert named["profile: skills"].ok is False

    def test_uninitialized_reports_setup_failure(self):
        checks = run_checks(offline=True)
        named = _by_name(checks)
        assert named["setup"].ok is False
        assert "leadhound init" in named["setup"].hint

    def test_bad_toml_is_caught_not_crash(self):
        config.init_files()
        config.profile_path().write_text("this is not [valid toml")
        checks = run_checks(offline=True)
        named = _by_name(checks)
        assert named["profile"].ok is False
        assert "unparsable" in named["profile"].detail

    def test_advisory_checks_are_warnings_not_failures(self):
        config.init_files()
        # strip highlights from the default profile -> advisory warning (None), not a failure
        path = config.profile_path()
        path.write_text(path.read_text().replace(
            'highlights = [\n'
            '  "Shipped 12 production apps with React Native + Stripe",\n'
            '  "3 years of Next.js, 2 with App Router and live Stripe payments",\n'
            ']',
            'highlights = []',
        ))
        checks = run_checks(offline=True)
        named = _by_name(checks)
        assert named["profile: proof bullets"].ok is None

    def test_disabled_telegram_and_llm_produce_no_checks(self):
        config.init_files()
        checks = run_checks(offline=True)
        assert not any(c.name == "llm" for c in checks)
        assert not any(c.name == "telegram" for c in checks)


# ------------------------------------------------------------------ update check
class FakeResp:
    def __init__(self, status=200, tag="v0.9.1"):
        self.status_code = status
        self._tag = tag

    def json(self):
        return {"tag_name": self._tag}


def test_update_check_outdated(monkeypatch):
    monkeypatch.setattr("leadhound.doctor.requests.get",
                        lambda *a, **k: FakeResp(tag="v99.0.0"))
    c = doctor._check_update()
    assert c.ok is None and "v99.0.0 is available" in c.detail


def test_update_check_up_to_date(monkeypatch):
    from leadhound import __version__
    monkeypatch.setattr("leadhound.doctor.requests.get",
                        lambda *a, **k: FakeResp(tag=f"v{__version__}"))
    assert doctor._check_update().ok is True


def test_update_check_no_releases_yet(monkeypatch):
    monkeypatch.setattr("leadhound.doctor.requests.get",
                        lambda *a, **k: FakeResp(status=404))
    assert doctor._check_update().ok is True


def test_update_check_network_down_is_only_a_warning(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr("leadhound.doctor.requests.get", boom)
    c = doctor._check_update()
    assert c.ok is None and "skipped" in c.detail


def test_offline_mode_skips_update_check():
    config.init_files()
    names = [c.name for c in doctor.run_checks(offline=True)]
    assert "version" not in names
