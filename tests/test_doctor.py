"""Doctor tests — offline checks only, no network."""

from leadhound import config
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
