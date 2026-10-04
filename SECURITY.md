# Security Policy

leadhound is a **local-first** tool: it runs on your machine, stores everything in
`~/.leadhound`, and ships no telemetry. This document explains what is in scope,
how to report issues, and what we promise.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅        |
| < 0.3   | ❌ upgrade |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting:
**[Security → Report a vulnerability](https://github.com/e2sy/leadhound/security/advisories/new)**

You'll get a response within **7 days**, a fix timeline for accepted reports, and
credit in the release notes (unless you prefer to stay anonymous).

## Scope

### In scope
- Anything that makes the local server (`leadhound web`) reachable beyond the
  configured bind address, or execute/serve unexpected content
- Path traversal or injection via gig titles/bodies coming from public job feeds
  (they are attacker-influenced data — treat them as hostile)
- Secrets (API keys, bot tokens) written to disk with wrong permissions, or
  leaking into logs / exports / error messages
- Command injection or unsafe deserialization anywhere in the package

### Out of scope
- The job boards themselves (report to the board's operators)
- "I can read my own database" — it's your machine
- ToS questions about automated polling: that's a policy topic, covered in
  [CONTRIBUTING.md](CONTRIBUTING.md) and the README's ToS section, not a
  security vulnerability — but if a watcher break *allows* abuse (e.g. bypassing
  rate limits we claim to respect), tell us

## Design commitments we defend

- `leadhound web` binds to `127.0.0.1` by default; `--host 0.0.0.0` is an
  explicit opt-in and the UI must never gain write access to your filesystem
- No auto-send, ever: proposals leave your machine only when *you* approve them
- Config files under `~/.leadhound` must stay `600` on POSIX systems
- External requests go only to the public feed endpoints the user configured

## Data handling

Everything lives in `~/.leadhound/` (override with `LEADHOUND_HOME`):
`config.toml`, `profile.toml`, `data/leadhound.db`. Deleting the directory is a
complete uninstall. The optional LLM mode sends gig text + your profile to the
endpoint *you* configure; nothing else is transmitted anywhere.
