"""SQLite storage. Local-first: your gig history never leaves your machine."""

from __future__ import annotations

import contextlib
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
    sniped_at: str | None = None
    snipe_method: str | None = None
    snipe_note: str | None = None
    sent_variant: str | None = None
    auto_rule: str | None = None
    user_id: int | None = None

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


OUTCOMES = ("replied", "interview", "won", "lost")


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
            outcome_at TEXT,
            sniped_at TEXT,
            snipe_method TEXT,
            snipe_note TEXT
        )
        """
    )
    _migrate(c)
    _ensure_accounts(c)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS draft_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            text TEXT NOT NULL,
            created TEXT DEFAULT (datetime('now')),
            UNIQUE(job_id, label)
        )
        """
    )
    c.commit()
    c.close()


def _migrate(c: sqlite3.Connection) -> None:
    """In-place upgrades for databases created before the learning loop."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
    if "outcome" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN outcome TEXT")
    if "outcome_at" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN outcome_at TEXT")
    if "user_id" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN user_id INTEGER")
    if "sniped_at" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN sniped_at TEXT")
    if "snipe_method" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN snipe_method TEXT")
    if "snipe_note" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN snipe_note TEXT")
    if "sent_variant" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN sent_variant TEXT")
    if "auto_rule" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN auto_rule TEXT")


def _ensure_accounts(c: sqlite3.Connection) -> None:
    """Accounts, sessions and per-user connector configs (the SaaS-shaped tables)."""
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created TEXT DEFAULT (datetime('now'))
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created TEXT DEFAULT (datetime('now')),
            expires TEXT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_config (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            connector_id TEXT NOT NULL,
            enabled INTEGER DEFAULT 0,
            settings TEXT DEFAULT '{}',
            last_run TEXT,
            last_status TEXT,
            last_error TEXT,
            last_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, connector_id)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS notify_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            telegram_token TEXT DEFAULT '',
            telegram_chat_id TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 0,
            listen_enabled INTEGER DEFAULT 0,
            push_min_score INTEGER DEFAULT 70,
            updated_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS snipe_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            min_score INTEGER DEFAULT 90,
            keywords TEXT DEFAULT '',
            source TEXT DEFAULT '',
            max_hourly REAL,
            max_fixed REAL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id)"
    )
    c.execute(
        "DELETE FROM sessions WHERE expires < datetime('now')"
    )


# ------------------------------------------------------------------- accounts
def users_count() -> int:
    c = _conn()
    n = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    c.close()
    return n


def create_user(email: str, password_hash: str) -> dict:
    try:
        c = _conn()
        cur = c.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.strip().lower(), password_hash),
        )
        uid = cur.lastrowid
        c.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("that email already has an account") from exc
    finally:
        c.close()
    return {"id": uid, "email": email.strip().lower()}


def user_by_email(email: str) -> dict | None:
    c = _conn()
    row = c.execute(
        "SELECT id, email, password_hash, created FROM users WHERE email = ?",
        (email.strip().lower(),),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def user_by_id(uid: int) -> dict | None:
    c = _conn()
    row = c.execute(
        "SELECT id, email, created FROM users WHERE id = ?", (uid,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


def create_session(user_id: int, token_hash: str, expires: str) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO sessions (token_hash, user_id, expires) VALUES (?, ?, ?)",
        (token_hash, user_id, expires),
    )
    c.commit()
    c.close()


def session_user(token_hash: str) -> dict | None:
    c = _conn()
    row = c.execute(
        """
        SELECT u.id, u.email, u.created FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires >= datetime('now')
        """,
        (token_hash,),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def delete_session(token_hash: str) -> None:
    c = _conn()
    c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    c.commit()
    c.close()


# ---------------------------------------------------------- connector configs
def connector_cfg(user_id: int, connector_id: str) -> dict:
    c = _conn()
    row = c.execute(
        "SELECT * FROM connector_config WHERE user_id = ? AND connector_id = ?",
        (user_id, connector_id),
    ).fetchone()
    c.close()
    if not row:
        return {
            "connector_id": connector_id,
            "enabled": False,
            "settings": {},
            "last_run": None,
            "last_status": None,
            "last_error": None,
            "last_count": 0,
        }
    d = dict(row)
    try:
        d["settings"] = json.loads(d.get("settings") or "{}")
    except json.JSONDecodeError:
        d["settings"] = {}
    return d


def connector_cfgs(user_id: int) -> dict[str, dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM connector_config WHERE user_id = ?", (user_id,)
    ).fetchall()
    c.close()
    out: dict[str, dict] = {}
    for row in rows:
        d = dict(row)
        try:
            d["settings"] = json.loads(d.get("settings") or "{}")
        except json.JSONDecodeError:
            d["settings"] = {}
        out[d["connector_id"]] = d
    return out


def save_connector_cfg(
    user_id: int,
    connector_id: str,
    *,
    enabled: bool | None = None,
    settings: dict | None = None,
) -> None:
    c = _conn()
    cur = c.execute(
        "SELECT enabled, settings FROM connector_config "
        "WHERE user_id = ? AND connector_id = ?",
        (user_id, connector_id),
    ).fetchone()
    if cur is None:
        c.execute(
            "INSERT INTO connector_config (user_id, connector_id, enabled, settings) "
            "VALUES (?, ?, ?, ?)",
            (
                user_id,
                connector_id,
                int(bool(enabled)),
                json.dumps(settings or {}),
            ),
        )
    else:
        new_enabled = int(bool(enabled)) if enabled is not None else cur["enabled"]
        new_settings = json.dumps(settings) if settings is not None else cur["settings"]
        c.execute(
            "UPDATE connector_config SET enabled = ?, settings = ? "
            "WHERE user_id = ? AND connector_id = ?",
            (new_enabled, new_settings, user_id, connector_id),
        )
    c.commit()
    c.close()


def record_connector_run(
    user_id: int, connector_id: str, status: str, error: str | None, count: int
) -> None:
    c = _conn()
    c.execute(
        """
        INSERT INTO connector_config (user_id, connector_id, last_run, last_status,
                                      last_error, last_count)
        VALUES (?, ?, datetime('now'), ?, ?, ?)
        ON CONFLICT(user_id, connector_id) DO UPDATE SET
            last_run = excluded.last_run,
            last_status = excluded.last_status,
            last_error = excluded.last_error,
            last_count = excluded.last_count
        """,
        (user_id, connector_id, status, error, count),
    )
    c.commit()
    c.close()


def enabled_connector_rows() -> list[tuple[int, str]]:
    """Every (user_id, connector_id) pair currently switched on — the poller feed."""
    c = _conn()
    rows = c.execute(
        "SELECT user_id, connector_id FROM connector_config WHERE enabled = 1"
    ).fetchall()
    c.close()
    return [(r["user_id"], r["connector_id"]) for r in rows]


def listen_enabled_rows() -> list[int]:
    """Accounts whose pocket listener should be armed when the server boots."""
    c = _conn()
    rows = c.execute(
        """
        SELECT user_id FROM notify_settings
        WHERE listen_enabled = 1 AND telegram_token != '' AND telegram_chat_id != ''
        """
    ).fetchall()
    c.close()
    return [r["user_id"] for r in rows]


# ------------------------------------------------------------- notify settings
def _seed_notify_from_file() -> dict:
    """One-time import path: config.toml's [telegram] block becomes the seed
    for a user's notify settings. File missing or empty -> silent no-op."""
    with contextlib.suppress(Exception):
        from .config import load_config

        _, _, tg_cfg, _, _ = load_config()
        if tg_cfg.bot_token and tg_cfg.chat_id:
            return {
                "telegram_token": tg_cfg.bot_token,
                "telegram_chat_id": tg_cfg.chat_id,
                "telegram_enabled": 1 if tg_cfg.enabled else 0,
            }
    return {}


