"""Starter packs — one-click niche bundles wired to real feed channels.

Every channel shipped in presets.py was verified against the live source
before landing; these tests pin the registry sanity, the fetch plumbing
(monkeypatched — CI never touches the network) and the apply endpoint.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from leadhound import config, db
from leadhound.api import create_app
from leadhound.connectors import REGISTRY
from leadhound.presets import PACKS, channel, validate
from leadhound.watchers import rss


class TestRegistry:
    def test_validate_clean(self):
        assert validate() == []

    def test_pack_targets_exist_in_registry(self):
        for p in PACKS.values():
            for t in p["targets"]:
                assert t["connector"] in REGISTRY, t["connector"]

    def test_channels_cover_every_preset_reference(self):
        for p in PACKS.values():
            for t in p["targets"]:
                assert channel(t["connector"], t["preset"]) is not None

    def test_unknown_preset_falls_back_to_none(self):
        assert channel("remotive", "nope") is None
        assert channel("remotive", None) is None

    def test_channel_known_bad_connector_is_none(self):
        assert channel("not-a-source", "design") is None


class TestFetchChannels:
    def test_wwr_preset_changes_feed_url(self, monkeypatch):
        seen = {}

        def fake_parse(url, request_headers=None):
            seen["url"] = url
            m = MagicMock()
            m.entries = []
            return m

        monkeypatch.setattr(rss.feedparser, "parse", fake_parse)
        rss.weworkremotely({"preset": "programming"})
        assert "remote-programming-jobs" in seen["url"]
        rss.weworkremotely({})  # no preset -> the classic freelance feed
        assert "remote-freelance-jobs" in seen["url"]

    def test_remotive_preset_changes_category(self, monkeypatch):
        seen = {}

        def fake_get(url, headers=None, timeout=None):
            seen["url"] = url
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {"jobs": []}
            return m

        monkeypatch.setattr(rss.requests, "get", fake_get)
        rss.remotive({"preset": "design"})
        assert "category=design" in seen["url"]
        rss.remotive({})
        assert "category=software-dev" in seen["url"]

    def test_registry_adapters_pass_settings_through(self, monkeypatch):
        seen = {}

        def fake_get(url, headers=None, timeout=None):
            seen["url"] = url
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {"jobs": []}
            return m

        monkeypatch.setattr(rss.requests, "get", fake_get)
        jobs, err = REGISTRY["remotive"].fetch({"preset": "sales"})
        assert err is None and jobs == []
        assert "category=sales" in seen["url"]


# ------------------------------------------------------------------------ api
def _client() -> TestClient:
    config.init_files()
    c = TestClient(create_app(start_poller=False))
    c.post("/api/auth/register",
           json={"email": "packs@test.dev", "password": "hunter2boogaloo"})
    return c


class TestPresetsApi:
    def test_requires_auth(self):
        config.init_files()
        c = TestClient(create_app(start_poller=False))
        assert c.get("/api/presets").status_code == 401
        assert c.post("/api/presets/dev/apply").status_code == 401

    def test_list_packs(self):
        c = _client()
        d = c.get("/api/presets").json()
        assert d["ok"] and len(d["packs"]) == len(PACKS)
        keys = {p["key"] for p in d["packs"]}
        assert "dev" in keys and "freelance" in keys
        assert all("blurb" in p for p in d["packs"])

    def test_apply_arms_sources_and_sets_channel(self):
        c = _client()
        r = c.post("/api/presets/dev/apply")
        assert r.status_code == 200
        d = r.json()
        assert d["armed"] == ["weworkremotely", "remotive"]
        for cid, preset in (("weworkremotely", "programming"), ("remotive", "software-dev")):
            cfg = db.connector_cfg(1, cid)
            assert cfg["enabled"] == 1
            assert cfg["settings"]["preset"] == preset

    def test_apply_keeps_existing_settings(self):
        c = _client()
        db.save_connector_cfg(1, "remotive", enabled=False, settings={"query": "react"})
        c.post("/api/presets/design/apply")
        cfg = db.connector_cfg(1, "remotive")
        assert cfg["enabled"] == 1
        assert cfg["settings"]["query"] == "react"      # kept
        assert cfg["settings"]["preset"] == "design"    # added

    def test_apply_unknown_pack_404(self):
        c = _client()
        assert c.post("/api/presets/vibecoding/apply").status_code == 404

    def test_accounts_are_isolated(self):
        c = _client()
        c.post("/api/presets/dev/apply")
        # a second account sees nothing armed
        c.post("/api/auth/logout")
        c.post("/api/auth/register",
               json={"email": "other@test.dev", "password": "hunter2boogaloo"})
        cfg = db.connector_cfg(2, "remotive")
        assert cfg.get("enabled") in (0, None)
