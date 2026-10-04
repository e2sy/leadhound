"""Digest — the one-screen morning briefing.

Every sniper checks in before the day starts. Digest shows the best gigs
from the last 24h with scores, money and flags — then hands you to the
approval queue. Pure rendering: the DB does the filtering.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel

from . import db
from .config import is_initialized, load_profile

console = Console()


def _money_line(job: db.Job) -> str:
    b = job.breakdown.get("budget", {})
    if b.get("hourly"):
        return f"${b['hourly']:g}/hr"
    if b.get("fixed_min"):
        return f"from ${b['fixed_min']:,.0f}"
    return "budget not stated"


def _entry(i: int, job: db.Job) -> str:
    b = job.breakdown
    matched = ", ".join((b.get("skills") or {}).get("matched", [])[:4]) or "no skill overlap"
    flags = f" | 🚩 {', '.join(b.get('red_flags'))}" if b.get("red_flags") else ""
    return (
        f"[bold]{i}. [{job.score}] {job.title}[/bold]\n"
        f"    {_money_line(job)} · {job.source} · {matched}{flags}\n"
        f"    [dim]{job.url}[/dim]"
    )


def build_digest(jobs: list[db.Job], name: str, hours: int) -> str:
    """Pure text builder — easy to test, reused by tests and the CLI."""
    if not jobs:
        return (
            f"🐺 Morning, {name}. Nothing above the bar in the last {hours}h.\n"
            "The radar keeps rotating — leadhound watch --loop"
        )
    lines = [
        f"🐺 Morning, {name}. {len(jobs)} gig(s) worth your coffee, last {hours}h:",
        "",
    ]
    lines += [_entry(i, j) for i, j in enumerate(jobs, 1)]
    lines += [
        "",
        "Drafts are waiting — leadhound queue · first shot wins.",
    ]
    return "\n".join(lines)


def cmd_digest(args) -> None:
    if not is_initialized():
        console.print("[red]Not initialized.[/red] Run: [bold]leadhound init[/bold]")
        sys.exit(1)
    profile = load_profile()
    jobs = db.recent_jobs(hours=args.hours, min_score=args.min_score, limit=args.limit)
    text = build_digest(jobs, profile.name, args.hours)
    console.print(Panel(text, title=f"leadhound digest · last {args.hours}h", title_align="left"))