def notify_cfg(user_id: int) -> dict:
    """Per-user notification settings. Seeds once from config.toml for
    pre-0.9 users so nobody has to re-paste their bot token."""
    c = _conn()
    row = c.execute(
        "SELECT * FROM notify_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        seed = _seed_notify_from_file()
        if seed:
            c.execute(
                "INSERT INTO notify_settings (user_id, telegram_token, "
                "telegram_chat_id, telegram_enabled) VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    seed["telegram_token"],
                    seed["telegram_chat_id"],
                    seed["telegram_enabled"],
                ),
            )
            c.commit()
            row = c.execute(
                "SELECT * FROM notify_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
    c.close()
    if row is None:
        return {
            "user_id": user_id,
            "telegram_token": "",
            "telegram_chat_id": "",
            "telegram_enabled": 0,
            "listen_enabled": 0,
            "push_min_score": 70,
            "updated_at": None,
        }
    return dict(row)


def save_notify_cfg(
    user_id: int,
    *,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_enabled: bool | None = None,
    listen_enabled: bool | None = None,
    push_min_score: int | None = None,
) -> dict:
    """Partial update — only the passed fields change, the rest persist."""
    cur = notify_cfg(user_id)  # current values (may be the virtual default)
    merged = {
        "telegram_token": cur["telegram_token"],
        "telegram_chat_id": cur["telegram_chat_id"],
        "telegram_enabled": int(bool(cur["telegram_enabled"])),
        "listen_enabled": int(bool(cur["listen_enabled"])),
        "push_min_score": int(cur["push_min_score"]),
    }
    if telegram_token is not None:
        merged["telegram_token"] = str(telegram_token).strip()
    if telegram_chat_id is not None:
        merged["telegram_chat_id"] = str(telegram_chat_id).strip()
    if telegram_enabled is not None:
        merged["telegram_enabled"] = int(bool(telegram_enabled))
    if listen_enabled is not None:
        merged["listen_enabled"] = int(bool(listen_enabled))
    if push_min_score is not None:
        merged["push_min_score"] = max(0, min(100, int(push_min_score)))
    c = _conn()
    c.execute(
        """
        INSERT INTO notify_settings (user_id, telegram_token, telegram_chat_id,
                                     telegram_enabled, listen_enabled, push_min_score,
                                     updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            telegram_token = excluded.telegram_token,
            telegram_chat_id = excluded.telegram_chat_id,
            telegram_enabled = excluded.telegram_enabled,
            listen_enabled = excluded.listen_enabled,
            push_min_score = excluded.push_min_score,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            merged["telegram_token"],
            merged["telegram_chat_id"],
            merged["telegram_enabled"],
            merged["listen_enabled"],
            merged["push_min_score"],
        ),
    )
    c.commit()
    row = c.execute(
        "SELECT * FROM notify_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    c.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------- snipe rules
def add_snipe_rule(
    user_id: int,
    name: str,
    min_score: int = 90,
    keywords: str = "",
    source: str = "",
    max_hourly: float | None = None,
    max_fixed: float | None = None,
) -> dict:
    """Arm an auto-snipe rule. Guardrails: min_score is clamped to 60..99 —
    a rule can auto-APPROVE a gig, but firing a real bid always needs a human
    click, so nothing here ever places one."""
    c = _conn()
    cur = c.execute(
        """
        INSERT INTO snipe_rules (user_id, name, min_score, keywords, source,
                                 max_hourly, max_fixed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name.strip()[:80],
            max(60, min(99, int(min_score))),
            keywords.strip().lower()[:300],
            source.strip()[:40],
            float(max_hourly) if max_hourly else None,
            float(max_fixed) if max_fixed else None,
        ),
    )
    rid = cur.lastrowid
    c.commit()
    c.close()
    return snipe_rule(user_id, rid)


def snipe_rule(user_id: int, rule_id: int) -> dict | None:
    c = _conn()
    row = c.execute(
        "SELECT * FROM snipe_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def snipe_rules_for(user_id: int) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM snipe_rules WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def delete_snipe_rule(user_id: int, rule_id: int) -> bool:
    c = _conn()
    cur = c.execute(
        "DELETE FROM snipe_rules WHERE id = ? AND user_id = ?", (rule_id, user_id)
    )
    c.commit()
    c.close()
    return cur.rowcount > 0


def set_snipe_rule_enabled(user_id: int, rule_id: int, enabled: bool) -> bool:
    c = _conn()
    cur = c.execute(
        "UPDATE snipe_rules SET enabled = ? WHERE id = ? AND user_id = ?",
        (1 if enabled else 0, rule_id, user_id),
    )
    c.commit()
    c.close()
    return cur.rowcount > 0


def match_snipe_rules(user_id: int, score: int, job: dict) -> list[dict]:
    """Rules the gig currently satisfies: enabled, score bar cleared, source
    matches, ANY keyword hits title+body, and the budget sits under the caps.
    No caps set on a rule = that dimension is unfiltered."""
    c = _conn()
    rows = c.execute(
        "SELECT * FROM snipe_rules WHERE user_id = ? AND enabled = 1 AND min_score <= ?",
        (user_id, int(score)),
    ).fetchall()
    c.close()
    haystack = f"{job.get('title', '')} {job.get('body', '')}".lower()
    source = (job.get("source") or "").lower()
    hourly = job.get("hourly")
    fixed = job.get("budget_max") if job.get("budget_max") else job.get("budget_min")
    hits: list[dict] = []
    for r in rows:
        if r["source"] and r["source"].lower() != source:
            continue
        kws = [k.strip() for k in (r["keywords"] or "").split(",") if k.strip()]
        if kws and not any(k in haystack for k in kws):
            continue
        if r["max_hourly"] is not None and hourly is not None and hourly > r["max_hourly"]:
            continue
        if r["max_fixed"] is not None and fixed is not None and fixed > r["max_fixed"]:
            continue
        hits.append(dict(r))
    return hits


def mark_auto_armed(job_id: int, rule_name: str) -> None:
    """Audit trail: this gig was auto-approved by rule <name> — the human
    still pulls the trigger."""
    c = _conn()
    c.execute("UPDATE jobs SET auto_rule = ? WHERE id = ?", (rule_name[:80], job_id))
    c.commit()
    c.close()


def upsert_job(
    job: dict, score: int, score_json: dict, draft: str, user_id: int | None = None
) -> tuple[int, bool]:
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
                          hourly, tags, posted_at, score, score_json, draft, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job["guid"], job["source"], job["title"], job["url"], job.get("body", ""),
            job.get("budget_min"), job.get("budget_max"), job.get("hourly"),
            ",".join(job.get("tags", [])), job.get("posted_at"),
            score, json.dumps(score_json), draft, user_id,
        ),
    )
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid, True


