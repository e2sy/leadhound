"""Freelancer.com ACCOUNT link — official OAuth2 + real bid placement.

This is NOT a job source: the public `freelancer` connector already hunts
gigs. This module links the user's own Freelancer.com account so leadhound
can act with it — placing a real bid through the documented API
(developers.freelancer.com) when the user hits 🎯 snipe.

Honesty + ToS notes:
  * bids are placed on the user's account with the user's own token,
    only when the user clicks fire — nothing bids in the background;
  * the token lives in local SQLite, masked in the UI like every secret;
  * every failure mode (rejected keys, expired token, API error envelope)
    surfaces as a human message, never silent and never fake success.

API reference: https://developers.freelancer.com
  OAuth2 : /oauth/authorise -> /oauth/token (authorization_code + refresh)
  whoami : GET  /users/0.1/self/
  bid    : POST /projects/0.1/projects/{project_id}/bids/
"""

from __future__ import annotations

import time

import requests

from ..watchers import UA

AUTHORIZE_URL = "https://www.freelancer.com/oauth/authorise"
TOKEN_URL = "https://www.freelancer.com/oauth/token"  # noqa: S105 — endpoint URL, not a secret
SELF_URL = "https://www.freelancer.com/api/users/0.1/self/"


class FreelancerError(RuntimeError):
    pass


class FreelancerNotConnectedError(FreelancerError):
    pass


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    if not client_id:
        raise FreelancerNotConnectedError("add your Freelancer.com client id first")
    return (
        f"{AUTHORIZE_URL}?response_type=code&client_id={client_id}"
        f"&redirect_uri={redirect_uri}&state={state}"
    )


def _token_request(data: dict) -> dict:
    r = requests.post(TOKEN_URL, data=data, headers=UA, timeout=25)
    if r.status_code in (400, 401):
        raise FreelancerError(
            f"Freelancer.com rejected the credentials ({r.status_code})"
        )
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise FreelancerError("Freelancer.com response had no access_token")
    return tok


def _merge_tokens(settings: dict, tok: dict) -> dict:
    merged = dict(settings or {})
    merged["access_token"] = tok["access_token"]
    if tok.get("refresh_token"):
        merged["refresh_token"] = tok["refresh_token"]
    merged["expires_at"] = int(time.time()) + int(tok.get("expires_in", 0) or 0)
    return merged


def exchange_code(settings: dict, code: str, redirect_uri: str) -> dict:
    """Authorization-code -> tokens. Returns updated settings to persist."""
    s = settings or {}
    if not (s.get("client_id") and s.get("client_secret")):
        raise FreelancerNotConnectedError("client id and client secret are both required")
    tok = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": s["client_id"],
            "client_secret": s["client_secret"],
        }
    )
    return _merge_tokens(s, tok)


def _ensure_access(settings: dict) -> tuple[str, dict | None]:
    """Return (access_token, updated_settings_if_refreshed)."""
    s = settings or {}
    if not s.get("refresh_token") and not s.get("access_token"):
        raise FreelancerNotConnectedError(
            "not linked yet — paste your app keys and connect your account"
        )
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


def _api_call(token: str, method: str, url: str, json_body: dict | None = None) -> dict:
    """Call the API and unwrap its {status, result|error} envelope honestly."""
    r = requests.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}", **UA, "Accept": "application/json"},
        json=json_body,
        timeout=30,
    )
    if r.status_code == 401:
        raise FreelancerError(
            "Freelancer.com says the token is invalid — reconnect the account"
        )
    r.raise_for_status()
    payload = r.json()
    if str(payload.get("status", "")).lower() == "error":
        err = payload.get("error") or {}
        msg = (
            err.get("message")
            or err.get("detail")
            or (f"API error code {err.get('code')}" if err else "unknown API error")
        )
        raise FreelancerError(f"Freelancer.com API error: {msg}")
    if str(payload.get("status", "")).lower() != "success":
        raise FreelancerError("Freelancer.com returned an unexpected response envelope")
    return payload.get("result") or {}


def whoami(settings: dict) -> tuple[dict, dict | None]:
    """(identity, updated_settings_if_refreshed). identity = {id, username, display_name}."""
    token, updated = _ensure_access(settings)
    result = _api_call(token, "GET", SELF_URL)
    identity = {
        "id": result.get("id"),
        "username": result.get("username") or "",
        "display_name": result.get("display_name") or result.get("username") or "",
    }
    if not identity["id"]:
        raise FreelancerError("could not read your Freelancer.com identity from /self")
    return identity, updated


def place_bid(
    settings: dict,
    project_id: int,
    *,
    amount: float,
    period: int = 7,
    description: str = "",
    milestone_percentage: int = 0,
) -> tuple[dict, dict | None]:
    """Fire a REAL bid on the user's account. Returns (bid_result, updated_settings).

    The result carries the platform bid id — leadhound records it as the
    snipe audit note so every fired shot is traceable.
    """
    if amount <= 0:
        raise FreelancerError("bid amount must be greater than zero")
    # one refresh path: whoami validates + refreshes, then we reuse the token
    identity, updated = whoami(settings)
    token = (updated or settings or {})["access_token"]
    body: dict = {
        "bidder_id": identity["id"],
        "amount": round(float(amount), 2),
        "period": int(period),
        "description": (description or "").strip(),
    }
    if milestone_percentage:
        body["milestone_percentage"] = int(milestone_percentage)
    url = f"https://www.freelancer.com/api/projects/0.1/projects/{int(project_id)}/bids/"
    result = _api_call(token, "POST", url, body)
    if not result.get("id"):
        raise FreelancerError("bid call succeeded but no bid id came back — verify on the site")
    return result, updated


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    """Validate the link by reading the account identity. Returns no gigs.

    This card exists to link the account for sniping; gig hunting stays on
    the public `freelancer` source card. The identity is stashed into
    settings so the accounts hub can show `linked as @username`.
    """
    identity, updated = whoami(settings)
    merged = dict(updated or settings or {})
    merged["identity"] = identity
    return [], merged
