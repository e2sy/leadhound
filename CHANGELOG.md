# Changelog

All notable changes to leadhound are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [1.3.0] - 2026-10-06

The wide-net release. Three more sources joined the hunt, and the same gig stopped wearing five hats.

### Added
- **👽 Reddit connector** — [Hiring] posts from freelance subreddits (r/forhire, r/hiring, r/jobbit — editable list, max 5) via Reddit's public JSON with an honest descriptive User-Agent and a polite 5-minute floor. [For Hire] posts (other freelancers advertising) are skipped by design. Per-sub source tagging teaches the funnel which niche replies.
- **🌐 Guru.com + PeoplePerHour connectors** — their public job RSS feeds through shared board-RSS plumbing. Honesty rule front and center: when bot protection serves an HTML wall instead of XML, the radar reports exactly that ("blocked this server's IP — self-hosting from a residential machine usually fixes it") instead of going quiet.
- **⧉ Cross-source dedup** — fingerprint = normalized title × money bucket, hashed. A second sighting on another board bumps `seen_count` and remembers the board (`also_on`) instead of inserting a clone or re-notifying your pocket. GUID refetches never count as sightings; account scoping respected; the board shows a ⧉ chip when a gig is a confirmed multi-board listing.

## [1.2.0] - 2026-10-06

The closer's copilot release. The chase stopped being manual: quiet threads get one honest nudge (human-gated), interviews get a prepared kit instead of hope, and the money finally has a ledger.

### Added
- **🔁 Follow-up bumps** — every fired shot auto-schedules a +3-day bump; one click generates the 3-sentence text (deterministic, never invents claims) and copies it for you to paste in the thread. Any verdict cancels the chase. `GET/POST /api/followups`, `POST /api/followups/{id}/fire|cancel`, a bump line on sent cards, and `/followups` in the pocket.
- **🎤 Interview kit** — when a gig reaches the interview stage: the gaps in the post become your questions, the money frame anchors above your floor with a walk-away line, talking points tie matched skills to YOUR highlights, and matched red flags become named red lines. Cached per gig, regenerable. `GET/POST /api/jobs/{id}/kit`, the 🎤 button on sent cards, `/kit <id>` in the pocket.
- **💼 Money ledger** — record what YOU quoted per gig; every win and every in-play gig then values at your quote (posted budget as the honest fallback). In-play pipeline, banked total, average win, monthly bars. `POST /api/jobs/{id}/quote`, `GET /api/money`, a 💼 chip + quote setter on sent cards, a money panel on the stats tab, `/money` in the pocket.

## [1.1.0] - 2026-10-06

The learner release. The scope stopped guessing: it now nudges scores from your real wins and losses, names lowballs before you waste a proposal on them, hands you a six-line pre-flight read before you approve, and orders the queue by urgency instead of raw fit.

### Added
- **🧠 Win-memory** — every `won`/`lost` outcome snapshots the gig's shape; new gigs that fuzz-match a memory (rapidfuzz, difflib fallback) get a capped nudge of ±10 points — wins lean in, losses warn. Your battle record now feeds the scope. `breakdown.memory` exposes points + notes.
- **🛡 Price guard** — €/£ quotes normalize to USD (rough public rates, stated as such) so floors compare fairly across sources; half-your-floor lowballs take an extra −5 and get named in the note; too-shiny rates (>$300/hr) warn instead of celebrate; every money read carries a confidence (`structured > regex > silence`) in `breakdown.budget.confidence`.
- **✅ Qualification checklist** — one tap on any pending/approved card (or `GET /api/jobs/{id}/checklist`): six honest lines — stack fit, budget reality, client signals, red flags, freshness — each yes / no / **unknown**. A missing budget is not a pass.
- **⌖ Queue ranking v2** — rank = score × freshness × source trust. Freshness decays in honest tiers (1h/6h/24h/72h); source trust is your own funnel reply-rate per source (neutral until 5 shots on record); late catch-up gigs get a freshness floor because you just saw them. `/api/queue` returns the ranked queue, pending cards carry a ⌖ rank chip, and the pending column orders by it. A 95-pointer from four days ago finally loses to an 80-pointer from ten minutes ago.

