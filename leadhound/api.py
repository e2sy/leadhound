"""leadhound API — the real backend.

FastAPI + your local SQLite. Every dashboard route is account-scoped:

    /api/health                  liveness + version (no auth)
    /api/auth/register|login|logout|me
    /api/state                   board, stats, calibration (auth)
    /api/status|draft|outcome    pipeline mutations (auth)
    /api/demo                    load the sample gigs (auth)
    /api/connectors              source list + per-account config
    /api/connectors/{id}         save enabled/settings
    /api/connectors/{id}/run     fetch that one source now
    /api/fetch                   fetch every enabled source now
    /                            the single-page dashboard

A daemon poller re-runs enabled connectors every interval (default 15 min,
politeness floor 5 min) while the server is up — the sniping radar.
"""

from __future__ import annotations

import html as _html
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import __version__, auth, connectors, db
from .config import load_config, load_profile
from .connectors import upwork as _upwork
from .engine import intel
from .pipeline import ingest_jobs
from .webassets import PAGE

_MAX_PREVIEW = 400
_MASK = "•••"  # sentinel returned instead of stored secrets
POLL_FLOOR_MIN = 5


# --------------------------------------------------------------------- state
def job_to_dict(j: db.Job) -> dict:
    b = j.breakdown
    body = (j.body or "").strip()
    if len(body) > _MAX_PREVIEW:
        body = body[:_MAX_PREVIEW].rstrip() + "…"
    return {
        "id": j.id,
        "source": j.source,
        "title": j.title,
        "url": j.url,
        "body": body,
        "budget_min": j.budget_min,
        "budget_max": j.budget_max,
        "hourly": j.hourly,
        "tags": [t for t in (j.tags or "").split(",") if t],
        "fetched_at": j.fetched_at,
        "score": j.score,
        "matched": b.get("skills", {}).get("matched", []),
        "red_flags": b.get("red_flags", []),
        "budget_note": b.get("budget", {}).get("note", ""),
        "status": j.status,
        "draft": j.draft,
        "outcome": j.outcome,
        "intel": intel.intel_for(j),
    }


def build_state(user_id: int | None = None) -> dict:
    """Everything the dashboard needs in one round trip."""
    db.ensure_db()
    jobs = db.all_jobs(limit=300, user_id=user_id)
    demo = bool(jobs) and all(j.source == "demo" for j in jobs)
    return {
        "stats": db.stats(),
        "calibration": db.calibration(),
        "demo": demo,
        "jobs": [job_to_dict(j) for j in jobs],
    }


def _mask_settings(conn: connectors.Connector, settings: dict) -> dict:
    out = dict(settings or {})
    for f in conn.fields:
        if f.secret and out.get(f.name):
            out[f.name] = _MASK
    return out


def _unmask_settings(conn: connectors.Connector, incoming: dict, stored: dict) -> dict:
    """Sentinel values mean 'unchanged' — swap them back for the real secret."""
    merged = dict(stored or {})
    for k, v in (incoming or {}).items():
        if v == _MASK:
            continue
        merged[k] = v
    for f in conn.fields:
        if f.secret and merged.get(f.name) == _MASK:
            merged.pop(f.name, None)
    return merged


def _connector_payload(user_id: int) -> list[dict]:
    cfgs = db.connector_cfgs(user_id)
    out = []
    for conn in connectors.all_connectors():
        cfg = cfgs.get(conn.id, {})
        out.append(
            {
                "id": conn.id,
                "label": conn.label,
                "kind": conn.kind,
                "blurb": conn.blurb,
                "setup_url": conn.setup_url,
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "placeholder": f.placeholder,
                        "secret": f.secret,
                        "hint": f.hint,
                    }
                    for f in conn.fields
                ],
                "enabled": bool(cfg.get("enabled")),
                "settings": _mask_settings(conn, cfg.get("settings") or {}),
                "status": {
                    "last_run": cfg.get("last_run"),
                    "last_status": cfg.get("last_status"),
                    "last_error": cfg.get("last_error"),
                    "last_count": cfg.get("last_count") or 0,
                },
            }
        )
    return out


# --------------------------------------------------------------- fetch runner
_fetch_lock = threading.Lock()


