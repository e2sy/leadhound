"""Fiverr connector (beta, unofficial) — buyer requests via your session cookie.

Fiverr has no public API. This connector polls the buyer-requests page with a
cookie you paste from your own logged-in browser, and tries to read the JSON
the page embeds. Fiverr can change their page layout at any time; when that
happens this connector reports it honestly instead of inventing gigs.

Beta means: it may stop working the day Fiverr redesigns. The rest of
leadhound won't.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from ..watchers import UA

BUYER_REQUESTS_URL = "https://www.fiverr.com/buyer_requests"


class FiverrError(RuntimeError):
    pass


def _extract_json_blobs(html: str, limit: int = 12) -> list[Any]:
    """Pull embedded JSON from <script> blocks and window.* assignments."""
    blobs: list[Any] = []
    patterns = [
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        r"window\.__\w+\s*=\s*(\{.*?\});",
    ]
    for pat in patterns:
        for raw in re.findall(pat, html, re.S)[:limit]:
            with_json = raw.strip()
            if not with_json.startswith("{") and not with_json.startswith("["):
                continue
            try:
                blobs.append(json.loads(with_json))
            except json.JSONDecodeError:
                continue
    return blobs


def _walk(node: Any, depth: int = 0):
    """Yield every dict in a nested structure (depth-limited for sanity)."""
    if depth > 14:
        return
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v, depth + 1)
    elif isinstance(node, list):
        for v in node[:200]:
            yield from _walk(v, depth + 1)


def _as_number(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"[\d,]+(?:\.\d+)?", v.replace(" ", ""))
        if m:
            digits = m.group().replace(",", "")
            try:
                return float(digits)
            except ValueError:
                return None
    return None


def _looks_like_request(d: dict) -> bool:
    keys = set(d.keys())
    has_text = bool(keys & {"title", "brief", "name", "headline", "request_title"}) or bool(
        keys & {"description", "details", "body", "text"}
    )
    has_context = bool(
        keys
        & {
            "budget",
            "min_budget",
            "minBudget",
            "max_budget",
            "maxBudget",
            "buyer",
            "username",
            "category",
            "sub_category",
            "published_at",
            "created_at",
            "requests_id",
            "id",
        }
    )
    return has_text and has_context


def _normalize(d: dict, idx: int) -> dict | None:
    title = d.get("title") or d.get("brief") or d.get("name") or d.get("headline")
    body = d.get("description") or d.get("details") or d.get("body") or d.get("text") or ""
    if isinstance(title, dict):
        title = title.get("text") or title.get("name")
    if not title or not isinstance(title, str):
        return None
    budget = d.get("budget")
    bmin = bmax = None
    if isinstance(budget, dict):
        bmin, bmax = _as_number(budget.get("min") or budget.get("minimum")), _as_number(
            budget.get("max") or budget.get("maximum")
        )
    elif budget is not None:
        bmin = _as_number(budget)
    if bmin is None:
        bmin = _as_number(d.get("min_budget") or d.get("minBudget"))
    if bmax is None:
        bmax = _as_number(d.get("max_budget") or d.get("maxBudget"))
    rid = d.get("id") or d.get("requests_id") or idx
    user = d.get("buyer") or {}
    username = (
        user.get("username") if isinstance(user, dict) else None
    ) or d.get("username")
    return {
        "guid": f"fiverr-{rid}",
        "source": "fiverr",
        "title": re.sub(r"\s+", " ", str(title)).strip()[:200],
        "url": BUYER_REQUESTS_URL,
        "body": re.sub(r"<[^>]+>", " ", str(body))[:4000].strip(),
        "tags": [str(d[key]) for key in ("category", "sub_category") if d.get(key)],
        "posted_at": d.get("published_at") or d.get("created_at"),
        "budget_min": bmin,
        "budget_max": bmax,
        "hourly": None,
        "buyer": username or "",
    }


def fetch(settings: dict) -> tuple[list[dict], dict | None]:
    cookie = str((settings or {}).get("cookie") or "").strip()
    if not cookie:
        raise FiverrError("paste your Fiverr session cookie first (Settings below)")
    r = requests.get(
        BUYER_REQUESTS_URL,
        headers={
            **UA,
            "Cookie": cookie,
            "Accept": "text/html,application/json",
        },
        timeout=30,
    )
    if r.status_code in (401, 403):
        raise FiverrError("Fiverr rejected that cookie — paste a fresh one from your browser")
    if r.status_code == 302 or (r.url and "login" in str(r.url)):
        raise FiverrError("the cookie expired — log into Fiverr and paste a fresh cookie")
    r.raise_for_status()
    seen: list[dict] = []
    identities: set[str] = set()
    for blob in _extract_json_blobs(r.text):
        for d in _walk(blob):
            if isinstance(d, dict) and _looks_like_request(d):
                job = _normalize(d, len(seen))
                if job and job["guid"] not in identities:
                    identities.add(job["guid"])
                    seen.append(job)
    if not seen:
        raise FiverrError(
            "connected, but couldn't find buyer requests in the page — "
            "Fiverr likely changed their layout (or you have no requests yet)"
        )
    return seen, None
