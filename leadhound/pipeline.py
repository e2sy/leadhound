"""The ingest pipeline — score → draft → store → notify.

One shared path so the CLI, the dashboard's "fetch now" button and the
background poller behave identically. Notify targets (Telegram, webhooks,
email) are passed in as configs; nothing here prints or touches the console.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import EmailConfig, LLMConfig, Profile, TelegramConfig, WebhookConfig
from .engine.scorer import score_job
from .engine.voice import draft_proposal
from .notify import email as em
from .notify import telegram as tg
from .notify import webhooks as wh


@dataclass
class Ingested:
    rid: int
    job: dict
    score: int
    breakdown: dict
    draft: str
    mode: str
    is_new: bool
    notified: bool = field(default=False)
    auto_rule: str | None = field(default=None)


def ingest_jobs(
    jobs: list[dict],
    *,
    profile: Profile,
    llm_cfg: LLMConfig,
    min_score: int = 0,
    tg_cfg: TelegramConfig | None = None,
    tg_min_score: int = 0,
    wh_cfg: WebhookConfig | None = None,
    em_cfg: EmailConfig | None = None,
    user_id: int | None = None,
) -> list[Ingested]:
    """Run every job through the scope. Returns per-job results.

    tg_min_score raises the bar for Telegram pushes specifically (0 = push
    everything that made the board), so the pocket stays quiet until a gig
    is actually worth the buzz."""
    from . import db  # local import: db imports config, avoids cycles

    results: list[Ingested] = []
    tg_on = bool(tg_cfg and tg_cfg.enabled)
    wh_on = bool(wh_cfg and (wh_cfg.discord_webhook_url or wh_cfg.slack_webhook_url))
    em_on = bool(em_cfg and em_cfg.enabled)

    for job in jobs:
        score, breakdown = score_job(job, profile)
        draft, mode = "", ""
        if score >= min_score:
            draft, mode = draft_proposal(
                job, profile, llm_cfg, breakdown["skills"]["matched"]
            )
        rid, is_new = db.upsert_job(job, score, breakdown, draft, user_id=user_id)
        ing = Ingested(
            rid=rid, job=job, score=score, breakdown=breakdown,
            draft=draft, mode=mode, is_new=is_new,
        )
        if user_id and is_new:
            hits = db.match_snipe_rules(user_id, score, job)
            if hits:
                db.set_status(rid, "approved")
                db.mark_auto_armed(rid, hits[0]["name"])
                ing.auto_rule = hits[0]["name"]
        tg_wants = tg_on and score >= (tg_min_score if tg_min_score > 0 else min_score)
        if is_new and draft and (tg_wants or wh_on or em_on):
            stored = db.get_job(rid)
            if tg_wants:
                ok = tg.send_job_card(tg_cfg.bot_token, tg_cfg.chat_id, stored, breakdown)
                if draft:
                    tg.send_draft(tg_cfg.bot_token, tg_cfg.chat_id, stored)
                ing.notified = ing.notified or ok
            if wh_on:
                hits = wh.send_webhooks(stored, breakdown, wh_cfg)
                ing.notified = ing.notified or any(ok for _, ok in hits)
            if em_on:
                ok = em.send_job_email(em_cfg, stored, breakdown)
                ing.notified = ing.notified or ok
            if ing.notified:
                db.mark_notified(rid)
        results.append(ing)
    return results
