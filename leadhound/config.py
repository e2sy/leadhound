"""Config + profile management. Everything lives in ~/.leadhound (override with LEADHOUND_HOME)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SOURCES = ["weworkremotely", "remoteok", "remotive"]

CONFIG_TOML = """\
# leadhound configuration
[watch]
# Minimum fit score (0-100) required before a gig reaches your queue
min_score = 60
# Minutes between polls
interval_minutes = 15
# Active sources (watchers).
# Available: weworkremotely, remoteok, remotive, hackernews
sources = ["weworkremotely", "remoteok", "remotive"]

[llm]
# Optional: OpenAI-compatible endpoint for smarter proposal drafts.
# Works with OpenAI, Groq, OpenRouter, or a local Ollama (base_url = "http://localhost:11434/v1")
enabled = false
base_url = "https://api.openai.com/v1"
api_key = ""
model = "gpt-4o-mini"

[telegram]
# Optional: approval queue in your pocket.
# 1) Talk to @BotFather -> /newbot -> copy the token
# 2) Send any message to your bot, then open:
#    https://api.telegram.org/bot<TOKEN>/getUpdates  -> copy chat.id
enabled = false
bot_token = ""
chat_id = ""

[webhooks]
# Optional: push gig cards straight into your Discord server or Slack.
# Discord: Server Settings -> Integrations -> Webhooks -> New Webhook -> copy URL
# Slack:   api.slack.com/messaging/webhooks -> create an incoming webhook
# Leave empty to disable. Both can be active at once.
discord_webhook_url = ""
slack_webhook_url = ""
"""

PROFILE_TOML = """\
# Your sniper profile — the more honest this file, the sharper the scores.
name = "Your Name"
headline = "Full-stack dev — React Native, Next.js, Stripe"

# Skills the scorer hunts for in job posts (lowercase). Order = priority.
skills = [
  "react native", "next.js", "react", "stripe", "node.js",
  "python", "fastapi", "postgresql", "openai", "typescript",
]

# Earnings floor — gigs below this get scored down hard.
min_hourly = 30          # USD/hour for hourly gigs
min_fixed_budget = 800   # USD for fixed-price gigs

# Instant red flags — each match costs the gig 15 points.
red_flags = ["unpaid", "for exposure", "equity only", "revenue share only", "free work"]

# Proof bullets injected into every proposal draft.
highlights = [
  "Shipped 12 production apps with React Native + Stripe",
  "3 years of Next.js, 2 with App Router and live Stripe payments",
]

# 1-3 samples of YOUR past winning proposals — the voice engine copies your tone.
tone_samples = [
  '''
  Hey — I built something very similar last quarter (offline-first RN app, 40k users).
  Here's how I'd approach yours: 1) auth + payments in week one, 2) weekly demo builds,
  3) launch with analytics. I can start Monday — worth a quick chat?
  ''',
]
"""


@dataclass
class Profile:
    name: str = "Your Name"
    headline: str = ""
    skills: list[str] = field(default_factory=list)
    min_hourly: float = 30.0
    min_fixed_budget: float = 800.0
    red_flags: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    tone_samples: list[str] = field(default_factory=list)


@dataclass
class LLMConfig:
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class WebhookConfig:
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""


@dataclass
class WatchConfig:
    min_score: int = 60
    interval_minutes: int = 15
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))


def home() -> Path:
    return Path(os.environ.get("LEADHOUND_HOME", str(Path.home() / ".leadhound")))


def config_path() -> Path:
    return home() / "config.toml"


def profile_path() -> Path:
    return home() / "profile.toml"


def db_path() -> Path:
    return home() / "data" / "leadhound.db"


def is_initialized() -> bool:
    return config_path().exists() and profile_path().exists()


def init_files() -> None:
    """Create ~/.leadhound with default config, profile and database."""
    from .db import ensure_db

    h = home()
    (h / "data").mkdir(parents=True, exist_ok=True)
    if not config_path().exists():
        config_path().write_text(CONFIG_TOML)
    if not profile_path().exists():
        profile_path().write_text(PROFILE_TOML)
    ensure_db()


def load_config() -> tuple[WatchConfig, LLMConfig, TelegramConfig, WebhookConfig]:
    raw = tomllib.loads(config_path().read_text())
    w = raw.get("watch", {})
    ll = raw.get("llm", {})
    t = raw.get("telegram", {})
    wb = raw.get("webhooks", {})
    return (
        WatchConfig(
            min_score=int(w.get("min_score", 60)),
            interval_minutes=int(w.get("interval_minutes", 15)),
            sources=list(w.get("sources", DEFAULT_SOURCES)),
        ),
        LLMConfig(
            enabled=bool(ll.get("enabled", False)),
            base_url=str(ll.get("base_url", "https://api.openai.com/v1")),
            api_key=str(ll.get("api_key", "")),
            model=str(ll.get("model", "gpt-4o-mini")),
        ),
        TelegramConfig(
            enabled=bool(t.get("enabled", False)),
            bot_token=str(t.get("bot_token", "")),
            chat_id=str(t.get("chat_id", "")),
        ),
        WebhookConfig(
            discord_webhook_url=str(wb.get("discord_webhook_url", "")),
            slack_webhook_url=str(wb.get("slack_webhook_url", "")),
        ),
    )


def load_profile() -> Profile:
    raw = tomllib.loads(profile_path().read_text())
    return Profile(
        name=str(raw.get("name", "Your Name")),
        headline=str(raw.get("headline", "")),
        skills=[str(s).lower() for s in raw.get("skills", [])],
        min_hourly=float(raw.get("min_hourly", 30)),
        min_fixed_budget=float(raw.get("min_fixed_budget", 800)),
        red_flags=[str(r).lower() for r in raw.get("red_flags", [])],
        highlights=[str(h) for h in raw.get("highlights", [])],
        tone_samples=[str(t) for t in raw.get("tone_samples", [])],
    )
