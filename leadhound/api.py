"""leadhound API — the real backend.

FastAPI + your local SQLite. Every dashboard route is account-scoped:

    /api/health                  liveness + version (no auth)
    /api/auth/register|login|logout|me
    /api/state                   board, stats, calibration (auth)
    /api/stats                   funnel, per-source + per-method conversion (auth)
    /api/status|draft|outcome    pipeline mutations (auth)
    /api/jobs/{id}/snipe-plan    how this gig can be sniped (auth)
    /api/jobs/{id}/snipe         fire: real bid on Freelancer.com (auth)
    /api/jobs/{id}/snipe-confirm kit send confirmed by the user (auth)
    /api/jobs/{id}/variants      proposal A/B variants list + upsert (auth)
    /api/demo                    load the sample gigs (auth)
    /api/connectors              source list + per-account config
    /api/connectors/{id}         save enabled/settings
    /api/connectors/{id}/run     fetch that one source now
    /api/fetch                   fetch every enabled source now
    /api/radar                   poller status: running, interval, enabled count
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
from .connectors import freelancer_account as _fla
from .connectors import upwork as _upwork
from .engine import intel
from .engine.voice import draft_proposal
from .notify import telegram as tg
from .pipeline import ingest_jobs
from .webassets import PAGE

_MAX_PREVIEW = 400
_MASK = "•••"  # sentinel returned instead of stored secrets
POLL_FLOOR_MIN = 5


# --------------------------------------------------------------------- state
def job_to_dict(j: db.Job, variants: dict[int, list[dict]] | None = None) -> dict:
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
        "sniped_at": j.sniped_at,
        "snipe_method": j.snipe_method,
        "snipe_note": j.snipe_note,
        "sent_variant": j.sent_variant,
        "variants": (variants or {}).get(j.id, []),
        "intel": intel.intel_for(j),
    }


def build_state(user_id: int | None = None) -> dict:
    """Everything the dashboard needs in one round trip."""
    db.ensure_db()
    jobs = db.all_jobs(limit=300, user_id=user_id)
    demo = bool(jobs) and all(j.source == "demo" for j in jobs)
    variants = db.all_variants()
    return {
        "stats": db.stats(user_id),
        "calibration": db.calibration(user_id),
        "demo": demo,
        "snipe": db.snipe_stats(user_id),
        "linked": {"freelancer": bool(_fl_tokens(user_id))},
        "jobs": [job_to_dict(j, variants) for j in jobs],
    }


# ------------------------------------------------------------------ sniping
def _fl_tokens(user_id: int | None) -> dict | None:
    """Linked Freelancer.com account settings, or None when not linked."""
    if not user_id:
        return None
    settings = db.connector_cfg(user_id, "freelancer_account").get("settings") or {}
    return settings if (settings.get("access_token") or settings.get("refresh_token")) else None


def _snipe_text(job: db.Job) -> str:
    """Ammunition: the stored draft, or a fresh template draft on the spot."""
    if (job.draft or "").strip():
        return job.draft
    _, llm_cfg, _, _, _ = load_config()
    job_dict = {
        "title": job.title,
        "body": job.body,
        "hourly": job.hourly,
        "budget_max": job.budget_max,
        "tags": [t for t in (job.tags or "").split(",") if t],
        "source": job.source,
        "url": job.url,
    }
    matched = (job.breakdown.get("skills") or {}).get("matched") or []
    text, _mode = draft_proposal(job_dict, load_profile(), llm_cfg, matched)
    return text


def _project_id_of(job: db.Job) -> int | None:
    """Numeric Freelancer.com project id from the guid (freelancer-<id>)."""
    if job.source != "freelancer":
        return None
    try:
        return int(job.guid.rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return None


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
        watch_cfg, llm_cfg, tg_cfg, wh_cfg, em_cfg = load_config()
        results = ingest_jobs(
            jobs,
            profile=load_profile(),
            llm_cfg=llm_cfg,
            min_score=watch_cfg.min_score,
            tg_cfg=tg_cfg,
            wh_cfg=wh_cfg,
            em_cfg=em_cfg,
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
_poller_state = {"running": False, "interval": 0}


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


class VariantBody(BaseModel):
    label: str
    text: str


class SnipeConfirmBody(BaseModel):
    variant: str | None = None


class SnipeBody(BaseModel):
    amount: float | None = None
    period: int = 7
    text: str | None = None
    variant: str | None = None


class ConnectorBody(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None


class NotifyBody(BaseModel):
    token: str | None = None
    chat_id: str | None = None
    enabled: bool | None = None
    listen: bool | None = None
    push_min_score: int | None = None


def create_app(*, start_poller: bool = False) -> FastAPI:
    watch_cfg, _, _, _, _ = load_config()
    stop_event = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        thread = None
        if start_poller:
            _poller_state["running"] = True
            _poller_state["interval"] = max(
                POLL_FLOOR_MIN, int(watch_cfg.interval_minutes)
            )
            thread = threading.Thread(
                target=_poll_loop, args=(stop_event, watch_cfg.interval_minutes),
                daemon=True, name="lh-poller",
            )
            thread.start()
        yield
        _poller_state["running"] = False
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

    @app.get("/api/radar")
    def radar(request: Request) -> dict:
        """Is the sniping radar actually hunting? Honest visibility into the poller."""
        user = _user(request)
        enabled = sum(
            1 for cfg in db.connector_cfgs(user["id"]).values() if cfg.get("enabled")
        )
        return {
            "ok": True,
            "running": _poller_state["running"],
            "interval_minutes": _poller_state["interval"],
            "enabled_sources": enabled,
        }

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

    @app.get("/api/stats")
    def stats(request: Request) -> dict:
        """The closer's scoreboard: funnel, per-source conversion, per-method."""
        user = _user(request)
        return {
            "ok": True,
            "funnel": db.funnel_stats(user["id"]),
            "pipeline": db.stats(user["id"]),
            "calibration": db.calibration(user["id"]),
        }

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

        _, llm_cfg, _, _, _ = load_config()
        results = ingest_jobs(
            [dict(j) for j in DEMO_JOBS],
            profile=load_profile(),
            llm_cfg=llm_cfg,
            min_score=0,
            user_id=user["id"],
        )
        return {"ok": True, "added": sum(1 for r in results if r.is_new)}

    # --------------------------------------------------------------- sniping
    def _snipe_plan(user: dict, job: db.Job) -> dict:
        pid = _project_id_of(job)
        settings = _fl_tokens(user["id"])
        linked = bool(settings)
        mode = "api" if (pid and linked) else "kit"
        return {
            "ok": True,
            "id": job.id,
            "mode": mode,
            "source": job.source,
            "url": job.url,
            "project_id": pid,
            "linked": linked,
            "identity": (settings or {}).get("identity"),
            "amount": job.budget_max or job.budget_min or 0,
            "period": 7,
            "text": _snipe_text(job),
            "variants": db.variants_for(job.id),
            "sent_variant": None,
        }

    @app.get("/api/jobs/{job_id}/snipe-plan")
    def snipe_plan(job_id: int, request: Request) -> dict:
        user = _user(request)
        job = _own_job(user, job_id)
        if job.status not in ("pending", "approved"):
            raise HTTPException(
                400, f"this gig is '{job.status}' — only pending/approved gigs can be sniped"
            )
        return _snipe_plan(user, job)

    @app.post("/api/jobs/{job_id}/snipe")
    def snipe_fire(job_id: int, body: SnipeBody, request: Request) -> JSONResponse:
        """Pull the trigger for real: place a bid on Freelancer.com with the
        user's own linked account. User-triggered only — no background firing."""
        user = _user(request)
        job = _own_job(user, job_id)
        if job.status not in ("pending", "approved"):
            raise HTTPException(
                400, f"this gig is '{job.status}' — only pending/approved gigs can be sniped"
            )
        pid = _project_id_of(job)
        settings = _fl_tokens(user["id"])
        if not pid or not settings:
            raise HTTPException(
                400,
                "real bids need a linked Freelancer.com account (accounts tab) — "
                "use the snipe kit for this gig instead",
            )
        amount = body.amount if body.amount is not None else (job.budget_max or job.budget_min or 0)
        if amount <= 0:
            raise HTTPException(400, "set a bid amount before firing")
        text = body.text if body.text is not None else _snipe_text(job)
        variant = (body.variant or "A").strip().upper() or "A"
        if variant != "A":
            stored = {v["label"]: v["text"] for v in db.variants_for(job.id)}
            if variant not in stored:
                raise HTTPException(400, f"variant {variant} does not exist for this gig")
            if text != stored[variant]:
                db.save_variant(job.id, variant, text)  # dialog edits write back
        try:
            result, updated = _fla.place_bid(
                settings, pid, amount=amount, period=max(1, int(body.period)), description=text
            )
        except _fla.FreelancerError as exc:
            raise HTTPException(502, str(exc)) from exc
        if updated:
            db.save_connector_cfg(user["id"], "freelancer_account", settings=updated)
        db.mark_sniped(
            job.id, "freelancer-api", f"bid #{result.get('id')}",
            None if variant == "A" else variant,
        )
        return JSONResponse(
            {
                "ok": True,
                "mode": "api",
                "bid_id": result.get("id"),
                "amount": round(float(amount), 2),
                "status": "sent",
                "url": job.url,
            }
        )

    @app.post("/api/jobs/{job_id}/snipe-confirm")
    def snipe_confirm(job_id: int, request: Request,
                      body: SnipeConfirmBody | None = None) -> dict:
        """Kit snipe: the user pasted the proposal and sent it — record the shot."""
        user = _user(request)
        job = _own_job(user, job_id)
        if job.status not in ("pending", "approved"):
            raise HTTPException(
                400, f"this gig is '{job.status}' — only pending/approved gigs can be sniped"
            )
        variant = ((body or SnipeConfirmBody()).variant or "A").strip().upper() or "A"
        if variant != "A" and variant not in {v["label"] for v in db.variants_for(job.id)}:
            raise HTTPException(400, f"variant {variant} does not exist for this gig")
        db.mark_sniped(
            job.id, "kit", "send confirmed from snipe dialog",
            None if variant == "A" else variant,
        )
        return {"ok": True, "mode": "kit", "status": "sent", "variant": variant}

    # ------------------------------------------------- proposal A/B variants
    @app.get("/api/jobs/{job_id}/variants")
    def list_variants(job_id: int, request: Request) -> dict:
        user = _user(request)
        _own_job(user, job_id)
        return {"ok": True, "variants": db.variants_for(job_id)}

    @app.post("/api/jobs/{job_id}/variants")
    def put_variant(job_id: int, body: VariantBody, request: Request) -> dict:
        user = _user(request)
        _own_job(user, job_id)
        try:
            db.save_variant(job_id, body.label, body.text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "variants": db.variants_for(job_id)}

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
                 "hint": "no sources enabled yet — open the accounts tab and connect one"}
            )
        return JSONResponse({"ok": True, "results": results})

    # -------------------------------------------------------- notify targets
    @app.get("/api/notify")
    def get_notify(request: Request) -> dict:
        user = _user(request)
        cfg = db.notify_cfg(user["id"])
        return {
            "ok": True,
            "notify": {
                "has_token": bool(cfg.get("telegram_token")),
                "telegram_chat_id": cfg.get("telegram_chat_id") or "",
                "telegram_enabled": bool(cfg.get("telegram_enabled")),
                "listen_enabled": bool(cfg.get("listen_enabled")),
                "push_min_score": int(cfg.get("push_min_score") or 70),
            },
        }

    @app.post("/api/notify/telegram")
    def save_notify(body: NotifyBody, request: Request) -> dict:
        user = _user(request)
        db.save_notify_cfg(
            user["id"],
            telegram_token=body.token,
            telegram_chat_id=body.chat_id,
            telegram_enabled=body.enabled,
            listen_enabled=body.listen,
            push_min_score=body.push_min_score,
        )
        return {"ok": True, **get_notify(request)}

    @app.post("/api/notify/telegram/test")
    def test_notify(request: Request) -> JSONResponse:
        user = _user(request)
        cfg = db.notify_cfg(user["id"])
        token = cfg.get("telegram_token") or ""
        chat = cfg.get("telegram_chat_id") or ""
        if not (token and chat):
            raise HTTPException(
                400, "save your bot token and chat id first — then fire the test"
            )
        ok, detail = tg.send_test_message(token, chat)
        return JSONResponse({"ok": ok, "detail": detail}, status_code=200 if ok else 502)

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

    # ------------------------------------------- freelancer account oauth
    def _fl_redirect_uri(request: Request) -> str:
        return str(request.base_url).rstrip("/") + "/api/connectors/freelancer_account/callback"

    @app.post("/api/connectors/freelancer_account/auth/start")
    def freelancer_auth_start(request: Request) -> dict:
        user = _user(request)
        settings = db.connector_cfg(user["id"], "freelancer_account").get("settings") or {}
        if not settings.get("client_id"):
            raise HTTPException(400, "save your Freelancer.com client id first")
        state = secrets.token_urlsafe(16)
        settings["oauth_state"] = state
        redirect_uri = _fl_redirect_uri(request)
        db.save_connector_cfg(user["id"], "freelancer_account", settings=settings)
        return {
            "ok": True,
            "authorize_url": _fla.authorize_url(settings["client_id"], redirect_uri, state),
            "redirect_uri": redirect_uri,
        }

    @app.get("/api/connectors/freelancer_account/callback")
    def freelancer_callback(
        request: Request, code: str | None = None, state: str | None = None
    ) -> HTMLResponse:
        user = _user(request)
        settings = db.connector_cfg(user["id"], "freelancer_account").get("settings") or {}
        if not code or not state or state != settings.get("oauth_state"):
            return HTMLResponse(
                "<h2>🎯 Freelancer.com connect failed</h2>"
                "<p>state mismatch — start the flow again</p>",
                status_code=400,
            )
        try:
            updated = _fla.exchange_code(settings, code, _fl_redirect_uri(request))
        except Exception as exc:
            return HTMLResponse(
                "<h2>🎯 Freelancer.com connect failed</h2>"
                f"<p>{_html.escape(str(exc))}</p>",
                status_code=400,
            )
        updated.pop("oauth_state", None)
        # greet the user with their real identity right away
        try:
            identity, refreshed = _fla.whoami(updated)
            updated = refreshed or updated
            updated["identity"] = identity
        except Exception:  # defensive: identity is cosmetic here, token is saved either way
            pass
        db.save_connector_cfg(user["id"], "freelancer_account", settings=updated)
        who = (updated.get("identity") or {}).get("username")
        line = f"linked as <b>@{_html.escape(who)}</b>" if who else "account linked"
        return HTMLResponse(
            "<h2>🎯 Freelancer.com account linked</h2>"
            f"<p>{line} — close this tab; the 🎯 snipe button now fires real bids.</p>"
        )

    return app
