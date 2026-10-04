"""Connector tests — every network touch is mocked; nothing leaves localhost."""

from __future__ import annotations

import json

import pytest

from leadhound.connectors import REGISTRY, Connector, fiverr, freelancer, rss_custom, upwork


def _fake_response(payload=None, *, status=200, text="", url=""):
    class R:
        def __init__(self):
            self.status_code = status
            self.text = text
            self.url = url
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError("no json")
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                import requests

                raise requests.HTTPError(f"{self.status_code}")

    return R()


# ------------------------------------------------------------------ registry
def test_registry_has_expected_sources():
    ids = set(REGISTRY)
    assert {"remoteok", "remotive", "weworkremotely", "hackernews",
            "freelancer", "upwork", "fiverr", "rss"} <= ids
    for cid in ("remoteok", "remotive", "weworkremotely", "hackernews"):
        assert REGISTRY[cid].kind == "public"


# ---------------------------------------------------------------- freelancer
def test_freelancer_normalizes(monkeypatch):
    payload = {"result": {"projects": [
        {"id": 40744513, "title": "Build <b>React</b> app", "seo_url": "web/Build-React",
         "preview_description": "Need a  react  dev.", "submitdate": 1790861932,
         "type": "fixed", "budget": {"minimum": 750.0, "maximum": 1500.0},
         "jobs": [{"name": "React.js"}, {"name": "Nextjs"}]},
        {"id": 2, "title": "Hourly dev", "seo_url": "x/Hourly", "type": "hourly",
         "budget": {"minimum": 40.0, "maximum": 60.0}, "jobs": []},
        {"id": 3, "title": "deleted one", "deleted": True},
    ]}}
    monkeypatch.setattr(freelancer.requests, "get",
                        lambda *a, **k: _fake_response(payload))
    jobs, updated = freelancer.fetch({"query": "react"})
    assert updated is None
    assert len(jobs) == 2
    j = jobs[0]
    assert j["guid"] == "freelancer-40744513"
    assert j["source"] == "freelancer"
    assert j["title"] == "Build React app"
    assert j["budget_min"] == 750.0 and j["budget_max"] == 1500.0
    assert j["hourly"] is None
    assert "React.js" in j["tags"]
    assert j["url"].startswith("https://www.freelancer.com/projects/")
    assert jobs[1]["hourly"] == 40.0


def test_freelancer_http_error_surfaces(monkeypatch):
    import requests as _requests

    monkeypatch.setattr(freelancer.requests, "get",
                        lambda *a, **k: _fake_response(status=500))
    with pytest.raises(_requests.HTTPError):
        freelancer.fetch({})


# ----------------------------------------------------------------- rss feed
def test_rss_custom_requires_url():
    with pytest.raises(rss_custom.FeedError, match="feed URL"):
        rss_custom.fetch({})


def test_rss_custom_rejects_non_http():
    with pytest.raises(rss_custom.FeedError, match="http"):
        rss_custom.fetch({"url": "file:///etc/passwd"})


def test_rss_custom_parses(monkeypatch):
    class Entry(dict):
        pass

    feed = type("F", (), {})()
    feed.bozo = False
    feed.entries = [
        {"id": "abc", "title": "Gig one", "link": "https://x.example/1",
         "summary": "<p>body</p>", "tags": [{"term": "react"}], "published_parsed": None},
    ]
    monkeypatch.setattr(rss_custom.feedparser, "parse", lambda url, request_headers=None: feed)
    jobs, _ = rss_custom.fetch({"url": "https://feeds.example/jobs.rss"})
    assert len(jobs) == 1
    assert jobs[0]["guid"] == "rss:feeds.example:abc"
    assert jobs[0]["source"] == "rss:feeds.example"
    assert jobs[0]["body"] == "body"


# -------------------------------------------------------------------- upwork
def test_upwork_authorize_url_requires_client():
    with pytest.raises(upwork.UpworkNotConnectedError):
        upwork.authorize_url("", "http://x/cb", "state123")


def test_upwork_authorize_url_shape():
    url = upwork.authorize_url("cid-1", "http://127.0.0.1:7800/api/connectors/upwork/callback", "s1")
    assert "client_id=cid-1" in url and "state=s1" in url
    assert url.startswith("https://www.upwork.com/ab/account-security/oauth2/authorize")


def test_upwork_not_connected_when_no_tokens():
    with pytest.raises(upwork.UpworkNotConnectedError):
        upwork.fetch({"client_id": "a", "client_secret": "b"})


