"""The polite fast lane — conditional GET (ETag / Last-Modified) for the
cheap public feeds, per-connector poll floors, and ±20% jitter so a fleet
of hounds never lands on a source at the same second. Network is mocked."""

from __future__ import annotations

import random

import pytest

from leadhound.api import _connector_interval, _jittered, _poll_floor_for
from leadhound.watchers import rss


@pytest.fixture(autouse=True)
def clean_cache():
    rss._cond.clear()
    yield
    rss._cond.clear()


class _Resp:
    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_remoteok_stores_etag_then_304_short_circuits(monkeypatch):
    payload = [
        {"legal": "notice"},
        {"id": 1, "position": "React dev", "url": "https://remoteok.com/1",
         "description": "react", "tags": ["react"], "date": 1767000000},
    ]
    seen: list[dict] = []

    def fake_get(url, headers=None, timeout=None):
        seen.append(dict(headers or {}))
        if len(seen) == 1:
            return _Resp(200, {"ETag": '"abc123"', "Content-Type": "application/json"},
                         payload)
        return _Resp(304)

    monkeypatch.setattr(rss.requests, "get", fake_get)
    jobs = rss.remoteok()
    assert len(jobs) == 1 and jobs[0]["source"] == "remoteok"
    assert seen[0].get("If-None-Match") is None          # first poll: full GET
    jobs2 = rss.remoteok()
    assert jobs2 == []                                    # 304 → nothing new
    assert seen[1].get("If-None-Match") == '"abc123"'     # second poll: conditional


def test_remotive_uses_last_modified_too(monkeypatch):
    payload = {"jobs": [{"id": 9, "title": "Node dev", "url": "https://r/9",
                         "description": "node", "tags": ["node.js"]}]}
    seen: list[dict] = []

    def fake_get(url, headers=None, timeout=None):
        seen.append(dict(headers or {}))
        if len(seen) == 1:
            return _Resp(200, {"Last-Modified": "Tue, 06 Oct 2026 09:00:00 GMT"},
                         payload)
        return _Resp(304)

    monkeypatch.setattr(rss.requests, "get", fake_get)
    assert len(rss.remotive()) == 1
    assert rss.remotive() == []
    assert seen[1].get("If-Modified-Since") == "Tue, 06 Oct 2026 09:00:00 GMT"


class _Feed:
    def __init__(self, entries, etag=None, modified=None, status=200):
        self.entries = entries
        self.etag = etag
        self.modified = modified
        self.status = status


def test_weworkremotely_conditional_feedparser(monkeypatch):
    entry = {"id": "e1", "link": "https://wwr/1", "title": "Designer",
             "summary": "design gig", "tags": []}
    calls: list[dict] = []

    def fake_parse(url, request_headers=None, etag=None, modified=None):
        calls.append({"url": url, "etag": etag, "modified": modified})
        if etag == '"w1"':
            return _Feed([], etag='"w1"', status=304)
        return _Feed([entry], etag='"w1"')

    monkeypatch.setattr(rss.feedparser, "parse", fake_parse)
    jobs = rss.weworkremotely()
    assert len(jobs) == 1
    assert calls[0]["etag"] is None                     # first poll: no validators
    assert rss.weworkremotely() == []                   # 304 on the second
    assert calls[1]["etag"] == '"w1"'                   # validator replayed


def test_poll_floor_by_connector():
    assert _poll_floor_for({"connector_id": "remoteok"}) == 2
    assert _poll_floor_for({"connector_id": "hackernews"}) == 2
    assert _poll_floor_for({"connector_id": "fiverr"}) == 5
    assert _poll_floor_for({"connector_id": "upwork"}) == 5
    assert _poll_floor_for({"connector_id": "who-knows"}) == 5  # unknown = safe


def test_interval_clamps_to_connector_floor():
    fast = {"connector_id": "remoteok", "settings": {"poll_minutes": 3}}
    slow = {"connector_id": "fiverr", "settings": {"poll_minutes": 3}}
    assert _connector_interval(fast, 15) == 3    # fast lane allowed
    assert _connector_interval(slow, 15) == 5    # cookie floor holds
    huge = {"connector_id": "remoteok", "settings": {"poll_minutes": 500}}
    assert _connector_interval(huge, 15) == 120  # ceiling everywhere
    unset = {"connector_id": "remoteok", "settings": {}}
    assert _connector_interval(unset, 15) == 15  # global default


def test_jitter_stays_within_twenty_percent():
    random.seed(42)
    for _ in range(200):
        assert 8.0 <= _jittered(10) <= 12.0
