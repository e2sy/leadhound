# 🚀 Taking leadhound to GitHub — the 5-minute launch

The repo is release-ready: CI, tests, templates, changelog, badges, tag.
This guide gets it online **with a description and topics attached**, then
polishes the storefront.

---

## Option A — one command (GitHub CLI, recommended)

```bash
# once: install gh (https://cli.github.com) and log in
gh auth login

# then, from this folder:
./push-to-github.sh            # or: ./push-to-github.sh my-fork-name
```

The script: fills in your username everywhere (badges, URLs, user-agent),
creates the **public** repo, sets the About description, adds all topics,
pushes `main` + the `v0.1.0` tag, and prints the next two steps.

---

## Option B — manual (browser + git)

1. **Create the repo** at <https://github.com/new>
   - Name: `leadhound`
   - Visibility: **Public**
   - Description (paste):
     > 🐺 The gig sniper — watches freelance job boards 24/7, scores every gig against your profile, drafts proposals in your voice. You just approve and send.
   - Do **NOT** initialize with README / .gitignore / license — the repo has all three.

2. **Connect and push**

   ```bash
   git remote add origin https://github.com/e2sy/leadhound.git
   git push -u origin main
   git push origin --tags
   ```

3. **Add topics** — repo page → About ⚙️ → paste one by one:

   `freelance` · `freelancer` · `upwork` · `remote-work` · `job-search` ·
   `job-board` · `automation` · `cli` · `python` · `python3` · `llm` ·
   `telegram-bot` · `productivity` · `ai-tools`

---

## After it's live — the 10-minute storefront pass

| Step | Where | Why it matters |
|---|---|---|
| Replace `e2sy` in README.md, pyproject.toml, CONTRIBUTING.md, `.github/ISSUE_TEMPLATE/config.yml`, `leadhound/watchers/rss.py` | any editor | Badges/links go live (the push script does this automatically) |
| Social preview image (1280×640) | Settings → Social preview | This is what cards look like when the repo is shared — make a simple logo-on-dark shot |
| Publish the release | Releases → Draft → tag `v0.1.0` → *Generate release notes* → Publish | The `release.yml` workflow auto-attaches the built `.whl` + `.tar.gz` |
| Watch the first CI run | Actions tab | Should be green — 29 tests, ruff, Python 3.11–3.13. Red? That's a real bug, tell us. |
| Pin the repo on your profile | Your profile → Customize pins | Profile visitors see it first |
| Add a website link | About ⚙️ (e.g. the YouTube demo) | Extra trust signal |

## Launch content (for the YouTube description / social post)

```
leadhound — the gig sniper (open source)
→ https://github.com/e2sy/leadhound

What it does: watches freelance job boards 24/7, scores every gig against
YOUR profile, drafts the proposal in YOUR voice. You just approve and send.

ToS-safe by design: public feeds only, no auto-bidding, you always fire
the final shot. Local-first SQLite. MIT licensed.

Stack: Python 3.11+, SQLite, Rich, feedparser — works on Win/Mac/Linux.
```

## Release checklist

- [ ] `./push-to-github.sh` completed, CI green
- [ ] About description + all 14 topics visible on the repo page
- [ ] Social preview uploaded
- [ ] `v0.1.0` release published with auto-attached artifacts
- [ ] Demo GIF recorded (`asciinema rec` + `agg`) and dropped into `docs/demo.gif` (uncomment the README block)
- [ ] Repo pinned on profile