def run_connector_for(user_id: int, cid: str, *, wait: bool = True) -> dict:
    """Fetch one source for one account, ingest, record the outcome honestly."""
    conn = connectors.get(cid)
    if conn is None:
        return {"connector": cid, "error": "unknown connector"}
    if wait:
        if not _fetch_lock.acquire(blocking=False):
            return {"connector": cid, "error": "another fetch is still running"}
    else:  # pragma: no cover - poller path
        _fetch_lock.acquire()
    try:
        cfg = db.connector_cfg(user_id, cid)
        try:
            jobs, updated = conn.fetch(cfg.get("settings") or {})
        except Exception as exc:
            db.record_connector_run(user_id, cid, "error", str(exc), 0)
            return {"connector": cid, "new": 0, "error": str(exc)}
        watch_cfg, llm_cfg, tg_cfg, wh_cfg = load_config()
        results = ingest_jobs(
            jobs,
            profile=load_profile(),
            llm_cfg=llm_cfg,
            min_score=watch_cfg.min_score,
            tg_cfg=tg_cfg,
            wh_cfg=wh_cfg,
            user_id=user_id,
        )
        new = sum(1 for r in results if r.is_new)
        if updated:
            db.save_connector_cfg(user_id, cid, settings=updated)
        db.record_connector_run(user_id, cid, "ok", None, new)
        return {"connector": cid, "seen": len(results), "new": new}
    except Exception as exc:  # defensive: config file problems etc.
        db.record_connector_run(user_id, cid, "error", str(exc), 0)
        return {"connector": cid, "new": 0, "error": str(exc)}
    finally:
        _fetch_lock.release()


def fetch_all_for(user_id: int) -> list[dict]:
    cfgs = db.connector_cfgs(user_id)
    return [
        run_connector_for(user_id, cid)
        for cid, cfg in cfgs.items()
        if cfg.get("enabled")
    ]


# ------------------------------------------------------------------- poller
def _last_run_age_min(cfg: dict) -> float:
    raw = cfg.get("last_run")
    if not raw:
        return float("inf")
    try:
        last = datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S")
        return (datetime.now(UTC).replace(tzinfo=None) - last).total_seconds() / 60
    except ValueError:
        return float("inf")


def _poll_loop(stop: threading.Event, interval_min: int) -> None:
    """Background radar: every enabled connector, politely spaced."""
    first_delay = 45  # let the server finish booting before hunting
    interval = max(POLL_FLOOR_MIN, int(interval_min))
    while not stop.wait(first_delay):
        for uid, cid in db.enabled_connector_rows():
            if stop.is_set():
                return
            cfg = db.connector_cfg(uid, cid)
            if _last_run_age_min(cfg) < interval:
                continue
            run_connector_for(uid, cid)


# ------------------------------------------------------------------ app factory
class AuthBody(BaseModel):
    email: str
    password: str


class StatusBody(BaseModel):
    id: int
    status: str


class DraftBody(BaseModel):
    id: int
    text: str


class OutcomeBody(BaseModel):
    id: int
    outcome: str | None = None


