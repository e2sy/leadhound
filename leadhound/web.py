"""leadhound web — runs the FastAPI backend with uvicorn.

Binds to 127.0.0.1 by default; your gig data never leaves your machine
unless you explicitly pass --host 0.0.0.0.
"""

from __future__ import annotations

import socket
import threading
import webbrowser

from rich.console import Console

from . import db

console = Console()

STATUSES = ("pending", "approved", "sent", "rejected")


def serve(host: str = "127.0.0.1", port: int = 7800, open_browser: bool = True) -> None:
    """Run the dashboard + API until Ctrl-C."""
    db.ensure_db()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            console.print(f"[red]Could not bind {host}:{port} — {exc}[/red]")
            raise SystemExit(1) from exc

    import uvicorn

    from .api import create_app

    shown_host = "127.0.0.1" if host in ("0.0.0.0", "") else host  # noqa: S104 — explicit opt-in
    url = f"http://{shown_host}:{port}/"
    lan = f"http://<your-ip>:{port}/"
    lines = [
        f"[bold green]🐺 leadhound running:[/bold green] [bold underline]{url}[/bold underline]",
        "Create an account in the browser, connect sources, then hit Fetch —",
        "the radar re-polls your sources every few minutes. Ctrl-C to stop.",
    ]
    if host in ("0.0.0.0", ""):  # noqa: S104 — explicit opt-in, flagged string check only
        lines.append(f"[yellow]Exposed on your LAN — open {lan} from your phone.[/yellow]")
    console.print("\n".join(lines))
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        create_app(start_poller=True),
        host=host,
        port=port,
        log_level="warning",
        log_config=None,
    )