def test_upwork_fetch_uses_access_token(monkeypatch):
    calls = {}

    def fake_post(url, **kw):
        calls["url"] = url
        calls["headers"] = kw.get("headers")
        return _fake_response({"data": {"jobs_market_place_job_postings_search": {
            "edges": [{"node": {
                "id": "u1", "title": "React dev needed",
                "description": "<p>long-term</p>",
                "createdDateTime": "2026-10-01T00:00:00Z",
                "budget": {"minAmount": 500, "maxAmount": 900},
            }}]}}})

    monkeypatch.setattr(upwork.requests, "post", fake_post)
    settings = {"access_token": "tok123", "expires_at": upwork.time.time() + 9999,
                "refresh_token": "r1", "client_id": "a", "client_secret": "b"}
    jobs, updated = upwork.fetch(settings)
    assert updated is None  # token still valid, nothing rotated
    assert calls["url"] == upwork.GQL_URL
    assert calls["headers"]["Authorization"] == "Bearer tok123"
    assert jobs[0]["guid"] == "upwork-u1"
    assert jobs[0]["budget_min"] == 500


def test_upwork_refresh_rotates_settings(monkeypatch):
    def fake_post(url, **kw):
        if url == upwork.TOKEN_URL:
            assert kw["data"]["grant_type"] == "refresh_token"
            return _fake_response({"access_token": "newtok", "refresh_token": "r2",
                                   "expires_in": 3600})
        return _fake_response({"data": {"jobs_market_place_job_postings_search": {"edges": []}}})

    monkeypatch.setattr(upwork.requests, "post", fake_post)
    expired = {"access_token": "old", "expires_at": upwork.time.time() - 10,
               "refresh_token": "r1", "client_id": "a", "client_secret": "b"}
    jobs, updated = upwork.fetch(expired)
    assert jobs == []
    assert updated["access_token"] == "newtok"
    assert updated["refresh_token"] == "r2"
    assert updated["expires_at"] > upwork.time.time()


def test_upwork_graphql_errors_surfaced(monkeypatch):
    monkeypatch.setattr(
        upwork.requests, "post",
        lambda *a, **k: _fake_response({"errors": [{"message": "access denied"}]}),
    )
    settings = {"access_token": "t", "expires_at": upwork.time.time() + 9999,
                "refresh_token": "r", "client_id": "a", "client_secret": "b"}
    with pytest.raises(upwork.UpworkError, match="access denied"):
        upwork.fetch(settings)


# --------------------------------------------------------------------- fiverr
def test_fiverr_requires_cookie():
    with pytest.raises(fiverr.FiverrError, match="cookie"):
        fiverr.fetch({})


def test_fiverr_rejected_cookie(monkeypatch):
    monkeypatch.setattr(fiverr.requests, "get",
                        lambda *a, **k: _fake_response(status=401))
    with pytest.raises(fiverr.FiverrError, match="fresh"):
        fiverr.fetch({"cookie": "stale"})


def test_fiverr_parses_embedded_json(monkeypatch):
    blob = json.dumps({"buyerRequests": {"requests": [
        {"id": 551, "brief": "Need a React dashboard",
         "description": "Funded startup. Budget $1,500 - $2,500 fixed.",
         "budget": {"min": 1500, "max": 2500}, "category": "Programming",
         "buyer": {"username": "startup_owl"}},
        {"id": 552, "title": "Python scraper", "details": "quick task",
         "minBudget": 50},
    ]}})
    html = f"<html><script type=\"application/json\">{blob}</script></html>"
    monkeypatch.setattr(
        fiverr.requests, "get",
        lambda *a, **k: _fake_response(text=html, url="https://www.fiverr.com/buyer_requests"),
    )
    jobs, _ = fiverr.fetch({"cookie": "c=1"})
    assert len(jobs) == 2
    assert jobs[0]["guid"] == "fiverr-551"
    assert jobs[0]["source"] == "fiverr"
    assert jobs[0]["title"] == "Need a React dashboard"
    assert jobs[0]["budget_min"] == 1500.0 and jobs[0]["budget_max"] == 2500.0
    assert jobs[1]["budget_min"] == 50.0


def test_fiverr_honest_failure_on_unknown_layout(monkeypatch):
    monkeypatch.setattr(
        fiverr.requests, "get",
        lambda *a, **k: _fake_response(text="<html>no data here</html>",
                                       url="https://www.fiverr.com/buyer_requests"),
    )
    with pytest.raises(fiverr.FiverrError, match="couldn't find buyer requests"):
        fiverr.fetch({"cookie": "c=1"})


# ------------------------------------------------------------------ registry
def test_connector_object_contract():
    for conn in REGISTRY.values():
        assert isinstance(conn, Connector)
        assert conn.id and conn.label and conn.kind in ("public", "keys", "cookie", "feed")
        assert callable(conn.fetch)