## [1.0.0] - 2026-10-06

The machine gun release. Detection latency collapsed from minutes to seconds (Freelancer webhooks), downtime stopped costing gigs (catch-up sweeps), dead threads stopped pretending to be alive (radar heartbeat + watchdog), and the cheap feeds learned to poll twice a minute without being rude (conditional GET + jitter). This is what "working" was supposed to mean.

### Added
- **📡 Freelancer webhook receiver** — `POST /webhook/freelancer` verifies the HMAC-SHA256 signature against the raw body (constant-time, every common signature header name, `sha256=` prefix tolerated) and flows the project straight into the shared ingest path: scored, drafted, pushed per user. Detection latency: seconds, not the next poll. Secrets live on the Freelancer source card (masked), one-click rotation via `POST /api/webhook/freelancer/rotate` (old secret dies instantly, new one shown exactly once), and the accounts hub gains the 📡 instant webhook card with live event counters. Honest door: 401 bad signature, 503 unarmed, 202 nothing to hunt, guid dedupe so webhook + poll never double-push.
- **⏰ Downtime catch-up** — at boot, if the newest connector `last_run` is over an hour old, the poller's first sweep runs as a catch-up sweep: every new gig posted during the blackout lands flagged `late=1` (amber ⏰ late chip on the board), with timezone-aware posted-vs-reboot comparison and no re-flagging on re-ingest.
- **💓 Radar heartbeat** — the poller records a heartbeat after every sweep (`last_tick`, `sweeps`, `started_at`); sweep crashes are recorded instead of killing the thread; `thread_alive` checks the actual thread, and `stalled` fires when no heartbeat arrives for 3× the interval. `/api/health` went from `{ok, version}` to real vitals (db, uptime, poller, listeners — aggregate only, nothing per-user).
- **🐕 Watchdog supervisor** — a minute-beat supervisor relaunches a dead poller thread with exponential backoff (1s doubling, 15-min cap), respawns dead pocket bots from the db's own arm-state, never resurrects anything during shutdown, and reports every restart in the vitals' `watchdog` block.
- **🤫 /ping heartbeat board** — one command answers all of ops: ✅ healthy source with cadence + last sweep age, 🟡 overdue (tick older than 2× cadence) or never swept, ❌ erroring with the reason inline, the radar thread's own pulse, and the webhook's armed state with rejected-signature warnings.
- **⚡ Polite fast lane** — RemoteOK, Remotive, WeWorkRemotely, Hacker News and custom RSS poll on a 2-minute floor (was 5), paying their way with ETag/Last-Modified conditional GET (a 304 costs nothing). `Connector.min_poll` is the per-source politeness truth — keys, cookies and search APIs keep their 5-minute floor — and every sweep re-rolls ±20% jitter so a fleet of self-hosted hounds never stamps a source at the same second. The cadence endpoint clamps through the same floor function.

## [0.9.1] - 2026-10-06

The routine release. v0.9.0 put the sniper in your pocket; v0.9.1 makes the daily grind disappear — the board adapts to daylight, installs to a phone home screen, rewrites your proposals, arms a whole niche in one click, and self-hosts in one container.

