"""SQLite storage. Local-first: your gig history never leaves your machine."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import db_path


@dataclass
class Job:
    id: int
    guid: str
    source: str
    title: str
    url: str
    body: str
    budget_min: float | None
    budget_max: float | None
    hourly: float | None
    tags: str
    posted_at: str | None
    fetched_at: str | None = None
    score: int = 0
    score_json: str = "{}"
    status: str = "pending"
    notified: int = 0
    draft: str = ""
    outcome: str | None = None
    outcome_at: str | None = None

    @property
    def breakdown(self) -> dict:
        try:
            return json.loads(self.score_json or "{}")
        except json.JSONDecodeError:
            return {}


def _conn() -> sqlite3.Connection:
    p: Path = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


OUTCOMES = ("replied", "won", "lost")


def ensure_db() -> None:
    c = _conn()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            body TEXT DEFAULT '',
            budget_min REAL,
            budget_max REAL,
            hourly REAL,
            tags TEXT DEFAULT '',
            posted_at TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            score INTEGER DEFAULT 0,
            score_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            notified INTEGER DEFAULT 0,
            draft TEXT DEFAULT '',
            outcome TEXT,
            outcome_at TEXT
        )
        """
    )
    _migrate(c)
    c.commit()
    c.close()


def _migrate(c: sqlite3.Connection) -> None:
    """In-place upgrades for databases created before the learning loop."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
    if "outcome" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN outcome TEXT")
    if "outcome_at" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN outcome_at TEXT")


def upsert_job(job: dict, score: int, score_json: dict, draft: str) -> tuple[int, bool]:
    """Insert a job if the guid is new. Returns (row_id, is_new)."""
    c = _conn()
    cur = c.execute("SELECT id, status FROM jobs WHERE guid = ?", (job["guid"],))
    row = cur.fetchone()
    if row:
        c.close()
        return row["id"], False
    cur = c.execute(
        """
        INSERT INTO jobs (guid, source, title, url, body, budget_min, budget_max,
                          hourly, tags, posted_at, score, score_json, draft)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job["guid"], job["source"], job["title"], job["url"], job.get("body", ""),
            job.get("budget_min"), job.get("budget_max"), job.get("hourly"),
            ",".join(job.get("tags", [])), job.get("posted_at"),
            score, json.dumps(score_json), draft,
        ),
    )
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid, True


def jobs_by_status(status: str, min_score: int = 0, limit: int = 50) -> list[Job]:
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM jobs WHERE status = ? AND score >= ?
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (status, min_score, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def get_job(job_id: int) -> Job | None:
    c = _conn()
    row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    c.close()
    return Job(**dict(row)) if row else None


def set_status(job_id: int, status: str) -> None:
    c = _conn()
    c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    c.commit()
    c.close()


def pending_unnotified(min_score: int = 0, limit: int = 20) -> list[Job]:
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM jobs WHERE status = 'pending' AND notified = 0 AND score >= ?
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (min_score, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def recent_jobs(hours: int = 24, min_score: int = 0, limit: int = 5) -> list[Job]:
    """Best gigs fetched within the last N hours — the digest feed."""
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM jobs
        WHERE fetched_at >= datetime('now', ?) AND score >= ?
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (f"-{int(hours)} hours", min_score, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def mark_notified(job_id: int) -> None:
    c = _conn()
    c.execute("UPDATE jobs SET notified = 1 WHERE id = ?", (job_id,))
    c.commit()
    c.close()


def stats() -> dict:
    c = _conn()
    out = {}
    for st in ("pending", "approved", "rejected", "sent"):
        row = c.execute("SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (st,)).fetchone()
        out[st] = row["n"]
    row = c.execute("SELECT COUNT(*) AS n, MAX(score) AS hi FROM jobs").fetchone()
    out["total"], out["highest_score"] = row["n"], row["hi"]
    c.close()
    return out


def set_outcome(job_id: int, outcome: str) -> None:
    """Record what happened after you sent the proposal — the learning signal."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    c = _conn()
    c.execute(
        "UPDATE jobs SET outcome = ?, outcome_at = datetime('now') WHERE id = ?",
        (outcome, job_id),
    )
    c.commit()
    c.close()


def calibration() -> dict:
    """Score-vs-outcome aggregation: does the sniper scope actually track wins?

    Returns {outcome: {"n": int, "avg_score": float}} plus a human hint.
    """
    c = _conn()
    rows = c.execute(
        """
        SELECT outcome, COUNT(*) AS n, AVG(score) AS avg_score
        FROM jobs WHERE outcome IS NOT NULL
        GROUP BY outcome
        """
    ).fetchall()
    c.close()
    out = {r["outcome"]: {"n": r["n"], "avg_score": round(r["avg_score"], 1)} for r in rows}
    out["hint"] = _calibration_hint(out)
    return out


def _calibration_hint(by_outcome: dict) -> str:
    won, lost, replied = (
        by_outcome.get("won"),
        by_outcome.get("lost"),
        by_outcome.get("replied"),
    )
    if not won and not lost:
        if replied:
            return (
                f"{replied['n']} reply(ies) so far — keep marking outcomes after "
                "each 'won'/'lost' to calibrate."
            )
        return "No outcomes marked yet. After a client replies, run: leadhound mark <id> replied"
    if won and lost:
        gap = won["avg_score"] - lost["avg_score"]
        if gap >= 5:
            return f"Scope is calibrated — winners outscore losers by {gap:g} pts. Trust the ranking."
        if gap <= -5:
            return (
                f"Losers outscore winners by {abs(gap):g} pts — tighten red flags "
                "or revisit your skills list."
            )
        return "Winners and losers score similarly — outcome data will sharpen the scope."
    if won and won["avg_score"] < 60:
        return (
            f"Your winner(s) average {won['avg_score']:g} — your market scores low. "
            "Consider a lower min_score so these gigs aren't dimmed."
        )
    if won:
        return f"Winner(s) average {won['avg_score']:g} — the scope points the right way."
    return "Mark more outcomes (leadhound mark <id> won|lost) to calibrate."
