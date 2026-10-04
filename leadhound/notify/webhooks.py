"""Discord + Slack webhook notifications — gig cards where your community lives.

Zero SDKs: both platforms accept one POST per card. If a webhook is
configured in [webhooks] of config.toml, every gig that clears your
threshold lands in your server the moment the watcher sees it.
"""

from __future__ import annotations

import requests

UA = {"User-Agent": "leadhound/0.2 (+https://github.com/e2sy/leadhound)"}

# Discord embed colors by score band
GREEN, YELLOW, GREY = 0x2ECC40, 0xFFDC00, 0x95A5A6


def _score_color(score: int) -> int:
    return GREEN if score >= 80 else YELLOW if score >= 60 else GREY


def _money_line(b: dict) -> str:
    if b.get("hourly"):
        return f"${b['hourly']:g}/hr"
    if b.get("fixed_min"):
        return f"from ${b['fixed_min']:,.0f}"
    return "not stated"


def _matched(b: dict) -> list[str]:
    return (b.get("skills") or {}).get("matched", [])


def discord_payload(job, breakdown: dict) -> dict:
    """Rich embed card for Discord webhooks."""
    b = breakdown.get("budget", {})
    flags = breakdown.get("red_flags") or []
    matched = ", ".join(_matched(breakdown)[:6]) or "—"
    desc = (
        f"**Score {job.score}/100** · {_money_line(b)}\n"
        f"**Skills:** {matched}"
    )
    if flags:
        desc += f"\n🚩 {', '.join(flags)}"
    if job.draft:
        desc += "\n\n_Draft ready in your queue — leadhound queue_"
    return {
        "username": "leadhound",
        "embeds": [{
            "title": job.title[:250],
            "url": job.url,
            "description": desc[:3900],
            "color": _score_color(job.score),
            "footer": {"text": f"leadhound · {job.source} · you fire the final shot"},
        }],
    }


def slack_payload(job, breakdown: dict) -> dict:
    """Block-kit text for Slack incoming webhooks."""
    b = breakdown.get("budget", {})
    flags = breakdown.get("red_flags") or []
    matched = ", ".join(_matched(breakdown)[:6]) or "—"
    flag_line = f"\n:triangular_flag_on_post: _{', '.join(flags)}_" if flags else ""
    text = (
        f":wolf: *<{job.url}|{job.title[:180]}>*\n"
        f"*Score {job.score}/100* · {_money_line(b)} · {job.source}\n"
        f"Skills: {matched}{flag_line}\n"
        f"{'> ' + job.draft[:280] + '…' if job.draft else '_no draft — below threshold_'}"
    )
    return {"text": text}


def send_webhooks(job, breakdown: dict, cfg) -> list[tuple[str, bool]]:
    """Post the card to every configured webhook. Returns [(platform, ok)]."""
    results: list[tuple[str, bool]] = []
    targets = [
        ("discord", cfg.discord_webhook_url, discord_payload(job, breakdown)),
        ("slack", cfg.slack_webhook_url, slack_payload(job, breakdown)),
    ]
    for platform, url, payload in targets:
        if not url:
            continue
        try:
            r = requests.post(url, json=payload, headers=UA, timeout=15)
            results.append((platform, r.status_code in (200, 204)))
        except requests.RequestException:
            results.append((platform, False))
    return results