### Added
- **🌓 Dark/light theme** — the console adapts to daylight. Light palette via CSS variables, moon/sun button in the header, choice persists in localStorage, no flash on reload.
- **📲 Installable pocket console (PWA)** — `manifest.webmanifest` + a shell-caching service worker + a sniper-scope SVG icon. `/api/*` live data is never cached; navigation is network-first so updates land on the next reload. The dashboard now installs to a phone home screen — pairs with the Telegram pocket sniper.
- **⚡ Auto-snipe rules** — arm a rule (min score 60–99, optional keywords/source/budget caps) and any fresh gig that clears it lands straight in **Approved** with an ⚡ auto badge and the rule name in the audit trail. The guardrail stays honest: **rules auto-approve, they never auto-bid** — firing stays behind a human click on the board or `/snipe` in the pocket. Refetching never re-arms a gig you demoted. `GET/POST /api/rules`, `DELETE /api/rules/{id}`, `POST /api/rules/{id}/enabled`; the accounts hub grows a rules card.
- **✨ Improve-draft** — one-click rewrite of the proposal being edited. LLM mode rewrites in your voice (your tone samples attached, never invents experience); template mode sharpens deterministically with zero config — adds the missing closing question, concrete plan and budget ack, keeps every custom line. LLM failures fall back silently. `POST /api/jobs/{id}/improve`.
- **📦 Starter packs** — six verified packs (💻 dev, 🎨 design, 📣 marketing, 🎧 support, 🧭 product, 🐺 freelance firehose): one click switches the right sources on **and** points each at its feed channel (WeWorkRemotely category feeds, Remotive categories — every slug verified live before landing). Existing queries/cookies/keys are kept. `GET /api/presets`, `POST /api/presets/{key}/apply`.
- **🤖 Pocket bot `/digest` + `/ping`** — `/digest`: pending/approved/sniped counts, reply + win rates, and the three best pending gigs with ids; `/ping`: liveness, armed sources, last sweep time. Composed by pure functions — zero db, zero network in the formatter.
- **💾 Saved views** — the filter bar gains a source picker, a score bar and named views (localStorage, max 8): one click back to "hot react gigs ≥ 80".
- **🐳 One-container self-host** — `Dockerfile` + `compose.yml`: `docker compose up` and you're hunting. Everything lives under `LEADHOUND_HOME=/data`, so the container is disposable and your gig history is not; first boot auto-inits (idempotent).
- **🩺 Update checker in doctor** — compares your version against the latest GitHub release; a newer version is a yellow warning with the upgrade hint, never a hard fail, and `--offline` skips it.

### Changed
- 40+ new tests (rules matcher + pipeline hook + API, improve paths, pack registry + channels, bot digest/ping, doctor update check — all network-free); 350+ total.

## [0.9.0] - 2026-10-06

The pocket sniper release. The board lives on your phone now — gigs land in Telegram the moment the radar spots them, and you can run the whole queue from your chat.

### Added
- **📱 Two-way Telegram bot** — arm the listener in the accounts tab and your chat becomes a cockpit: `/queue [n]` (best pending gigs), `/gig <id>` (full card + draft), `/approve <id>`, **`/snipe <id> [amount]`** (arms a real Freelancer.com bid — shows the plan, waits for the inline 🔥 Fire tap; the confirm state is memory-only with a 5-minute TTL, so a restart can never leave a half-armed bid), `/stats`. Every handler is **chat-gated**: a stray command from any other chat gets silence, never your board. Sends are serialized at ~1/s per chat and 429s honor `retry_after`.
- **🎧 Listener lifecycle** — one long-poll bot per account (cap 8), restart-clean (re-arming never double-polls a token), auto-armed on server boot for accounts that left it on, disarmed on shutdown. `POST /api/notify/telegram/listen`.
- **⚠️ Honest failure alerts** — when a source breaks (expired Fiverr cookie, dead token), the bot messages you **once per new failure** — repeated errors stay silent, so the pocket never becomes a boy who cried wolf.
- **🎚️ Per-source radar cadence** — each connector polls on its own `poll_minutes` (clamped 5–120, global interval remains the fallback). `POST /api/notify/cadence`; `GET /api/radar` reports live cadence + push + listener state.
- **📱 Telegram settings in the dashboard** — the accounts hub grows a pocket-sniper card: token (masked, never echoed back), chat id, push score bar, **send test message** that surfaces Telegram's own verdict verbatim, and the arm/disarm listener toggle.
- **🔐 Per-user notify settings** — a `notify_settings` table (token, chat id, push toggle, listener toggle, push score bar) replaces the global config file for Telegram. Pre-0.9 users are migrated silently: the first read seeds from `[telegram]` in `config.toml`.

