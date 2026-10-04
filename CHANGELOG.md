# Changelog

All notable changes to leadhound are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.3.0] - 2026-10-04

The dashboard release. leadhound gets a face — and a memory of what you're good at.

### Added
- **`leadhound web` — local pipeline dashboard.** A dark, kanban-style board of your whole gig pipeline in the browser: four columns (pending / approved / sent / rejected), score rings, matched-skill chips, red-flag chips, client-intel lines, one-click status moves, inline draft editor with save + copy, outcome select, live search, auto-refresh. Zero new dependencies: a stdlib HTTP server serves an embedded single-page app, fully offline. Binds to 127.0.0.1 by default; `--host 0.0.0.0` drives it from your phone on the same Wi-Fi.
- **`leadhound profile learn <user-or-url>` — GitHub recon.** Scans a public GitHub profile via the unauthenticated API (ToS-safe, same stance as the watchers), ranks languages by repo count, picks up topics, maps them to job-post skill tokens (`Go`→`golang`, `Vue`→`vue.js`, topic `react-native`→`react native`; noise like HTML/CSS/Jupyter dropped, forks skipped). Your own skills keep priority; detected ones are appended, capped at 16. Surgical `profile.toml` edit — comments and settings preserved. `--dry-run` previews; 403/404 handled with hints.
- **`leadhound export --format csv|json`** — the whole pipeline (or any status/min-score slice) as clean rows: flat CSV for spreadsheets (semicolon-joined multi-values), JSON with body + draft for scripts and CRMs. `--out FILE` writes to disk.
- **Victory banner + pipeline value.** `leadhound mark <id> won` now prints a screenshot-worthy wolf banner with the gig's title, value and source. `leadhound stats` tracks money: in-play value (approved+sent, no outcome yet) and won value, fixed-price only.

### Changed
- `db.stats()` now reports `inplay_n`, `inplay_value`, `won_n`, `won_value`.
- New db helpers: `all_jobs`, `set_draft`, `clear_outcome`.

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