class ConnectorBody(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None


def create_app(*, start_poller: bool = False) -> FastAPI:
    watch_cfg, _, _, _ = load_config()
    stop_event = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        thread = None
        if start_poller:
            thread = threading.Thread(
                target=_poll_loop, args=(stop_event, watch_cfg.interval_minutes),
                daemon=True, name="lh-poller",
            )
            thread.start()
        yield
        stop_event.set()

    app = FastAPI(title="leadhound", version=__version__, lifespan=lifespan)

    # ------------------------------------------------------------- helpers
    def _user(request: Request) -> dict:
        user = auth.user_for_token(request.cookies.get(auth.COOKIE_NAME))
        if not user:
            raise HTTPException(401, "not logged in")
        return user

    def _own_job(user: dict, job_id: int) -> db.Job:
        job = db.get_job(job_id)
        if not job or (job.user_id is not None and job.user_id != user["id"]):
            raise HTTPException(404, "no such job")
        return job

    def _set_session(response: Response, user_id: int) -> None:
        token = auth.start_session(user_id)
        response.set_cookie(
            auth.COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            max_age=auth.SESSION_TTL_DAYS * 86400,
            path="/",
        )

    # --------------------------------------------------------------- pages
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/favicon.ico", status_code=204)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    # ---------------------------------------------------------------- auth
    @app.post("/api/auth/register")
    def register(body: AuthBody, response: Response) -> dict:
        try:
            user = auth.register(body.email, body.password)
        except auth.AuthError as exc:
            raise HTTPException(
                409 if "already" in str(exc) else 400, str(exc)
            ) from exc
        _set_session(response, user["id"])
        return {"ok": True, "user": user}

    @app.post("/api/auth/login")
    def login(body: AuthBody, response: Response) -> dict:
        try:
            user = auth.login(body.email, body.password)
        except auth.AuthError as exc:
            raise HTTPException(401, str(exc)) from exc
        _set_session(response, user["id"])
        return {"ok": True, "user": user}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        auth.end_session(request.cookies.get(auth.COOKIE_NAME))
        response.delete_cookie(auth.COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(request: Request) -> dict:
        return {"ok": True, "user": _user(request)}

    # --------------------------------------------------------------- board
    @app.get("/api/state")
    def state(request: Request) -> dict:
        user = _user(request)
        payload = build_state(user["id"])
        payload["user"] = user
        return payload

    @app.post("/api/status")
    def set_status(body: StatusBody, request: Request) -> dict:
        user = _user(request)
        if body.status not in ("pending", "approved", "sent", "rejected"):
            raise HTTPException(400, "invalid status")
        _own_job(user, body.id)
        db.set_status(body.id, body.status)
        return {"ok": True}

    @app.post("/api/draft")
    def set_draft(body: DraftBody, request: Request) -> dict:
        user = _user(request)
        _own_job(user, body.id)
        db.set_draft(body.id, body.text)
        return {"ok": True}

    @app.post("/api/outcome")
    def set_outcome(body: OutcomeBody, request: Request) -> dict:
        user = _user(request)
        _own_job(user, body.id)
        if body.outcome in (None, "", "none"):
            db.clear_outcome(body.id)
            return {"ok": True}
        try:
            db.set_outcome(body.id, str(body.outcome))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.post("/api/demo")
    def load_demo(request: Request) -> dict:
        user = _user(request)
        from .demo import DEMO_JOBS

        _, llm_cfg, _, _ = load_config()
        results = ingest_jobs(
            [dict(j) for j in DEMO_JOBS],
            profile=load_profile(),
            llm_cfg=llm_cfg,
            min_score=0,
            user_id=user["id"],
        )
        return {"ok": True, "added": sum(1 for r in results if r.is_new)}

    # ---------------------------------------------------------- connectors
    @app.get("/api/connectors")
    def list_connectors(request: Request) -> dict:
        user = _user(request)
        return {"ok": True, "connectors": _connector_payload(user["id"])}

    @app.post("/api/connectors/{cid}")
    def save_connector(cid: str, body: ConnectorBody, request: Request) -> dict:
        user = _user(request)
        conn = connectors.get(cid)
        if conn is None:
            raise HTTPException(404, "unknown connector")
        stored = db.connector_cfg(user["id"], cid)
        settings = stored.get("settings") or {}
        if body.settings is not None:
            if unknown := set(body.settings) - {f.name for f in conn.fields}:
                raise HTTPException(400, f"unknown setting(s): {', '.join(sorted(unknown))}")
            settings = _unmask_settings(conn, body.settings, settings)
        db.save_connector_cfg(user["id"], cid, enabled=body.enabled, settings=settings)
        return {"ok": True, "connectors": _connector_payload(user["id"])}

    @app.post("/api/connectors/{cid}/run")
    def run_connector(cid: str, request: Request) -> JSONResponse:
        user = _user(request)
        result = run_connector_for(user["id"], cid)
        code = 502 if result.get("error") else 200
        return JSONResponse({"ok": "error" not in result, **result}, status_code=code)

    @app.post("/api/fetch")
    def fetch_now(request: Request) -> JSONResponse:
        user = _user(request)
        results = fetch_all_for(user["id"])
        if not results:
            return JSONResponse(
                {"ok": True, "results": [],
                 "hint": "no sources enabled yet — open ⚙ sources and switch one on"}
            )
        return JSONResponse({"ok": True, "results": results})

    # ------------------------------------------------------ upwork oauth
    def _redirect_uri(request: Request) -> str:
        return str(request.base_url).rstrip("/") + "/api/connectors/upwork/callback"

    @app.post("/api/connectors/upwork/auth/start")
    def upwork_auth_start(request: Request) -> dict:
        user = _user(request)
        settings = db.connector_cfg(user["id"], "upwork").get("settings") or {}
        if not settings.get("client_id"):
            raise HTTPException(400, "save your Upwork client id first")
        state = secrets.token_urlsafe(16)
        settings["oauth_state"] = state
        redirect_uri = _redirect_uri(request)
        db.save_connector_cfg(user["id"], "upwork", settings=settings)
        return {
            "ok": True,
            "authorize_url": _upwork.authorize_url(settings["client_id"], redirect_uri, state),
            "redirect_uri": redirect_uri,
        }

    @app.get("/api/connectors/upwork/callback")
    def upwork_callback(
        request: Request, code: str | None = None, state: str | None = None
    ) -> HTMLResponse:
        user = _user(request)
        settings = db.connector_cfg(user["id"], "upwork").get("settings") or {}
        if not code or not state or state != settings.get("oauth_state"):
            return HTMLResponse(
                "<h2>🐺 Upwork connect failed</h2><p>state mismatch — start the flow again</p>",
                status_code=400,
            )
        try:
            updated = _upwork.exchange_code(settings, code, _redirect_uri(request))
        except Exception as exc:
            return HTMLResponse(
                f"<h2>🐺 Upwork connect failed</h2><p>{_html.escape(str(exc))}</p>",
                status_code=400,
            )
        updated.pop("oauth_state", None)
        db.save_connector_cfg(user["id"], "upwork", settings=updated)
        return HTMLResponse(
            "<h2>🐺 Upwork connected</h2>"
            "<p>close this tab and hit ⚡ run now on the Upwork source.</p>"
        )

    return app
