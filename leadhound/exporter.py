"""leadhound export — get your pipeline out as CSV or JSON.

Your data, your machine, no lock-in: one command hands everything to
spreadsheets, scripts, or your CRM.
"""

from __future__ import annotations

import csv
import io
import json

from . import db

CSV_COLUMNS = (
    "id", "score", "status", "outcome", "source", "title", "url",
    "hourly", "budget_min", "budget_max", "matched_skills", "red_flags",
    "tags", "posted_at", "fetched_at",
)

VALID_STATUSES = ("all", "pending", "approved", "sent", "rejected")


def _rows(jobs: list[db.Job]) -> list[dict]:
    out = []
    for j in jobs:
        b = j.breakdown
        out.append({
            "id": j.id,
            "score": j.score,
            "status": j.status,
            "outcome": j.outcome or "",
            "source": j.source,
            "title": j.title,
            "url": j.url,
            "hourly": j.hourly,
            "budget_min": j.budget_min,
            "budget_max": j.budget_max,
            "matched_skills": ";".join(b.get("skills", {}).get("matched", [])),
            "red_flags": ";".join(b.get("red_flags", [])),
            "tags": (j.tags or "").replace(",", ";"),
            "posted_at": j.posted_at or "",
            "fetched_at": j.fetched_at or "",
            "body": j.body,
            "draft": j.draft,
        })
    return out


def export_json(status: str = "all", min_score: int = 0) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    jobs = db.all_jobs(limit=10_000)
    jobs = [
        j for j in jobs
        if j.score >= min_score and (status == "all" or j.status == status)
    ]
    return json.dumps(_rows(jobs), indent=2, ensure_ascii=False)


def export_csv(status: str = "all", min_score: int = 0) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    jobs = db.all_jobs(limit=10_000)
    jobs = [
        j for j in jobs
        if j.score >= min_score and (status == "all" or j.status == status)
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
    w.writeheader()
    w.writerows(_rows(jobs))
    return buf.getvalue()


def export_to_file(fmt: str, path: str, status: str = "all", min_score: int = 0) -> int:
    """Write the export to a file; returns the number of gigs written."""
    payload = export_json(status, min_score) if fmt == "json" else export_csv(status, min_score)
    n = len(json.loads(payload)) if fmt == "json" else max(0, payload.count("\n") - 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)
    return n
