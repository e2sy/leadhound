"""Double-click launcher — turns the frozen exe into a real desktop app.

Launching the binary with no arguments used to print a terminal guide.
Now it does the obvious thing:

    double-click → auto-setup → demo data on first run → dashboard opens
    in the browser → console shows the server status until Ctrl+C.

The CLI stays unchanged for terminal users (`leadhound web`, etc.).
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


def ensure_first_run_data() -> int:
    """Create the home dir and, when the database is empty, seed demo gigs.

    Returns the number of gigs seeded (0 when the user already has data).
    """
    if not is_initialized():
        init_files()
    db.ensure_db()
    if db.stats().get("total", 0) > 0:
        return 0
    from .cli import _process  # lazy: avoids import cycle at module load
    from .demo import DEMO_JOBS

    _process([dict(j) for j in DEMO_JOBS], min_score=0, notify=False, quiet=True)
    return len(DEMO_JOBS)


def launch_app() -> None:
    """The double-click experience: set up, seed, serve, open the browser."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    seeded = ensure_first_run_data()
    if seeded:
        console.print(Panel.fit(
            f"[bold green]Welcome to leadhound![/bold green]\n"
            f"Loaded [bold]{seeded} demo gigs[/bold] so you can explore the app.\n"
            f"They're marked [cyan]demo[/cyan] — run [bold]leadhound watch[/bold]\n"
            f"(from a terminal) to replace them with real gigs.",
            title="🐺 first run",
            border_style="green",
        ))

    from .web import serve

    port = find_free_port(7800)
    serve(host="127.0.0.1", port=port, open_browser=True)
