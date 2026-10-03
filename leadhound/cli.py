"""leadhound CLI — init, demo, watch, queue, show, telegram, stats, doctor."""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import db
from .config import (
    init_files,
    is_initialized,
    load_config,
    load_profile,
)
from .demo import DEMO_JOBS
from .digest import cmd_digest
from .doctor import cmd_doctor
from .engine.scorer import score_job
from .engine.voice import draft_proposal
from .notify import telegram as tg
from .notify import webhooks as wh
from .watchers.rss import poll

console = Console()


def _require_init() -> None:
    if not is_initialized():
        console.print("[red]Not initialized.[/red] Run: [bold]leadhound init[/bold]")
        sys.exit(1)


# ------------------------------------------------------------------ commands
def cmd_init(args) -> None:
    init_files()
    console.print(Panel.fit(
        "[bold green]leadhound initialized.[/bold green]\n\n"
        "Next steps:\n"
        "  1. Edit  [cyan]~/.leadhound/profile.toml[/cyan]  (skills, rates, highlights)\n"
        "  2. Edit  [cyan]~/.leadhound/config.toml[/cyan]   (sources, Telegram, LLM)\n"
        "  3. Try it offline:  [bold]leadhound demo[/bold] then [bold]leadhound queue[/bold]\n"
        "  4. Go live:         [bold]leadhound watch[/bold]",
        title="leadhound",
    ))


def _process(jobs: list[dict], min_score: int, notify: bool) -> None:
    """Score → draft → store → optionally push to Telegram."""
    profile = load_profile()
    _, llm_cfg, tg_cfg, wh_cfg = load_config()
    new_count = 0

    table = Table(title="Poll results", show_lines=False)
    for col in ("score", "source", "title", "money", "status"):
        table.add_column(col)

    for job in jobs:
        score, breakdown = score_job(job, profile)
        draft, mode = "", ""
        if score >= min_score:
            draft, mode = draft_proposal(job, profile, llm_cfg, breakdown["skills"]["matched"])
        rid, is_new = db.upsert_job(job, score, breakdown, draft)
        if not is_new:
            continue
        new_count += 1
        b = breakdown
        money = (b["budget"]["hourly"] and f"${b['budget']['hourly']:g}/hr") or (
            (b["budget"]["fixed_min"] and f"${b['budget']['fixed_min']:,.0f}") or "—"
        )
        color = "green" if score >= 80 else "yellow" if score >= min_score else "dim"
        table.add_row(
            f"[{color}]{score}[/{color}]", job["source"],
            job["title"][:48], str(money),
            ("drafted (" + mode + ")") if draft else "below threshold",
        )

        if draft and notify and tg_cfg.enabled:
            j = db.get_job(rid)
            ok = tg.send_job_card(tg_cfg.bot_token, tg_cfg.chat_id, j, breakdown)
            tg.send_draft(tg_cfg.bot_token, tg_cfg.chat_id, j)
            db.mark_notified(rid)
            if not ok:
                console.print("[red]Telegram push failed — check config.toml[/red]")

        if draft and notify and (wh_cfg.discord_webhook_url or wh_cfg.slack_webhook_url):
            j = db.get_job(rid)
            results = wh.send_webhooks(j, breakdown, wh_cfg)
            db.mark_notified(rid)
            for platform, ok in results:
                if not ok:
                    console.print(f"[red]{platform} webhook failed — check the URL[/red]")

    console.print(table)
    console.print(f"[bold]{new_count} new[/bold] gig(s) processed.")


def cmd_watch(args) -> None:
    _require_init()
    watch_cfg, _, _, _ = load_config()
    min_score = args.min_score if args.min_score is not None else watch_cfg.min_score
    sources = args.sources.split(",") if args.sources else watch_cfg.sources

    while True:
        console.rule(f"[bold]leadhound watching: {', '.join(sources)}")
        jobs, warnings = poll(sources)
        for w in warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
        if jobs:
            _process(jobs, min_score, notify=True)
        else:
            console.print("[dim]no jobs returned from any source.[/dim]")
        if not args.loop:
            break
        try:
            time.sleep(watch_cfg.interval_minutes * 60)
        except KeyboardInterrupt:
            break


def cmd_demo(args) -> None:
    _require_init()
    console.print("[bold]Injecting demo gigs...[/bold]")
    _process([dict(j) for j in DEMO_JOBS], min_score=0, notify=False)
    console.print("\nNow run: [bold]leadhound queue[/bold]")


def cmd_queue(args) -> None:
    _require_init()
    load_config()
    load_profile()
    min_score = args.min_score or 0
    pending = db.jobs_by_status("pending", min_score=min_score)

    if not pending:
        console.print("[green]Queue empty — you're all caught up.[/green]")
        return

    if args.list:
        _print_list(pending)
        return

    for job in pending:
        b = job.breakdown
        matched = ", ".join(b.get("skills", {}).get("matched", [])) or "—"
        body = Panel(
            f"[bold]{job.title}[/bold]\n"
            f"{job.source} | {job.url}\n\n"
            f"[bold]Score {job.score}/100[/bold] — matched: {matched}\n"
            f"{b.get('budget', {}).get('note', '')}\n"
            + (f"[red]Red flags: {', '.join(b.get('red_flags', []))}[/red]\n" if b.get("red_flags") else "")
            + f"\n{job.draft}",
            title=f"#{job.id} · {job.source}",
        )
        console.print(body)
        prompt = "[bold][a][/bold] approve  [r] reject  [s] skip  [o] open  [q] quit > "
        answer = console.input(prompt).strip().lower()
        if answer == "a":
            db.set_status(job.id, "approved")
            console.print(f"[green]Approved.[/green] Open + send: {job.url}")
            webbrowser.open(job.url)
        elif answer == "r":
            db.set_status(job.id, "rejected")
            console.print("[dim]Rejected.[/dim]")
        elif answer == "q":
            break
        console.print()

    console.print(f"[bold]Stats:[/bold] {db.stats()}")


