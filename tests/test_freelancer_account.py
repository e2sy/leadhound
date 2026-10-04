"""Freelancer.com account-link tests — every network touch is mocked."""

from __future__ import annotations

import pytest

from leadhound.connectors import REGISTRY
from leadhound.connectors import freelancer_account as fa


def _resp(payload, *, status=200):
    class R:
        def __init__(self):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            import requests

            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}")

    return R()


# ------------------------------------------------------------------ registry
def test_registered_as_account_link():
    conn = REGISTRY["freelancer_account"]
    assert conn.kind == "keys"
    assert conn.needs_setup
    assert "snipe" in conn.blurb.lower()


# --------------------------------------------------------------------- oauth
def test_authorize_url_shape():
    url = fa.authorize_url("cid-1", "http://x/cb", "state-1")
    assert "response_type=code" in url and "client_id=cid-1" in url
    assert "state=state-1" in url and "redirect_uri=" in url
    with pytest.raises(fa.FreelancerNotConnectedError):
        fa.authorize_url("", "http://x/cb", "s")


def test_exchange_code_merges_tokens(monkeypatch):
    monkeypatch.setattr(
        fa, "_token_request", lambda data: {"access_token": "at", "refresh_token": "rt",
                                            "expires_in": 3600}
    )
    merged = fa.exchange_code({"client_id": "a", "client_secret": "b"}, "code", "cb")
    assert merged["access_token"] == "at"
    assert merged["refresh_token"] == "rt"
    assert merged["expires_at"] > 0


def test_exchange_code_requires_keys():
    with pytest.raises(fa.FreelancerNotConnectedError):
        fa.exchange_code({}, "code", "cb")


def test_ensure_access_fresh_token_skips_refresh():
    import time

    tok, updated = fa._ensure_access({"access_token": "t", "expires_at": int(time.time()) + 600})
    assert tok == "t" and updated is None


def test_ensure_access_refreshes_expired(monkeypatch):
    monkeypatch.setattr(
        fa, "_token_request", lambda data: {"access_token": "new", "expires_in": 60}
    )
    tok, updated = fa._ensure_access({"refresh_token": "r", "expires_at": 1})
    assert tok == "new"
    assert updated and updated["access_token"] == "new"


def test_ensure_access_unlinked_is_honest():
    with pytest.raises(fa.FreelancerNotConnectedError):
        fa._ensure_access({})


# --------------------------------------------------------------------- whoami
def test_whoami_parses_identity(monkeypatch):
    seen = {}

    def fake_request(method, url, **kw):
        seen["method"], seen["url"] = method, url
        return _resp({"status": "success",
                      "result": {"id": 9, "username": "mayank", "display_name": "Mayank B."}})

    monkeypatch.setattr(fa.requests, "request", fake_request)
    identity, updated = fa.whoami({"access_token": "t", "expires_at": 10**12})
    assert identity == {"id": 9, "username": "mayank", "display_name": "Mayank B."}
    assert updated is None
    assert seen["url"].endswith("/users/0.1/self/")


def test_whoami_error_envelope_is_human(monkeypatch):
    monkeypatch.setattr(
        fa.requests, "request",
        lambda *a, **k: _resp({"status": "error", "error": {"code": 100, "message": "bad token"}}),
    )
    with pytest.raises(fa.FreelancerError, match="bad token"):
        fa.whoami({"access_token": "t", "expires_at": 10**12})


# ------------------------------------------------------------------- bidding
def test_place_bid_fires_real_bid(monkeypatch):
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw.get("json")))
        if "/bids/" in url:
            return _resp({"status": "success", "result": {"id": 424242}})
        return _resp({"status": "success", "result": {"id": 9, "username": "mayank"}})

    monkeypatch.setattr(fa.requests, "request", fake_request)
    result, _updated = fa.place_bid(
        {"access_token": "t", "expires_at": 10**12},
        40744513,
        amount=1500,
        period=7,
        description="I can ship this in React.",
    )
    assert result["id"] == 424242
    method, url, body = calls[-1]
    assert method == "POST" and "/projects/40744513/bids/" in url
    assert body["bidder_id"] == 9
    assert body["amount"] == 1500.0
    assert body["period"] == 7
    assert "React" in body["description"]


def test_place_bid_rejects_zero_amount():
    with pytest.raises(fa.FreelancerError, match="amount"):
        fa.place_bid({}, 1, amount=0)


def test_place_bid_surfaces_api_error(monkeypatch):
    def fake_request(method, url, **kw):
        if "/bids/" in url:
            return _resp({"status": "error", "error": {"code": 4, "message": "bid too low"}})
        return _resp({"status": "success", "result": {"id": 9, "username": "m"}})

    monkeypatch.setattr(fa.requests, "request", fake_request)
    with pytest.raises(fa.FreelancerError, match="bid too low"):
        fa.place_bid({"access_token": "t", "expires_at": 10**12}, 5, amount=10)


# ---------------------------------------------------------------------- fetch
def test_fetch_validates_and_stashes_identity(monkeypatch):
    monkeypatch.setattr(
        fa.requests, "request",
        lambda *a, **k: _resp({"status": "success",
                               "result": {"id": 9, "username": "mayank", "display_name": "M"}}),
    )
    jobs, updated = fa.fetch({"access_token": "t", "expires_at": 10**12})
    assert jobs == []
    assert updated["identity"]["username"] == "mayank"
    assert updated["access_token"] == "t"
