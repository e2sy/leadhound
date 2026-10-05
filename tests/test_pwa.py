"""PWA endpoints — manifest, service worker, icon.

The dashboard is installable as a pocket console (pairs with the Telegram
pocket sniper). These tests pin the contract: the manifest is valid JSON
with an icon, the worker never caches /api/* live data, and the shell
references all three.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from leadhound import config
from leadhound.api import create_app
from leadhound.webassets import PAGE


def _client() -> TestClient:
    config.init_files()
    return TestClient(create_app(start_poller=False))


class TestManifest:
    def test_manifest_is_valid_json(self):
        r = _client().get("/manifest.webmanifest")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/manifest+json")
        m = json.loads(r.text)
        assert "leadhound" in m["name"]
        assert m["start_url"] == "/" and m["display"] == "standalone"

    def test_manifest_declares_icon(self):
        m = json.loads(_client().get("/manifest.webmanifest").text)
        assert m["icons"], "manifest must declare at least one icon"
        assert m["icons"][0]["src"] == "/icon.svg"


class TestServiceWorker:
    def test_sw_served_as_js(self):
        r = _client().get("/sw.js")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/javascript")

    def test_sw_never_caches_api(self):
        js = _client().get("/sw.js").text
        assert 'startsWith("/api/")' in js, "live data must bypass the cache"
        assert "fetch" in js and "install" in js and "activate" in js

    def test_sw_served_fresh_per_browser(self):
        # /sw.js must not be cached by the worker itself (stale-worker trap)
        js = _client().get("/sw.js").text
        assert 'url.pathname === "/sw.js"' in js


class TestIconAndShell:
    def test_icon_is_svg(self):
        r = _client().get("/icon.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert r.text.lstrip().startswith("<svg")

    def test_shell_links_manifest_and_registers_worker(self):
        html = _client().get("/").text
        assert PAGE  # shell is the served page
        assert 'rel="manifest"' in html
        assert "serviceWorker" in html
        assert 'href="/icon.svg"' in html
