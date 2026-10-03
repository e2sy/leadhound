# Contributing to leadhound

Thanks for hunting with us. This project lives or dies by the quality of its
watchers and the honesty of its scorer — both are great first-contribution
targets. This doc gets you from clone to merged PR.

## Dev setup

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/leadhound && cd leadhound
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install pytest ruff                              # test + lint toolchain
```

Run the offline demo first — it injects sample gigs (including two red-flag
traps) so you can see the whole pipeline without touching any network:

```bash
leadhound demo && leadhound queue --list
```

## Ground rules

1. **ToS-safe by design.** Watchers may only read *public* feeds/APIs with a
   polite user-agent and human-rate polling. No logins, no headless-browser
   scraping of logged-in pages, no auto-sending anything on any platform.
   A PR that violates this gets closed, no matter how clean the code is.
2. **The user always fires the final shot.** Nothing in the pipeline may
   submit, bid, or send without explicit human approval.
3. **Local-first.** No telemetry, no accounts, no cloud dependencies for
   core features. Optional integrations (LLM, Telegram) are opt-in.
4. **Every scorer change ships with tests.** The score *is* the product.

## Adding a watcher

Watchers are pluggable connectors in `leadhound/watchers/`. A watcher returns
a list of job dicts with at minimum: `guid`, `source`, `title`, `url`, `body`,
`tags` (list), and optionally `budget_min` / `budget_max` / `hourly` /
`posted_at`. Look at `watchers/rss.py` for the shape, then:

1. Create `leadhound/watchers/mysource.py` with a `fetch() -> list[dict]`.
2. Register it in the watcher registry (see `watchers/__init__.py`).
3. Add the source name to the docs in `README.md` and `config.toml` template.
4. Add a test that feeds a saved **fixture** of the feed through your watcher
   (never hit the live API in tests).

## Running tests and lint

```bash
pytest            # unit tests, fully offline
ruff check .      # lint
```

CI runs the same two commands on Python 3.11 / 3.12 / 3.13 — please make them
green before requesting review.

## Commit style

Short imperative subject (`scorer: punish vague budgets harder`), details in
the body. Reference issues with `#123` when relevant.

## Reporting bugs

Open a GitHub issue using the bug report template. Redact anything personal —
do **not** paste your `profile.toml` or Telegram token into an issue.
