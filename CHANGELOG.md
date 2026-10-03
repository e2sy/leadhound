# Changelog

All notable changes to leadhound are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.2.0] - 2026-10-04

The scope learns, the pack grows. This release turns leadhound from a demo
into a daily-habit tool.

### Added
- **`leadhound doctor`** — pre-flight checks for profile, config, feeds, database, Telegram/LLM/webhook credentials; `--offline` mode included. Exit code 1 only on hard failures; advisory items warn.
- **Discord + Slack webhooks** — gig cards land in your server the moment the watcher sees them. `[webhooks]` in config.toml; `leadhound webhooks` pushes pending cards on demand.
- **`leadhound digest`** — the one-screen morning briefing: best gigs of the last 24h, score-ranked, with money, flags and links.
- **Hacker News watcher** — the monthly "Freelancer? Seeking freelancer?" thread via HN's public Algolia API. Demand-side posts only (`SEEKING WORK` ads are skipped). Opt-in: add `hackernews` to sources.
- **Learning loop** — `leadhound mark <id> replied|won|lost` + calibration stats: winners vs losers by average score, with hints (trust the ranking / tighten red flags / lower min_score). v0.1.0 databases migrate in place.
- **Client intel** — poster identity (email/URL domain) cross-referenced against your own history; repeat lowballers flagged in the queue before you write a word.
- **Native binaries** — Windows `.exe`, macOS (arm64) and Linux one-file builds, automatically attached to every release by CI (`binaries.yml`).

### Fixed
- Binaries: dedicated `entry.py` with absolute imports (PyInstaller broke package-relative `__main__.py`).
- HN watcher: strict thread matching (was hijacked by unrelated "freelancer" stories).
- Circular import between watchers when registering the HN source.

## [0.1.0] - 2025-01-15

First public release. The sniper ships with a complete kill chain:

### Added
- **Watchers** — ToS-friendly connectors for WeWorkRemotely (RSS), RemoteOK (public API) and Remotive (public API), with polite user-agent and human-rate polling (`leadhound watch`, `--loop`, `--min-score`, `--sources`).
- **Parser** — regex signal extraction from raw job text: money (hourly / fixed / ranges), client-quality signals (payment verified, past hires, top-rated), red flags, skill matching.
- **Scorer** — 0-100 fit score against your profile: `skills 0-60 · budget 0-25 · client quality 0-15 · red flags -15 each`, with a human-readable "why this score" breakdown for every gig.
- **Voice engine** — zero-config template drafts, or plug any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, local Ollama) to ghostwrite in your tone using your past winning proposals.
- **Approval queue** — rich CLI review flow (`leadhound queue`) with approve/reject; you always fire the final shot.
- **Telegram notifications** — gig cards + drafts pushed to your phone (`leadhound telegram`), 2-minute BotFather setup.
- **Demo mode** — `leadhound demo` injects sample gigs (including red-flag traps) so the full pipeline can be shown offline in 60 seconds.
- **Local-first storage** — SQLite database under `~/.leadhound/data/`; your gig history never leaves your machine.
- Unit test suite and GitHub Actions CI (ruff + pytest on Python 3.11-3.13).
