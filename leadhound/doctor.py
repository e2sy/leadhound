"""Doctor — pre-flight checks. Catches config problems before they cost you gigs.

Usage:
    leadhound doctor            # full check, including feed reachability
    leadhound doctor --offline  # skip every network call
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import requests
from rich.console import Console
from rich.table import Table

from .config import (
    db_path,
    home,
    is_initialized,
    load_config,
    load_profile,
    profile_path,
)
from .watchers.rss import SOURCES

console = Console()

#politeness floor for the polling interval (minutes)
MIN_INTERVAL = 5


@dataclass
class Check:
    name: str
    ok: bool | None  # True pass, False fail, None warning
    detail: str = ""
    hint: str = ""


def _check_profile() -> list[Check]:
    if not profile_path().exists():
        return [Check("profile", False, "profile.toml not found", "run: leadhound init")]
    try:
        p = load_profile()
    except Exception as exc:  # malformed TOML
        return [Check("profile", False, f"unparsable: {exc}", "fix the TOML syntax in profile.toml")]
    checks = [
        Check("profile: parse", True, f"hello {p.name}"),
        Check(
            "profile: skills",
            bool(p.skills),
            f"{len(p.skills)} skills" if p.skills else "no skills listed",
            "" if p.skills else "add 3-10 skills to profile.toml — the scorer hunts with these",
        ),
        Check(
            "profile: rate floors",
            bool(p.min_hourly > 0 and p.min_fixed_budget > 0),
            f"${p.min_hourly:g}/hr · ${p.min_fixed_budget:,.0f} fixed",
            "" if p.min_hourly > 0 and p.min_fixed_budget > 0
            else "set min_hourly / min_fixed_budget above zero",
        ),
        Check(
            "profile: proof bullets",
            None if not p.highlights else True,
            f"{len(p.highlights)} highlight(s)" if p.highlights else "no highlights",
            "" if p.highlights
            else "advisory: highlights are injected into every draft — add 1-3 with numbers",
        ),
        Check(
            "profile: tone samples",
            None if not p.tone_samples else True,
            f"{len(p.tone_samples)} sample(s)" if p.tone_samples else "none (template voice)",
            "" if p.tone_samples else "advisory: 1-3 past winning proposals unlock the LLM voice engine",
        ),
    ]
    return checks


def _check_config() -> list[Check]:
    if not is_initialized():
        return [Check("config", False, "not initialized", "run: leadhound init")]
    try:
        w, llm, tg, whc = load_config()
    except Exception as exc:
        return [Check("config", False, f"unparsable: {exc}", "fix the TOML syntax in config.toml")]
    checks = [
        Check("config: parse", True, f"min_score={w.min_score} · interval={w.interval_minutes}m"),
        Check(
            "config: sources",
            bool(w.sources),
            ", ".join(w.sources),
            "" if w.sources else "no sources enabled — nothing will be watched",
        ),
    ]
    unknown = [s for s in w.sources if s not in SOURCES]
    if unknown:
        checks.append(Check(
            "config: sources", False, f"unknown: {', '.join(unknown)}",
            f"available: {', '.join(sorted(SOURCES))}",
        ))
    if w.interval_minutes < MIN_INTERVAL:
        checks.append(Check(
            "config: interval", None, f"{w.interval_minutes}m is aggressive",
            f"advisory: poll every >= {MIN_INTERVAL} min to stay polite to the feeds",
        ))
    if llm.enabled:
        checks.append(Check(
            "llm", bool(llm.api_key),
            f"{llm.model} @ {llm.base_url}",
            "" if llm.api_key else "llm.enabled=true but api_key is empty",
        ))
    if tg.enabled:
        creds = bool(tg.bot_token) and bool(tg.chat_id)
        checks.append(Check(
            "telegram", creds,
            "token + chat_id present" if creds else "missing credentials",
            "" if creds else "fill bot_token and chat_id, or set enabled=false",
        ))
    if whc.discord_webhook_url and not whc.discord_webhook_url.startswith("https://"):
        checks.append(Check(
            "webhooks: discord", False, "URL must start with https://",
            "copy the full webhook URL from Discord server settings",
        ))
    if whc.slack_webhook_url and not whc.slack_webhook_url.startswith("https://hooks.slack.com/"):
        checks.append(Check(
            "webhooks: slack", False, "not a Slack webhook URL",
            "expecting https://hooks.slack.com/services/...",
        ))
    return checks


def _check_db() -> Check:
    try:
        c = sqlite3.connect(db_path())
        n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        c.close()
        return Check("database", True, f"{n} gig(s) stored at {db_path()}")
    except sqlite3.Error:
        return Check("database", False, "unreadable", "delete the data dir and run: leadhound init")


def _check_feeds(sources: list[str]) -> list[Check]:
    """Light reachability probe — one GET per source, short timeout."""
    probes = {
        "weworkremotely": "https://weworkremotely.com/categories/remote-freelance-jobs.rss",
        "remoteok": "https://remoteok.com/api",
        "remotive": "https://remotive.com/api/remote-jobs?category=software-dev",
        "hackernews": "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=freelancer",
    }
    out = []
    for name in sources:
        url = probes.get(name)
        if not url:
            continue
        try:
            r = requests.get(url, timeout=8, stream=True)
            ok = r.status_code == 200
            r.close()
            out.append(Check(f"feed: {name}", True if ok else None, f"HTTP {r.status_code}",
                             "" if ok else "feed responded but not OK — may be rate-limited"))
        except requests.RequestException as exc:
            out.append(Check(f"feed: {name}", None, type(exc).__name__,
                             "unreachable right now — check your connection or try later"))
    return out


def run_checks(offline: bool = False) -> list[Check]:
    if not is_initialized():
        return [Check("setup", False, "not initialized", "run: leadhound init")]
    checks = [Check("home", True, str(home()))]
    checks += _check_profile()
    checks += _check_config()
    checks.append(_check_db())
    if not offline:
        try:
            w, _, _, _ = load_config()
            checks += _check_feeds(w.sources)
        except Exception:
            checks.append(Check("feeds", None, "skipped — config unparsable"))
    return checks


def cmd_doctor(args) -> None:
    console.print("[bold]🩺 leadhound doctor[/bold] — checking your setup\n")
    checks = run_checks(offline=args.offline)
    t = Table(show_header=False, box=None, pad_edge=False)
    t.add_column(width=3)
    t.add_column()
    hard_fail = False
    for c in checks:
        mark, style = ("✓", "green") if c.ok is True else ("✗", "red") if c.ok is False else ("!", "yellow")
        if c.ok is False:
            hard_fail = True
        line = f"[{style}]{mark}[/{style}] [bold]{c.name}[/bold] — {c.detail}"
        if c.hint:
            line += f"\n    [dim]↳ {c.hint}[/dim]"
        t.add_row("", line)
    console.print(t)
    if hard_fail:
        console.print("\n[red]Problems found.[/red] Fix the ✗ items above, then re-run.")
        raise SystemExit(1)
    console.print("\n[green]All clear.[/green] Happy hunting — leadhound watch")