### Changed
- The ingest pipeline pushes through **each account's own bot with their own score bar** — account A's gigs can never buzz account B's pocket, and `push_min_score` keeps the pocket quiet until a gig is worth the buzz (0 = old board-threshold behavior).
- 30 new tests (command parser, confirm TTL, chat gating, per-user isolation, listener lifecycle, alert-once discipline — all network-free); 316 total.

## [0.8.0] - 2026-10-05

The closer's release. Sniping was v0.7.0; v0.8.0 teaches the sniper to **count kills** — and to learn which ammo wins.

### Added
- **📊 Stats tab — the sniper's scoreboard**: six funnel cards (shots fired, reply rate, win rate, won value, in-play value, interviews), **per-source conversion bars** (which source actually converts), **live-fire vs kit** split, and the calibration chips. Backed by a new account-scoped `GET /api/stats`.
- **🎤 Interview outcome** — the funnel is now sent → replied → **interview** → won/lost. Interviews count as replies everywhere (stats, chips, calibration hints).
- **⚔ Proposal A/B testing** — every draft editor has A/B tabs ("⚔ add B" clones your draft), the snipe dialog gains a version picker, and the fired variant is recorded on the job (`kit · B` / `live-fire · B` badges). The scoreboard grows a **proposal duel** panel with a verdict line once both sides have shots. `GET/POST /api/jobs/{id}/variants` + per-variant stats.
- **⌨ Keyboard cockpit** — `j`/`k` aim through the board with wrap-around, `a` approve, `x`/`r` reject, `s` snipe, `o` open gig, `c` copy proposal, `d` edit draft; acting auto-aims the next gig, `?` shows the shortcut card. Keys pause while you type.
- **📧 Email notifications** — plain-STMTP gig cards (score, money, matched skills, red flags, gig link + draft) via the new `[email]` config section; stdlib only, works with Gmail app passwords, Fastmail, or your own server. `leadhound doctor` checks the credentials.
- **🔔 Browser alerts** — optional bell toggle: new gigs raise a native browser notification (top score + title) while the dashboard is open; click it to jump to the board.

### Changed
- `db.stats()` and `db.calibration()` are now **account-scoped** like the rest of the dashboard — accounts no longer see each other's counts.
- `leadhound stats` (CLI) prints a sniper line with reply/win rates.
- 59 new tests (funnel math, A/B attribution, SMTP fakes, scoping); 265 total.

## [0.7.0] - 2026-10-04

The sniper release. The loop is closed: leadhound doesn't just find and draft — it fires, with YOUR account, and tracks every shot.

### Added
- **🎯 Snipe mode** — every pending/approved gig card has a snipe button with a fire dialog:
  - **🔥 live-fire** (Freelancer.com, linked account): a **real bid is placed on Freelancer.com** through the official API with your own token — editable bid amount + delivery period, bid id recorded, toast confirms the shot. User-triggered only; nothing bids in the background.
  - **🎯 snipe kit** (every other source): the proposal lands in an editable textarea, one click copies it and opens the gig page in your own logged-in session, and an honest confirm step records the send. No fake buttons.
- **Freelancer.com account link** — a new card in the accounts hub: official OAuth2 (create a free dev app, paste keys, 🔗 connect), the same auto-refreshing token treatment as Upwork. Shows `linked as @username` once connected.
- **Snipe audit trail** — jobs record `sniped_at`, the method (`freelancer-api` bid id / `kit` confirmation) and a note; the board's Sniped column shows badges with tooltips.
- **Sniper stats** — chips for sniped-in-7d and reply rate; `GET /api/state` carries `snipe` + `linked`; learning loop stays: mark replied/won/lost to calibrate.
- **New API**: `GET /api/jobs/{id}/snipe-plan`, `POST /api/jobs/{id}/snipe`, `POST /api/jobs/{id}/snipe-confirm`, plus the Freelancer.com OAuth `auth/start` + `callback` flow.

### Changed
- The board's "Sent" column is now **🔥 Sniped** — fired shots with receipts, not manual bookkeeping.
- Hero checklist step 3 is "snipe with your account" — the app now leads all the way to the trigger.

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
