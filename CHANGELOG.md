# Changelog

All notable changes to leadhound are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [0.6.0] - 2026-10-04

The real-accounts release. The dashboard now leads with connecting your job sites — the sample data takes a back seat.

### Added
- **Accounts hub**: a full-page connections view (board/accounts tabs) — one card per job site with an honest state badge (connected / error / on-not-tested / setup needed / off), last-sweep line with the real error text, inline settings, and per-source `save & test` probing.
- **Setup wizards**: Upwork (free dev-app steps, copyable redirect URI, one-click OAuth connect) and Fiverr (cookie-extraction steps with an honest beta warning).
- **Radar visibility**: `GET /api/radar` exposes the poller's real state — running, sweep interval, armed sources — and the accounts page shows it as a heartbeat.
- **First-run connect checklist**: the empty board is now a 3-step list (connect a source → fetch real gigs → approve & send) that ticks itself green as you go.
- Fetch-all now reports per source with friendly labels ("Freelancer.com +23 · RemoteOK +0").

### Changed
- The sources drawer is gone — replaced by the accounts hub.
- **Demo demoted**: the 🎲 sample-gigs button left the hero; it's a small "just exploring?" link now. The app opens pointing at real hunting, not sample data.

## [0.5.0] - 2026-10-04

The real-backend release. No more demo-by-default: log in, connect the job sites you actually want, and fetch live gigs.

### Added
- **Login system.** Register/log in from the dashboard. scrypt-hashed passwords, 256-bit session tokens (only token hashes are stored), HttpOnly SameSite=Lax cookies. Accounts live in your local SQLite — no cloud, no telemetry.
- **FastAPI backend.** The dashboard is now served by a real REST API (`/api/auth/*`, `/api/state`, `/api/connectors/*`, `/api/fetch`, `/api/health`) with an interactive OpenAPI schema at `/docs`. The stdlib HTTP server is retired.
- **Source connectors (8).** New `leadhound/connectors/` registry:
  - **Freelancer.com** — live search over their public API with real budgets, zero setup.
  - **Upwork** — official OAuth2 (authorization-code + auto refresh): paste your dev-app keys, hit 🔗 connect, leadhound stores the refresh token locally and rotates access tokens on every poll.
  - **Fiverr (beta)** — buyer requests via your own session cookie; honest failure modes when Fiverr changes their layout instead of fake data.
  - **Custom RSS/Atom** — point it at any job feed (niche boards, Upwork/Fiverr mirrors).
  - RemoteOK, Remotive, WeWorkRemotely, Hacker News — the original public sources, now behind the same interface.
- **Background radar.** While the app runs, enabled connectors re-poll every `interval_minutes` (politeness floor: 5 min), ingest, score, draft and notify — per account.
- **Sources drawer UI.** The ⚙ panel lists every connector with kind chips (no setup / API keys / cookie / feed), per-source settings (secrets masked `•••`), last-run status, "⚡ run now" buttons and the Upwork connect flow.
- **Account-scoped data.** Jobs, connector configs and settings are per-account; CLI-fetched gigs stay in a shared local pool. The schema (users, sessions, connector_config) is shaped for the later hosted-SaaS mode.
- **Dashboard onboarding.** An empty board now offers "⚡ fetch gigs now", "⚙ connect sources" and an explicit "🎲 load sample gigs" — demo data is a choice, never a surprise.

### Changed
- **First run is honest.** The double-click launch no longer seeds demo gigs automatically; the board starts empty and onboards you into real fetching.
- `leadhound web` runs on uvicorn; the PyInstaller builds ship the extra uvicorn hidden imports and the CI launch test now exercises register → demo → authed state on all three OSes.
- CLI, dashboard "fetch" and the background radar share one ingest pipeline (`leadhound/pipeline.py`) — score → draft → store → notify behaves identically everywhere.
- Tests: 176 (from 125) — auth, connectors, API round-trips, pipeline, launcher; ruff clean.

## [0.4.0] - 2026-10-04

The double-click release. The binary is now the app.

### Added
- **🖱️ Double-click = the dashboard.** Launching the binary with no arguments no longer shows a terminal guide — it runs the whole setup for you: creates `~/.leadhound` if missing, seeds 4 demo gigs on first run so the board is never empty, starts the dashboard (auto-picks a free port from 7800), and opens your browser. Close the console (or Ctrl+C) to stop. The terminal guide remains as a fallback only if the dashboard itself fails to start.
- **🎲 Demo mode banner.** When every gig in the database is demo data, the dashboard says so and points to `leadhound watch` to go live — no more "is this real?" confusion.
- **Launch tests.** CI now starts each release binary with no arguments on real Windows / macOS / Linux runners and asserts the dashboard comes up seeded with demo data (`LAUNCH OK`).

### Changed
- `cli._process` gained a `quiet` flag (used by the first-run seeding).
- `build_state()` now includes a `demo` boolean.

## [0.3.1] - 2026-10-04

The "it doesn't vanish anymore" release. Fixes the frozen exe flashing away on double-click.

### Fixed
- **Double-click welcome.** Launching the binary with no arguments used to print an argparse error and close the console before anyone could read it. It now shows a welcome screen with the exact commands to run, and waits for Enter.
- **Crash catcher.** Any unexpected error now prints a full traceback plus an issue link and holds the window open (frozen builds only) — no more invisible crashes.
- **UTF-8 console.** stdout/stderr are reconfigured to UTF-8 in frozen builds, so rich tables, emoji and pipes/redirects on Windows (cp1252) can no longer raise `UnicodeEncodeError`.
- **Real smoke tests.** The Binaries workflow now *executes* each binary on real Windows, macOS and Linux runners before attaching it to a release: `init → doctor --offline → demo → queue --list → show → mark → stats → export → digest`. A broken exe can no longer ship.

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
