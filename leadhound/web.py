"""leadhound web — the local pipeline dashboard.

stdlib-only HTTP server (http.server) serving an embedded single-page app.
Binds to 127.0.0.1 by default; your gig data never leaves your machine
unless you explicitly pass --host 0.0.0.0.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rich.console import Console

from . import db
from .engine import intel
from .webassets import PAGE

console = Console()

STATUSES = ("pending", "approved", "sent", "rejected")
_MAX_BODY = 1_000_000  # 1 MB cap on request bodies
_PREVIEW_LEN = 400


def job_to_dict(j: db.Job) -> dict:
    b = j.breakdown
    body = (j.body or "").strip()
    if len(body) > _PREVIEW_LEN:
        body = body[:_PREVIEW_LEN].rstrip() + "…"
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


def build_state() -> dict:
    """Everything the dashboard needs in one round trip."""
    db.ensure_db()
    cal = db.calibration()  # includes "hint"
    jobs = db.all_jobs(limit=300)
    demo = bool(jobs) and all(j.source == "demo" for j in jobs)
    return {
        "stats": db.stats(),
        "calibration": cal,
        "demo": demo,
        "jobs": [job_to_dict(j) for j in jobs],
    }


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console clean
            pass

        # ------------------------------------------------------------ helpers
        def _json(self, payload: dict, code: int = 200) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _read_body(self) -> dict | None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if n <= 0 or n > _MAX_BODY:
                return None
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            return data if isinstance(data, dict) else None

        # --------------------------------------------------------------- GET
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                raw = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)
            elif path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif path == "/api/state":
                try:
                    self._json(build_state())
                except Exception as exc:  # defensive: dashboard must not die
                    self._json({"ok": False, "error": str(exc)}, 500)
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        # -------------------------------------------------------------- POST
        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            data = self._read_body()
            if data is None:
                self._json({"ok": False, "error": "invalid JSON body"}, 400)
                return
            try:
                if path == "/api/status":
                    jid, status = data.get("id"), data.get("status")
                    if not isinstance(jid, int) or status not in STATUSES:
                        self._json({"ok": False,
                                    "error": f"id must be int, status one of {STATUSES}"}, 400)
                        return
                    if not db.get_job(jid):
                        self._json({"ok": False, "error": "no such job"}, 404)
                        return
                    db.set_status(jid, status)
                    self._json({"ok": True})
                elif path == "/api/draft":
                    jid, text = data.get("id"), data.get("text")
                    if not isinstance(jid, int) or not isinstance(text, str):
                        self._json({"ok": False, "error": "id must be int, text must be str"}, 400)
                        return
                    if not db.get_job(jid):
                        self._json({"ok": False, "error": "no such job"}, 404)
                        return
                    db.set_draft(jid, text)
                    self._json({"ok": True})
                elif path == "/api/outcome":
                    jid, outcome = data.get("id"), data.get("outcome")
                    if not isinstance(jid, int):
                        self._json({"ok": False, "error": "id must be int"}, 400)
                        return
                    if outcome in (None, "", "none"):
                        db.clear_outcome(jid)
                        self._json({"ok": True})
                        return
                    try:
                        db.set_outcome(jid, str(outcome))
                    except ValueError:
                        self._json({"ok": False,
                                    "error": f"outcome must be one of {db.OUTCOMES}"}, 400)
                        return
                    self._json({"ok": True})
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 7800, open_browser: bool = True) -> None:
    """Run the dashboard until Ctrl-C."""
    db.ensure_db()
    try:
        httpd = ThreadingHTTPServer((host, port), make_handler())
    except OSError as exc:
        console.print(f"[red]Could not bind {host}:{port} — {exc}[/red]")
        raise SystemExit(1) from exc

    shown_host = "127.0.0.1" if host in ("0.0.0.0", "") else host  # noqa: S104 — explicit opt-in
    url = f"http://{shown_host}:{httpd.server_address[1]}/"
    lan = f"http://<your-ip>:{httpd.server_address[1]}/"
    lines = [
        f"[bold green]🐺 leadhound dashboard running:[/bold green] [bold underline]{url}[/bold underline]",
        "Pipeline board + draft editor in your browser. Ctrl-C to stop.",
    ]
    if host in ("0.0.0.0", ""):  # noqa: S104 — explicit opt-in, flagged string check only
        lines.append(f"[yellow]Exposed on your LAN — open {lan} from your phone.[/yellow]")
    console.print("\n".join(lines))
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]dashboard stopped.[/dim]")
    finally:
        httpd.server_close()
