"""Voice engine — drafts the proposal in YOUR voice.

Two modes:
  * template (zero-config, always works) — fills your highlights + matched skills
  * llm (optional) — any OpenAI-compatible endpoint, tuned by your tone samples
"""

from __future__ import annotations

import re

import requests

from ..config import LLMConfig, Profile

SKILL_STEPS = {
    "react native": "set up the app shell with offline-first storage and push notifications",
    "next.js": "scaffold Next.js (App Router) with SSR pages and clean component structure",
    "react": "build the component library and state management first",
    "stripe": "wire Stripe payments with webhooks and receipt emails",
    "node.js": "design the API layer with Node and proper validation",
    "python": "build the backend service in Python with typed models",
    "fastapi": "stand up a FastAPI service with typed endpoints",
    "postgresql": "model the database in PostgreSQL with migrations",
    "openai": "integrate the AI feature with streaming and graceful fallbacks",
    "typescript": "enforce typed contracts end-to-end with TypeScript",
}
FALLBACK_STEP = "break the scope into weekly milestones with a demo at the end of each one"


def _template_draft(job: dict, profile: Profile, matched: list[str]) -> str:
    top = matched[:3]
    steps = [SKILL_STEPS.get(s, FALLBACK_STEP) for s in top] or [FALLBACK_STEP]
    while len(steps) < 3:
        steps.append(FALLBACK_STEP)
    highlights = "\n".join(f"- {h}" for h in profile.highlights[:2])
    highlights = highlights or "- 5+ years shipping production software"
    hl = profile.headline or "Full-stack developer"
    budget_line = ""
    if job.get("hourly"):
        budget_line = f"Your ${job['hourly']:g}/hr budget works for me."
    elif job.get("budget_max"):
        budget_line = "Your budget range works for me."

    return (
        f"Hey there,\n\n"
        f"Saw your post for \"{job['title']}\" — this is squarely in my lane ({hl}).\n\n"
        f"A bit of proof:\n{highlights}\n\n"
        f"Here's how I'd tackle it:\n"
        f"1) {steps[0]}\n"
        f"2) {steps[1]}\n"
        f"3) {steps[2]}\n\n"
        f"{budget_line} I can start this week and will share a working demo every week "
        f"so you're never guessing where things stand.\n\n"
        f"Worth a quick chat?\n\n"
        f"— {profile.name}"
    )


def _llm_draft(job: dict, profile: Profile, llm: LLMConfig, matched: list[str]) -> str:
    system = (
        "You are a freelance proposal ghostwriter. You write in the exact voice of the "
        "freelancer, based on their tone samples. Rules: max 150 words, no fluff, no "
        "generic praise, open with something specific to the job post, include one or "
        "two proof bullets, a 3-step plan, and end with a question. Never invent "
        "experience the profile doesn't show."
    )
    tone = "\n---\n".join(profile.tone_samples[:3]) or "(no samples — keep it warm and direct)"
    user = (
        f"MY PROFILE\nName: {profile.name}\nHeadline: {profile.headline}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Highlights: {' | '.join(profile.highlights)}\n\n"
        f"MY TONE SAMPLES\n{tone}\n\n"
        f"JOB POST\nTitle: {job['title']}\nMatched skills: {', '.join(matched)}\n"
        f"Budget: hourly={job.get('hourly')} fixed={job.get('budget_min')}-{job.get('budget_max')}\n"
        f"Body: {job.get('body', '')[:1500]}\n\n"
        f"Write the proposal now."
    )
    r = requests.post(
        f"{llm.base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {llm.api_key}"},
        json={
            "model": llm.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "max_tokens": 350,
        },
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def draft_proposal(
    job: dict, profile: Profile, llm: LLMConfig, matched: list[str]
) -> tuple[str, str]:
    """Returns (draft, mode). Falls back to template on any LLM failure."""
    if llm.enabled and llm.api_key:
        try:
            return _llm_draft(job, profile, llm, matched), "llm"
        except Exception:
            pass
    return _template_draft(job, profile, matched), "template"


def _llm_improve(
    job: dict, profile: Profile, llm: LLMConfig, draft: str, matched: list[str]
) -> str:
    system = (
        "You are a freelance proposal editor. Rewrite the freelancer's draft so it "
        "earns the reply: a specific opener tied to the job post, one or two proof "
        "bullets, a concrete 3-step plan, and a closing question. Max 150 words. "
        "Keep the freelancer's voice and every factual claim already present — "
        "never invent experience, never flatter, never repeat the job post back."
    )
    tone = "\n---\n".join(profile.tone_samples[:3]) or "(no samples — keep it warm and direct)"
    user = (
        f"MY PROFILE\nName: {profile.name}\nHeadline: {profile.headline}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Highlights: {' | '.join(profile.highlights)}\n\n"
        f"MY TONE SAMPLES\n{tone}\n\n"
        f"JOB POST\nTitle: {job['title']}\nMatched skills: {', '.join(matched)}\n\n"
        f"CURRENT DRAFT\n{draft}\n\n"
        f"Rewrite it. Output only the improved proposal."
    )
    r = requests.post(
        f"{llm.base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {llm.api_key}"},
        json={
            "model": llm.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.6,
            "max_tokens": 400,
        },
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def improve_template(
    job: dict, profile: Profile, draft: str, matched: list[str]
) -> tuple[str, list[str]]:
    """Deterministic sharpening — zero-config, zero-network.

    Keeps every custom line the freelancer wrote; appends only the pieces a
    winning proposal usually misses: a closing question, a concrete plan,
    a budget acknowledgment. Returns (text, changes)."""
    text = (draft or "").strip()
    if not text:
        return _template_draft(job, profile, matched), [
            "empty draft — started a fresh template"
        ]
    changes: list[str] = []
    lowered = text.lower()
    if "?" not in text:
        text += "\n\nWorth a quick chat?"
        changes.append("added a closing question")
    if not any(w in lowered for w in ("week", "milestone", "step", "plan", "start", "demo")):
        steps = [SKILL_STEPS.get(s, FALLBACK_STEP) for s in matched[:2]] or [FALLBACK_STEP]
        plan = "\n".join(f"{i}) {s}" for i, s in enumerate(steps, 1))
        text += f"\n\nQuick plan:\n{plan}"
        changes.append("added a concrete plan")
    if (
        not any(w in lowered for w in ("budget", "$", "rate", "/hr", "fixed"))
        and (job.get("hourly") or job.get("budget_max") or job.get("budget_min"))
    ):
        text += "\n\nYour budget works for me."
        changes.append("acknowledged the budget")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, changes


def improve_draft(
    job: dict, profile: Profile, llm: LLMConfig, draft: str, matched: list[str]
) -> tuple[str, str, list[str]]:
    """One-click rewrite of an existing draft.

    LLM mode rewrites in your voice; template mode sharpens deterministically.
    Never raises: any LLM failure falls back to the template pass.
    Returns (text, mode, changes)."""
    if llm.enabled and llm.api_key:
        try:
            return _llm_improve(job, profile, llm, draft, matched), "llm", [
                "rewritten in your voice"
            ]
        except Exception:
            pass
    text, changes = improve_template(job, profile, draft, matched)
    return text, "template", changes
