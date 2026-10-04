"""profile learn tests — pure logic + mocked GitHub API (no network)."""

import pytest

from leadhound import learn
from leadhound.config import Profile, load_profile


class TestParseTarget:
    def test_bare_username(self):
        assert learn.parse_github_target("e2sy") == "e2sy"

    def test_full_url(self):
        assert learn.parse_github_target("https://github.com/e2sy") == "e2sy"

    def test_www_and_trailing_slash(self):
        assert learn.parse_github_target("https://www.github.com/e2sy/") == "e2sy"

    def test_http_url(self):
        assert learn.parse_github_target("http://github.com/torvalds") == "torvalds"

    @pytest.mark.parametrize("bad", ["", "a/b", "https://gitlab.com/x", "has space"])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            learn.parse_github_target(bad)


class TestNormalize:
    def test_go_is_mapped_not_kept(self):
        assert learn.normalize_skill("Go") == "golang"

    def test_noise_dropped(self):
        assert learn.normalize_skill("HTML") is None
        assert learn.normalize_skill("Jupyter Notebook") is None

    def test_map_hits(self):
        assert learn.normalize_skill("Vue") == "vue.js"
        assert learn.normalize_skill("Shell") == "bash"
        assert learn.normalize_skill("TypeScript") == "typescript"

    def test_topic_hyphens_become_spaces(self):
        assert learn.normalize_skill("react-native", is_topic=True) == "react native"

    def test_topic_nextjs(self):
        assert learn.normalize_skill("nextjs", is_topic=True) == "next.js"


class TestLearnSkills:
    def _fake_repos(self):
        return [
            {"fork": False, "language": "TypeScript", "topics": ["react", "nextjs"]},
            {"fork": False, "language": "TypeScript", "topics": ["stripe"]},
            {"fork": False, "language": "Python", "topics": []},
            {"fork": True, "language": "Rust", "topics": ["wasm"]},  # skipped
            {"fork": False, "language": None, "topics": []},
            {"fork": False, "language": "HTML", "topics": ["css"]},  # noise
        ]

    def test_ranking_and_fork_skip(self, monkeypatch):
        def fake_get(url):
            return self._fake_repos() if "/repos?" in url else {"name": "Mayank", "bio": "builder"}

        monkeypatch.setattr(learn, "_get_json", fake_get)
        out = learn.learn_skills("e2sy")
        assert out["name"] == "Mayank"
        assert out["repos_scanned"] == 5  # fork skipped
        assert out["languages"][0] == "typescript"  # 2 repos, top
        assert "rust" not in out["languages"]
        assert "html" not in out["languages"]
        assert out["topics"][:2] == ["react", "next.js"]

    def test_user_not_found(self, monkeypatch):
        monkeypatch.setattr(learn, "_get_json", lambda url: {"message": "Not Found"})
        with pytest.raises(ValueError):
            learn.learn_skills("ghost404")


class TestMergeAndToml:
    def test_merge_keeps_user_order_and_appends(self):
        merged = learn.merge_skills(
            ["react", "stripe"], ["golang", "stripe", "vue.js"], cap=4
        )
        assert merged == ["react", "stripe", "golang", "vue.js"]

    def test_merge_respects_cap(self):
        merged = learn.merge_skills(["a"], ["b", "c", "d"], cap=2)
        assert merged == ["a", "b"]

    PROFILE = (
        "# my profile\nname = \"Me\"\n\n"
        "# skills the scorer hunts for\n"
        "skills = [\n  \"react\",\n  \"stripe\",\n]\n\n"
        "min_hourly = 30\n"
    )

    def test_update_replaces_only_skills_block(self):
        new, ok = learn.update_profile_skills(
            self.PROFILE, ["react", "stripe", "golang"]
        )
        assert ok
        assert "golang" in new
        assert "# my profile" in new and "# skills the scorer hunts for" in new
        assert "min_hourly = 30" in new
        assert '  "react",' in new

    def test_update_still_valid_toml(self):
        import tomllib

        new, ok = learn.update_profile_skills(
            self.PROFILE, ["react", "golang"]
        )
        assert ok
        raw = tomllib.loads(new)
        assert raw["skills"] == ["react", "golang"]
        assert raw["min_hourly"] == 30

    def test_update_without_skills_block(self):
        new, ok = learn.update_profile_skills("name = \"X\"\n", ["react"])
        assert not ok and new == "name = \"X\"\n"

    def test_roundtrip_with_real_profile(self, isolated_home):
        from leadhound.config import init_files

        init_files()
        before = load_profile()
        detected = ["typescript", "stripe", "python"]
        merged = learn.merge_skills(before.skills, detected)
        from leadhound.config import profile_path

        text = profile_path().read_text()
        new, ok = learn.update_profile_skills(text, merged)
        assert ok
        profile_path().write_text(new)
        after = load_profile()
        assert isinstance(after, Profile)
        assert "stripe" in after.skills
        assert set(detected) <= set(after.skills)
