"""Double-click launcher — turns the frozen exe into a real desktop app.

Launching the binary with no arguments now does the obvious thing:

    double-click → auto-setup → dashboard opens in the browser →
    create your account → connect sources → Fetch gigs

No demo seeding: the empty board offers "Fetch gigs now" (real sources)
and "Load sample gigs" (an explicit, labeled demo). The CLI stays unchanged
for terminal users (`leadhound watch`, `leadhound demo`, etc.).
"""

from __future__ import annotations

import socket

from . import db
from .config import init_files, is_initialized


def find_free_port(start: int = 7800, tries: int = 10) -> int:
    """First free localhost port in [start, start+tries); raises OSError if none."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"no free port in range {start}..{start + tries - 1}")


def launch_app() -> None:
    """The double-click experience: set up, serve, open the browser."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    if not is_initialized():
        init_files()
    db.ensure_db()

    console.print(Panel.fit(
        "[bold green]🐺 leadhound is starting…[/bold green]\n"
        "Your browser is opening — create your account, connect\n"
        "your sources (Freelancer.com works instantly, Upwork/Fiverr\n"
        "connect from the ⚙ sources panel), then hit [bold]Fetch gigs[/bold].",
        title="first run",
        border_style="green",
    ))

    from .web import serve

    port = find_free_port(7800)
    serve(host="127.0.0.1", port=port, open_browser=True)