def _scope_params(user_id: int | None) -> tuple[int, int]:
    """Static-SQL scope args: (has_scope, uid). NULL user_id rows are the
    local/CLI pool, shared by every account."""
    return (1, user_id) if user_id else (0, 0)


def jobs_by_status(
    status: str, min_score: int = 0, limit: int = 50, user_id: int | None = None
) -> list[Job]:
    c = _conn()
    flag, uid = _scope_params(user_id)
    rows = c.execute(
        """
        SELECT * FROM jobs WHERE status = ? AND score >= ?
          AND (? = 0 OR user_id IS NULL OR user_id = ?)
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (status, min_score, flag, uid, limit),
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


def mark_sniped(job_id: int, method: str, note: str = "", variant: str | None = None) -> None:
    """The shot was fired: status -> sent with an honest audit trail.

    method is 'freelancer-api' (a real bid was placed) or 'kit' (proposal
    copied + gig opened, user confirmed the send). note carries the platform
    bid id or the confirmation context. variant records WHICH proposal went
    out (None/'A' = the job's main draft, 'B' = an A/B variant) — the
    learning signal for the proposal duel.
    """
    c = _conn()
    if variant:
        c.execute(
            "UPDATE jobs SET status = 'sent', sniped_at = datetime('now'), "
            "snipe_method = ?, snipe_note = ?, sent_variant = ? WHERE id = ?",
            (method, note, variant, job_id),
        )
    else:
        c.execute(
            "UPDATE jobs SET status = 'sent', sniped_at = datetime('now'), "
            "snipe_method = ?, snipe_note = ? WHERE id = ?",
            (method, note, job_id),
        )
    c.commit()
    c.close()


# ------------------------------------------------------------------- variants
def variants_for(job_id: int) -> list[dict]:
    """A/B variants stored for a job (label 'B' and beyond)."""
    c = _conn()
    rows = c.execute(
        "SELECT label, text, created FROM draft_variants "
        "WHERE job_id = ? ORDER BY label",
        (job_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def all_variants() -> dict[int, list[dict]]:
    """Every variant row, grouped by job id — one query for the board feed."""
    c = _conn()
    rows = c.execute(
        "SELECT job_id, label, text, created FROM draft_variants ORDER BY label"
    ).fetchall()
    c.close()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["job_id"], []).append(
            {"label": r["label"], "text": r["text"], "created": r["created"]}
        )
    return out


def save_variant(job_id: int, label: str, text: str) -> None:
    """Upsert one proposal variant (label 'A' is the job's main draft —
    it lives on the job row itself, so only B+ belongs here)."""
    label = label.strip().upper()
    if not label or len(label) > 2 or not label.isalpha():
        raise ValueError("variant label must be 1-2 letters")
    if label == "A":
        raise ValueError("A is the main draft — save variants as B, C, …")
    c = _conn()
    c.execute(
        "INSERT INTO draft_variants (job_id, label, text) VALUES (?, ?, ?) "
        "ON CONFLICT(job_id, label) DO UPDATE SET text = excluded.text",
        (job_id, label, text),
    )
    c.commit()
    c.close()


def pending_unnotified(
    min_score: int = 0, limit: int = 20, user_id: int | None = None
) -> list[Job]:
    c = _conn()
    flag, uid = _scope_params(user_id)
    rows = c.execute(
        """
        SELECT * FROM jobs WHERE status = 'pending' AND notified = 0 AND score >= ?
          AND (? = 0 OR user_id IS NULL OR user_id = ?)
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (min_score, flag, uid, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def all_jobs(limit: int = 300, user_id: int | None = None) -> list[Job]:
    """Every tracked gig visible to this account, best first — the dashboard feed."""
    c = _conn()
    flag, uid = _scope_params(user_id)
    rows = c.execute(
        """
        SELECT * FROM jobs WHERE (? = 0 OR user_id IS NULL OR user_id = ?)
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (flag, uid, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def set_draft(job_id: int, text: str) -> None:
    """Overwrite the proposal draft (dashboard editor)."""
    c = _conn()
    c.execute("UPDATE jobs SET draft = ? WHERE id = ?", (text, job_id))
    c.commit()
    c.close()


def clear_outcome(job_id: int) -> None:
    """Undo an outcome marking (dashboard)."""
    c = _conn()
    c.execute("UPDATE jobs SET outcome = NULL, outcome_at = NULL WHERE id = ?", (job_id,))
    c.commit()
    c.close()


def recent_jobs(
    hours: int = 24, min_score: int = 0, limit: int = 5, user_id: int | None = None
) -> list[Job]:
    """Best gigs fetched within the last N hours — the digest feed."""
    c = _conn()
    flag, uid = _scope_params(user_id)
    rows = c.execute(
        """
        SELECT * FROM jobs
        WHERE fetched_at >= datetime('now', ?) AND score >= ?
          AND (? = 0 OR user_id IS NULL OR user_id = ?)
        ORDER BY score DESC, id DESC LIMIT ?
        """,
        (f"-{int(hours)} hours", min_score, flag, uid, limit),
    ).fetchall()
    c.close()
    return [Job(**dict(r)) for r in rows]


def mark_notified(job_id: int) -> None:
    c = _conn()
    c.execute("UPDATE jobs SET notified = 1 WHERE id = ?", (job_id,))
    c.commit()
    c.close()


def stats(user_id: int | None = None) -> dict:
    """Pipeline counts for this account (user_id=None = the shared CLI pool)."""
    c = _conn()
    flag, uid = _scope_params(user_id)
    out = {}
    for st in ("pending", "approved", "rejected", "sent"):
        row = c.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status = ? "
            "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
            (st, flag, uid),
        ).fetchone()
        out[st] = row["n"]
    row = c.execute(
        "SELECT COUNT(*) AS n, MAX(score) AS hi FROM jobs "
        "WHERE (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    out["total"], out["highest_score"] = row["n"], row["hi"]
    inplay = c.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(budget_max), 0) AS v FROM jobs "
        "WHERE status IN ('approved', 'sent') AND outcome IS NULL "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    out["inplay_n"], out["inplay_value"] = inplay["n"], inplay["v"]
    won = c.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(budget_max), 0) AS v "
        "FROM jobs WHERE outcome = 'won' "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    out["won_n"], out["won_value"] = won["n"], won["v"]
    c.close()
    return out


def funnel_stats(user_id: int | None = None) -> dict:
    """The closer's scoreboard — everything that happened AFTER firing.

    A reply counts as replied, interview or won. reply_rate is measured
    against every sniped gig; win_rate only against resolved (won/lost)
    gigs — the honest closing number, since young shots haven't had time
    to be won or lost yet.
    """
    c = _conn()
    flag, uid = _scope_params(user_id)

    row = c.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE status = 'sent' "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    sniped = row["n"]

    rows = c.execute(
        "SELECT outcome, COUNT(*) AS n, COALESCE(SUM(budget_max), 0) AS v "
        "FROM jobs WHERE outcome IN ('replied','interview','won','lost') "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY outcome",
        (flag, uid),
    ).fetchall()
    by = {r["outcome"]: {"n": r["n"], "v": r["v"]} for r in rows}
    replies = (
        by.get("replied", {}).get("n", 0)
        + by.get("interview", {}).get("n", 0)
        + by.get("won", {}).get("n", 0)
    )
    interviews = by.get("interview", {}).get("n", 0)
    wins = by.get("won", {}).get("n", 0)
    losses = by.get("lost", {}).get("n", 0)
    resolved = wins + losses

    out = {
        "sniped": sniped,
        "replies": replies,
        "interviews": interviews,
        "wins": wins,
        "losses": losses,
        "reply_rate": round(100 * replies / sniped, 1) if sniped else None,
        "win_rate": round(100 * wins / resolved, 1) if resolved else None,
        "won_value": by.get("won", {}).get("v", 0),
    }

    src_rows = c.execute(
        "SELECT source, COUNT(*) AS tracked, "
        "SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) AS sent, "
        "SUM(CASE WHEN outcome IN ('replied','interview','won') THEN 1 ELSE 0 END) AS replies, "
        "SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) AS wins, "
        "COALESCE(SUM(CASE WHEN outcome = 'won' THEN budget_max ELSE 0 END), 0) AS won_value "
        "FROM jobs WHERE (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY source",
        (flag, uid),
    ).fetchall()
    out["by_source"] = [
        {
            "source": r["source"],
            "tracked": r["tracked"],
            "sent": r["sent"] or 0,
            "replies": r["replies"] or 0,
            "wins": r["wins"] or 0,
            "won_value": r["won_value"] or 0,
            "reply_rate": (
                round(100 * (r["replies"] or 0) / r["sent"], 1) if r["sent"] else None
            ),
        }
        for r in sorted(src_rows, key=lambda r: (-(r["sent"] or 0), -r["tracked"]))
    ]

    method_rows = c.execute(
        "SELECT snipe_method AS m, COUNT(*) AS n, "
        "SUM(CASE WHEN outcome IN ('replied','interview','won') THEN 1 ELSE 0 END) AS replies, "
        "SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) AS wins "
        "FROM jobs WHERE status = 'sent' AND snipe_method IS NOT NULL "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY snipe_method",
        (flag, uid),
    ).fetchall()
    out["by_method"] = {
        (r["m"] or "kit"): {
            "sent": r["n"],
            "replies": r["replies"] or 0,
            "wins": r["wins"] or 0,
        }
        for r in method_rows
    }

    variant_rows = c.execute(
        "SELECT COALESCE(sent_variant, 'A') AS v, COUNT(*) AS n, "
        "SUM(CASE WHEN outcome IN ('replied','interview','won') THEN 1 ELSE 0 END) AS replies, "
        "SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) AS wins "
        "FROM jobs WHERE status = 'sent' "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY v",
        (flag, uid),
    ).fetchall()
    out["by_variant"] = {
        (r["v"] or "A"): {
            "sent": r["n"],
            "replies": r["replies"] or 0,
            "wins": r["wins"] or 0,
        }
        for r in variant_rows
    }
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


def snipe_stats(user_id: int | None = None) -> dict:
    """Firing + result stats for the sniper: shots fired, replies, wins.

    reply_rate counts (replied + won) against every sniped gig — the number
    a sniper actually cares about.
    """
    c = _conn()
    flag, uid = _scope_params(user_id)
    row = c.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE status = 'sent' "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    out = {"sniped_total": row["n"]}
    row = c.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE status = 'sent' "
        "AND sniped_at >= datetime('now', '-7 days') "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?)",
        (flag, uid),
    ).fetchone()
    out["sniped_7d"] = row["n"]
    rows = c.execute(
        "SELECT outcome, COUNT(*) AS n FROM jobs "
        "WHERE outcome IN ('replied','interview','won') "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY outcome",
        (flag, uid),
    ).fetchall()
    by = {r["outcome"]: r["n"] for r in rows}
    out["replies"] = by.get("replied", 0) + by.get("interview", 0) + by.get("won", 0)
    out["wins"] = by.get("won", 0)
    out["reply_rate"] = (
        round(100 * out["replies"] / out["sniped_total"], 1)
        if out["sniped_total"]
        else None
    )
    c.close()
    return out


def calibration(user_id: int | None = None) -> dict:
    """Score-vs-outcome aggregation: does the sniper scope actually track wins?

    Returns {outcome: {"n": int, "avg_score": float}} plus a human hint.
    """
    c = _conn()
    flag, uid = _scope_params(user_id)
    rows = c.execute(
        "SELECT outcome, COUNT(*) AS n, AVG(score) AS avg_score "
        "FROM jobs WHERE outcome IS NOT NULL "
        "AND (? = 0 OR user_id IS NULL OR user_id = ?) GROUP BY outcome",
        (flag, uid),
    ).fetchall()
    c.close()
    out = {r["outcome"]: {"n": r["n"], "avg_score": round(r["avg_score"], 1)} for r in rows}
    out["hint"] = _calibration_hint(out)
    return out


def _calibration_hint(by_outcome: dict) -> str:
    won, lost, replied, interview = (
        by_outcome.get("won"),
        by_outcome.get("lost"),
        by_outcome.get("replied"),
        by_outcome.get("interview"),
    )
    if not won and not lost:
        if replied or interview:
            n = (replied or {"n": 0})["n"] + (interview or {"n": 0})["n"]
            return (
                f"{n} reply/interview(s) so far — keep marking outcomes after "
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
