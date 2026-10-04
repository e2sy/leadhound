## What does this PR change?

<!-- One or two sentences: what problem, what behavior changes. -->

## How was it tested?

- [ ] `pytest` passes locally (fully offline tests)
- [ ] `ruff check .` is clean
- [ ] `leadhound demo && leadhound queue --list` still works end-to-end

## ToS-safe checklist (hard requirement)

- [ ] Only reads **public** feeds / APIs, with a polite user-agent
- [ ] Polls at human-rate intervals (no hammering)
- [ ] Never submits, bids, or sends anything without explicit human approval
- [ ] No logins / cookies / headless scraping of logged-in pages

## Screenshot / terminal capture

<!-- Paste the relevant CLI output. Big diffs for scorer logic? Include before/after scores for the demo gigs. -->
