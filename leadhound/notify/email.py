"""Email notifications — gig cards in your inbox via plain SMTP.

Zero SDKs, stdlib only (smtplib + EmailMessage). Configure [email] in
config.toml; every gig that clears your threshold lands as a clean text
card with the score, the money, the matched skills and the draft.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import EmailConfig


def _money_line(b: dict) -> str:
    if b.get("hourly"):
        return f"${b['hourly']:g}/hr"
    if b.get("fixed_min"):
        return f"from ${b['fixed_min']:,.0f}"
    return "not stated"


def card_text(job, breakdown: dict) -> str:
    b = breakdown.get("budget", {})
    matched = ", ".join((breakdown.get("skills") or {}).get("matched", [])[:8]) or "—"
    flags = (breakdown.get("red_flags") or [])
    lines = [
        f"SCORE {job.score}/100 · {_money_line(b)}",
        f"SOURCE: {job.source}",
        f"MATCHED: {matched}",
    ]
    if flags:
        lines.append(f"RED FLAGS: {', '.join(flags)}")
    lines += ["", job.title, job.url, ""]
    if job.draft:
        lines += ["--- your draft ---", job.draft]
    return "\n".join(lines)


def send_email(cfg: EmailConfig, subject: str, body: str) -> bool:
    """One plain-text email through SMTP. Honest bool, never raises."""
    if not (cfg.enabled and cfg.smtp_host and cfg.to_addr):
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.smtp_user or "leadhound@localhost"
        msg["To"] = cfg.to_addr
        msg.set_content(body)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as s:
            if cfg.use_tls:
                s.starttls()
            if cfg.smtp_user:
                s.login(cfg.smtp_user, cfg.smtp_pass)
            s.send_message(msg)
        return True
    except Exception:  # an SMTP hiccup must never kill the pipeline
        return False


def send_job_email(cfg: EmailConfig, job, breakdown: dict) -> bool:
    """Gig card + draft for one newly spotted gig."""
    return send_email(
        cfg,
        f"🐺 #{job.score} · {job.title[:70]}",
        card_text(job, breakdown),
    )