def _print_list(pending) -> None:
    table = Table(title=f"Pending queue ({len(pending)})")
    for col in ("id", "score", "source", "title", "url"):
        table.add_column(col)
    for j in pending:
        color = "green" if j.score >= 80 else "yellow"
        table.add_row(str(j.id), f"[{color}]{j.score}[/{color}]", j.source, j.title[:52], j.url[:60])
    console.print(table)


def cmd_show(args) -> None:
    _require_init()
    job = db.get_job(args.id)
    if not job:
        console.print("[red]No such job.[/red]")
        return
    b = job.breakdown
    matched = ", ".join(b.get("skills", {}).get("matched", [])) or "—"
    console.print(Panel(
        f"{job.title}\n{job.source} | {job.url}\n"
        f"Score {job.score}/100 — matched: {matched} — status: {job.status}",
        title=f"Job #{job.id}",
    ))
    console.print(Panel(job.draft or "(no draft — score below threshold)", title="Draft proposal"))


def cmd_telegram(args) -> None:
    _require_init()
    watch_cfg, _, tg_cfg, _ = load_config()
    if not tg_cfg.enabled:
        console.print("[red]Telegram not enabled in config.toml[/red]")
        return
    pending = db.pending_unnotified(min_score=watch_cfg.min_score)
    sent = 0
    for job in pending:
        b = job.breakdown
        if tg.send_job_card(tg_cfg.bot_token, tg_cfg.chat_id, job, b):
            if job.draft:
                tg.send_draft(tg_cfg.bot_token, tg_cfg.chat_id, job)
            db.mark_notified(job.id)
            sent += 1
    console.print(f"[green]Pushed {sent} gig card(s) to Telegram.[/green]")


def cmd_webhooks(args) -> None:
    _require_init()
    watch_cfg, _, _, wh_cfg = load_config()
    if not (wh_cfg.discord_webhook_url or wh_cfg.slack_webhook_url):
        console.print("[red]No webhooks configured — fill [webhooks] in config.toml[/red]")
        return
    pending = db.pending_unnotified(min_score=watch_cfg.min_score)
    sent = 0
    for job in pending:
        results = wh.send_webhooks(job, job.breakdown, wh_cfg)
        if any(ok for _, ok in results):
            db.mark_notified(job.id)
            sent += 1
        for platform, ok in results:
            if not ok:
                console.print(f"[red]{platform} webhook failed — check the URL[/red]")
    console.print(f"[green]Pushed {sent} gig card(s) to your webhooks.[/green]")


def cmd_stats(args) -> None:
    _require_init()
    s = db.stats()
    console.print(Panel.fit(
        f"Total gigs seen: [bold]{s['total']}[/bold]\n"
        f"Highest score:   [bold]{s['highest_score']}[/bold]\n"
        f"Pending:  {s['pending']}   Approved: {s['approved']}\n"
        f"Rejected: {s['rejected']}   Sent:     {s['sent']}",
        title="leadhound stats",
    ))


# --------------------------------------------------------------------- parser
def main() -> None:
    p = argparse.ArgumentParser(
        prog="leadhound",
        description="The gig sniper — job boards watched 24/7, proposals drafted in your voice.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create ~/.leadhound with config + profile").set_defaults(fn=cmd_init)

    d = sub.add_parser("demo", help="inject sample gigs (offline test / YT demo)")
    d.set_defaults(fn=cmd_demo)

    w = sub.add_parser("watch", help="poll job sources now")
    w.add_argument("--loop", action="store_true", help="keep polling on an interval")
    w.add_argument("--min-score", type=int, default=None, help="override min score")
    w.add_argument("--sources", type=str, default=None, help="comma list: remoteok,remotive,weworkremotely")
    w.set_defaults(fn=cmd_watch)

    q = sub.add_parser("queue", help="review pending gigs: approve / reject")
    q.add_argument("--list", action="store_true", help="print queue non-interactively")
    q.add_argument("--min-score", type=int, default=0)
    q.set_defaults(fn=cmd_queue)

    s = sub.add_parser("show", help="show one job + its draft")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_show)

    t = sub.add_parser("telegram", help="push pending gig cards to Telegram")
    t.set_defaults(fn=cmd_telegram)

    wb = sub.add_parser("webhooks", help="push pending gig cards to Discord/Slack")
    wb.set_defaults(fn=cmd_webhooks)

    st = sub.add_parser("stats", help="pipeline stats")
    st.set_defaults(fn=cmd_stats)

    dr = sub.add_parser("doctor", help="pre-flight check: config, profile, feeds, db")
    dr.add_argument("--offline", action="store_true", help="skip all network checks")
    dr.set_defaults(fn=cmd_doctor)

    dg = sub.add_parser("digest", help="morning briefing: best gigs from the last 24h")
    dg.add_argument("--hours", type=int, default=24, help="lookback window")
    dg.add_argument("--min-score", type=int, default=0)
    dg.add_argument("--limit", type=int, default=5, help="max gigs to show")
    dg.set_defaults(fn=cmd_digest)

    args = p.parse_args()
    try:
        args.fn(args)
    except KeyboardInterrupt:
        console.print("\n[dim]bye.[/dim]")


if __name__ == "__main__":
    main()
