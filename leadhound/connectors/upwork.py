"""Upwork connector — real OAuth2, real GraphQL job search.

Upwork has no anonymous feed (their RSS requires a logged-in session), so
this connector uses the official path: the user creates a free developer app
at upwork.com, pastes the client id + secret once, and leadhound runs the
authorization-code flow, stores the refresh token locally, and auto-refreshes
the access token on every poll.

Public API reference: https://developers.upwork.com
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import datetime

import requests

from ..watchers import UA

AUTHORIZE_URL = "https://www.upwork.com/ab/account-security/oauth2/authorize"
TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"  # noqa: S105 — endpoint URL, not a secret
GQL_URL = "https://api.upwork.com/graphql"

_SEARCH_GQL = """
query lh($q: String!) {
  jobs_market_place_job_postings_search(
    searchType: eq
    searchExpression_eq: $q
    sortType: RECENCY
    pageSize: 50
  ) {
    total_count
    edges {
      node {
        id
        title
        description
        createdDateTime
        totalApplicants
        verifiedPaymentMethod
        budget { minAmount maxAmount currencyCode }
      }
    }
  }
}
"""


class UpworkError(RuntimeError):
    pass


class UpworkNotConnectedError(UpworkError):
    pass


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    if not client_id:
        raise UpworkNotConnectedError("add your Upwork client id first")
    return (
        f"{AUTHORIZE_URL}?response_type=code&client_id={client_id}"
        f"&redirect_uri={redirect_uri}&state={state}"
    )


def _token_request(data: dict) -> dict:
    r = requests.post(TOKEN_URL, data=data, headers=UA, timeout=25)
    if r.status_code in (400, 401):
        raise UpworkError(f"Upwork rejected the credentials ({r.status_code})")
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise UpworkError("Upwork response had no access_token")
    return tok


def exchange_code(settings: dict, code: str, redirect_uri: str) -> dict:
    """Authorization-code -> tokens. Returns updated settings to persist."""
    client_id = (settings or {}).get("client_id", "")
    client_secret = (settings or {}).get("client_secret", "")
    if not (client_id and client_secret):
        raise UpworkNotConnectedError("client id and client secret are both required")
    tok = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )
    return _merge_tokens(settings, tok)


def _merge_tokens(settings: dict, tok: dict) -> dict:
    merged = dict(settings or {})
    merged["access_token"] = tok["access_token"]
    if tok.get("refresh_token"):
        merged["refresh_token"] = tok["refresh_token"]
    merged["expires_at"] = int(time.time()) + int(tok.get("expires_in", 0) or 0)
    return merged


def _ensure_access(settings: dict) -> tuple[str, dict | None]:
    """Return (access_token, updated_settings_if_refreshed)."""
    s = settings or {}
    if not s.get("refresh_token") and not s.get("access_token"):
        raise UpworkNotConnectedError("not connected yet — paste your app keys and connect")
    if s.get("access_token") and time.time() < float(s.get("expires_at") or 0) - 60:
        return s["access_token"], None
    tok = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": s.get("refresh_token", ""),
            "client_id": s.get("client_id", ""),
            "client_secret": s.get("client_secret", ""),
        }
    )
    merged = _merge_tokens(s, tok)
    return merged["access_token"], merged


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _iso(ts) -> str | None:
    with contextlib.suppress(Exception):
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).isoformat(
            timespec="seconds"
        )
    return None


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    token, updated = _ensure_access(settings)
    variables = {"q": str((settings or {}).get("query") or "").strip() or "web"}
    r = requests.post(
        GQL_URL,
        headers={"Authorization": f"Bearer {token}", **UA, "Content-Type": "application/json"},
        json={"query": _SEARCH_GQL, "variables": variables},
        timeout=30,
    )
    if r.status_code == 401:
        raise UpworkError("Upwork says the token is invalid — reconnect the connector")
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        msg = payload["errors"][0].get("message", "unknown GraphQL error")
        raise UpworkError(f"Upwork search failed: {msg}")
    search = ((payload.get("data") or {}).get("jobs_market_place_job_postings_search") or {})
    out = []
    for edge in search.get("edges") or []:
        node = edge.get("node") or {}
        if not node.get("title"):
            continue
        budget = node.get("budget") or {}
        out.append(
            {
                "guid": f"upwork-{node.get('id')}",
                "source": "upwork",
                "title": _strip(node["title"]),
                "url": f"https://www.upwork.com/jobs/{node.get('id')}",
                "body": _strip(node.get("description", "")),
                "tags": [],
                "posted_at": _iso(node.get("createdDateTime")),
                "budget_min": budget.get("minAmount"),
                "budget_max": budget.get("maxAmount"),
                "hourly": None,
            }
        )
    return out, updated
