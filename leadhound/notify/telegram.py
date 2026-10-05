"""Telegram approval queue — gig cards land in your pocket with the draft."""

from __future__ import annotations

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_job_card(bot_token: str, chat_id: str, job, breakdown: dict) -> bool:
    skills = breakdown.get("skills", {})
    matched = ", ".join(skills.get("matched", [])[:6]) or "—"
    budget = breakdown.get("budget", {})
    money = (budget.get("hourly") and f"${budget['hourly']:g}/hr") or (
        (budget.get("fixed_min") and f"from ${budget['fixed_min']:,.0f}") or "not stated"
    )
    flags = breakdown.get("red_flags") or []
    flag_line = f"\n⚠️ Red flags: {', '.join(flags)}" if flags else ""

    text = (
        f"🔔 <b>{job.score}/100</b> — {_esc(job.title)}\n"
        f"<b>Source:</b> {job.source} | <b>Money:</b> {money}\n"
        f"<b>Matched skills:</b> {_esc(matched)}{flag_line}\n"
        f"<a href=\"{_esc(job.url)}\">Open gig ↗</a>\n\n"
        f"<i>Draft ready — use 'leadhound show {job.id}' to read it.</i>"
    )
    try:
        r = requests.post(
            API.format(token=bot_token),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        return r.ok
    except Exception:
        return False


def send_draft(bot_token: str, chat_id: str, job) -> bool:
    text = f"✍️ <b>Draft for:</b> {_esc(job.title)}\n\n{_esc(job.draft)}"
    try:
        r = requests.post(
            API.format(token=bot_token),
            json={
                "chat_id": chat_id,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        return r.ok
    except Exception:
        return False


def send_test_message(bot_token: str, chat_id: str) -> tuple[bool, str]:
    """Pocket-sniper arming check. Returns (ok, telegram's own words) so the
    dashboard can show the platform's verdict verbatim instead of guessing."""
    try:
        r = requests.post(
            API.format(token=bot_token),
            json={
                "chat_id": chat_id,
                "text": "🐺 leadhound pocket sniper armed — gigs will land here.",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if r.ok:
            return True, "Telegram accepted the message"
        try:
            detail = r.json().get("description", f"HTTP {r.status_code}")
        except Exception:
            detail = f"HTTP {r.status_code}"
        return False, detail
    except Exception as exc:
        return False, str(exc)


def send_plain(bot_token: str, chat_id: str, text: str) -> bool:
    """No parse_mode, no formatting — error alerts where honesty beats style."""
    try:
        r = requests.post(
            API.format(token=bot_token),
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=20,
        )
        return r.ok
    except Exception:
        return False
