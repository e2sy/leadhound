"""Freelancer.com webhook receiver — instant gig detection, no polling.

The user registers their app's webhook in the Freelancer developer portal
pointing at `POST /webhook/freelancer` with their signing secret. Events
arrive, the HMAC-SHA256 signature is verified against the raw body, and a
project-posted event flows straight into the pipeline — detection latency
drops from the next poll to seconds.

Honesty rules kept from the connector: garbage in, an honest error out;
we never invent gig fields. The signature header name is accepted from
every common variant because the exact casing is theirs to change."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import re
from datetime import UTC, datetime

# every header name the platform (or a proxy in front of it) plausibly uses
SIGNATURE_HEADERS = (
    "x-freelancer-signature",
    "freelancer-signature",
    "x-signature",
    "x-hub-signature-256",
)


def verify_signature(secret: str, raw: bytes, headers) -> bool:
    """HMAC-SHA256 over the raw body, constant-time compared. Accepts an
    optional 'sha256=' prefix and any casing — proxies mangle both, and a
    plain dict is case-sensitive where Starlette Headers are not."""
    if not secret:
        return False
    try:
        provided = {str(k).lower(): str(v) for k, v in headers.items()}
    except AttributeError:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw or b"", hashlib.sha256).hexdigest()
    for name in SIGNATURE_HEADERS:
        got = provided.get(name, "").strip().removeprefix("sha256=").strip()
        if got and hmac.compare_digest(got.lower(), expected.lower()):
            return True
    return False


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _iso(ts) -> str | None:
    with contextlib.suppress(Exception):
        return datetime.fromtimestamp(int(ts), tz=UTC).isoformat(timespec="seconds")
    return None


def parse_event(payload: dict) -> list[dict]:
    """Extract NormalizedJob dicts from a webhook event. Returns [] for any
    event that is not a real, public project — silently and on purpose."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    project = payload.get("project") or data.get("project")
    if not isinstance(project, dict):
        project = data if data.get("id") else None
    if not isinstance(project, dict) or not project.get("id"):
        return []
    if project.get("deleted") or project.get("nonpublic") or not project.get("title"):
        return []

    budget = project.get("budget") or {}
    hourly = project.get("type") == "hourly"
    return [
        {
            "guid": f"freelancer-{project.get('id')}",
            "source": "freelancer",
            "title": _clean(str(project["title"])),
            "url": f"https://www.freelancer.com/projects/{project.get('seo_url', '')}".rstrip("/"),
            "body": _clean(str(project.get("preview_description", ""))),
            "tags": [j.get("name", "") for j in (project.get("jobs") or []) if j.get("name")],
            "posted_at": _iso(project.get("submitdate") or project.get("time_submitted")),
            "budget_min": budget.get("minimum"),
            "budget_max": budget.get("maximum"),
            "hourly": budget.get("minimum") if hourly else None,
        }
    ]
